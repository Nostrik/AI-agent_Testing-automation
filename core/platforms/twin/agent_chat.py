"""ИИ-агент TWIN — так же, как тестовый чат интерфейса.

HTTP:  POST twin24.ai/agent/api/v1/chat/sessions/create | /{id}/start | /{id} | /{id}/close  (sync=false)
WS:    wss://twin24.ai/centrifugo/connection/websocket: connect(token) -> rpc joinDialog ->
       push в канал notifications:dialog.{id}; pub.data = base64(JSON), event = BotAnswerSent;
       answer: str — реплика | dict {type: TOOL_CALL|TOOL_CALL_RESULT, tool: {funcName, funcArgs}}; status STOP
Конец хода: N секунд тишины после реплики или STOP. Конец звонка: TOOL_CALL END_CONVERSATION / STOP.
"""
import base64
import json
import queue
import re
import threading
import time
from collections import Counter

import requests
import websocket
import certifi

from core.platforms.twin.auth import TwinAuth

BASE = "https://twin24.ai/agent/api/v1/chat/sessions"
WS_URL = "wss://twin24.ai/centrifugo/connection/websocket"
ASYNC = {"sync": False, "callback": {"socket": True, "service": "", "url": "", "data": ""}}
DEFAULT_NUDGES = r"^\s*(говорите, вас не слышно|вас не слышно)"


def decode_pub(pub_data):
    """pub.data из Centrifugo: base64(JSON) -> dict."""
    if isinstance(pub_data, str):
        try:
            return json.loads(base64.b64decode(pub_data))
        except Exception:  # noqa: BLE001
            return None
    return pub_data


def short_error(err) -> str:
    """Ошибка провайдера LLM приходит с HTTP-заголовками; оставляем статус и сообщение из JSON-тела."""
    text = err if isinstance(err, str) else json.dumps(err, ensure_ascii=False)
    status = re.search(r"HTTP/[\d.]+ (\d{3}[^\r\n]*?)(?= [A-Z][\w-]+:|$)", text)
    body = re.search(r"\{.*\}\s*$", text, flags=re.S)
    msg = ""
    if body:
        try:
            j = json.loads(body.group(0))
            msg = j.get("message") or (j.get("error") or {}).get("message") or body.group(0)
        except ValueError:
            msg = body.group(0)
    return " — ".join(x for x in ((status.group(1).strip() if status else ""), msg) if x) or text[:300]


