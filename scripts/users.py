"""Управление пользователями тестера из консоли сервера.

  python scripts/users.py add       — создать пользователя или сменить пароль (имя и пароль спросит)
  python scripts/users.py delete    — удалить пользователя
  python scripts/users.py list      — список пользователей

В Docker:  docker compose exec app python scripts/users.py add
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.auth import delete_user, list_users, set_user, user_exists  # noqa: E402

MIN_LEN = 8


def add():
    username = input("Имя пользователя: ").strip()
    if not username:
        sys.exit("Имя не может быть пустым.")
    if user_exists(username) and input(f"«{username}» уже есть. Сменить пароль? [y/N]: ").strip().lower() != "y":
        sys.exit("Отменено.")
    password = getpass.getpass("Пароль (не отображается): ")
    if len(password) < MIN_LEN:
        sys.exit(f"Пароль слишком короткий: нужно не меньше {MIN_LEN} символов.")
    if getpass.getpass("Повторите пароль: ") != password:
        sys.exit("Пароли не совпадают.")
    print(f"Пользователь «{username}» {'создан' if set_user(username, password) else 'обновлён: пароль изменён'}.")


def delete():
    username = input("Кого удалить: ").strip()
    if input(f"Удалить «{username}»? [y/N]: ").strip().lower() != "y":
        sys.exit("Отменено.")
    print("Удалён." if delete_user(username) else "Такого пользователя нет.")


def show():
    users = list_users()
    if not users:
        print("Пользователей нет. Создайте: python scripts/users.py add")
    for u in users:
        print(f"{u['username']:<20} создан {u['created'] or '—':<20} последний вход {u['last_login'] or '—'}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"add": add, "delete": delete, "list": show}.get(cmd, lambda: sys.exit(__doc__))()
