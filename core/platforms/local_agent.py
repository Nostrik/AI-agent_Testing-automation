"""Локальная копия агента на Ollama (/api/chat): промпт агента, приветствие платформы, инструменты
(END_CONVERSATION, SKIP_TURN, этапы сделки) через вызов функций и тайминги модели на каждый ответ.

Тайминги из ответа Ollama (в наносекундах, переводим в секунды):
  prompt_eval_count / prompt_eval_duration — сколько токенов входа прочитано и за сколько (без кэша),
  eval_count / eval_duration — сколько токенов сгенерировано и за сколько,
  load_duration — загрузка модели в видеопамять, total_duration — всё вместе.
"""
import json
import time
import uuid
import re
import requests

from core.platforms.base import AgentTurn, finish_meta

# qwen часто говорит закрывающую фразу текстом, а END_CONVERSATION не вызывает — закрываем за неё
CLOSING = re.compile(r"менеджер\w*.{0,60}(свяж|перезвон|рассчита|посчита|отправит|сориентир)"
                     r"|передам\s+(\w+\s+){0,3}менеджер|не буду (вас )?отвлекать|договорились, спасибо", re.I)
SPEAKER = re.compile(r"^\s*(Елена|Агент|Ассистент)\s*:\s*")   # «Елена: …» из эталонов в начале ответа

# qwen иногда пишет вызов инструмента текстом: «END_CONVERSATION{"reason": …}», «set_stage_no_need </tool_call>»
TEXT_TOOL = re.compile(r"\b(END_CONVERSATION|SKIP_TURN|set_stage_[a-z_]+)\b\s*(\{[^{}]*\})?|</?tool_call>", re.I)


def text_tool_calls(text: str) -> list[dict]:
    """Превращает вызов, написанный текстом, в настоящий вызов инструмента."""
    calls = []
    for m in TEXT_TOOL.finditer(text or ""):
        if not m.group(1):
            continue
        name = m.group(1)
        name = name.upper() if name.upper() in ("END_CONVERSATION", "SKIP_TURN") else name.lower()
        try:
            args = json.loads(m.group(2)) if m.group(2) else {}
        except ValueError:
            args = {}
        calls.append({"function": {"name": name, "arguments": args}})
    return calls


STAGE_TOOLS = {
    "set_stage_qualified": "продукт и объём собраны и сказана закрывающая фраза про менеджера, "
                           "просьба менеджера, расчёта или предложения, срочная заявка",
    "set_stage_no_need": "не закупают топливо, твёрдый отказ, всё устраивает, раздражён и не рассматривает",
    "set_stage_do_not_call": "просьба больше не звонить или убрать номер",
    "set_stage_voicemail": "автоответчик, голосовая почта",
    "set_stage_wrong_number": "неверный номер",
    "set_stage_contact_found": "получен контакт или отдел ответственного, время повторного звонка, "
                               "следующая закупка позже, данные по тендеру, «подумаю»",
}


def _tool(name: str, description: str, props: dict | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props or {}, "required": list(props or {})}}}


TOOLS = [
    _tool("END_CONVERSATION", "Завершить звонок. Вызывать сразу после завершающей фразы, в том же ответе.",
          {"reason": {"type": "string", "description": "кратко, почему звонок завершён"}}),
    _tool("SKIP_TURN", "Пауза: собеседник просит подождать или соединяет с ответственным."),
    *[_tool(name, f"Перенести карточку в этап: {desc}. Вызывать один раз перед END_CONVERSATION.")
      for name, desc in STAGE_TOOLS.items()],
]

NS = 1e9


