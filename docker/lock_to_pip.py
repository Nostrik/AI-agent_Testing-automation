"""Готовит файлы для pip из pyproject.toml и poetry.lock — чтобы собирать образ без Poetry и через зеркало PyPI.

  requirements.txt — зависимости проекта из [project].dependencies
  constraints.txt  — точные версии пакетов из poetry.lock (ставятся ровно те, что у тебя локально).
                     Пакеты, у которых в lock несколько версий под разные Python (например numpy),
                     не закрепляются — pip сам выберет подходящую из разрешённых.
"""
from collections import Counter
import sys
import tomllib
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
deps = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))["project"]["dependencies"]
lock = tomllib.loads((root / "poetry.lock").read_text("utf-8"))["package"]
(root / "requirements.txt").write_text("\n".join(deps) + "\n")
count = Counter(p["name"] for p in lock)
pins = [f"{p['name']}=={p['version']}" for p in lock if count[p["name"]] == 1]
(root / "constraints.txt").write_text("\n".join(pins) + "\n")
multi = sorted(n for n, c in count.items() if c > 1)
print(f"requirements: {len(deps)}, constraints: {len(pins)}" + (f", без закрепления: {', '.join(multi)}" if multi else ""))
