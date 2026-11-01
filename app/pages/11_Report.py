import streamlit as st

from app.ui import MODES, pick_project
from core import storage
from core.judge import analyst_report
from core.llm import LLM
from core.metrics import compute_metrics

st.title("🧠 Отчёт аналитика")
project = pick_project()
if not project:
    st.stop()
runs = [r for r in storage.project_runs(project["id"]) if r["status"] != "running"]
if not runs:
    st.info("Нет завершённых прогонов.")
    st.stop()
run_id = st.selectbox("Прогон", [r["id"] for r in runs],
                      format_func=lambda i: next(f"№{r['id']} · {r['created']} · {MODES.get(r['mode'], r['mode'])} · {r['label'] or ''}"
                                                 for r in runs if r["id"] == i))
key = f"report_{run_id}"
if st.button("🧠 Сформировать отчёт", type="primary"):
    settings = storage.get_settings()
    dialogs = storage.run_dialogs(run_id)
    with st.spinner("Аналитик пишет отчёт (1–2 минуты)…"):
        st.session_state[key] = analyst_report(LLM.from_settings(settings), settings, project, dialogs,
                                               compute_metrics(dialogs, project, settings))
if st.session_state.get(key):
    st.markdown(st.session_state[key])
    st.download_button("⬇️ Скачать .md", st.session_state[key], file_name=f"report_run{run_id}.md")
