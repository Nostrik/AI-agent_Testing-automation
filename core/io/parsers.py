"""Разбор вставленного текста диалога в реплики.

Понимает форматы:
  «Клиент: текст» / «Бот: текст» / «Елена: текст» / «К: ...» / «Е: ...»
  выгрузку тестового чата TWIN: строка «Бот» или «Клиент», ниже текст, время «15:35»
Несколько диалогов разделяются строкой «---».
"""
import re

AGENT_WORDS = {"бот", "агент", "елена", "ассистент", "assistant", "bot", "agent", "оператор", "менеджер", "е", "а"}
CLIENT_WORDS = {"клиент", "пользователь", "user", "client", "к", "абонент", "собеседник"}
SKIP_LINES = re.compile(r"^(\d{1,2}:\d{2}(:\d{2})?|dialog created|dialog closed)$", re.I)
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
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or SKIP_LINES.match(line) or line.startswith("▶ TOOL") or line.startswith("▸ TOOL"):
            continue
        r = _role(line, agent_name)
        if r:                                       # строка-заголовок роли (формат TWIN)
            role = r
            turns.append({"role": role, "text": ""})
            continue
        m = PREFIX_RE.match(line)
        if m and _role(m.group(1), agent_name):     # «Роль: текст»
            role = _role(m.group(1), agent_name)
            turns.append({"role": role, "text": m.group(2).strip()})
            continue
        if role is None:                            # текст до заголовка — реплика агента (приветствие)
            role = "agent"
            turns.append({"role": role, "text": ""})
        if turns and turns[-1]["role"] == role:
            turns[-1]["text"] = (turns[-1]["text"] + " " + line).strip()
        else:
            turns.append({"role": role, "text": line})
    return [t for t in turns if t["text"]]


def parse_many(text: str, agent_name: str = "") -> list[list[dict]]:
    chunks = re.split(r"^\s*-{3,}\s*$", text or "", flags=re.M)
    return [d for d in (parse_dialog(c, agent_name) for c in chunks) if d]


def client_lines(turns: list[dict]) -> list[str]:
    return [t["text"] for t in turns if t["role"] == "client"]


def to_text(turns: list[dict]) -> str:
    return "\n".join(f"{'Агент' if t['role'] == 'agent' else 'Клиент'}: {t['text']}"
                     for t in turns if t.get("role") in ("agent", "client"))




# ---------- выгрузка прогона: «[sid] 👩 Елена : текст ⏱0.8с» / «[sid] 🙂 Клиент: текст»
LOG_LINE = re.compile(r"^\[([^\]]+)\]\s*(.*)$")
LOG_ROLE = re.compile(r"^(?:\S+\s+)?([A-Za-zА-Яа-яЁё]+)\s*:\s*(.*)$")
LOG_LATENCY = re.compile(r"\s*⏱\s*[\d.,]+\s*с\s*$")


def parse_run_log(text: str, agent_name: str = "") -> dict[str, list[dict]]:
    """Выгрузка прогона -> {sid: [реплики]}. Строки без [sid] — продолжение прошлой реплики."""
    out: dict[str, list[dict]] = {}
    sid = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = LOG_LINE.match(line)
        if m:
            sid, body = m.group(1).strip(), m.group(2).strip()
            if body.startswith("──"):                       # «── конец: … ──»
                continue
            r = LOG_ROLE.match(body)
            if not r:
                continue
            role = "client" if _role(r.group(1), agent_name) == "client" else "agent"
            out.setdefault(sid, []).append({"role": role, "text": LOG_LATENCY.sub("", r.group(2)).strip()})
        elif sid and out.get(sid):                         # перенос строки внутри реплики
            out[sid][-1]["text"] = (out[sid][-1]["text"] + " " + LOG_LATENCY.sub("", line)).strip()
    return out
