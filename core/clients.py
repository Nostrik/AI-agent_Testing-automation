"""Кто играет клиента: шаблон (A), помощник по шаблону (B), свободный LLM-клиент."""
import re

from core.llm import parse_json


class _Hangup:
    def __repr__(self):
        return "HANGUP"


HANGUP = _Hangup()
END_ANY = re.compile(r"\[?\s*/?\s*КОНЕЦ\s*\]?")
BYE = re.compile(r"до свидан|всего доброго|всего хорошего|кладу трубку", re.I)


def dialog_text(history):
    return "\n".join(f"{'АГЕНТ' if h['role'] == 'agent' else 'КЛИЕНТ'}: {h['text']}"
                     for h in history if h["role"] in ("agent", "client"))


class ScriptedClient:
    """Режим A: реплики скрипта дословно, по порядку."""
    def __init__(self, script):
        self.script, self.i = list(script or []), 0

    def next_line(self, history):
        if self.i >= len(self.script):
            return HANGUP
        self.i += 1
        return self.script[self.i - 1]


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
    """Режим B: LLM-помощник ведёт клиента по скрипту и подстраивается под агента."""
    def __init__(self, script, llm, model):
        self.script, self.llm, self.model, self.used, self.finish_next = list(script or []), llm, model, set(), False

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


SIM_PROMPT = """Ты играешь человека, которому позвонили на рабочий телефон. Звонит голосовой агент компании.
Ты НЕ ассистент и НЕ помогаешь звонящему. Ты клиент.
Кто ты: <<PERSONA>>
Как ты себя ведёшь: <<BEHAVIOR>>
Факты (называй только когда спросят, по одному): <<FACTS>>
Так говорил реальный клиент в похожем разговоре (перенимай стиль): <<EXAMPLE>>
Правила речи:
- Расшифровка телефонного разговора: 1–2 короткие фразы, разговорно, без списков и описаний действий.
- Реагируй на то, что реально сказал агент. Не повторяй дословно свои прошлые реплики.
- Если агент повторяется или не слышит тебя — скажи об этом с раздражением, на второй раз попрощайся.
- Отказ — не конец разговора: скажи его и дождись ответа агента.
- Допиши в конце [КОНЕЦ], только когда вы уже попрощались или ты кладёшь трубку.
Выдай только реплику клиента."""


class SimulatedClient:
    """Свободный клиент по персоне сценария."""
    def __init__(self, scenario, llm, model):
        self.sc, self.llm, self.model, self.finish_next = scenario, llm, model, False

    def next_line(self, history):
        if self.finish_next:
            return HANGUP
        sys_prompt = (SIM_PROMPT.replace("<<PERSONA>>", self.sc.get("persona") or "—")
                      .replace("<<BEHAVIOR>>", self.sc.get("behavior") or "—")
                      .replace("<<FACTS>>", self.sc.get("facts") or "—")
                      .replace("<<EXAMPLE>>", " / ".join(self.sc.get("script") or []) or "—"))
        msgs = [{"role": "system", "content": sys_prompt}]
        for h in history:
            if h["role"] == "agent":
                msgs.append({"role": "user", "content": h["text"]})
            elif h["role"] == "client":
                msgs.append({"role": "assistant", "content": h["text"]})
        raw = self.llm.chat(self.model, msgs, temperature=0.8, max_tokens=150)
        prev = [h["text"] for h in history if h["role"] == "client"]
        if prev and END_ANY.sub("", raw).strip() == prev[-1]:
            raw = self.llm.chat(self.model, msgs + [{"role": "user", "content": "(Не повторяй прошлую фразу.)"}],
                                temperature=1.0, max_tokens=150)
        done = bool(END_ANY.search(raw))
        text = END_ANY.sub("", raw).strip()
        last_agent = next((h["text"] for h in reversed(history) if h["role"] == "agent"), "")
        if done and BYE.search(text + " " + last_agent):
            self.finish_next = True
        return text or HANGUP


def make_client(mode, scenario, llm, settings):
    if mode == "scripted":
        return ScriptedClient(scenario.get("script"))
    if mode == "guided":
        return GuidedClient(scenario.get("script"), llm, settings["client_model"])
    if mode == "simulated":
        return SimulatedClient(scenario, llm, settings["client_model"])
    raise ValueError(mode)
