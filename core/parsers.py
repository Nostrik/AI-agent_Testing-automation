"""Разбор вставленного текста диалога в реплики.

Понимает форматы:
  «Клиент: текст» / «Бот: текст» / «Елена: текст» / «К: ...» / «Е: ...»
  выгрузку тестового чата TWIN: строка «Бот» или «Клиент», ниже текст, время «15:35»
Несколько диалогов разделяются строкой «---».
"""
import re

AGENT_WORDS = {"бот", "агент", "елена", "ассистент", "assistant", "bot", "agent", "оператор", "менеджер", "е", "а"}
CLIENT_WORDS = {"клиент", "пользователь", "user", "client", "к", "абонент", "собеседник"}
TIME_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
PREFIX_RE = re.compile(r"^\s*([A-Za-zА-Яа-яЁё]{1,20})\s*[:—-]\s*(.+)$")


def _role(word: str, agent_name: str = ""):
    w = word.strip().lower()
    if w in CLIENT_WORDS:
        return "client"
    if w in AGENT_WORDS or (agent_name and w == agent_name.lower()):
        return "agent"
    return None


def parse_dialog(text: str, agent_name: str = "") -> list[dict]:
    turns, role = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or TIME_RE.match(line):
            continue
        r = _role(line, agent_name)
        if r:                                   # строка-заголовок роли (формат TWIN)
            role = r
            continue
        m = PREFIX_RE.match(line)
        if m and _role(m.group(1), agent_name):  # «Роль: текст»
            role = _role(m.group(1), agent_name)
            turns.append({"role": role, "text": m.group(2).strip()})
            continue
        if role is None:                         # текст до любого заголовка — считаем репликой агента
            role = "agent"
        if turns and turns[-1]["role"] == role and not m:
            turns[-1]["text"] += " " + line      # продолжение той же реплики
        else:
            turns.append({"role": role, "text": line})
    return turns


def parse_many(text: str, agent_name: str = "") -> list[list[dict]]:
    return [d for d in (parse_dialog(chunk, agent_name) for chunk in re.split(r"^\s*-{3,}\s*$", text, flags=re.M)) if d]


def client_lines(turns: list[dict]) -> list[str]:
    return [t["text"] for t in turns if t["role"] == "client"]


def to_text(turns: list[dict]) -> str:
    return "\n".join(f"{'Агент' if t['role'] == 'agent' else 'Клиент'}: {t['text']}" for t in turns)