class LocalAgentAdapter:
    def __init__(self, params: dict, default_prompt: str = ""):
        for k in ("base_url", "model"):
            if not params.get(k):
                raise ValueError(f"В подключении не заполнено поле «{k}»")
        self.root = params["base_url"].rstrip("/").removesuffix("/v1")
        self.model = params["model"]
        self.temperature = float(params.get("temperature") or 0.3)
        self.max_tokens = int(params.get("max_tokens") or 300)
        self.num_ctx = int(params.get("num_ctx") or 16384)
        self.use_tools = str(params.get("use_tools", "да")).strip().lower() not in ("нет", "no", "0", "false")
        self.greeting = (params.get("greeting") or "").strip()
        prompt = params.get("system_prompt") or default_prompt or "Ты вежливый голосовой ассистент компании."
        self.msgs = [{"role": "system", "content": prompt}]
        self.http = requests.Session()
        self.sid = "local-" + uuid.uuid4().hex[:8]
        self.ended, self.end_reason, self.first_word_s = False, None, None
        self.tools_all: list[str] = []
        self.stage: str | None = None
        self.totals = {"prompt_tokens": 0, "gen_tokens": 0, "prompt_s": 0.0, "gen_s": 0.0, "calls": 0}

    # ---------- один запрос к Ollama
    def _call(self) -> tuple[dict, dict]:
        payload = {"model": self.model, "messages": self.msgs, "stream": False, "think": False,
                   "options": {"temperature": self.temperature, "num_predict": self.max_tokens,
                               "num_ctx": self.num_ctx}}
        if self.use_tools:
            payload["tools"] = TOOLS
        r = self.http.post(f"{self.root}/api/chat", json=payload, timeout=600)
        if r.status_code == 400 and "think" in r.text:            # модель без режима рассуждений
            payload.pop("think")
            r = self.http.post(f"{self.root}/api/chat", json=payload, timeout=600)
        if r.status_code >= 400:
            raise RuntimeError(f"Ollama {r.status_code}: {r.text[:300]}")
        data = r.json()
        stats = {
            "prompt_tokens": data.get("prompt_eval_count") or 0,
            "prompt_s": (data.get("prompt_eval_duration") or 0) / NS,
            "gen_tokens": data.get("eval_count") or 0,
            "gen_s": (data.get("eval_duration") or 0) / NS,
            "load_s": (data.get("load_duration") or 0) / NS,
            "total_s": (data.get("total_duration") or 0) / NS,
        }
        return data.get("message") or {}, stats

    @staticmethod
    def _merge(a: dict, b: dict) -> dict:
        return {k: round(a.get(k, 0) + b.get(k, 0), 3) for k in set(a) | set(b)}

    # ---------- ход агента: текст + инструменты (до 3 обращений, если модель ждёт результат инструмента)
    def _reply(self) -> AgentTurn:
        t0 = time.perf_counter()
        texts, tools, stats, first_token_s = [], [], {}, None
        for _ in range(3):
            msg, st = self._call()
            if first_token_s is None:                              # ≈ время до первого слова
                first_token_s = st["load_s"] + st["prompt_s"]
            stats = self._merge(stats, st)
            text = (msg.get("content") or "").strip()
            calls = list(msg.get("tool_calls") or []) + text_tool_calls(text)
            text = TEXT_TOOL.sub("", text).strip()

            if text:
                texts.append(text)
            self.msgs.append({"role": "assistant", "content": text,
                              **({"tool_calls": calls} if calls else {})})
            names = []
            for c in calls:
                fn = c.get("function") or {}
                name, args = fn.get("name"), fn.get("arguments") or {}
                names.append(name)
                tools.append({"name": name, "args": json.dumps(args, ensure_ascii=False) if args else ""})
                self.tools_all.append(name)
                if name in STAGE_TOOLS:
                    self.stage = name
                if name == "END_CONVERSATION":
                    self.ended = True
                    self.end_reason = (args or {}).get("reason") or "END_CONVERSATION"
                self.msgs.append({"role": "tool", "content": "ok", "tool_name": name})
            # продолжаем, только если модель вызвала инструмент без слов и без завершения — ждёт результат
            if not calls or text or self.ended or "SKIP_TURN" in names:
                break
        # модель вызвала инструмент без слов: один раз просим сказать реплику вслух
        if not texts  and self.stage not in ("set_stage_voicemail", "set_stage_wrong_number"):
            self.msgs.append({"role": "user", "content": "(Служебно: ты вызвала инструмент без слов. "
                                                         "Скажи собеседнику свою реплику вслух, коротко, без инструментов.)"})
            msg, st = self._call()
            self.msgs.pop()
            stats = self._merge(stats, st)
            said = TEXT_TOOL.sub("", msg.get("content") or "").strip()
            if said:
                texts.append(said)
                self.msgs.append({"role": "assistant", "content": said})
        if texts and not self.ended and not any(t["name"] == "SKIP_TURN" for t in tools) \
                and CLOSING.search(" ".join(texts)):
            self.ended, self.end_reason = True, "auto: закрывающая фраза без END_CONVERSATION"
            tools.append({"name": "END_CONVERSATION", "args": "auto"})
            self.tools_all.append("END_CONVERSATION")
        self.first_word_s = time.perf_counter() - t0
        for k in ("prompt_tokens", "gen_tokens", "prompt_s", "gen_s"):
            self.totals[k] = round(self.totals[k] + stats.get(k, 0), 3)
        self.totals["calls"] += 1
        llm = {**stats, "first_token_s": round(first_token_s or 0, 3),
               "tok_per_s": round(stats["gen_tokens"] / stats["gen_s"], 1) if stats.get("gen_s") else None}
        reply = SPEAKER.sub("", " ".join(texts).strip())
        reply = re.split(r"\s*(?:Собеседник|Клиент|Елена)\s*:", reply)[0].strip()   # обрезаем «разговор за двоих»
        return {"text": reply, "latency_s": self.first_word_s, "tools": tools, "nudges": [],
                "llm": llm}

    # ---------- интерфейс адаптера
    def start(self) -> AgentTurn:
        if self.greeting:                                          # приветствие платформы, без модели
            self.msgs.append({"role": "assistant", "content": self.greeting})
            return {"text": self.greeting, "latency_s": 0.0, "tools": [], "nudges": []}
        self.msgs.append({"role": "user", "content": "(Собеседник снял трубку.)"})
        return self._reply()

    def send(self, text: str) -> AgentTurn:
        self.msgs.append({"role": "user", "content": text})
        return self._reply()

    def finish(self) -> dict:
        meta = finish_meta(self, tools={n: self.tools_all.count(n) for n in set(self.tools_all)})
        return {**meta, "stage": self.stage, "llm_totals": self.totals}
