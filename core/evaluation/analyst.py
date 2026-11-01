"""Отчёт аналитика: вердикт 🟢🟡🔴, проблемы с цитатами, правки к промпту, «что хорошо» ✅,
новые сценарии.
"""
import json

from core.clients.base import dialog_text

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