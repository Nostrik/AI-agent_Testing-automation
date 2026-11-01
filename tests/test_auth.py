"""Пользователи и вход: пароли, блокировка после подбора, токен «Запомнить меня»."""
import pytest

from core import auth


@pytest.fixture(autouse=True)
def fast_hash(monkeypatch):
    monkeypatch.setattr(auth, "ITERATIONS", 1000)            # 600 000 итераций — это секунды на каждый тест
    auth._fails.clear()
    yield
    for u in auth.list_users():
        auth.delete_user(u["username"])


def test_create_and_login():
    assert auth.set_user("maksim", "secret123") is True
    assert auth.check_login("maksim", "secret123")
    assert auth.check_login("  maksim ", "secret123")         # пробелы вокруг имени не мешают
    assert auth.list_users()[0]["last_login"]


def test_wrong_password_and_unknown_user():
    auth.set_user("maksim", "secret123")
    assert not auth.check_login("maksim", "wrong")
    assert not auth.check_login("nobody", "secret123")
    assert not auth.check_login("maksim", "")


def test_password_is_hashed():
    auth.set_user("maksim", "secret123")
    stored = auth.execute("select pw_hash from users where username='maksim'").fetchone()["pw_hash"]
    assert stored.startswith("pbkdf2_sha256$") and "secret123" not in stored


def test_change_password():
    auth.set_user("maksim", "old-pass1")
    assert auth.set_user("maksim", "new-pass1") is False       # не создан, а обновлён
    assert not auth.check_login("maksim", "old-pass1")
    assert auth.check_login("maksim", "new-pass1")


def test_lockout_after_fails(monkeypatch):
    auth.set_user("maksim", "secret123")
    for _ in range(auth.MAX_FAILS):
        auth.check_login("maksim", "wrong")
    assert auth.locked_for("maksim") > 0
    assert not auth.check_login("maksim", "secret123")         # даже верный пароль не пускает
    now = auth.time.time()
    monkeypatch.setattr(auth.time, "time", lambda: now + auth.LOCK_S + 1)
    assert auth.locked_for("maksim") == 0
    assert auth.check_login("maksim", "secret123")


def test_success_resets_fail_counter():
    auth.set_user("maksim", "secret123")
    for _ in range(auth.MAX_FAILS - 1):
        auth.check_login("maksim", "wrong")
    assert auth.check_login("maksim", "secret123")
    auth.check_login("maksim", "wrong")
    assert auth.locked_for("maksim") == 0


def test_token_roundtrip():
    auth.set_user("Максим", "secret123")
    token = auth.make_token("Максим")
    assert auth.parse_token(token) == "Максим"
    assert auth.make_token("nobody") is None


@pytest.mark.parametrize("bad", [None, "", "junk", "a.b", "e30.abc"])
def test_token_garbage(bad):
    assert auth.parse_token(bad) is None


def test_token_tampered_expired_and_revoked():
    auth.set_user("maksim", "secret123")
    token = auth.make_token("maksim")
    assert auth.parse_token(token[:-1] + ("0" if token[-1] != "0" else "1")) is None
    assert auth.parse_token(auth.make_token("maksim", days=-1)) is None
    auth.set_user("maksim", "new-pass1")                        # смена пароля отзывает старые cookie
    assert auth.parse_token(token) is None
    token = auth.make_token("maksim")
    auth.delete_user("maksim")
    assert auth.parse_token(token) is None


def test_token_depends_on_secret(monkeypatch):
    auth.set_user("maksim", "secret123")
    token = auth.make_token("maksim")
    monkeypatch.setenv("AUTH_SECRET", "другой секрет")
    assert auth.parse_token(token) is None
