"""Служебные скрипты: подготовка зависимостей для Docker и делёж видеокарты."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_lock_to_pip(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["streamlit>=1.38", "pandas>=2.2"]\n', encoding="utf-8")
    (tmp_path / "poetry.lock").write_text(
        '[[package]]\nname = "streamlit"\nversion = "1.66.0"\n\n'
        '[[package]]\nname = "numpy"\nversion = "2.4.6"\n\n'
        '[[package]]\nname = "numpy"\nversion = "2.5.4"\n', encoding="utf-8")
    out = subprocess.run([sys.executable, str(ROOT / "docker" / "lock_to_pip.py"), str(tmp_path)],
                         capture_output=True, text=True, check=True).stdout
    assert "без закрепления: numpy" in out
    assert (tmp_path / "requirements.txt").read_text().split() == ["streamlit>=1.38", "pandas>=2.2"]
    assert (tmp_path / "constraints.txt").read_text().split() == ["streamlit==1.66.0"]   # две версии numpy не закрепляем


def test_real_lock_is_readable(tmp_path):
    """Настоящие pyproject.toml и poetry.lock проекта разбираются без ошибок."""
    for name in ("pyproject.toml", "poetry.lock"):
        (tmp_path / name).write_bytes((ROOT / name).read_bytes())
    subprocess.run([sys.executable, str(ROOT / "docker" / "lock_to_pip.py"), str(tmp_path)], check=True,
                   capture_output=True)
    pins = (tmp_path / "constraints.txt").read_text().split()
    names = [p.split("==")[0] for p in pins]
    assert "streamlit" in names and len(names) == len(set(names))
