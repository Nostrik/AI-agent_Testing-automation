"""Хранилище: SQLite + JSON-поля. Все данные приложения в data/tester.db."""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(os.getenv("TESTER_DB", Path(__file__).resolve().parents[1] / "data" / "tester.db"))

SCHEMA = """
create table if not exists settings (key text primary key, value text);
create table if not exists connections (
    id integer primary key, name text, type text, params text);
create table if not exists projects (
    id integer primary key, name text, connection_id integer, agent_prompt text, judge_rules text,
    outcomes text, violations text);
create table if not exists scenarios (
    id integer primary key, project_id integer, sid text, persona text, behavior text, facts text,
    check_text text, expected text, script text, golden text);
create table if not exists runs (
    id integer primary key, project_id integer, mode text, label text, status text, created text,
    config text, metrics text);
create table if not exists dialogs (
    id integer primary key, run_id integer, scenario text, expected text, repeat integer,
    history text, verdict text, meta text, error text, ended_by text);
"""

TABLES = {
    "connections": ["name", "type", "params"],
    "projects": ["name", "connection_id", "agent_prompt", "judge_rules", "outcomes", "violations"],
    "scenarios": ["project_id", "sid", "persona", "behavior", "facts", "check_text", "expected", "script", "golden"],
    "runs": ["project_id", "mode", "label", "status", "created", "config", "metrics"],
    "dialogs": ["run_id", "scenario", "expected", "repeat", "history", "verdict", "meta", "error", "ended_by"],
}
JSON_COLS = {"params", "outcomes", "violations", "script", "config", "metrics", "history", "verdict", "meta"}

DEFAULT_SETTINGS = {
    "llm_base_url": "https://openrouter.ai/api/v1",
    "llm_api_key": "",
    "judge_model": "nvidia/nemotron-3-super-120b-a12b:free",
    "client_model": "nvidia/nemotron-3-super-120b-a12b:free",
    "analyst_model": "nvidia/nemotron-3-super-120b-a12b:free",
    "fallback_models": "poolside/laguna-s-2.1:free",
    "slow_threshold_s": 3.0,
    "network_offset_s": 0.18,
    "max_turns": 14,
}

DEFAULT_OUTCOMES = [
    {"code": "hot", "desc": "клиент готов купить сейчас, согласие на расчёт/заказ", "lead": True},
    {"code": "warm", "desc": "согласие на расчёт/предложение без срочности или клиент сам попросил менеджера", "lead": True},
    {"code": "callback", "desc": "получен контакт ответственного или договорились о повторном звонке", "lead": False},
    {"code": "refusal", "desc": "отказ, нецелевой разговор, автоответчик — звонок корректно завершён", "lead": False},
    {"code": "dnc", "desc": "просьба больше не звонить, звонок прекращён", "lead": False},
    {"code": "unclear", "desc": "непонятно, разговор оборвался", "lead": False},
]
DEFAULT_VIOLATIONS = [
    {"code": "invented_facts", "desc": "выдумала цену, условия, сроки или факты, которых нет в инструкциях"},
    {"code": "pushy_after_refusal", "desc": "давление после твёрдого отказа"},
    {"code": "continued_after_dnc", "desc": "продолжила разговор после просьбы не звонить"},
    {"code": "lead_without_consent", "desc": "передала заявку без согласия клиента"},
    {"code": "long_or_unnatural", "desc": "монологи, несколько вопросов подряд, повторы, служебный текст в речи"},
    {"code": "ignored_question", "desc": "проигнорировала вопрос клиента или молчала"},
    {"code": "special_check_failed", "desc": "провалена особая проверка сценария"},
]

_lock = threading.RLock()
_conn = None


def _db():
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def _exec(sql, args=()):
    with _lock:
        cur = _db().execute(sql, args)
        _db().commit()
        return cur


def _dec(row):
    return {k: (json.loads(v) if k in JSON_COLS and v else v) for k, v in dict(row).items()}


def list_(table, where="", args=(), order="id"):
    with _lock:
        rows = _db().execute(f"select * from {table} {where} order by {order}", args).fetchall()
    return [_dec(r) for r in rows]


def get(table, id_):
    r = list_(table, "where id=?", (id_,))
    return r[0] if r else None


def save(table, data: dict) -> int:
    cols = TABLES[table]
    vals = [json.dumps(data.get(c), ensure_ascii=False) if c in JSON_COLS else data.get(c) for c in cols]
    if data.get("id"):
        _exec(f"update {table} set {', '.join(c + '=?' for c in cols)} where id=?", (*vals, data["id"]))
        return data["id"]
    cur = _exec(f"insert into {table} ({', '.join(cols)}) values ({', '.join('?' * len(cols))})", vals)
    return cur.lastrowid


def update(table, id_, **fields):
    row = get(table, id_)
    row.update(fields)
    save(table, row)


def delete(table, id_):
    _exec(f"delete from {table} where id=?", (id_,))


# ---------------- настройки
def get_settings() -> dict:
    with _lock:
        rows = _db().execute("select key, value from settings").fetchall()
    s = dict(DEFAULT_SETTINGS)
    s.update({r["key"]: json.loads(r["value"]) for r in rows})
    return s


def save_settings(s: dict):
    for k, v in s.items():
        _exec("insert or replace into settings (key, value) values (?, ?)", (k, json.dumps(v, ensure_ascii=False)))


# ---------------- удобные выборки
def project_scenarios(project_id):
    return list_("scenarios", "where project_id=?", (project_id,), order="sid")


def project_runs(project_id):
    return list_("runs", "where project_id=?", (project_id,), order="id desc")


def run_dialogs(run_id):
    return list_("dialogs", "where run_id=?", (run_id,), order="id")


def now():
    return time.strftime("%Y-%m-%d %H:%M")
