"""Общие элементы интерфейса."""
import streamlit as st

from app.components.chat_view import render_turn, render_verdict  # noqa: F401
from core import storage


def pick_project(key="project_id"):
    """Выбор проекта в боковой панели; возвращает проект или None."""
    projects = storage.list_("projects")
    if not projects:
        st.warning("Нет проектов — создайте его на странице «Проект».")
        return None
    ids = [p["id"] for p in projects]
    cur = st.session_state.get(key)
    idx = ids.index(cur) if cur in ids else 0
    pid = st.sidebar.selectbox("Проект", ids, index=idx, format_func=lambda i: next(p["name"] for p in projects if p["id"] == i))
    st.session_state[key] = pid
    return storage.get("projects", pid)


MODES = {
    "scripted": "A — шаблонные реплики дословно",
    "guided": "B — LLM-помощник по шаблону",
    "simulated": "Свободный LLM-клиент по персоне",
    "judge_only": "Только судья (эталонные диалоги)",
}


def flash(msg: str, icon: str = "✅"):
    """Сообщение, которое переживёт st.rerun(): покажется всплывающим уведомлением после перерисовки."""
    st.session_state["_flash"] = (msg, icon)


def show_flash():
    m = st.session_state.pop("_flash", None)
    if m:
        st.toast(m[0], icon=m[1])