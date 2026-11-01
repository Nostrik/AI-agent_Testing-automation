"""Локальный агент на Ollama: вызовы инструментов текстом, автозакрытие, очистка реплики.
Ollama не нужна: ответы модели подставляются вместо _call."""
from core.platforms.local_agent import LocalAgentAdapter, text_tool_calls


def agent(*messages, greeting=""):
    """Агент, которому модель по очереди «отвечает» сообщениями messages."""
    a = LocalAgentAdapter({"base_url": "http://ollama:11434/v1", "model": "qwen3:8b", "greeting": greeting})
    answers = list(messages)
    a.calls = 0

    def fake_call():
        a.calls += 1
        msg = answers.pop(0) if answers else {"content": ""}
        return msg, {"prompt_tokens": 100, "prompt_s": 0.1, "gen_tokens": 20, "gen_s": 0.5,
                     "load_s": 0.0, "total_s": 0.6}
    a._call = fake_call
    return a


def call(name, **args):
    return {"function": {"name": name, "arguments": args}}


def test_root_without_v1():
    assert agent().root == "http://ollama:11434"


def test_text_tool_calls_forms():
    calls = text_tool_calls('Пока. END_CONVERSATION{"reason": "отказ"} set_stage_No_Need </tool_call>')
    assert [c["function"]["name"] for c in calls] == ["END_CONVERSATION", "set_stage_no_need"]
    assert calls[0]["function"]["arguments"] == {"reason": "отказ"}
    assert text_tool_calls("просто текст") == []


def test_greeting_from_platform_without_model():
    a = agent(greeting="Добрый день! Закупаете топливо?")
    t = a.start()
    assert t["text"] == "Добрый день! Закупаете топливо?" and a.calls == 0


def test_tool_call_and_end():
    a = agent({"content": "Хорошо, тогда не буду отвлекать.",
               "tool_calls": [call("set_stage_no_need"), call("END_CONVERSATION", reason="отказ")]})
    t = a.send("Нам не нужно")
    assert t["text"] == "Хорошо, тогда не буду отвлекать."
    assert a.ended and a.end_reason == "отказ" and a.stage == "set_stage_no_need"
    assert a.finish()["stage"] == "set_stage_no_need"


def test_tool_written_as_text_is_removed_from_speech():
    a = agent({"content": 'Всего доброго! END_CONVERSATION{"reason": "конец"}'})
    t = a.send("До свидания")
    assert t["text"] == "Всего доброго!"
    assert a.ended and [x["name"] for x in t["tools"]] == ["END_CONVERSATION"]


def test_auto_close_on_closing_phrase():
    a = agent({"content": "Хорошо, всё поняла. Наш менеджер рассчитает стоимость и свяжется с вами."})
    t = a.send("Дизель, двадцать тонн")
    assert a.ended and a.end_reason.startswith("auto")
    assert t["tools"][-1] == {"name": "END_CONVERSATION", "args": "auto"}


def test_no_auto_close_on_question():
    a = agent({"content": "Подскажите, какой объём нужен?"})
    a.send("Дизель")
    assert not a.ended


def test_silent_tool_call_asks_to_speak():
    a = agent({"content": "", "tool_calls": [call("set_stage_contact_found")]},
              {"content": ""},                                   # повторный вызов после результата инструмента
              {"content": "Спасибо, перезвоню завтра."})
    t = a.send("Наберите завтра")
    assert t["text"] == "Спасибо, перезвоню завтра."


def test_speaker_prefix_and_two_sided_dialog_cut():
    a = agent({"content": "Елена: Понимаю. Какой объём? Клиент: двадцать тонн"})
    assert a.send("Дизель")["text"] == "Понимаю. Какой объём?"


def test_llm_stats():
    a = agent({"content": "Какой объём нужен?"})
    t = a.send("Дизель")
    assert t["llm"]["gen_tokens"] == 20 and t["llm"]["tok_per_s"] == 40.0
    assert a.finish()["llm_totals"]["calls"] == 1
