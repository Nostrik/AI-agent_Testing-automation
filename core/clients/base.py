"""Кто играет клиента. Общие константы и утилиты для всех клиентов."""
import re
from typing import Protocol


class _Hangup:
    """Клиент кладёт трубку."""
    def __repr__(self):
        return "HANGUP"


HANGUP = _Hangup()
END_ANY = re.compile(r"\[?\s*/?\s*КОНЕЦ\s*\]?")
BYE = re.compile(r"до свидан|всего доброго|всего хорошего|кладу трубку", re.I)


class ClientDriver(Protocol):
    def next_line(self, history: list[dict]) -> "str | _Hangup": ...


def dialog_text(history: list[dict]) -> str:
    return "\n".join(f"{'АГЕНТ' if h['role'] == 'agent' else 'КЛИЕНТ'}: {h['text']}"
                     for h in history if h.get("role") in ("agent", "client"))
