"""Модели данных ядра (Pydantic)."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    name: str
    args: dict | str | None = None
    result: str | None = None


class AgentTurn(BaseModel):
    """Один ход агента: то, что услышал клиент, и служебные события."""
    text: str = ""                     # '' = молчание
    tools: list[ToolCall] = Field(default_factory=list)
    nudges: list[str] = Field(default_factory=list)   # «Говорите, вас не слышно»
    latency_s: float | None = None     # до первого слова
    raw: list[dict] = Field(default_factory=list)


class Turn(BaseModel):
    role: Literal["agent", "client", "system"]
    text: str
    latency_s: float | None = None
    tools: list[ToolCall] = Field(default_factory=list)
    skip: bool = False                 # молчание агента


class Verdict(BaseModel):
    outcome: str = "unclear"
    violations: dict[str, int] = Field(default_factory=dict)
    params_collected: dict[str, bool] = Field(default_factory=dict)
    naturalness: int | None = None
    politeness: int | None = None
    problems: list[str] = Field(default_factory=list)
    comment: str = ""


class Dialog(BaseModel):
    scenario_id: str
    repeat: int = 1
    history: list[Turn] = Field(default_factory=list)
    ended_by: str = ""                 # agent / client / loop / max_turns / script_end
    end_reason: str | None = None
    meta: dict = Field(default_factory=dict)
    error: str | None = None
    verdict: Verdict | None = None


class Metrics(BaseModel):
    dialogs: int = 0
    passed_pct: float = 0
    errors: int = 0
    not_ended: int = 0
    slow3_pct: float = 0
    median_s: float = 0
    p95_s: float = 0
    max_s: float = 0
    sum_s: float = 0
    sum_no_net_s: float = 0
    replies: int = 0
