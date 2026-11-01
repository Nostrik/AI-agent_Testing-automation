"""Optuna (TPE): каждый trial = применить конфиг к агенту (ConfigControl) -> прогон -> score.
Хранение в SQLite (data/tuning.db), продолжение прерванного поиска по имени study.
Работает только когда для платформы реализован ConfigControl (см. core/platforms/twin/agent_config.py).
"""
from core.tuning.objective import score
from core.tuning.space import suggest


def tune(config_control, run_fn, trials: int = 25, space: dict | None = None, study_name: str = "agent",
         storage_url: str = "sqlite:///data/tuning.db", min_passed_pct: float = 90):
    """run_fn(cfg) -> metrics (dict). Возвращает optuna.Study."""
    import optuna

    original = config_control.get()

    def objective(trial):
        cfg = suggest(trial, space)
        config_control.apply(cfg)
        m = run_fn(cfg)
        for k, v in m.items():
            trial.set_user_attr(k, v)
        return score(m, min_passed_pct)

    study = optuna.create_study(study_name=study_name, storage=storage_url, load_if_exists=True,
                                direction="minimize", sampler=optuna.samplers.TPESampler(seed=42))
    try:
        study.optimize(objective, n_trials=trials)
    finally:
        config_control.apply(original)              # вернуть агенту исходные настройки
    return study
