"""Интерфейсы адаптеров тестируемых агентов.

Ход агента (AgentTurn) — обычный dict, чтобы его можно было сразу класть в БД/JSON:
    {"text": str, "latency_s": float | None, "tools": [{"name", "args"}], "nudges": [str]}
text == "" означает молчание агента.
"""
from typing import Protocol, TypedDict


class AgentTurn(TypedDict, total=False):
    text: str                 # что услышал клиент; '' = молчание
    latency_s: float | None   # до первого слова, с
    tools: list[dict]         # [{"name": "END_CONVERSATION", "args": "..."}]
    nudges: list[str]         # побуждения платформы («Говорите, вас не слышно»)


class AgentAdapter(Protocol):
    ended: bool                         # агент завершил разговор
    end_reason: str | None
    first_word_s: float | None
    sid: str | None                     # ID диалога на платформе

    def start(self) -> AgentTurn: ...   # открыть сессию, вернуть приветствие
    def send(self, text: str) -> AgentTurn: ...
    def finish(self) -> dict: ...       # закрыть сессию, вернуть служебные данные


class ConfigControl(Protocol):
    """Опционально: смена настроек агента (для автоподбора)."""
    def get(self) -> dict: ...
    def apply(self, cfg: dict) -> None: ...


def empty_turn(**kw) -> AgentTurn:
    return {"text": "", "latency_s": None, "tools": [], "nudges": [], **kw}


def finish_meta(adapter, closed: bool = True, tools: dict | None = None, silence_prompts: int = 0) -> dict:
    """Единый формат ответа finish() для всех адаптеров."""
    return {"dialog_id": adapter.sid, "ended": adapter.ended, "closed": closed, "end_reason": adapter.end_reason,
            "tools": tools or {}, "silence_prompts": silence_prompts}
