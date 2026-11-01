"""Оповещения на почту — запасной канал, работает в России без VPN.

Настройки в .env (без SMTP_USER или NOTIFY_EMAIL_TO канал выключен):
  SMTP_HOST=smtp.yandex.ru            Яндекс; Mail.ru — smtp.mail.ru
  SMTP_PORT=465                       465 — SSL; 587 — STARTTLS
  SMTP_USER=tester@yandex.ru          ящик, с которого шлём
  SMTP_PASSWORD=...                   пароль ПРИЛОЖЕНИЯ, не от ящика (Яндекс ID → Безопасность → Пароли приложений)
  NOTIFY_EMAIL_TO=me@yandex.ru        куда слать, можно несколько через запятую
"""
import html
import os
import re
import smtplib
import ssl
from email.message import EmailMessage


def configured() -> bool:
    return bool(os.getenv("SMTP_USER") and os.getenv("NOTIFY_EMAIL_TO"))


def send_email(text: str, doc: tuple[str, bytes, str] | None = None):
    """text — то же HTML-сообщение, что уходит в Telegram; первая строка становится темой письма."""
    user = os.getenv("SMTP_USER", "").strip()
    to = [a.strip() for a in os.getenv("NOTIFY_EMAIL_TO", "").split(",") if a.strip()]
    host = os.getenv("SMTP_HOST", "smtp.yandex.ru").strip()
    port = int(os.getenv("SMTP_PORT", "465"))

    first = text.split("\n", 1)[0]
    msg = EmailMessage()
    msg["Subject"] = "Тестер: " + html.unescape(re.sub(r"<[^>]+>", "", first))
    msg["From"] = user
    msg["To"] = ", ".join(to)
    plain = html.unescape(re.sub(r"<[^>]+>", "", text))
    msg.set_content(plain)
    body = re.sub(r"\n(?![^<]*</pre>)", "<br>\n", text)          # переносы строк вне <pre>
    msg.add_alternative(f"<html><body style='font-family:sans-serif'>{body}</body></html>", subtype="html")
    if doc:
        main, _, sub = doc[2].partition("/")
        msg.add_attachment(doc[1], maintype=main, subtype=sub, filename=doc[0])

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(user, os.getenv("SMTP_PASSWORD", ""))
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=ctx)
            s.login(user, os.getenv("SMTP_PASSWORD", ""))
            s.send_message(msg)
