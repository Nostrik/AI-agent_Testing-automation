"""Прогон набора сценариев в фоновом потоке: режим, повторы, стоп, ретрай упавшего старта,
события для Live, сохранение диалогов и метрик в БД.
"""
import threading
import time
import traceback

from core import storage
from core.clients import make_client
from core.engine.dialog import run_dialog
from core.engine.events import EventLog
from core.evaluation.checks import run_checks
from core.evaluation.judge import judge_dialog
from core.io.parsers import parse_dialog
from core.llm import LLM
from core.metrics import compute_metrics
from core.platforms import build_adapter

JOBS: dict[int, "Job"] = {}


class Job:
    """Состояние читает страница Live: done/total/current/status/log."""

    def __init__(self, run_id, project, connection, settings, scenarios, mode, repeats, start_retries=2):
        self.run_id, self.project, self.connection, self.settings = run_id, project, connection, settings
        self.scenarios, self.mode, self.repeats, self.start_retries = scenarios, mode, repeats, start_retries
        self.total, self.done, self.current = len(scenarios) * repeats, 0, ""
        self.events = EventLog()
        self.status, self.error, self.stop_requested = "running", None, False
        self.started = time.time()
        self.thread = threading.Thread(target=self._run, daemon=True)
        JOBS[run_id] = self

    @property
    def log(self) -> list[dict]:
        return self.events.items()

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.stop_requested = True

    def _one(self, sc, llm) -> dict:
        if self.mode == "judge_only":
            hist = [{"role": t["role"], "text": t["text"]} for t in parse_dialog(sc.get("golden") or "")]
            for h in hist:
                self.events.emit(sc["sid"], h)
            return {"history": hist, "ended_by": "golden", "meta": {"ended": True}, "error": None}
        d = None
        for attempt in range(self.start_retries + 1):
            adapter = build_adapter(self.connection, self.settings, self.project)
            client = make_client(self.mode, sc, llm, self.settings)
            d = run_dialog(adapter, client, int(self.settings["max_turns"]),
                           on_turn=lambda h, s=sc["sid"]: self.events.emit(s, h),
                           stop_flag=lambda: self.stop_requested)
            if not (d["error"] and len(d["history"]) == 0):     # упал сам старт — повторяем
                break
            self.events.emit(sc["sid"], {"role": "system", "text": f"старт не удался, повтор {attempt + 1}: {d['error']}"})
            time.sleep(3 * (attempt + 1))
        return d

    def _run(self):
        llm = LLM.from_settings(self.settings)
        try:
            for sc in self.scenarios:
                for rep in range(1, self.repeats + 1):
                    if self.stop_requested:
                        raise InterruptedError
                    self.current = f"{sc['sid']} #{rep}"
                    d = self._one(sc, llm)
                    self.events.emit(sc["sid"], {"role": "system",
                                                 "text": f"── конец: {'ошибка' if d['error'] else d['ended_by']} ──"})
                    verdict = None
                    if not d["error"] and d["history"]:
                        try:
                            verdict = judge_dialog(llm, self.settings, self.project, sc, d["history"],
                                                   self.mode, d["meta"])
                        except Exception as e:  # noqa: BLE001
                            verdict = {"outcome": "unclear", "violations": {}, "problems": [f"ошибка судьи: {e}"]}
                        verdict["checks"] = run_checks(d["history"], d["meta"], self.project)
                    storage.save("dialogs", {"run_id": self.run_id, "scenario": sc["sid"], "expected": sc.get("expected"),
                                             "repeat": rep, "history": d["history"], "verdict": verdict,
                                             "meta": d["meta"], "error": d["error"], "ended_by": d["ended_by"]})
                    self.done += 1
            self.status = "done"
        except InterruptedError:
            self.status = "stopped"
        except Exception as e:  # noqa: BLE001
            self.status, self.error = "error", traceback.format_exc()[-1500:]
            self.events.emit("", {"role": "system", "text": f"Ошибка прогона: {e}"})
        finally:
            metrics = compute_metrics(storage.run_dialogs(self.run_id), self.project, self.settings)
            storage.update("runs", self.run_id, status=self.status, metrics=metrics)
            from core.notify.telegram import notify_run
            why = notify_run(self.run_id, self.project, self.status, self.error)
            if why and "не задан" not in why:
                self.events.emit("", {"role": "system", "text": f"Telegram: {why}"})
