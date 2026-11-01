"""Пространство поиска: модели (провайдер/модель), температура, макс. время ожидания, резерв."""
DEFAULT_SPACE = {
    "model": ["gemma-4-31b-it", "gpt-oss-120b"],
    "temperature": [0.1, 0.2, 0.3],
    "timeout_s": [3, 4, 5, 6],
}


def suggest(trial, space: dict | None = None) -> dict:
    space = space or DEFAULT_SPACE
    return {k: trial.suggest_categorical(k, list(v)) for k, v in space.items()}
