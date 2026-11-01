"""Мастер проекта: по промпту агента черновики правил оценки, классов исходов,
нарушений и стартовых сценариев (JSON).
"""
from core.llm import parse_json

ONBOARD_PROMPT = """Ниже системный промпт голосового ИИ-агента. Подготовь черновик для его автотестирования.

ПРОМПТ АГЕНТА:
<<PROMPT>>

Верни только JSON:
{
 "judge_rules": "правила оценки: что агент обязан делать и что запрещено (маркированный текст)",
 "outcomes": [{"code": "латиница", "desc": "описание", "lead": true/false}],
 "violations": [{"code": "латиница", "desc": "описание"}],
 "scenarios": [{"sid": "S01", "persona": "...", "behavior": "...", "facts": "...", "check_text": "...",
                "expected": "код исхода", "script": ["реплика клиента 1", "реплика 2"]}]
}
Сценариев 6–10: позитивный, отказ, «не звонить», нецелевой, возражения, просьба перезвонить, вопрос не по теме."""


def draft_project(llm, settings, agent_prompt: str) -> dict:
    text = llm.chat(settings["analyst_model"],
                    [{"role": "system", "content": "Ты QA-инженер ИИ-агентов. Отвечай только JSON."},
                     {"role": "user", "content": ONBOARD_PROMPT.replace("<<PROMPT>>", agent_prompt or "—")}],
                    temperature=0.3, max_tokens=6000, json_mode=True)
    return parse_json(text)
