"""Ручной чат с агентом — кнопки ▶ / ■ как в тестовом чате TWIN."""
import streamlit as st

from app.ui import pick_project, render_turn, render_verdict
from core import storage
from core.engine import agent_turn_to_history
from core.judge import judge_dialog
from core.llm import LLM
from core.parsers import to_text
from core.platforms import build_adapter

st.title("Чат с агентом")
st.caption("┃ Общение с AI-агентом тарифицируется по вашему тарифному плану платформы.")

project = pick_project()
if not project:
    st.stop()
conn = storage.get("connections", project["connection_id"]) if project.get("connection_id") else None
if not conn:
    st.error("У проекта не выбрано подключение.")
    st.stop()
settings = storage.get_settings()
show_tools = st.sidebar.toggle("Показывать инструменты и побуждения", True)

ss = st.session_state
ss.setdefault("chat_agent", None)
ss.setdefault("chat_log", [])


def open_session():
    try:
        ss.chat_agent = build_adapter(conn, settings, project)
        ss.chat_log = [{"role": "system", "text": "Dialog created"}]
        ss.chat_log.append(agent_turn_to_history(ss.chat_agent.start()))
        ss.pop("chat_verdict", None)
    except Exception as e:  # noqa: BLE001
        ss.chat_agent = None
        ss.chat_log.append({"role": "system", "text": f"Ошибка: {e}"})


def close_session(note="Dialog closed"):
    if ss.chat_agent is not None:
        try:
            ss.chat_agent.finish()
        finally:
            ss.chat_log.append({"role": "system", "text": note})
            ss.chat_agent = None


c_play, c_stop, c_id = st.columns([1, 1, 10])
c_play.button("▶", disabled=ss.chat_agent is not None, on_click=open_session, help="Начать диалог")
c_stop.button("■", disabled=ss.chat_agent is None, on_click=close_session, help="Завершить диалог")
if ss.chat_agent is not None:
    c_id.code(f"DialogID: {ss.chat_agent.sid}", language=None)

for h in ss.chat_log:
    render_turn(h, show_tools)

msg = st.chat_input("Ваша реплика", disabled=ss.chat_agent is None)
if msg and ss.chat_agent is not None:
    ss.chat_log.append({"role": "client", "text": msg})
    with st.spinner("Агент отвечает…"):
        try:
            ss.chat_log.append(agent_turn_to_history(ss.chat_agent.send(msg)))
        except Exception as e:  # noqa: BLE001
            ss.chat_log.append({"role": "system", "text": f"Ошибка: {e}"})
    if ss.chat_agent.ended:
        close_session(f"Dialog closed: {ss.chat_agent.end_reason or 'END_CONVERSATION'}")
    st.rerun()

history = [h for h in ss.chat_log if h["role"] in ("agent", "client")]
if history and ss.chat_agent is None:
    st.divider()
    scen = storage.project_scenarios(project["id"])
    c1, c2, c3 = st.columns(3)
    if c1.button("⚖️ Оценить судьёй"):
        with st.spinner("Судья думает…"):
            ss.chat_verdict = judge_dialog(LLM.from_settings(settings), settings, project,
                                           {"persona": "живой тестировщик", "expected": "—"}, history, "manual")
    if scen:
        target = c2.selectbox("Сценарий", [s["id"] for s in scen], format_func=lambda i: next(s["sid"] for s in scen if s["id"] == i),
                              label_visibility="collapsed")
        if c3.button("⭐ Сохранить в сценарий (эталон + реплики)"):
            storage.update("scenarios", target, golden=to_text(history),
                           script=[h["text"] for h in history if h["role"] == "client"])
            st.success("Сохранено в сценарий")
    if ss.get("chat_verdict"):
        render_verdict(ss.chat_verdict)
