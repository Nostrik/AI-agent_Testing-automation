"""Сценарный бот TWIN (Bot API, тестовый режим):
POST bot.twin24.ai/api/v1/testMode/dialogs -> dialogId + первые реплики;
POST /dialogs/{id} {message} -> ответ; POST /dialogs/{id}/finish. status=STOP — бот завершил диалог."""
import time
import uuid

import requests

from core.platforms.twin.auth import TwinAuth

BOT_BASE = "https://bot.twin24.ai/api/v1"


class TwinBotAdapter:
    def __init__(self, params: dict):
        for k in ("email", "password", "bot_id"):
            if not params.get(k):
                raise ValueError(f"В подключении не заполнено поле «{k}»")
        self.p = params
        self.comm = params.get("communication_type") or "TEXT"
        self.http = requests.Session()
        self.sid, self.ended, self.end_reason, self.first_word_s = None, False, None, None

    def _post(self, path, body):
        r = None
        for attempt in range(3):
            token = TwinAuth.get(self.p["email"], self.p["password"], self.p.get("company_id"), force=attempt > 0)
            r = self.http.post(BOT_BASE + path, json=body, timeout=60, headers={"Authorization": f"Bearer {token}"})
            if r.status_code != 401:
                break
        if r.status_code >= 400:
            raise RuntimeError(f"TWIN bot {path}: {r.status_code} {r.text[:300]}")
        return r.json() if r.text else {}

    def _turn(self, data, t0) -> dict:
        self.first_word_s = time.perf_counter() - t0
        if str(data.get("status", "")).upper() == "STOP":
            self.ended, self.end_reason = True, "status STOP"
        text = " ".join(m.get("body", "") for m in data.get("messages") or [] if m.get("body")).strip()
        return {"text": text, "latency_s": self.first_word_s, "tools": [], "nudges": []}

    def start(self) -> dict:
        t0 = time.perf_counter()
        data = self._post("/testMode/dialogs", {
            "botId": self.p["bot_id"], "ttl": 600, "communicationType": self.comm, "returnAnswerAsync": False,
            "clientName": "Автотест", "clientExternalId": f"autotest-{uuid.uuid4()}"})
        self.sid = data["dialogId"]
        return self._turn(data, t0)

    def send(self, text: str) -> dict:
        t0 = time.perf_counter()
        return self._turn(self._post(f"/dialogs/{self.sid}", {"message": text, "communicationType": self.comm,
                                                               "returnAnswerAsync": False}), t0)

    def finish(self) -> dict:
        if self.sid and not self.ended:
            try:
                self._post(f"/dialogs/{self.sid}/finish", {})
            except Exception:  # noqa: BLE001
                pass
        return {"dialog_id": self.sid, "ended": self.ended, "closed": True, "end_reason": self.end_reason,
                "tools": {}, "silence_prompts": 0}
