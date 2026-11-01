"""Плитки метрик и графики задержки."""
import pandas as pd
import plotly.express as px
import streamlit as st

from core.metrics import METRIC_LABELS, latencies


def metric_tiles(m: dict, keys=("passed_pct", "errors", "not_ended", "slow_pct", "median_s", "p95_s")):
    for c, k in zip(st.columns(len(keys)), keys):
        c.metric(METRIC_LABELS.get(k, k), m.get(k))


def latency_hist(dialogs, threshold: float = 3.0):
    lat = latencies(dialogs)
    if not lat:
        return
    fig = px.histogram(pd.DataFrame({"Задержка, с": lat}), x="Задержка, с", nbins=30)
    fig.add_vline(x=threshold, line_dash="dash")
    st.plotly_chart(fig, use_container_width=True)
