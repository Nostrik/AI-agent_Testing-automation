import re
import pandas as pd
import plotly.express as px
import streamlit as st

from app.ui import MODES, pick_project, render_turn, render_verdict
from core import storage
from core.metrics import METRIC_LABELS, compute_metrics, dialog_passed, latencies, lead_codes
from core.io.export import run_frames, run_text, to_xlsx_sheets

st.title("📊 Результаты")
project = pick_project()
if not project:
    st.stop()
runs = storage.project_runs(project["id"])
if not runs:
    st.info("Прогонов ещё нет.")
    st.stop()
run_id = st.selectbox("Прогон", [r["id"] for r in runs],
                      format_func=lambda i: next(f"№{r['id']} · {r['created']} · {MODES.get(r['mode'], r['mode'])} · {r['label'] or ''}"
                                                 for r in runs if r["id"] == i))
run = storage.get("runs", run_id)
dialogs = storage.run_dialogs(run_id)
settings = storage.get_settings()
m = compute_metrics(dialogs, project, settings)
if m != run.get("metrics"):
    storage.update("runs", run_id, metrics=m)

cols = st.columns(6)
for c, k in zip(cols, ["passed_pct", "errors", "not_ended", "slow_pct", "median_s", "p95_s"]):
    c.metric(METRIC_LABELS[k], m.get(k))
cols = st.columns(6)
for c, k in zip(cols, ["max_s", "sum_s", "sum_no_net_s", "replies", "silences", "dialogs"]):
    c.metric(METRIC_LABELS[k], m.get(k))

leads = lead_codes(project)
rows = []
for d in dialogs:
    v = d.get("verdict") or {}
    lat = latencies([d])
    rows.append({"id": d["id"], "Сценарий": d["scenario"], "Повтор": d["repeat"], "Ожидалось": d["expected"],
                 "Получилось": v.get("outcome"), "✅": dialog_passed(d, leads),
                 "Нарушения": ", ".join(k for k, x in (v.get("violations") or {}).items() if x) or "—",
                 "Конец": d.get("ended_by"), "Завершила": (d.get("meta") or {}).get("ended"),
                 "Макс. пауза, с": round(max(lat), 2) if lat else None, "Ошибка": d.get("error") or ""})
table = pd.DataFrame(rows)
st.dataframe(table.drop(columns="id"), hide_index=True, use_container_width=True)
run_name = re.sub(r"[^\w\-.]+", "_", f"run{run_id}_{run.get('label') or run.get('mode') or ''}").strip("_")[:60]
run_title = f"Прогон №{run_id} · {run.get('created')} · {MODES.get(run['mode'], run['mode'])} · {run.get('label') or ''}"
c1, c2 = st.columns(2)
c1.download_button("⬇️ Скачать прогон (Excel)", to_xlsx_sheets(run_frames(dialogs, leads, run=run)),
                   file_name=f"{run_name}.xlsx", use_container_width=True)
c2.download_button("⬇️ Диалоги текстом (.txt)", run_text(dialogs, leads, run_title, run=run),
                   file_name=f"{run_name}.txt", use_container_width=True)

lat = latencies(dialogs)
if lat:
    fig = px.histogram(x=lat, nbins=30, labels={"x": "секунды"}, title="Задержка до первого слова агента")
    fig.add_vline(x=float(settings["slow_threshold_s"]), line_dash="dash", line_color="red")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Диалог")
flt = st.radio("Показать", ["все", "непройденные", "пройденные"], horizontal=True)
ids = [r["id"] for r in rows if flt == "все" or (flt == "пройденные") == r["✅"]]
if ids:
    did = st.selectbox("Диалог", ids, format_func=lambda i: next(
        f"{'✅' if r['✅'] else '❌'} {r['Сценарий']} #{r['Повтор']}" for r in rows if r["id"] == i))
    d = next(x for x in dialogs if x["id"] == did)
    meta = d.get("meta") or {}
    st.caption(f"Завершение: {meta.get('end_reason') or '—'} · инструменты: {meta.get('tools') or '—'} · "
               f"побуждений тишины: {meta.get('silence_prompts', 0)}")
    for h in d.get("history") or []:
        render_turn(h, True)
    render_verdict(d.get("verdict"), d.get("error"))
