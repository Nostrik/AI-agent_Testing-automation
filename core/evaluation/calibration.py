"""Калибровка: судья на эталонных диалогах (каждое найденное нарушение — ложное срабатывание)."""
from core.evaluation.judge import judge_dialog
from core.io.parsers import parse_dialog
from core.metrics import lead_codes, outcome_ok


def calibrate(llm, settings, project, scenarios, on_progress=None) -> list[dict]:
    leads, rows = lead_codes(project), []
    gold = [s for s in scenarios if s.get("golden")]
    for i, s in enumerate(gold):
        hist = [{"role": t["role"], "text": t["text"]} for t in parse_dialog(s["golden"])]
        try:
            v = judge_dialog(llm, settings, project, s, hist, "judge_only", {})
        except Exception as e:  # noqa: BLE001
            v = {"outcome": "ошибка", "violations": {}, "problems": [str(e)]}
        bad = [k for k, x in (v.get("violations") or {}).items() if x]
        rows.append({"Сценарий": s["sid"], "Ожидалось": s.get("expected"), "Судья": v.get("outcome"),
                     "Исход ок": outcome_ok(v.get("outcome"), s.get("expected"), leads),
                     "Ложные нарушения": ", ".join(bad) or "—", "Цитаты": "; ".join(v.get("problems") or [])})
        if on_progress:
            on_progress((i + 1) / len(gold))
    return rows
