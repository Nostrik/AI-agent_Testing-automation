"""Авторизация TWIN: POST iam.twin24.ai/api/v1/auth/login -> JWT.
Токен общий для HTTP и WebSocket, кэшируется по учётным данным, обновляется принудительно (force=True)."""
import threading

import requests

IAM_URL = "https://iam.twin24.ai/api/v1/auth/login"


class TwinAuth:
    _tokens: dict = {}
    _lock = threading.Lock()

    @classmethod
    def get(cls, email: str, password: str, company_id=None, force: bool = False) -> str:
        key = (email, str(company_id or ""))
        with cls._lock:
            if force or key not in cls._tokens:
                body = {"email": email, "password": password, "ttl": 86400}
                if company_id:
                    body["companyId"] = int(company_id)
                r = requests.post(IAM_URL, json=body, timeout=30)
                if r.status_code == 426:
                    raise RuntimeError("На аккаунте TWIN включена 2FA — заведите для тестов пользователя без 2FA")
                if r.status_code >= 400:
                    raise RuntimeError(f"TWIN login: {r.status_code} {r.text[:200]}")
                cls._tokens[key] = r.json()["token"]
            return cls._tokens[key]
