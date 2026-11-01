"""Целевая функция: жёсткие ограничения качества (ошибки=0, не завершила=0, пройдено>=порог),
минимизация «дольше 3 с» -> p95 -> медиана (свёрнуто в одно число).
"""
PENALTY = 1e6


def score(metrics: dict, min_passed_pct: float = 90) -> float:
    if metrics.get("errors") or metrics.get("not_ended") or (metrics.get("passed_pct") or 0) < min_passed_pct:
        return PENALTY + (100 - (metrics.get("passed_pct") or 0)) * 1000
    return (metrics.get("slow_pct") or 0) * 100 + (metrics.get("p95_s") or 0) * 10 + (metrics.get("median_s") or 0)
