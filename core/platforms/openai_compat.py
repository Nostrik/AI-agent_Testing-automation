"""Агент как LLM по системному промпту через любой OpenAI-совместимый API
(OpenRouter, Ollama, vLLM, LM Studio, свой сервер агента с /v1/chat/completions).

Инструментов нет, поэтому конец разговора агент отмечает маркером в тексте (по умолчанию [END]).
"""
import time
import uuid

from core.llm import LLM
from core.platforms.base import AgentTurn, finish_meta

END_MARK = "[END]"
TEXT_MODE_NOTE = ("\n\nТестовый текстовый режим: инструментов нет. Когда разговор окончен (ты попрощалась, "
                  "клиент отказался или попросил не звонить), допиши в конце реплики {mark}.")
PICKUP = "(Клиент снял трубку.)"


class OpenAICompatAdapter:
    def __init__(self, params: dict, llm: LLM, default_prompt: str = ""):
        if not params.get("model"):
            raise ValueError("В подключении не заполнено поле «model»")
        self.llm, self.model = llm, params["model"]
        self.temperature = float(params.get("temperature") or 0.3)
        self.max_tokens = int(params.get("max_tokens") or 400)
        self.end_mark = params.get("end_mark") or END_MARK
        prompt = params.get("system_prompt") or default_prompt or "Ты вежливый голосовой ассистент компании."
        self.msgs = [{"role": "system", "content": prompt + TEXT_MODE_NOTE.format(mark=self.end_mark)}]
        self.sid = "llm-" + uuid.uuid4().hex[:8]
        self.ended, self.end_reason, self.first_word_s = False, None, None

    def _reply(self) -> AgentTurn:
        t0 = time.perf_counter()
        text = self.llm.chat(self.model, self.msgs, temperature=self.temperature, max_tokens=self.max_tokens)
        self.first_word_s = time.perf_counter() - t0
        if self.end_mark in text:
            self.ended, self.end_reason = True, "агент завершил разговор"
            text = text.replace(self.end_mark, "").strip()
        self.msgs.append({"role": "assistant", "content": text})
        return {"text": text, "latency_s": self.first_word_s, "tools": [], "nudges": []}

    def start(self) -> AgentTurn:
        self.msgs.append({"role": "user", "content": PICKUP})
        return self._reply()

    def send(self, text: str) -> AgentTurn:
        self.msgs.append({"role": "user", "content": text})
        return self._reply()

    def finish(self) -> dict:
        return finish_meta(self)
