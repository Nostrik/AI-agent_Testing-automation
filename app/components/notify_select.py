"""Выбор канала оповещений на боковой панели. Настройка общая для всех пользователей тестера:
оповещения шлёт сервер, а не браузер, поэтому хранится она в базе (settings → notify_channel)."""
import streamlit as st

from core import storage
from core.notify import mail
from core.notify.telegram import CHANNELS, _token, channel


def notify_select():
    with st.sidebar:
        current = channel()
        ch = st.selectbox("🔔 Оповещения", list(CHANNELS), index=list(CHANNELS).index(current),
                          format_func=CHANNELS.get)   # без key: если канал сменил другой пользователь, виджет покажет актуальный
        if ch != current:
            storage.save_settings({"notify_channel": ch})
        missing = []
        if ch in ("auto", "telegram") and not _token():
            missing.append("TELEGRAM_BOT_TOKEN")
        if ch in ("auto", "email") and not mail.configured():
            missing.append("SMTP_USER и NOTIFY_EMAIL_TO")
        if ch == "auto" and len(missing) < 2:
            missing = []                      # хватает одного из двух каналов
        if missing:
            st.caption(f"⚠️ Не задано в .env: {', '.join(missing)}")
