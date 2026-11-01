"""Оповещения в Telegram:
  notify_run   — окончание прогона: сводка сообщением и все диалоги файлом .txt;
  notify_audio — окончание анализа аудио: таблица пауз сообщением и сводка файлом .xlsx.

Настройки в .env:
  TELEGRAM_BOT_TOKEN=123456:ABC...     токен бота от @BotFather
  TELEGRAM_CHAT_ID=123456789           куда слать (необязательно: если пусто, берётся чат,
                                       из которого последним написали боту, например /start)
Без токена оповещения молча выключены. Ошибка отправки ничего не ломает.
Подробный журнал в консоли: поменяйте logging.WARNING на logging.INFO ниже.
"""
import html
import io
import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
API = "https://api.telegram.org/bot{token}/{method}"
STATUS = {"done": "✅ завершён", "stopped": "⏹ остановлен", "error": "❌ упал с ошибкой"}
CHANNELS = {"auto": "Telegram, при сбое — почта", "telegram": "Только Telegram",
            "email": "Только почта", "off": "Выключены"}

log = logging.getLogger("tester.telegram")                 # пишет в консоль, где запущен Streamlit
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [telegram] %(levelname)s %(message)s", "%H:%M:%S"))
    log.addHandler(_h)
    log.setLevel(logging.WARNING)
    log.propagate = False


def _token() -> str:
    return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()


def _chat_id(token: str) -> str | None:
    cid = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if cid:
        log.info("чат из TELEGRAM_CHAT_ID: %s", cid)
        return cid
    log.info("TELEGRAM_CHAT_ID пуст — ищу чат через getUpdates")
    r = requests.get(API.format(token=token, method="getUpdates"), timeout=15).json()
    if not r.get("ok"):
        log.error("getUpdates вернул ошибку: %s", r)
    chats = [u[k]["chat"]["id"] for u in r.get("result") or [] for k in ("message", "channel_post") if k in u]
    log.info("getUpdates: найдено обновлений %s, чаты %s", len(r.get("result") or []), sorted(set(chats)))
    return str(chats[-1]) if chats else None


def _call(token: str, method: str, **kw):
    r = requests.post(API.format(token=token, method=method), timeout=30, **kw)
    if not r.ok:
        raise RuntimeError(f"Telegram {method}: {r.status_code} {r.text[:200]}")
    log.info("%s: ok", method)


def _send(what: str, text: str, doc: tuple[str, bytes, str] | None = None) -> str | None:
    """Отправка по выбранному каналу. None — отправлено, иначе причина."""
    from core.notify import mail

    ch = channel()
    if ch == "off":
        log.info("%s: оповещения выключены", what)
        return "оповещения выключены"
    errors = []
    if ch == "telegram" or (ch == "auto" and (_token() or not mail.configured())):
        err = _send_telegram(what, text, doc)
        if not err:
            return None
        errors.append(f"Telegram: {err}")
        if ch == "telegram":
            return errors[0]
    if not mail.configured():
        errors.append("почта: не заданы SMTP_USER и NOTIFY_EMAIL_TO в .env")
        return "; ".join(errors)
    try:
        mail.send_email(text, doc)
        log.info("%s: письмо отправлено", what)
        return None
    except Exception as e:  # noqa: BLE001
        log.exception("%s: письмо не отправлено", what)
        errors.append(f"почта: {e}")
    return "; ".join(errors)


def _send_telegram(what: str, text: str, doc: tuple[str, bytes, str] | None = None) -> str | None:
    """Сообщение (HTML) и, если есть, файл (имя, байты, тип). None — отправлено, иначе причина."""
    token = _token()
    if not token:
        log.warning("TELEGRAM_BOT_TOKEN не задан — оповещение выключено (.env: %s)",
                    Path(__file__).resolve().parents[2] / ".env")
        return "TELEGRAM_BOT_TOKEN не задан"
    log.info("%s: токен %s…%s", what, token[:6], token[-4:])
    try:
        chat = _chat_id(token)
        if not chat:
            log.error("чат не найден: напишите боту /start или задайте TELEGRAM_CHAT_ID")
            return "чат не найден: напишите боту /start или задайте TELEGRAM_CHAT_ID"
        _call(token, "sendMessage", data={"chat_id": chat, "text": text[:4000], "parse_mode": "HTML"})
        if doc:
            _call(token, "sendDocument", data={"chat_id": chat},
                  files={"document": (doc[0], io.BytesIO(doc[1]), doc[2])})
    except Exception as e:  # noqa: BLE001 — оповещение не должно ничего ронять
        log.exception("%s: не отправлено", what)
        return f"не отправлено: {e}"
    log.info("%s: отправлено", what)
    return None


