"""Разбор вставленных диалогов и выгрузки прогона."""
from core.io.parsers import client_lines, parse_dialog, parse_many, parse_run_log, to_text


def test_prefix_format():
    t = parse_dialog("Елена: Добрый день!\nКлиент: Здравствуйте\nЕлена: Удобно говорить?")
    assert [x["role"] for x in t] == ["agent", "client", "agent"]
    assert t[1]["text"] == "Здравствуйте"


def test_twin_export_format():
    t = parse_dialog("Dialog created\nБот\nДобрый день!\n15:35\nКлиент\nАлло\n15:35\nDialog closed")
    assert t == [{"role": "agent", "text": "Добрый день!"}, {"role": "client", "text": "Алло"}]


def test_many_and_helpers():
    ds = parse_many("Бот: А\nКлиент: Б\n---\nБот: В")
    assert len(ds) == 2
    assert client_lines(ds[0]) == ["Б"]
    assert to_text(ds[0]) == "Агент: А\nКлиент: Б"


def test_agent_name_is_agent():
    t = parse_dialog("Маша: Здравствуйте\nКлиент: Да", agent_name="Маша")
    assert [x["role"] for x in t] == ["agent", "client"]


def test_run_log():
    log = ("[s1] 👩 Елена : Добрый день! ⏱0.8с\n"
           "[s1] 🙂 Клиент: Алло\n"
           "продолжение реплики\n"
           "[s2] 👩 Елена : Здравствуйте ⏱1,2 с\n"
           "[s1] ── конец: agent ──\n")
    out = parse_run_log(log)
    assert set(out) == {"s1", "s2"}
    assert out["s1"][0] == {"role": "agent", "text": "Добрый день!"}
    assert out["s1"][1] == {"role": "client", "text": "Алло продолжение реплики"}
    assert out["s2"][0]["text"] == "Здравствуйте"
