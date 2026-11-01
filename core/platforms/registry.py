"""Реестр адаптеров: тип -> класс + схема формы для страницы «Подключения».
build_adapter(connection) — создать адаптер по сохранённому подключению.

Новая платформа = класс с start/send/finish (см. base.AgentAdapter) + запись в ADAPTERS.
Поле формы: (ключ, подпись, тип, значение по умолчанию); тип: text | password | number | textarea.
"""
from core.llm import LLM
from core.platforms.http_generic import HttpGenericAdapter
from core.platforms.mock import MockAdapter
from core.platforms.openai_compat import OpenAICompatAdapter
from core.platforms.twin import TwinAgentAdapter, TwinBotAdapter
from core.platforms.twin.agent_chat import DEFAULT_NUDGES
from core.platforms.local_agent import LocalAgentAdapter

TWIN_AUTH = [
    ("email", "Email пользователя TWIN", "text", ""),
    ("password", "Пароль TWIN", "password", ""),
    ("company_id", "ID компании (если их несколько)", "text", ""),
]

ADAPTERS = {
    "twin_agent": {
        "title": "TWIN — ИИ-агент",
        "fields": TWIN_AUTH + [
            ("agent_id", "ID ИИ-агента", "text", ""),
            ("turn_quiet_s", "Тишина = конец хода агента, с", "number", 2.5),
            ("turn_timeout_s", "Макс. ожидание ответа агента, с", "number", 45.0),
            ("nudge_regex", "Побуждения платформы (регулярное выражение)", "text", DEFAULT_NUDGES),
        ],
    },
    "twin_bot": {
        "title": "TWIN — сценарный бот",
        "fields": TWIN_AUTH + [
            ("bot_id", "ID бота", "text", ""),
            ("communication_type", "Тип коммуникации (TEXT / VOICE)", "text", "TEXT"),
        ],
    },
    "llm_agent": {
        "title": "LLM по промпту (OpenAI-совместимый API)",
        "fields": [
            ("base_url", "Base URL (пусто — как в Настройках)", "text", ""),
            ("api_key", "API-ключ (пусто — как в Настройках)", "password", ""),
            ("model", "Модель", "text", "nvidia/nemotron-3-super-120b-a12b:free"),
            ("temperature", "Температура", "number", 0.3),
            ("end_mark", "Маркер конца разговора", "text", "[END]"),
            ("system_prompt", "Системный промпт (пусто — промпт агента из проекта)", "textarea", ""),
        ],
    },
    "local_agent": {
        "title": "Локальная копия агента (Ollama, с инструментами)",
        "fields": [
            ("base_url", "Адрес Ollama", "text", "http://100.110.207.76:11434"),
            ("model", "Модель", "text", "qwen3:8b"),
            ("temperature", "Температура", "number", 0.3),
            ("num_ctx", "Окно контекста, токенов (промпт должен поместиться целиком)", "number", 16384),
            ("use_tools", "Инструменты END_CONVERSATION / SKIP_TURN / этапы (да / нет)", "text", "да"),
            ("greeting", "Приветствие платформы (первая реплика без модели)", "textarea",
             "Добрый день! Меня зовут Елена, компания «Кузбасс Нефте Транс». Мы поставляем ГСМ оптом. "
             "А подскажите, закупаете бензин, дизель, мазут, битум?"),
            ("system_prompt", "Системный промпт (пусто — промпт агента из проекта)", "textarea", ""),
        ],
    },
    "http_generic": {
        "title": "Произвольный HTTP API",
        "fields": [
            ("headers", "Заголовки (JSON)", "textarea", '{"Authorization": "Bearer ..."}'),
            ("start_url", "URL старта диалога (пусто — без старта)", "text", ""),
            ("start_body", "Тело старта (JSON-шаблон)", "textarea", "{}"),
            ("sid_path", "Путь к ID диалога в ответе старта", "text", "id"),
            ("send_url", "URL реплики, можно {sid}", "text", ""),
            ("send_body", "Тело реплики, {text} — текст клиента", "textarea", '{"message": "{text}"}'),
            ("text_path", "Путь к тексту ответа", "text", "answer"),
            ("end_path", "Путь к признаку конца (пусто — нет)", "text", ""),
            ("end_value", "Значение признака конца (пусто — любое истинное)", "text", ""),
            ("finish_url", "URL завершения, можно {sid}", "text", ""),
            ("finish_body", "Тело завершения", "textarea", ""),
            ("timeout_s", "Таймаут запроса, с", "number", 60.0),
        ],
    },
    "mock": {
        "title": "Имитация (без сети, для проверки)",
        "fields": [
            ("replies", "Реплики агента по порядку; [END] в конце — завершить", "textarea", ""),
            ("rules", "Правила «ключевое слово => ответ»", "textarea", ""),
            ("delay_s", "Задержка ответа, с", "number", 0.0),
        ],
    },
}


def build_adapter(connection: dict, settings: dict | None = None, project: dict | None = None):
    """connection = {"type": ..., "params": {...}} из БД; settings — общие Настройки (для LLM)."""
    t, p = connection["type"], connection.get("params") or {}
    if t == "twin_agent":
        return TwinAgentAdapter(p)
    if t == "twin_bot":
        return TwinBotAdapter(p)
    if t == "llm_agent":
        s = settings or {}
        llm = LLM(p.get("base_url") or s.get("llm_base_url"), p.get("api_key") or s.get("llm_api_key"))
        return OpenAICompatAdapter(p, llm, (project or {}).get("agent_prompt") or "")
    if t == "local_agent":
        return LocalAgentAdapter(p, (project or {}).get("agent_prompt") or "")
    if t == "http_generic":
        return HttpGenericAdapter(p)
    if t == "mock":
        return MockAdapter(p)
    raise ValueError(f"Неизвестный тип подключения: {t}")
