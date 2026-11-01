"""Универсальный HTTP-адаптер: URL-шаблоны старта/реплики/завершения и JSON-пути
к тексту ответа и признаку конца — всё задаётся в форме подключения.

Шаблоны URL и тел запросов поддерживают подстановки {sid} и {text} (text экранируется для JSON).
JSON-путь — через точку, индексы списков числами: "data.messages.0.body".
Если путь указывает на список строк/объектов с полем body/text — реплики склеиваются.
"""
import json
import time

import requests

from core.platforms.base import AgentTurn, finish_meta


def get_path(data, path: str):
    if not path:
        return None
    cur = data
    for part in path.split("."):
        if isinstance(cur, list) and part.lstrip("-").isdigit():
            idx = int(part)
            cur = cur[idx] if -len(cur) <= idx < len(cur) else None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def as_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return " ".join(filter(None, (as_text(x) for x in v))).strip()
    if isinstance(v, dict):
        return str(v.get("body") or v.get("text") or v.get("content") or "")
    return str(v)


def render(tpl: str, sid: str | None, text: str = "") -> str:
    return (tpl or "").replace("{sid}", str(sid or "")).replace("{text}", json.dumps(text, ensure_ascii=False)[1:-1])


class HttpGenericAdapter:
    def __init__(self, params: dict):
        for k in ("send_url", "text_path"):
            if not params.get(k):
                raise ValueError(f"В подключении не заполнено поле «{k}»")
        self.p = params
        self.http = requests.Session()
        try:
            self.http.headers.update(json.loads(params.get("headers") or "{}"))
        except ValueError as e:
            raise ValueError("Заголовки должны быть JSON-объектом, например {\"Authorization\": \"Bearer ...\"}") from e
        self.timeout = float(params.get("timeout_s") or 60)
        self.sid, self.ended, self.end_reason, self.first_word_s = params.get("static_sid") or None, False, None, None

    def _call(self, url_tpl, body_tpl, text="") -> dict:
        url = render(url_tpl, self.sid, text)
        body = render(body_tpl, self.sid, text)
        r = self.http.post(url, data=body.encode() if body else None, timeout=self.timeout,
                           headers={"Content-Type": "application/json"} if body else None)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} {url}: {r.text[:300]}")
        try:
            return r.json() if r.text.strip() else {}
        except ValueError:
            return {"text": r.text}

    def _turn(self, data: dict, t0: float) -> AgentTurn:
        self.first_word_s = time.perf_counter() - t0
        end_val = get_path(data, self.p.get("end_path") or "")
        expected = (self.p.get("end_value") or "").strip()
        if end_val is not None and (str(end_val).lower() == expected.lower() if expected else bool(end_val)):
            self.ended, self.end_reason = True, f"{self.p.get('end_path')}={end_val}"
        return {"text": as_text(get_path(data, self.p["text_path"])).strip(),
                "latency_s": self.first_word_s, "tools": [], "nudges": []}

    def start(self) -> AgentTurn:
        t0 = time.perf_counter()
        if not self.p.get("start_url"):
            return {"text": "", "latency_s": None, "tools": [], "nudges": []}   # агент молчит до клиента
        data = self._call(self.p["start_url"], self.p.get("start_body") or "")
        sid = get_path(data, self.p.get("sid_path") or "")
        if sid is not None:
            self.sid = str(sid)
        return self._turn(data, t0)

    def send(self, text: str) -> AgentTurn:
        t0 = time.perf_counter()
        return self._turn(self._call(self.p["send_url"], self.p.get("send_body") or '{"message": "{text}"}', text), t0)

    def finish(self) -> dict:
        closed = False
        if self.p.get("finish_url"):
            try:
                self._call(self.p["finish_url"], self.p.get("finish_body") or "")
                closed = True
            except Exception:  # noqa: BLE001
                pass
        return finish_meta(self, closed=closed)
