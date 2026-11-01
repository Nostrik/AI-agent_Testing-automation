"""Движок: один диалог (run_dialog) и фоновый прогон набора сценариев (Job)."""
import threading
import time
import traceback

from core import storage
from core.clients import HANGUP, make_client
from core.judge import judge_dialog
from core.llm import LLM
from core.metrics import compute_metrics
from core.parsers import parse_dialog
from core.platforms import build_adapter

SILENCE = "(молчание: нет ответа)"


def agent_turn_to_history(turn: dict) -> dict:
    if not turn.get("text"):
        return {"role": "agent", "text": SILENCE, "skip": True, "tools": turn.get("tools", []),
                "nudges": turn.get("nudges", [])}
    return {"role": "agent", "text": turn["text"], "latency_s": round(turn["latency_s"] or 0, 3),
            "tools": turn.get("tools", []), "nudges": turn.get("nudges", [])}


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


# ---------------------------------------------------------------- фоновые прогоны
JOBS: dict[int, "Job"] = {}


class Job:
    """Прогон набора сценариев в фоновом потоке. Состояние читает страница Live."""

    def __init__(self, run_id, project, connection, settings, scenarios, mode, repeats):
        self.run_id, self.project, self.connection, self.settings = run_id, project, connection, settings
        self.scenarios, self.mode, self.repeats = scenarios, mode, repeats
        self.total, self.done, self.current = len(scenarios) * repeats, 0, ""
        self.log: list[dict] = []
        self.status, self.error, self.stop_requested = "running", None, False
        self.started = time.time()
        self.thread = threading.Thread(target=self._run, daemon=True)
        JOBS[run_id] = self

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.stop_requested = True

    def _emit(self, sid, h):
        self.log.append({"scenario": sid, **h})

    def _run(self):
        llm = LLM.from_settings(self.settings)
        try:
            for sc in self.scenarios:
                for rep in range(1, self.repeats + 1):
                    if self.stop_requested:
                        raise InterruptedError
                    self.current = f"{sc['sid']} #{rep}"
                    if self.mode == "judge_only":
                        hist = [{"role": t["role"], "text": t["text"]} for t in parse_dialog(sc.get("golden") or "")]
                        d = {"history": hist, "ended_by": "golden", "meta": {"ended": True}, "error": None}
                        for h in hist:
                            self._emit(sc["sid"], h)
                    else:
                        adapter = build_adapter(self.connection, self.settings, self.project)
                        client = make_client(self.mode, sc, llm, self.settings)
                        d = run_dialog(adapter, client, int(self.settings["max_turns"]),
                                       on_turn=lambda h, s=sc["sid"]: self._emit(s, h),
                                       stop_flag=lambda: self.stop_requested)
                    self._emit(sc["sid"], {"role": "system", "text": f"── конец: {d['error'] and 'ошибка' or d['ended_by']} ──"})
                    verdict = None
                    if not d["error"] and d["history"]:
                        try:
                            verdict = judge_dialog(llm, self.settings, self.project, sc, d["history"],
                                                   self.mode, d["meta"])
                        except Exception as e:  # noqa: BLE001
                            verdict = {"outcome": "unclear", "violations": {}, "problems": [f"ошибка судьи: {e}"]}
                    storage.save("dialogs", {"run_id": self.run_id, "scenario": sc["sid"], "expected": sc.get("expected"),
                                             "repeat": rep, "history": d["history"], "verdict": verdict,
                                             "meta": d["meta"], "error": d["error"], "ended_by": d["ended_by"]})
                    self.done += 1
            self.status = "done"
        except InterruptedError:
            self.status = "stopped"
        except Exception as e:  # noqa: BLE001
            self.status, self.error = "error", traceback.format_exc()[-1500:]
            self._emit("", {"role": "system", "text": f"Ошибка прогона: {e}"})
        finally:
            metrics = compute_metrics(storage.run_dialogs(self.run_id), self.project, self.settings)
            storage.update("runs", self.run_id, status=self.status, metrics=metrics)
