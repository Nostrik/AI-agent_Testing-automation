"""Режим B: LLM-помощник выбирает подходящую реплику скрипта (дословно) или кратко отвечает
по фактам скрипта; hang_up при прощании.
"""
from core.clients.base import HANGUP, dialog_text
from core.llm import parse_json

GUIDED_PROMPT = """Ты помощник тестировщика и играешь клиента в телефонном разговоре с агентом.
Реплики клиента по сценарию (номер. текст):
<<SCRIPT>>
Уже использованы номера: <<USED>>

Разговор до этого момента:
<<DIALOG>>

Выбери, что клиент скажет сейчас в ответ на последнюю реплику агента:
- если следующая неиспользованная реплика сценария подходит — верни её номер;
- если агент спросил о том, что есть в другой неиспользованной реплике, — верни номер той реплики;
- если подходящей нет — ответь коротко в стиле клиента, используя ТОЛЬКО факты из сценария; номер null;
- hang_up = true, если агент попрощался или клиенту больше нечего сказать после этой реплики.
Верни только JSON: {"index": номер или null, "line": "реплика клиента", "hang_up": true или false}"""


class GuidedClient:
    def __init__(self, script, llm, model):
        self.script, self.llm, self.model = list(script or []), llm, model
        self.used, self.finish_next = set(), False

    def next_line(self, history):
        if self.finish_next:
            return HANGUP
        prompt = (GUIDED_PROMPT.replace("<<SCRIPT>>", "\n".join(f"{i}. {t}" for i, t in enumerate(self.script)))
                  .replace("<<USED>>", ", ".join(map(str, sorted(self.used))) or "нет")
                  .replace("<<DIALOG>>", dialog_text(history)))
        r = parse_json(self.llm.chat(self.model, [{"role": "system", "content": "Ты отвечаешь только JSON."},
                                                  {"role": "user", "content": prompt}],
                                     temperature=0.2, max_tokens=400, json_mode=True))
        idx, line = r.get("index"), (r.get("line") or "").strip()
        if isinstance(idx, int) and 0 <= idx < len(self.script):
            self.used.add(idx)
            line = self.script[idx]
        if r.get("hang_up"):
            self.finish_next = True
        return line or HANGUP
