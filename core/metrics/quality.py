"""Пройдено %, исходы (матрица ожидаемый/фактический), нарушения, ошибки,
«не завершила звонок», молчания.
"""
from collections import Counter


def lead_codes(project) -> set:
    return {o["code"] for o in (project.get("outcomes") or []) if o.get("lead")}


def outcome_ok(outcome, expected, leads) -> bool:
    allowed = [e.strip() for e in str(expected or "").split("|") if e.strip()]
    return outcome in allowed or (outcome in leads and any(e in leads for e in allowed))


def dialog_passed(d, leads) -> bool:
    if d.get("error"):
        return False
    v = d.get("verdict") or {}
    no_viol = not any((v.get("violations") or {}).values())
    return outcome_ok(v.get("outcome"), d.get("expected"), leads) and no_viol


def quality_metrics(dialogs, project) -> dict:
    leads, n = lead_codes(project), len(dialogs)
    return {
        "dialogs": n,
        "passed_pct": round(100 * sum(dialog_passed(d, leads) for d in dialogs) / n) if n else 0,
        "errors": sum(bool(d.get("error")) for d in dialogs),
        "not_ended": sum(1 for d in dialogs if not d.get("error") and not (d.get("meta") or {}).get("ended")),
        "silences": sum(1 for d in dialogs for h in (d.get("history") or []) if h.get("skip")),
    }


def violation_counts(dialogs) -> dict:
    c = Counter()
    for d in dialogs:
        for k, x in ((d.get("verdict") or {}).get("violations") or {}).items():
            if x:
                c[k] += 1
    return dict(c.most_common())


def outcome_matrix(dialogs) -> dict:
    """{(ожидаемый, фактический): число}"""
    return dict(Counter((d.get("expected"), (d.get("verdict") or {}).get("outcome")) for d in dialogs))
