"""Метрики качества и задержки по диалогам прогона."""
import statistics as st


def lead_codes(project):
    return {o["code"] for o in (project.get("outcomes") or []) if o.get("lead")}


def outcome_ok(outcome, expected, leads):
    return outcome == expected or (outcome in leads and expected in leads)


def dialog_passed(d, leads) -> bool:
    if d.get("error"):
        return False
    v = d.get("verdict") or {}
    no_viol = not any((v.get("violations") or {}).values())
    return outcome_ok(v.get("outcome"), d.get("expected"), leads) and no_viol


def latencies(dialogs):
    return [h["latency_s"] for d in dialogs for h in (d.get("history") or [])
            if h.get("role") == "agent" and h.get("latency_s") is not None]


def compute_metrics(dialogs, project, settings) -> dict:
    leads = lead_codes(project)
    n = len(dialogs)
    lat = latencies(dialogs)
    slow = float(settings.get("slow_threshold_s", 3))
    net = float(settings.get("network_offset_s", 0))
    s = sorted(lat)
    return {
        "dialogs": n,
        "passed_pct": round(100 * sum(dialog_passed(d, leads) for d in dialogs) / n) if n else 0,
        "errors": sum(bool(d.get("error")) for d in dialogs),
        "not_ended": sum(1 for d in dialogs if not d.get("error") and not (d.get("meta") or {}).get("ended")),
        "silences": sum(1 for d in dialogs for h in (d.get("history") or []) if h.get("skip")),
        "slow_pct": round(100 * sum(x > slow for x in lat) / len(lat)) if lat else 0,
        "median_s": round(st.median(lat), 2) if lat else None,
        "p95_s": round(s[max(int(len(s) * .95) - 1, 0)], 2) if s else None,
        "max_s": round(max(lat), 2) if lat else None,
        "sum_s": round(sum(lat), 1),
        "sum_no_net_s": round(sum(lat) - net * len(lat), 1),
        "replies": len(lat),
    }


METRIC_LABELS = {
    "slow_pct": "Дольше порога, %", "median_s": "Медиана, с", "p95_s": "p95, с", "max_s": "Макс, с",
    "sum_s": "Сумма, с", "sum_no_net_s": "Сумма без сети, с", "replies": "Реплик",
    "passed_pct": "Пройдено, %", "errors": "Ошибок", "not_ended": "Не завершила звонок",
    "silences": "Молчаний", "dialogs": "Диалогов",
}