class TwinAgentAdapter:
    def __init__(self, params: dict):
        for k in ("email", "password", "agent_id"):
            if not params.get(k):
                raise ValueError(f"В подключении не заполнено поле «{k}»")
        self.p = params
        self.quiet = float(params.get("turn_quiet_s") or 2.5)
        self.turn_timeout = float(params.get("turn_timeout_s") or 45)
        self.nudge_re = re.compile(params.get("nudge_regex") or DEFAULT_NUDGES, re.I)
        self.http = requests.Session()
        self.sid, self.ended, self.end_reason, self.first_word_s = None, False, None, None
        self.tools_all, self.nudges_all = [], []
        self.q, self.ws, self._stop, self._wlock = queue.Queue(), None, False, threading.Lock()

    # ---------- HTTP
    def _token(self, force=False):
        return TwinAuth.get(self.p["email"], self.p["password"], self.p.get("company_id"), force)

    def _post(self, path, body=None):
        r = None
        for attempt in range(3):
            r = self.http.post(BASE + path, timeout=60,
                               **({"json": body} if body is not None else {"data": b""}),
                               headers={"Authorization": f"Bearer {self._token(force=attempt > 0)}",
                                        "Content-Type": "application/json"})
            if r.status_code != 401:
                break
        if r.status_code >= 400:
            raise RuntimeError(f"TWIN POST {path}: {r.status_code} {r.text[:300]}")
        return r

    # ---------- WebSocket
    def _ws_send(self, obj):
        with self._wlock:
            self.ws.send(obj if isinstance(obj, str) else json.dumps(obj))

    def _connect(self):
        """Подключение к Centrifugo с повторами (временные ошибки сервера, протухший токен)."""
        last = None
        for attempt in range(6):
            try:
                self.ws = websocket.create_connection(WS_URL, timeout=30, header=["Origin: https://twin24.ai"],
                                                      sslopt={"ca_certs": certifi.where()})
                self._ws_send({"connect": {"data": {"application": "notifications",
                               "settings": {"token": self._token(force=attempt > 0)}}}, "id": 1})
                raw = ""
                for _ in range(3):
                    raw = self.ws.recv().strip()
                    if raw:
                        break
                reply = json.loads(raw.split("\n")[0]) if raw else {"error": {"message": "пустой ответ"}}
            except Exception as e:  # noqa: BLE001
                reply = {"error": {"message": repr(e)}}
            if "error" not in reply:
                self.ws.settimeout(1)
                threading.Thread(target=self._reader, daemon=True).start()
                return
            last = reply["error"]
            try:
                self.ws.close()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(min(2 ** attempt, 20))
        raise RuntimeError(f"Centrifugo connect: {last}")

    def _reader(self):
        while not self._stop:
            try:
                frame = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:  # noqa: BLE001
                break
            for line in filter(None, frame.split("\n")):
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if msg == {}:                       # пинг Centrifugo -> понг
                    try:
                        self._ws_send("{}")
                    except Exception:  # noqa: BLE001
                        pass
                    continue
                self.q.put(msg)

    def _wait_rpc(self, rpc_id, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg = self.q.get(timeout=1)
            except queue.Empty:
                continue
            if msg.get("id") == rpc_id:
                if "error" in msg:
                    raise RuntimeError(f"Centrifugo rpc: {msg['error']}")
                return
        raise RuntimeError("Нет подтверждения joinDialog от TWIN")

    def _collect(self, t0) -> dict:
        """Собирает события одного хода агента: реплики, инструменты, побуждения, STOP."""
        texts, tools, nudges, self.first_word_s = [], [], [], None
        while time.time() < t0 + self.turn_timeout:
            try:
                msg = self.q.get(timeout=self.quiet if texts else 1.0)
            except queue.Empty:
                if texts:
                    break                           # сказал и замолчал — ход окончен
                continue
            pub = (msg.get("push") or {}).get("pub")
            ev = decode_pub(pub.get("data")) if pub else None
            if not isinstance(ev, dict) or ev.get("event") != "BotAnswerSent":
                continue
            d = ev.get("data") or {}
            if d.get("dialogId") != self.sid:
                continue
            if d.get("error"):
                raise RuntimeError(f"TWIN error: {short_error(d['error'])}")
            ans = d.get("answer")
            if isinstance(ans, dict):
                tool = ans.get("tool") or {}
                if ans.get("type") == "TOOL_CALL":
                    name = tool.get("funcName")
                    tools.append({"name": name, "args": tool.get("funcArgs")})
                    self.tools_all.append(name)
                    if name == "END_CONVERSATION":
                        self.ended = True
                        try:
                            self.end_reason = json.loads(tool.get("funcArgs") or "{}").get("reason")
                        except ValueError:
                            self.end_reason = tool.get("funcArgs")
            elif isinstance(ans, str) and ans.strip():
                if self.nudge_re.match(ans):
                    nudges.append(ans)
                    self.nudges_all.append(ans)
                else:
                    if self.first_word_s is None:
                        self.first_word_s = time.time() - t0
                    texts.append(ans)
            if str(d.get("status", "")).upper() == "STOP":
                self.ended = True
                break
        return {"text": " ".join(texts).strip(), "latency_s": self.first_word_s, "tools": tools, "nudges": nudges}

    # ---------- интерфейс AgentAdapter
    def start(self) -> dict:
        self._connect()
        r = self._post("/create", {"agentId": self.p["agent_id"], "ttl": 600})
        try:
            self.sid = r.json()["id"]
        except ValueError as e:
            raise RuntimeError(f"TWIN create: ответ не JSON: {r.text[:200]}") from e
        self._ws_send({"rpc": {"method": "joinDialog",
                               "data": {"dialogId": self.sid, "allMyConnections": False}}, "id": 2})
        self._wait_rpc(2)                           # сначала подписка, потом старт — иначе теряется приветствие
        t0 = time.time()
        self._post(f"/{self.sid}/start", ASYNC)
        return self._collect(t0)

    def send(self, text: str) -> dict:
        t0 = time.time()
        self._post(f"/{self.sid}", {"message": text, **ASYNC})
        return self._collect(t0)

    def finish(self) -> dict:
        closed = False
        if self.sid:
            try:
                self._post(f"/{self.sid}/close")
                closed = True
            except Exception:  # noqa: BLE001
                pass
        self._stop = True
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass
        return {"dialog_id": self.sid, "ended": self.ended, "closed": closed, "end_reason": self.end_reason,
                "tools": dict(Counter(self.tools_all)), "silence_prompts": len(self.nudges_all)}
