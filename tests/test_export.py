"""Экспорт прогона: шапка, Excel, текст."""
import io

import pandas as pd

from core.io.export import run_frames, run_header, run_text, to_xlsx_sheets

LEADS = {"qualified"}
RUN = {"config": {"connection": "Елена вер 15", "conn_type": "twin_agent", "agent_model": "gemma-4-31b",
                  "judge_model": "qwen3:8b", "scenarios": [f"d{i:02}" for i in range(1, 9)], "repeats": 2}}
DIALOGS = [
    {"scenario": "d01", "repeat": 1, "expected": "qualified", "meta": {"ended": True, "tools": {"END_CONVERSATION": 1}},
     "verdict": {"outcome": "qualified", "violations": {}, "comment": "ок"},
     "history": [{"role": "agent", "text": "Добрый день!", "latency_s": 2.7},
                 {"role": "client", "text": "Дизель, двадцать тонн"},
                 {"role": "agent", "text": "Передам менеджеру.", "latency_s": 3.1,
                  "tools": [{"name": "END_CONVERSATION", "args": "{}"}]}]},
    {"scenario": "d02", "repeat": 1, "expected": "qualified", "error": "timeout", "history": []},
]


def test_run_header_short_and_full():
    short = dict(run_header(RUN, DIALOGS, LEADS))
    assert short["Пройдено"] == "1 из 2"
    assert short["Подключение"] == "Елена вер 15 (twin_agent)"
    assert short["Сценарии"] == "8 × 2: d01 … d08"
    assert "Поставщик" not in short                                   # пустые строки не выводятся
    full = dict(run_header(RUN, full=True))
    assert full["Сценарии"].endswith("d07, d08") and "Пройдено" not in full


def test_run_frames_and_xlsx_roundtrip():
    frames = run_frames(DIALOGS, LEADS, run=RUN)
    assert list(frames) == ["Прогон", "Итоги", "Диалоги"]
    assert list(frames["Итоги"]["Пройден"]) == ["да", "нет"]
    assert len(frames["Диалоги"]) == 3
    back = pd.read_excel(io.BytesIO(to_xlsx_sheets(frames)), sheet_name=None)
    assert set(back) == {"Прогон", "Итоги", "Диалоги"}
    assert back["Диалоги"]["Задержка, с"].dropna().tolist() == [2.7, 3.1]   # числа, а не текст


def test_run_text():
    text = run_text(DIALOGS, LEADS, "Прогон №17", run=RUN)
    assert text.startswith("Прогон №17\nПройдено: 1 из 2")
    assert "=== ✅ d01 #1" in text and "=== ❌ d02 #1" in text
    assert "Агент: Добрый день!\nКлиент: Дизель, двадцать тонн" in text
    assert "Судья: ок" in text and "Ошибка: timeout" in text
