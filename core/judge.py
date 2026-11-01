"""Судья и аналитик."""
import json

from core.clients import dialog_text
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


ANALYST_PROMPT = """Ты эксперт по настройке голосовых ИИ-агентов.
Ниже результаты автотеста агента.

ПРОМПТ АГЕНТА:
<<PROMPT>>

ОБЩИЕ МЕТРИКИ:
<<METRICS>>

ЗАМЕЧАНИЯ СУДЬИ С ЦИТАТАМИ (по сценариям):
<<EVIDENCE>>

ХУДШИЕ ДИАЛОГИ:
<<WORST>>

Правило: указывай проблему и сценарий, только если она подтверждается цитатой выше. Не обобщай, не выдумывай.
Задержку ответа даёт модель и платформа, не предлагай сокращать реплики ради скорости.

Напиши отчёт на русском в Markdown строго в этой структуре:
## 1. Вердикт
Одна строка: 🟢 готов к пилоту / 🟡 готов с доработками / 🔴 не готов. Дальше 2–3 предложения.
## 2. Главные проблемы
Таблица: Важность (🔴/🟠/🟡) | Проблема | Сценарии | Что происходит (с цитатой).
## 3. Правки к промпту
Для каждой: значок важности, в какой блок промпта, готовый текст правки в цитате (>).
## 4. Что уже хорошо
2–4 пункта с ✅.
## 5. Новые сценарии
3–5 сценариев списком: id, персона, поведение, факты, проверка, ожидаемый исход."""


def analyst_report(llm, settings, project, dialogs, metrics) -> str:
    evidence = "\n".join(f"[{d['scenario']}] {p}" for d in dialogs
                         for p in ((d.get("verdict") or {}).get("problems") or []))
    bad = sorted(dialogs, key=lambda d: -sum(((d.get("verdict") or {}).get("violations") or {}).values()))[:5]
    worst = "\n\n".join(f"[{d['scenario']}] {(d.get('verdict') or {}).get('comment', '')}\n" + dialog_text(d["history"] or [])
                        for d in bad)
    prompt = (ANALYST_PROMPT.replace("<<PROMPT>>", project.get("agent_prompt") or "—")
              .replace("<<METRICS>>", json.dumps(metrics, ensure_ascii=False))
              .replace("<<EVIDENCE>>", evidence[:12000] or "—")
              .replace("<<WORST>>", worst[:12000] or "—"))
    return llm.chat(settings["analyst_model"], [{"role": "system", "content": "Ты опытный консультант по ИИ-агентам."},
                                                {"role": "user", "content": prompt}],
                    temperature=0.3, max_tokens=6000)
