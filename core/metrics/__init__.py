"""Метрики прогона: качество + задержка."""
from core.metrics.latency import latencies, latency_metrics, slowest
from core.metrics.quality import (dialog_passed, lead_codes, outcome_matrix, outcome_ok, quality_metrics,
                                  violation_counts)

METRIC_LABELS = {
    "slow_pct": "Дольше порога, %", "median_s": "Медиана, с", "p95_s": "p95, с", "max_s": "Макс, с",
    "sum_s": "Сумма, с", "sum_no_net_s": "Сумма без сети, с", "replies": "Реплик",
    "passed_pct": "Пройдено, %", "errors": "Ошибок", "not_ended": "Не завершила звонок",
    "silences": "Молчаний", "dialogs": "Диалогов",
}


def compute_metrics(dialogs, project, settings) -> dict:
    return {**quality_metrics(dialogs, project), **latency_metrics(dialogs, settings)}


__all__ = ["METRIC_LABELS", "compute_metrics", "dialog_passed", "latencies", "latency_metrics", "lead_codes",
           "outcome_matrix", "outcome_ok", "quality_metrics", "slowest", "violation_counts"]
