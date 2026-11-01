"""Единая точка вызова LLM: любой OpenAI-совместимый API (OpenRouter и т.п.) или локальная Ollama.
Цепочка запасных моделей, ретраи, очистка <think>, проверка JSON."""
import json
import re
import time

from openai import OpenAI

from core.llm.ollama import is_ollama, ollama_chat


def parse_json(text: str):
    m = re.search(r"\{.*\}", text or "", flags=re.S)
    return json.loads(m.group(0) if m else text)


def _clean(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


class LLM:
    def __init__(self, base_url: str, api_key: str, fallbacks=None):
        self.base_url = base_url
        self.native_ollama = is_ollama(base_url)
        self.client = None if self.native_ollama else OpenAI(base_url=base_url, api_key=api_key or "none", timeout=120)
        self.fallbacks = [m.strip() for m in (fallbacks or []) if m and m.strip()]
        self.usage: dict[str, int] = {}

    @classmethod
    def from_settings(cls, s: dict) -> "LLM":
        return cls(s["llm_base_url"], s["llm_api_key"], (s.get("fallback_models") or "").split(","))

    def _call(self, model, messages, temperature, max_tokens, json_mode) -> str:
        if self.native_ollama:
            return ollama_chat(self.base_url, model, messages, temperature, max_tokens, json_mode)
        r = self.client.chat.completions.create(model=model, messages=messages,
                                                temperature=temperature, max_tokens=max_tokens)
        return r.choices[0].message.content

    def chat(self, model, messages, temperature=0.3, max_tokens=800, json_mode=False) -> str:
        models = [model] + [m for m in self.fallbacks if m != model]
        last = None
        for round_ in range(3):
            for m in models:
                try:
                    text = _clean(self._call(m, messages, temperature, max_tokens, json_mode))
                    if not text:
                        raise ValueError("пустой ответ модели")
                    if json_mode:
                        parse_json(text)
                    self.usage[f"{m} ✓"] = self.usage.get(f"{m} ✓", 0) + 1
                    return text
                except Exception as e:  # noqa: BLE001
                    last = e
                    self.usage[f"{m} ✗"] = self.usage.get(f"{m} ✗", 0) + 1
                    if "402" in str(e):
                        raise RuntimeError("LLM-провайдер вернул 402: нет средств на балансе") from e
            time.sleep(10 * (round_ + 1))
        raise last
