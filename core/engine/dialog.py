"""run_dialog(agent, client, ...) -> dict
Цикл: приветствие -> (реплика клиента -> ход агента)*; стоп по END_CONVERSATION / STOP,
прощанию клиента, трём одинаковым ответам (loop), max_turns; молчание агента фиксируется;
сессия закрывается в finally; частичная история сохраняется при ошибке.
"""
from core.clients.base import HANGUP

SILENCE = "(молчание: нет ответа)"


def agent_turn_to_history(turn: dict) -> dict:
    base = {"role": "agent", "tools": turn.get("tools") or [], "nudges": turn.get("nudges") or [],
            **({"llm": turn["llm"]} if turn.get("llm") else {})}
    if not turn.get("text"):
        return {**base, "text": SILENCE, "skip": True}
    return {**base, "text": turn["text"], "latency_s": round(turn.get("latency_s") or 0, 3)}


def run_dialog(adapter, client, max_turns=14, on_turn=None, stop_flag=None) -> dict:
    on_turn = on_turn or (lambda h: None)
    history, ended_by, error, meta = [], "max_turns", None, {}
    try:
        history.append(agent_turn_to_history(adapter.start()))
        on_turn(history[-1])
        for _ in range(max_turns):
            if stop_flag and stop_flag():
                ended_by = "stopped"
                break
            if adapter.ended:
                ended_by = "agent"
                break
            line = client.next_line(history)
            if line is HANGUP:
                ended_by = "client"
                break
            history.append({"role": "client", "text": line})
            on_turn(history[-1])
            history.append(agent_turn_to_history(adapter.send(line)))
            on_turn(history[-1])
            said = [h["text"] for h in history if h["role"] == "agent" and not h.get("skip")]
            if len(said) >= 3 and said[-1] == said[-2] == said[-3]:
                ended_by = "loop"
                break
        else:
            if adapter.ended:
                ended_by = "agent"
    except Exception as e:  # noqa: BLE001
        error = repr(e)
    finally:
        try:
            meta = adapter.finish()
        except Exception as e:  # noqa: BLE001
            meta = {"finish_error": repr(e)}
    return {"history": history, "ended_by": ended_by, "meta": meta, "error": error}
