"""Задержка до первого слова: «дольше N с, %», медиана, p95, макс, сумма, вычет сети,
самые медленные ответы.
"""
import statistics as st
import math


def latencies(dialogs) -> list[float]:
    return [h["latency_s"] for d in dialogs for h in (d.get("history") or [])
            if h.get("role") == "agent" and h.get("latency_s") is not None]


def latency_metrics(dialogs, settings) -> dict:
    lat = latencies(dialogs)
    slow = float(settings.get("slow_threshold_s", 3))
    net = float(settings.get("network_offset_s", 0))
    s = sorted(lat)
    return {
        "slow_pct": round(100 * sum(x > slow for x in lat) / len(lat)) if lat else 0,
        "median_s": round(st.median(lat), 2) if lat else None,
        "p95_s": round(s[math.ceil(len(s) * .95) - 1], 2) if s else None,
        "max_s": round(max(lat), 2) if lat else None,
        "sum_s": round(sum(lat), 1),
        "sum_no_net_s": round(sum(lat) - net * len(lat), 1),
        "replies": len(lat),
    }


def slowest(dialogs, n=10) -> list[dict]:
    rows = [{"scenario": d.get("scenario"), "latency_s": h["latency_s"], "text": h["text"]}
            for d in dialogs for h in (d.get("history") or [])
            if h.get("role") == "agent" and h.get("latency_s") is not None]
    return sorted(rows, key=lambda r: -r["latency_s"])[:n]
