"""Свободный LLM-клиент по персоне/поведению/фактам сценария; защита от повторов,
распознавание метки конца, пример речи реального клиента.
"""
import difflib
import re
from core.clients.base import BYE, END_ANY, HANGUP

SIM_PROMPT = """Ты играешь человека, которому позвонили на рабочий телефон. Звонит голосовой агент компании.
Ты НЕ ассистент и НЕ помогаешь звонящему. Ты клиент.
Кто ты: <<PERSONA>>
Как ты себя ведёшь: <<BEHAVIOR>>
Факты (называй только когда спросят, по одному): <<FACTS>>
Так говорил реальный клиент в похожем разговоре (перенимай стиль): <<EXAMPLE>>
Правила речи:
- Расшифровка телефонного разговора: 1–2 короткие фразы, разговорно, без списков и описаний действий.
- Реагируй на то, что реально сказал агент.
- Никогда не повторяй свои прошлые реплики и не пересказывай слова агента: каждая реплика новая по смыслу.
- В первой реплике говори только то, что следует из поведения. Факты не выкладывай все сразу: называй их по одному и только когда агент спросит.
- Если агент уже ответил на твой вопрос, не задавай его снова: уточни другое, согласись или закончи разговор.
- Ты не агент: не говори его фразами вроде «передам менеджеру» или «записала».
- Если агент повторяется или не слышит тебя — скажи об этом с раздражением, на второй раз попрощайся.
- Отказ — не конец разговора: скажи его и дождись ответа агента.
- Допиши в конце [КОНЕЦ], только когда вы уже попрощались или ты кладёшь трубку.
Выдай только реплику клиента."""


def _norm(s: str) -> str:
    return re.sub(r"[^\w ]", "", (s or "").lower()).strip()


def _repeats(text: str, seen: list[str], threshold: float = 0.85) -> bool:
    """Реплика почти совпадает с уже сказанной (своей или агента). Короткие «да», «хорошо» не считаем."""
    t = _norm(text)
    if len(t) < 15:
        return False
    return any(difflib.SequenceMatcher(None, t, _norm(s)).ratio() >= threshold for s in seen if _norm(s))


class SimulatedClient:
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
        seen = [h["text"] for h in history if h["role"] in ("client", "agent") and not h.get("skip")]
        if _repeats(END_ANY.sub("", raw).strip(), seen):
            raw = self.llm.chat(self.model, msgs + [{"role": "user", "content":
                                "(Ты повторил уже сказанную фразу, свою или агента. Скажи что-то новое по ситуации "
                                "своими словами, одну-две короткие фразы.)"}],
                                temperature=1.0, max_tokens=150)
        done = bool(END_ANY.search(raw))
        text = END_ANY.sub("", raw).strip()
        last_agent = next((h["text"] for h in reversed(history) if h["role"] == "agent"), "")
        if done and BYE.search(text + " " + last_agent):
            self.finish_next = True
        return text or HANGUP
