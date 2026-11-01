"""Смена настроек ИИ-агента TWIN (модель, температура, макс. время ожидания, резерв) — для автоподбора.

Эндпоинт сохранения настроек не описан в публичной документации. Чтобы его узнать: открыть агента в TWIN,
F12 → Network, изменить модель, нажать «Сохранить» и взять URL, метод и тело запроса.
После этого реализовать get()/apply() ниже.
"""


class TwinAgentConfig:
    """Реализация интерфейса ConfigControl для ИИ-агента TWIN."""

    def __init__(self, params: dict):
        self.p = params

    def get(self) -> dict:
        raise NotImplementedError("Эндпоинт чтения настроек агента TWIN ещё не определён (см. docstring модуля)")

    def apply(self, cfg: dict) -> None:
        raise NotImplementedError("Эндпоинт сохранения настроек агента TWIN ещё не определён (см. docstring модуля)")
