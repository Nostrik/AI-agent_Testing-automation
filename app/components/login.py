"""Экран входа. Пока пользователь не вошёл, в навигации есть только эта страница —
остальные страницы недоступны даже по прямой ссылке.

«Запомнить меня» — подписанный токен в cookie (core.auth.make_token / parse_token).
Streamlit не умеет ставить cookie с сервера, поэтому их пишет крошечный JS-компонент.
st.context.cookies — это cookie на момент открытия вкладки, после выхода они там ещё «видны»,
поэтому выход помечается флагом в сессии, и до перезагрузки страницы cookie не читается.
"""
import json

import streamlit as st
import streamlit.components.v1 as components

from core.auth import REMEMBER_DAYS, check_login, locked_for, make_token, parse_token

COOKIE = "tester_auth"


def _write_cookie(value: str, max_age: int):
    secure = "(location.protocol === 'https:' ? '; Secure' : '')"
    components.html(
        f"<script>parent.document.cookie = {json.dumps(COOKIE)} + '=' + {json.dumps(value)}"
        f" + '; path=/; max-age={max_age}; SameSite=Strict' + {secure};</script>",
        height=0,
    )


def _flush_cookie():
    """Отложенная запись cookie: после st.rerun компонент из прошлого прогона не успевает отрисоваться."""
    token = st.session_state.pop("_set_cookie", None)
    if token:
        _write_cookie(token, REMEMBER_DAYS * 86400)
    if st.session_state.pop("_clear_cookie", False):
        _write_cookie("", 0)


def current_user() -> str | None:
    user = st.session_state.get("auth_user")
    if user or st.session_state.get("_logged_out"):
        return user
    user = parse_token(st.context.cookies.get(COOKIE))
    if user:
        st.session_state["auth_user"] = user
    return user


def login_page():
    _flush_cookie()
    st.title("🔐 Вход")
    st.caption("Автотестер ИИ-агентов. Учётную запись выдаёт администратор.")
    with st.form("login", clear_on_submit=False):
        username = st.text_input("Имя пользователя")
        password = st.text_input("Пароль", type="password")
        remember = st.checkbox(f"Запомнить меня на {REMEMBER_DAYS} дней", value=True)
        ok = st.form_submit_button("Войти", type="primary")
    if ok:
        username = username.strip()
        wait = locked_for(username)
        if wait:
            st.error(f"Слишком много неудачных попыток. Попробуйте через {wait} с.")
        elif check_login(username, password):
            st.session_state.pop("_logged_out", None)
            st.session_state["auth_user"] = username
            if remember:
                st.session_state["_set_cookie"] = make_token(username)
            st.rerun()
        else:
            st.error("Неверное имя пользователя или пароль.")


def logout_button():
    with st.sidebar:
        _flush_cookie()
        st.caption(f"👤 {current_user()}")
        if st.button("Выйти", use_container_width=True):
            st.session_state.clear()
            st.session_state["_logged_out"] = True
            st.session_state["_clear_cookie"] = True
            st.rerun()
