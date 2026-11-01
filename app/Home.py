"""Точка входа: streamlit run app/Home.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from core import storage  # noqa: E402
from app.ui import show_flash  # noqa: E402

from app.components.login import current_user, login_page, logout_button  # noqa: E402
from app.ui import show_flash  # noqa: E402

st.set_page_config(page_title="Автотестер агентов", page_icon="🧪", layout="wide")


def dashboard():
    st.title("🧪 Автотестер ИИ-агентов")
    projects = storage.list_("projects")
    c1, c2, c3 = st.columns(3)
    c1.metric("Проектов", len(projects))
    c2.metric("Подключений", len(storage.list_("connections")))
    runs = storage.list_("runs", order="id desc")
    c3.metric("Прогонов", len(runs))
    if not storage.get_settings().get("llm_api_key"):
        st.warning("Не задан ключ LLM — откройте «Настройки».")
    if not projects:
        st.info("Начните с «Подключения» → «Проект» → «Сценарии».")
    if runs:
        st.subheader("Последние прогоны")
        names = {p["id"]: p["name"] for p in projects}
        st.dataframe(pd.DataFrame([{
            "№": r["id"], "Проект": names.get(r["project_id"]), "Режим": r["mode"], "Метка": r["label"],
            "Статус": r["status"], "Дата": r["created"],
            "Пройдено, %": (r.get("metrics") or {}).get("passed_pct"),
            "Медиана, с": (r.get("metrics") or {}).get("median_s"),
        } for r in runs[:15]]), hide_index=True, use_container_width=True)


pages = {
    "": [st.Page(dashboard, title="Главная", icon="🏠", default=True)],
    "Настройка": [
        st.Page("pages/1_Connections.py", title="Подключения", icon="🔌"),
        st.Page("pages/2_Project.py", title="Проект", icon="📁"),
        st.Page("pages/3_Scenarios.py", title="Сценарии", icon="📜"),
        st.Page("pages/12_Settings.py", title="Настройки", icon="⚙️"),
    ],
    "Тестирование": [
        st.Page("pages/5_Chat.py", title="Чат с агентом", icon="💬"),
        st.Page("pages/4_Run.py", title="Запуск", icon="▶️"),
        st.Page("pages/6_Live.py", title="Live", icon="📡"),
    ],
    "Анализ": [
        st.Page("pages/7_Results.py", title="Результаты", icon="📊"),
        st.Page("pages/8_Compare.py", title="Сравнение", icon="⚖️"),
        st.Page("pages/9_Calibration.py", title="Калибровка судьи", icon="🎯"),
        st.Page("pages/11_Report.py", title="Отчёт", icon="🧠"),
        st.Page("pages/13_Audio.py", title="Анализ аудио", icon="🎧"),
        st.Page("pages/10_Autotune.py", title="Автоподбор", icon="🤖"),
    ],
}
show_flash()
if not current_user():
    st.navigation([st.Page(login_page, title="Вход", icon="🔐")]).run()
else:
    logout_button()
    show_flash()
    st.navigation(pages).run()
