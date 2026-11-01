"""Судья: правила проекта + сценарий + диалог + служебные данные платформы -> вердикт (JSON).
Нарушения только с цитатой реплики агента; заметка о режиме теста (A/B/свободный/ручной).
"""
import json

from core.clients.base import dialog_text
from core.llm import parse_json

MODE_NOTES = {
    "scripted": "Тест по шаблону: клиент произносит заранее записанные фразы по порядку и НЕ слушает агента. "
                "Если реплика клиента не отвечает на вопрос агента — это особенность теста, а не ошибка агента.",
    "guided": "Тест с помощником: клиент следует сценарию, но подстраивается под вопросы агента.",
    "simulated": "Клиента играет модель по описанию персоны.",
    "judge_only": "Оценивается готовый записанный диалог.",
    "manual": "Ручной диалог, клиента играл человек.",
}

JUDGE_PROMPT = """Ты строгий и справедливый QA-инженер. Оцени разговор голосового ИИ-агента с клиентом.

ПРАВИЛА АГЕНТА (что правильно и что нарушение):
<<RULES>>

КЛАССЫ ИСХОДА:
<<OUTCOMES>>

НАРУШЕНИЯ:
<<VIOLATIONS>>

СЦЕНАРИЙ ТЕСТА:
Персона клиента: <<PERSONA>>
Поведение клиента: <<BEHAVIOR>>
Факты клиента: <<FACTS>>
Ожидаемый исход: <<EXPECTED>>
Особая проверка: <<CHECK>>
Режим теста: <<MODE>>

СЛУЖЕБНЫЕ ДАННЫЕ ПЛАТФОРМЫ (вызванные инструменты, причина завершения):
<<META>>

ДИАЛОГ:
<<DIALOG>>

Правила оценки:
- Отмечай нарушение, только если можешь привести точную цитату реплики агента, которая его доказывает.
- Реплика «(молчание: нет ответа)» — агент не ответил клиенту: это нарушение ignored_question (если оно есть в списке).
- Не придумывай ошибки, которых нет в диалоге.

Верни ТОЛЬКО JSON:
{
 "outcome": "<<OUTCOME_CODES>>",
 "violations": {<<VIOL_KEYS>>},
 "naturalness": 1-5,
 "politeness": 1-5,
 "problems": ["код нарушения — «точная цитата реплики агента»"],
 "worst_agent_reply": "цитата или пустая строка",
 "comment": "1–2 предложения итоговой оценки"
}"""


def judge_dialog(llm, settings, project, scenario, history, mode, meta=None) -> dict:
    outcomes = project.get("outcomes") or []
    violations = project.get("violations") or []
    prompt = (JUDGE_PROMPT
              .replace("<<RULES>>", project.get("judge_rules") or "—")
              .replace("<<OUTCOMES>>", "\n".join(f"- {o['code']}: {o.get('desc', '')}" for o in outcomes))
              .replace("<<VIOLATIONS>>", "\n".join(f"- {v['code']}: {v.get('desc', '')}" for v in violations))
              .replace("<<PERSONA>>", scenario.get("persona") or "—")
              .replace("<<BEHAVIOR>>", scenario.get("behavior") or "—")
              .replace("<<FACTS>>", scenario.get("facts") or "—")
              .replace("<<EXPECTED>>", scenario.get("expected") or "—")
              .replace("<<CHECK>>", scenario.get("check_text") or "—")
              .replace("<<MODE>>", MODE_NOTES.get(mode, mode))
              .replace("<<META>>", json.dumps({k: (meta or {}).get(k) for k in ("end_reason", "tools")}, ensure_ascii=False))
              .replace("<<DIALOG>>", dialog_text(history))
              .replace("<<OUTCOME_CODES>>", "|".join(o["code"] for o in outcomes))
              .replace("<<VIOL_KEYS>>", ", ".join(f'"{v["code"]}": 0 или 1' for v in violations)))
    return parse_json(llm.chat(settings["judge_model"], [{"role": "system", "content": "Ты отвечаешь только JSON."},
                                                         {"role": "user", "content": prompt}],
                               temperature=0, max_tokens=2500, json_mode=True))
