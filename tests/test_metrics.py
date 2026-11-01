"""Метрики качества и задержки, проверки без LLM."""
from core.evaluation.checks import run_checks
from core.metrics import dialog_passed, latency_metrics, lead_codes, outcome_ok, quality_metrics
from core.metrics.latency import slowest
from core.metrics.quality import outcome_matrix, violation_counts

PROJECT = {"outcomes": [{"code": "qualified", "lead": True}, {"code": "contact_found", "lead": True},
                        {"code": "no_need"}]}
LEADS = lead_codes(PROJECT)


def dlg(outcome, expected, violations=None, error=None, ended=True, lat=(1.0,), scenario="d01"):
    hist = [{"role": "agent", "text": "x", "latency_s": x} for x in lat]
    return {"scenario": scenario, "expected": expected, "error": error, "meta": {"ended": ended},
            "verdict": {"outcome": outcome, "violations": violations or {}}, "history": hist}


def test_lead_codes():
    assert LEADS == {"qualified", "contact_found"}


def test_outcome_ok():
    assert outcome_ok("no_need", "no_need", LEADS)
    assert outcome_ok("no_need", "qualified | no_need", LEADS)          # несколько допустимых
    assert outcome_ok("contact_found", "qualified", LEADS)               # лид засчитывается за лид
    assert not outcome_ok("no_need", "qualified", LEADS)
    assert not outcome_ok("qualified", "", LEADS)


def test_dialog_passed():
    assert dialog_passed(dlg("qualified", "qualified"), LEADS)
    assert not dialog_passed(dlg("qualified", "qualified", violations={"price": True}), LEADS)
    assert dialog_passed(dlg("qualified", "qualified", violations={"price": False}), LEADS)
    assert not dialog_passed(dlg("qualified", "qualified", error="boom"), LEADS)


def test_quality_metrics():
    ds = [dlg("qualified", "qualified"), dlg("no_need", "qualified"),
          dlg(None, "qualified", error="boom"), dlg("qualified", "qualified", ended=False)]
    ds[0]["history"].append({"role": "agent", "text": "...", "skip": True})
    m = quality_metrics(ds, PROJECT)
    assert m == {"dialogs": 4, "passed_pct": 50, "errors": 1, "not_ended": 1, "silences": 1}
    assert quality_metrics([], PROJECT)["passed_pct"] == 0


def test_violations_and_matrix():
    ds = [dlg("a", "a", {"price": True, "repeat": False}), dlg("b", "a", {"price": True, "repeat": True})]
    assert violation_counts(ds) == {"price": 2, "repeat": 1}
    assert outcome_matrix(ds) == {("a", "a"): 1, ("a", "b"): 1}


def test_latency_metrics():
    ds = [dlg("a", "a", lat=[1.0, 2.0, 3.0, 4.0]), dlg("a", "a", lat=[10.0])]
    m = latency_metrics(ds, {"slow_threshold_s": 3, "network_offset_s": 0.5})
    assert m["replies"] == 5 and m["median_s"] == 3.0 and m["max_s"] == 10.0 and m["p95_s"] == 10.0
    assert m["slow_pct"] == 40                                           # 4 и 10 дольше 3 с
    assert m["sum_s"] == 20.0 and m["sum_no_net_s"] == 17.5
    assert latency_metrics([], {})["median_s"] is None
    assert slowest(ds, 1)[0]["latency_s"] == 10.0


def test_run_checks():
    hist = [{"role": "agent", "text": "Добрый день! Цена 50 рублей. Удобно? Объём?"},
            {"role": "client", "text": "Да"},
            {"role": "agent", "text": "(молчание)", "skip": True},
            {"role": "agent", "text": "слово " * 50}]
    r = run_checks(hist, {"ended": True}, {"required_phrases": ["менеджер"], "forbidden_phrases": ["цена"]})
    assert r["ended_call"] is True
    assert r["digits_in_speech"] == 1 and r["multi_questions"] == 1 and r["long_replies"] == 1
    assert r["silences"] == 1
    assert r["missing_phrases"] == ["менеджер"] and r["forbidden_found"] == ["цена"]
