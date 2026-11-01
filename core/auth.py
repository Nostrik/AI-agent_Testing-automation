"""Пользователи тестера: таблица users в той же SQLite-базе, пароли — PBKDF2-SHA256 с солью (только stdlib).

Создание пользователей — консольным скриптом scripts/users.py на сервере, в интерфейсе регистрации нет.
Защита от подбора: после MAX_FAILS неудачных попыток вход для этого имени блокируется на LOCK_S секунд.
"""
import base64
import hashlib
import hmac
import os
import secrets
import threading
import time

from core.storage.db import DB_PATH, execute

ITERATIONS = 600_000
MAX_FAILS, LOCK_S = 5, 300

execute("""create table if not exists users (
    username text primary key, pw_hash text not null, created text, last_login text)""")

_fails: dict[str, list[float]] = {}          # имя -> времена неудачных попыток (в памяти процесса)
_lock = threading.Lock()


def _hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${dk.hex()}"


def _verify(password: str, stored: str) -> bool:
    try:
        _, iters, salt, dk = stored.split("$")
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(test.hex(), dk)
    except ValueError:
        return False


_DUMMY = _hash(secrets.token_hex(16))


def set_user(username: str, password: str) -> bool:
    """Создаёт пользователя или меняет пароль. True — создан новый."""
    exists = user_exists(username)
    if exists:
        execute("update users set pw_hash=? where username=?", (_hash(password), username))
    else:
        execute("insert into users (username, pw_hash, created) values (?, ?, ?)",
                (username, _hash(password), time.strftime("%Y-%m-%d %H:%M:%S")))
    return not exists


def delete_user(username: str) -> bool:
    return execute("delete from users where username=?", (username,)).rowcount > 0


def user_exists(username: str) -> bool:
    return execute("select 1 from users where username=?", (username,)).fetchone() is not None


def list_users() -> list[dict]:
    return [dict(r) for r in execute("select username, created, last_login from users order by username").fetchall()]


def locked_for(username: str) -> int:
    """Сколько секунд ещё заблокирован вход для имени (0 — не заблокирован)."""
    with _lock:
        recent = [t for t in _fails.get(username, []) if time.time() - t < LOCK_S]
        _fails[username] = recent
        return int(LOCK_S - (time.time() - recent[0])) + 1 if len(recent) >= MAX_FAILS else 0


def check_login(username: str, password: str) -> bool:
    username = (username or "").strip()
    if not username or not password or locked_for(username):
        return False
    row = execute("select pw_hash from users where username=?", (username,)).fetchone()
    if row:
        ok = _verify(password, row["pw_hash"])
    else:
        _verify(password, _DUMMY)          # то же время ответа, что и для существующего имени
        ok = False
    with _lock:
        if ok:
            _fails.pop(username, None)
        else:
            _fails.setdefault(username, []).append(time.time())
    if ok:
        execute("update users set last_login=? where username=?", (time.strftime("%Y-%m-%d %H:%M:%S"), username))
    return ok


# --- «Запомнить меня»: подписанный токен для cookie ---------------------------------------------
# Токен = base64(имя|срок).подпись. Подпись HMAC-SHA256 секретом сервера и куском хэша пароля:
# смена пароля или удаление пользователя сразу делают старые cookie недействительными.
# Секрет: AUTH_SECRET из .env, иначе генерируется один раз и лежит рядом с базой (data/.auth_secret).

REMEMBER_DAYS = 30


def _secret() -> bytes:
    env = os.getenv("AUTH_SECRET")
    if env:
        return env.encode()
    path = DB_PATH.parent / ".auth_secret"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return path.read_text().strip().encode()


def _sign(payload: str, pw_hash: str) -> str:
    return hmac.new(_secret(), f"{payload}|{pw_hash[-16:]}".encode(), hashlib.sha256).hexdigest()


def make_token(username: str, days: int = REMEMBER_DAYS) -> str | None:
    row = execute("select pw_hash from users where username=?", (username,)).fetchone()
    if not row:
        return None
    payload = base64.urlsafe_b64encode(f"{username}|{int(time.time()) + days * 86400}".encode()).decode()
    return f"{payload}.{_sign(payload, row['pw_hash'])}"


def parse_token(token: str | None) -> str | None:
    """Имя пользователя, если токен цел, не просрочен и пользователь с тем же паролем существует."""
    try:
        payload, sig = (token or "").split(".")
        username, exp = base64.urlsafe_b64decode(payload.encode()).decode().rsplit("|", 1)
        if int(exp) < time.time():
            return None
    except (ValueError, UnicodeDecodeError):
        return None
    row = execute("select pw_hash from users where username=?", (username,)).fetchone()
    return username if row and hmac.compare_digest(sig, _sign(payload, row["pw_hash"])) else None
