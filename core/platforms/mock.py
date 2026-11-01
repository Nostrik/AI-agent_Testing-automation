"""Имитация агента без платформы — для тестов, демо и отладки интерфейса.

Режимы:
- replies: заранее заданные реплики по порядку (по одной в строке), без сети и LLM;
  строка, оканчивающаяся на [END], завершает разговор.
- rules: «ключевое слово => ответ» (по одному правилу в строке); первое совпавшее срабатывает.
Задержка ответа имитируется параметром delay_s.
"""
import time
import uuid

from core.platforms.base import AgentTurn, finish_meta

END_MARK = "[END]"
DEFAULT_REPLIES = [
    "Здравствуйте! Меня зовут Елена, компания «Пример». Удобно говорить?",
    "Подскажите, какое топливо вы закупаете и в каком объёме?",
    "Спасибо, передам менеджеру, он свяжется с вами. Всего доброго! [END]",
]


class MockAdapter:
    def __init__(self, params: dict | None = None):
        p = params or {}
        self.replies = [l.strip() for l in (p.get("replies") or "").splitlines() if l.strip()] or DEFAULT_REPLIES
        self.rules = []
        for line in (p.get("rules") or "").splitlines():
            if "=>" in line:
                k, v = line.split("=>", 1)
                self.rules.append((k.strip().lower(), v.strip()))
        self.delay = float(p.get("delay_s") or 0)
        self.i = 0
        self.sid = "mock-" + uuid.uuid4().hex[:8]
        self.ended, self.end_reason, self.first_word_s = False, None, None

    def _say(self, text: str) -> AgentTurn:
        t0 = time.perf_counter()
        if self.delay:
            time.sleep(self.delay)
        tools = []
        if text.endswith(END_MARK):
            text = text[: -len(END_MARK)].strip()
            self.ended, self.end_reason = True, "сценарий имитации окончен"
            tools.append({"name": "END_CONVERSATION", "args": '{"reason": "mock"}'})
        self.first_word_s = time.perf_counter() - t0
        return {"text": text, "latency_s": self.first_word_s, "tools": tools, "nudges": []}

    def _next(self) -> str:
        if self.i >= len(self.replies):
            return ""                                   # реплики кончились — молчание
        self.i += 1
        return self.replies[self.i - 1]

    def start(self) -> AgentTurn:
        return self._say(self._next())

    def send(self, text: str) -> AgentTurn:
        low = text.lower()
        for key, answer in self.rules:
            if key in low:
                return self._say(answer)
        return self._say(self._next())

    def finish(self) -> dict:
        return finish_meta(self, tools={"END_CONVERSATION": 1} if self.ended else {})
