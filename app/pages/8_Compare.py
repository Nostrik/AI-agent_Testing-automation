import pandas as pd
import streamlit as st

from app.ui import MODES, pick_project
from core import storage
from core.export import to_xlsx
from core.metrics import METRIC_LABELS

st.title("⚖️ Сравнение прогонов")
project = pick_project()
if not project:
    st.stop()
runs = [r for r in storage.project_runs(project["id"]) if r.get("metrics")]
if not runs:
    st.info("Нет завершённых прогонов.")
    st.stop()

rows = []
for r in runs:
    c, m = r.get("config") or {}, r.get("metrics") or {}
    rows.append({"№": r["id"], "Дата": r["created"], "Режим": MODES.get(r["mode"], r["mode"]), "Метка": r["label"],
                 "Поставщик": c.get("provider"), "Модель": c.get("model"), "Температура": c.get("temperature"),
                 "Ожидание, с": c.get("timeout"),
                 **{METRIC_LABELS[k]: m.get(k) for k in ("slow_pct", "median_s", "p95_s", "max_s", "sum_s",
                                                          "sum_no_net_s", "replies", "passed_pct", "errors", "not_ended")},
                 "Комментарий": c.get("note")})
df = pd.DataFrame(rows)

st.caption("Ориентиры: «Дольше порога» ≤ 5% — хорошо; ошибки и незавершённые звонки должны быть 0.")
sel = st.multiselect("Сравнить прогоны", df["№"].tolist(), default=df["№"].tolist()[:10])
view = df[df["№"].isin(sel)] if sel else df
GOOD = "background-color: rgba(46, 160, 67, .35)"
st.dataframe(view.style.highlight_min(subset=[METRIC_LABELS["slow_pct"], METRIC_LABELS["p95_s"]], props=GOOD),
             hide_index=True, use_container_width=True)

ok = view[(view[METRIC_LABELS["errors"]] == 0) & (view[METRIC_LABELS["not_ended"]] == 0)]
if not ok.empty:
    best = ok.sort_values([METRIC_LABELS["passed_pct"], METRIC_LABELS["slow_pct"], METRIC_LABELS["median_s"]],
                          ascending=[False, True, True]).iloc[0]
    st.success(f"Лучший без ошибок и с завершёнными звонками: №{best['№']} · {best['Поставщик'] or ''} "
               f"{best['Модель'] or best['Метка'] or ''}")

st.download_button("⬇️ Скачать Excel", to_xlsx(view), file_name="runs_compare.xlsx")
