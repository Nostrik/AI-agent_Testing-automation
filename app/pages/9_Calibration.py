import pandas as pd
import streamlit as st

from app.ui import pick_project
from core import storage
from core.judge import judge_dialog
from core.llm import LLM
from core.metrics import lead_codes, outcome_ok
from core.parsers import parse_dialog

st.title("🎯 Калибровка судьи")
st.caption("Судья оценивает ваши эталонные (правильные) диалоги. Каждое найденное нарушение — его ложное "
           "срабатывание: правьте «Правила оценки» в проекте, пока согласие не станет близким к 100%.")
project = pick_project()
if not project:
    st.stop()
scen = [s for s in storage.project_scenarios(project["id"]) if s.get("golden")]
if not scen:
    st.info("Нет сценариев с эталонным диалогом (вкладка «Сценарии»).")
    st.stop()

if st.button("🎯 Проверить судью", type="primary"):
    settings = storage.get_settings()
    llm, leads, rows = LLM.from_settings(settings), lead_codes(project), []
    bar = st.progress(0.0)
    for i, s in enumerate(scen):
        hist = [{"role": t["role"], "text": t["text"]} for t in parse_dialog(s["golden"])]
        try:
            v = judge_dialog(llm, settings, project, s, hist, "judge_only", {})
        except Exception as e:  # noqa: BLE001
            v = {"outcome": "ошибка", "violations": {}, "problems": [str(e)]}
        bad = [k for k, x in (v.get("violations") or {}).items() if x]
        rows.append({"Сценарий": s["sid"], "Ожидалось": s["expected"], "Судья": v.get("outcome"),
                     "Исход ок": outcome_ok(v.get("outcome"), s["expected"], leads),
                     "Ложные нарушения": ", ".join(bad) or "—", "Цитаты": "; ".join(v.get("problems") or [])})
        bar.progress((i + 1) / len(scen))
    st.session_state["calib"] = rows

if st.session_state.get("calib"):
    df = pd.DataFrame(st.session_state["calib"])
    agree = (df["Исход ок"] & (df["Ложные нарушения"] == "—")).sum()
    st.metric("Согласие судьи с эталонами", f"{agree} из {len(df)}")
    st.dataframe(df, hide_index=True, use_container_width=True)
