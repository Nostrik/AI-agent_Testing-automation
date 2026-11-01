"""Шифрование секретов (пароли и ключи подключений, ключ LLM) ключом MASTER_KEY из .env (Fernet).
Если MASTER_KEY не задан — секреты хранятся в открытом виде."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

SECRET_KEYS = {"password", "api_key", "llm_api_key"}
PREFIX = "enc:"


def _fernet():
    key = os.getenv("MASTER_KEY")
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode())


def encrypt(value):
    f = _fernet()
    if not f or not value or str(value).startswith(PREFIX):
        return value
    return PREFIX + f.encrypt(str(value).encode()).decode()


def decrypt(value):
    if isinstance(value, str) and value.startswith(PREFIX):
        f = _fernet()
        if not f:
            raise RuntimeError("Секреты в базе зашифрованы, а MASTER_KEY не задан в .env")
        return f.decrypt(value[len(PREFIX):].encode()).decode()
    return value


def encrypt_params(params: dict) -> dict:
    return {k: (encrypt(v) if k in SECRET_KEYS else v) for k, v in (params or {}).items()}


def decrypt_params(params: dict) -> dict:
    return {k: (decrypt(v) if k in SECRET_KEYS else v) for k, v in (params or {}).items()}