def channel() -> str:
    """Канал из настроек тестера (выбор на боковой панели), по умолчанию auto."""
    from core.storage.db import get_settings
    ch = get_settings().get("notify_channel", "auto")
    return ch if ch in CHANNELS else "auto"


def notify_run(run_id: int, project: dict, status: str, error: str | None = None) -> str | None:
    """Окончание прогона: сводка и все диалоги файлом .txt."""
    from core import storage
    from core.io.export import run_header, run_text
    from core.metrics import dialog_passed, lead_codes

    run = storage.get("runs", run_id) or {}
    dialogs = storage.run_dialogs(run_id)
    leads = lead_codes(project)
    m = run.get("metrics") or {}
    failed = [f"{d['scenario']} #{d['repeat']}" for d in dialogs if not dialog_passed(d, leads)]

    lines = [f"<b>Прогон №{run_id} {STATUS.get(status, status)}</b>",
             f"Проект: {html.escape(project.get('name') or '')}"]
    lines += [f"{html.escape(k)}: {html.escape(v)}" for k, v in run_header(run, dialogs, leads)
              if k != "Сценарии"]
    if m:
        lines.append(f"Пауза: медиана {m.get('median_s')} с, p95 {m.get('p95_s')} с, макс {m.get('max_s')} с")
        if m.get("errors") or m.get("not_ended"):
            lines.append(f"Ошибок: {m.get('errors', 0)} · не завершила звонок: {m.get('not_ended', 0)}")
    if failed:
        lines.append("Не пройдены: " + html.escape(", ".join(failed[:15]))
                     + (f" и ещё {len(failed) - 15}" if len(failed) > 15 else ""))
    if error:
        lines.append("<pre>" + html.escape(error[-600:]) + "</pre>")

    doc = None
    if dialogs:
        title = f"Прогон №{run_id} · {run.get('created', '')}"
        doc = (f"run{run_id}.txt", run_text(dialogs, leads, title, run=run).encode("utf-8"), "text/plain")
    return _send(f"прогон №{run_id}", "\n".join(lines), doc)


def _num(v) -> str:
    return "—" if v is None else f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def notify_audio(results: list[dict], slow_s: float, failed: list[str] | None = None) -> str | None:
    """Окончание анализа аудио: таблица пауз по файлам (быстрые сверху) и сводка файлом .xlsx."""
    import pandas as pd

    from core.io.export import to_xlsx
    from core.voice.analysis import VOICE_LABELS

    rows = sorted(results, key=lambda r: (r["metrics"].get("agent_gap_median_s") is None,
                                          r["metrics"].get("agent_gap_median_s") or 0))
    w = 22                                                      # ширина имени файла: влезает в экран телефона
    table = [f"{'Файл':<{w}} {'мед':>5} {'p95':>5} {'макс':>5}"]
    for r in rows:
        m = r["metrics"]
        name = r["name"].rsplit(".", 1)[0]
        name = name if len(name) <= w else name[:w - 1] + "…"
        table.append(f"{name:<{w}} {_num(m.get('agent_gap_median_s')):>5} "
                     f"{_num(m.get('agent_gap_p95_s')):>5} {_num(m.get('agent_gap_max_s')):>5}")

    lines = [f"<b>🎧 Анализ аудио готов: {len(results)} файл(ов)</b>",
             f"Пауза перед ответом агента, с (долгая — дольше {_num(float(slow_s))} с):",
             "<pre>" + html.escape("\n".join(table)) + "</pre>"]
    if rows and rows[0]["metrics"].get("agent_gap_median_s") is not None:
        lines.append(f"Быстрее всех: <b>{html.escape(rows[0]['name'])}</b>")
    if failed:
        lines.append("Не разобраны: " + html.escape(", ".join(failed)))

    df = pd.DataFrame([{"Файл": r["name"], **{VOICE_LABELS.get(k, k): v for k, v in r["metrics"].items()}}
                       for r in rows])
    doc = ("audio_summary.xlsx", to_xlsx(df, "Сводка"),
           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return _send("анализ аудио", "\n".join(lines), doc)
