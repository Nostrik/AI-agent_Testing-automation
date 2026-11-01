"""Детерминированные проверки без LLM: вызов END_CONVERSATION, цифры в речи,
длина реплик, несколько вопросов в одной реплике, обязательные/запрещённые фразы проекта.

Обязательные/запрещённые фразы берутся из проекта (необязательные поля):
  project["required_phrases"], project["forbidden_phrases"] — списки строк.
"""
import re

DIGITS = re.compile(r"\d")


def run_checks(history: list[dict], meta: dict | None, project: dict | None = None,
               max_words: int = 45, max_questions: int = 1) -> dict:
    meta, project = meta or {}, project or {}
    agent = [h["text"] for h in history if h.get("role") == "agent" and not h.get("skip")]
    joined = " ".join(agent).lower()
    res = {
        "ended_call": bool(meta.get("ended")),
        "digits_in_speech": sum(bool(DIGITS.search(t)) for t in agent),
        "long_replies": sum(len(t.split()) > max_words for t in agent),
        "multi_questions": sum(t.count("?") > max_questions for t in agent),
        "silences": sum(1 for h in history if h.get("skip")),
    }
    req = project.get("required_phrases") or []
    forb = project.get("forbidden_phrases") or []
    if req:
        res["missing_phrases"] = [p for p in req if p.lower() not in joined]
    if forb:
        res["forbidden_found"] = [p for p in forb if p.lower() in joined]
    return res
