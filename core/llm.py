"""LLM-клиент: любой OpenAI-совместимый API, цепочка запасных моделей, ретраи, разбор JSON."""
import json
import re
import time

from openai import OpenAI


def parse_json(text: str):
    m = re.search(r"\{.*\}", text or "", flags=re.S)
    return json.loads(m.group(0) if m else text)


def _clean(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


class LLM:
    def __init__(self, base_url: str, api_key: str, fallbacks=None):
        self.client = OpenAI(base_url=base_url, api_key=api_key or "none", timeout=120)
        self.fallbacks = [m.strip() for m in (fallbacks or []) if m and m.strip()]
        self.usage = {}

    @classmethod
    def from_settings(cls, s: dict):
        return cls(s["llm_base_url"], s["llm_api_key"], (s.get("fallback_models") or "").split(","))

    def chat(self, model, messages, temperature=0.3, max_tokens=800, json_mode=False) -> str:
        models = [model] + [m for m in self.fallbacks if m != model]
        last = None
        for round_ in range(3):
            for m in models:
                try:
                    r = self.client.chat.completions.create(model=m, messages=messages,
                                                            temperature=temperature, max_tokens=max_tokens)
                    text = _clean(r.choices[0].message.content)
                    if not text:
                        raise ValueError("пустой ответ")
                    if json_mode:
                        parse_json(text)
                    self.usage[m] = self.usage.get(m, 0) + 1
                    return text
                except Exception as e:  # noqa: BLE001
                    last = e
                    if "402" in str(e):
                        raise RuntimeError("LLM-провайдер: 402, нет средств на балансе") from e
            time.sleep(10 * (round_ + 1))
        raise last
