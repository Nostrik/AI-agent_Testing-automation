"""Оповещения: выбор канала (Telegram / почта / выключены) и сборка письма. Сеть не нужна."""
import pytest

from core.notify import mail, telegram
from core.storage import save_settings


@pytest.fixture
def sent(monkeypatch):
    """Подменяет отправку: Telegram и SMTP только записывают, что ушло."""
    log = {"telegram": [], "email": []}

    def fake_telegram(what, text, doc=None):
        if monkeypatch_state["telegram_fails"]:
            return "не отправлено: timeout"
        log["telegram"].append(text)

    monkeypatch_state = {"telegram_fails": False}
    monkeypatch.setattr(telegram, "_send_telegram", fake_telegram)
    monkeypatch.setattr(mail, "send_email", lambda text, doc=None: log["email"].append(text))
    monkeypatch.setattr(telegram, "_token", lambda: "123:abc")
    monkeypatch.setenv("SMTP_USER", "tester@yandex.ru")
    monkeypatch.setenv("NOTIFY_EMAIL_TO", "me@yandex.ru")
    log["state"] = monkeypatch_state
    yield log
    save_settings({"notify_channel": "auto"})


def test_auto_prefers_telegram(sent):
    save_settings({"notify_channel": "auto"})
    assert telegram._send("x", "привет") is None
    assert sent["telegram"] == ["привет"] and sent["email"] == []


def test_auto_falls_back_to_email(sent):
    save_settings({"notify_channel": "auto"})
    sent["state"]["telegram_fails"] = True
    assert telegram._send("x", "привет") is None
    assert sent["email"] == ["привет"]


def test_email_only(sent):
    save_settings({"notify_channel": "email"})
    assert telegram._send("x", "привет") is None
    assert sent["telegram"] == [] and sent["email"] == ["привет"]


def test_telegram_only_does_not_fall_back(sent):
    save_settings({"notify_channel": "telegram"})
    sent["state"]["telegram_fails"] = True
    assert "timeout" in telegram._send("x", "привет")
    assert sent["email"] == []


def test_off(sent):
    save_settings({"notify_channel": "off"})
    assert telegram._send("x", "привет") == "оповещения выключены"
    assert sent["telegram"] == sent["email"] == []


def test_email_not_configured(sent, monkeypatch):
    save_settings({"notify_channel": "email"})
    monkeypatch.setenv("SMTP_USER", "")
    assert "SMTP_USER" in telegram._send("x", "привет")


def test_unknown_channel_means_auto(sent):
    save_settings({"notify_channel": "pigeon"})
    assert telegram.channel() == "auto"


def test_email_message(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "tester@yandex.ru")
    monkeypatch.setenv("NOTIFY_EMAIL_TO", "a@ya.ru, b@ya.ru")
    monkeypatch.setenv("SMTP_PORT", "465")
    out = []

    class FakeSMTP:
        def __init__(self, host, port, **kw):
            out.append((host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def login(self, user, password):
            out.append(user)

        def send_message(self, msg):
            out.append(msg)

    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FakeSMTP)
    mail.send_email("<b>Прогон №5 ✅ завершён</b>\nПроект: Елена &amp; Ко\n<pre>a  1\nb  2</pre>",
                    ("run5.txt", "диалоги".encode(), "text/plain"))
    (host, port), user, msg = out
    assert (host, port, user) == ("smtp.yandex.ru", 465, "tester@yandex.ru")
    assert msg["Subject"] == "Тестер: Прогон №5 ✅ завершён"
    assert msg["To"] == "a@ya.ru, b@ya.ru"
    assert "Проект: Елена & Ко" in msg.get_body(("plain",)).get_content()
    html = msg.get_body(("html",)).get_content()
    assert "Проект: Елена &amp; Ко<br>" in html and "<pre>a  1\nb  2</pre>" in html   # внутри <pre> без <br>
    att = next(msg.iter_attachments())
    assert att.get_filename() == "run5.txt" and att.get_content() == "диалоги"
