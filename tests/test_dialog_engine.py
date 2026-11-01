"""Движок диалога на mock-адаптере: конец звонка, loop-стоп, молчание, закрытие при ошибке."""
from core.clients.scripted import ScriptedClient
from core.engine.dialog import SILENCE, run_dialog
from core.platforms.mock import MockAdapter


def mock(*replies):
    return MockAdapter({"replies": "\n".join(replies)})


def test_agent_ends_call():
    r = run_dialog(mock("Привет", "Пока [END]"), ScriptedClient(["Алло", "Ещё"]))
    assert r["ended_by"] == "agent"
    assert r["meta"]["ended"] is True
    assert [h["role"] for h in r["history"]] == ["agent", "client", "agent"]
    assert r["history"][-1]["tools"][0]["name"] == "END_CONVERSATION"
    assert r["error"] is None


def test_client_hangs_up_when_script_ends():
    r = run_dialog(mock("А", "Б", "В", "Г"), ScriptedClient(["Алло"]))
    assert r["ended_by"] == "client"
    assert len(r["history"]) == 3


def test_loop_stop_on_three_same_replies():
    r = run_dialog(mock("Привет", "Повтор", "Повтор", "Повтор", "Другое"),
                   ScriptedClient(["1", "2", "3", "4", "5"]))
    assert r["ended_by"] == "loop"
    assert r["history"][-1]["text"] == "Повтор"


def test_silence_is_marked():
    r = run_dialog(mock("Привет"), ScriptedClient(["Алло"]))
    last = r["history"][-1]
    assert last["skip"] is True and last["text"] == SILENCE


def test_max_turns():
    r = run_dialog(mock("1", "2", "3", "4", "5"), ScriptedClient(["x"] * 10), max_turns=2)
    assert r["ended_by"] == "max_turns"
    assert sum(h["role"] == "client" for h in r["history"]) == 2


def test_stop_flag():
    r = run_dialog(mock("А", "Б"), ScriptedClient(["1", "2"]), stop_flag=lambda: True)
    assert r["ended_by"] == "stopped"
    assert len(r["history"]) == 1


def test_error_keeps_partial_history_and_finishes():
    class Broken(MockAdapter):
        finished = False

        def send(self, text):
            raise RuntimeError("сеть упала")

        def finish(self):
            Broken.finished = True
            return super().finish()

    r = run_dialog(Broken({"replies": "Привет"}), ScriptedClient(["Алло"]))
    assert "сеть упала" in r["error"]
    assert [h["role"] for h in r["history"]] == ["agent", "client"]
    assert Broken.finished


def test_on_turn_called_for_every_reply():
    seen = []
    run_dialog(mock("Привет", "Пока [END]"), ScriptedClient(["Алло"]), on_turn=seen.append)
    assert [h["role"] for h in seen] == ["agent", "client", "agent"]
