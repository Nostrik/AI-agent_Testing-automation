"""ChatSession — живой ручной диалог для страницы «Чат» (▶ открыть / ■ закрыть):
start(), say(text), close(), ended; хранится в st.session_state.
"""
from core.engine.dialog import agent_turn_to_history
from core.platforms import build_adapter


class ChatSession:
    def __init__(self, connection: dict, settings: dict, project: dict | None = None):
        self.adapter = build_adapter(connection, settings, project)
        self.log: list[dict] = []
        self.open = False

    @property
    def sid(self):
        return self.adapter.sid

    @property
    def ended(self) -> bool:
        return self.adapter.ended

    def start(self) -> dict:
        self.log = [{"role": "system", "text": "Dialog created"}]
        self.open = True
        self.log.append(agent_turn_to_history(self.adapter.start()))
        return self.log[-1]

    def say(self, text: str) -> dict:
        self.log.append({"role": "client", "text": text})
        self.log.append(agent_turn_to_history(self.adapter.send(text)))
        if self.adapter.ended:
            self.close(f"Dialog closed: {self.adapter.end_reason or 'END_CONVERSATION'}")
        return self.log[-1]

    def close(self, note: str = "Dialog closed") -> dict:
        meta = {}
        if self.open:
            try:
                meta = self.adapter.finish()
            finally:
                self.open = False
                self.log.append({"role": "system", "text": note})
        return meta

    @property
    def history(self) -> list[dict]:
        return [h for h in self.log if h["role"] in ("agent", "client")]
