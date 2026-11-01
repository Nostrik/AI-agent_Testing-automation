"""Общие настройки тестов: отдельная временная база и пустые ключи.

Переменные задаются до импорта core: база берёт путь из DB_URL при импорте, а load_dotenv
не перезаписывает уже заданные переменные — поэтому настоящий .env с токенами в тесты не попадёт.
"""
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="tester-tests-")
os.environ["DB_URL"] = f"sqlite:///{Path(_TMP) / 'test.db'}"
for key in ("MASTER_KEY", "AUTH_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
            "SMTP_USER", "SMTP_PASSWORD", "NOTIFY_EMAIL_TO"):
    os.environ[key] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
