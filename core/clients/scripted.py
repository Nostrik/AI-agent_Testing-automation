"""Режим A: реплики клиента из скрипта дословно, по порядку."""
from core.clients.base import HANGUP


class ScriptedClient:
    def __init__(self, script):
        self.script, self.i = list(script or []), 0

    def next_line(self, history):
        if self.i >= len(self.script):
            return HANGUP
        self.i += 1
        return self.script[self.i - 1]
