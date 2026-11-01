"""Экспорт в Excel и текст (числа хранятся числами, а не текстом)."""
import io
import statistics

import pandas as pd


def to_xlsx_sheets(sheets: dict[str, pd.DataFrame]) -> bytes:
    """Несколько листов в одном файле: {имя листа: таблица}."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets.items():
            sheet = name[:31]                                   # ограничение Excel на имя листа
            df.to_excel(xw, index=False, sheet_name=sheet)
            ws = xw.sheets[sheet]
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col) + 2
                ws.column_dimensions[col[0].column_letter].width = min(max(width, 10), 60)
            ws.freeze_panes = "A2"
    return buf.getvalue()


def to_xlsx(df: pd.DataFrame, sheet="Прогоны") -> bytes:
    return to_xlsx_sheets({sheet: df})


def _tools(tools) -> str:
    return ", ".join(f"{t.get('name')}({t.get('args') or ''})" for t in tools or [])


def run_header(run: dict | None, dialogs: list[dict] | None = None, leads: set | None = None,
               full: bool = False) -> list[tuple[str, str]]:
    """Шапка прогона: на чём и как он шёл. full=True — полный список сценариев (для Excel)."""
    from core.metrics import dialog_passed
    c = (run or {}).get("config") or {}
    sc = c.get("scenarios") or []
    if sc and not full and len(sc) > 6:
        scen = f"{len(sc)} × {c.get('repeats', 1)}: {sc[0]} … {sc[-1]}"
    elif sc:
        scen = f"{len(sc)} × {c.get('repeats', 1)}: " + ", ".join(sc)
    else:
        scen = ""
    rows = [
        ("Пройдено", f"{sum(dialog_passed(d, leads) for d in dialogs)} из {len(dialogs)}"
                     if dialogs is not None and leads is not None else ""),
        ("Подключение", f"{c['connection']} ({c.get('conn_type', '')})" if c.get("connection") else ""),
        ("Модель агента", c.get("agent_model") or c.get("model") or ""),
        ("Поставщик", c.get("provider") or ""),
        ("Температура", c.get("temperature") or ""),
        ("Судья", c.get("judge_model") or ""),
        ("Клиент", c.get("client_model") or ""),
        ("Промпт", c.get("prompt_id") or ""),
        ("Сценарии", scen),
        ("Комментарий", c.get("note") or ""),
    ]
    return [(k, str(v)) for k, v in rows if v not in ("", None)]


def run_frames(dialogs: list[dict], leads: set, run: dict | None = None) -> dict[str, pd.DataFrame]:
    """Прогон -> {"Итоги": строка на диалог, "Диалоги": строка на реплику}."""
    from core.metrics import dialog_passed, latencies
    summary, turns = [], []
    for d in dialogs:
        v = d.get("verdict") or {}
        meta = d.get("meta") or {}
        lat = latencies([d])
        summary.append({
            "Сценарий": d.get("scenario"), "Повтор": d.get("repeat"),
            "Ожидалось": d.get("expected"), "Получилось": v.get("outcome"),
            "Пройден": "да" if dialog_passed(d, leads) else "нет",
            "Нарушения": ", ".join(k for k, x in (v.get("violations") or {}).items() if x),
            "Замечания судьи": "\n".join(v.get("problems") or []),
            "Комментарий судьи": v.get("comment") or "",
            "Естественность": v.get("naturalness"), "Вежливость": v.get("politeness"),
            "Проверки без LLM": ", ".join(f"{k}={x}" for k, x in (v.get("checks") or {}).items()),
            "Конец": d.get("ended_by"),
            "Завершила звонок": "да" if meta.get("ended") else "нет",
            "Причина завершения": meta.get("end_reason") or "",
            "Инструменты": ", ".join(f"{k}×{n}" for k, n in (meta.get("tools") or {}).items()),
            "Этап": meta.get("stage") or "",
            "Токенов входа за диалог": (meta.get("llm_totals") or {}).get("prompt_tokens"),
            "Токенов ответа за диалог": (meta.get("llm_totals") or {}).get("gen_tokens"),
            "Реплик агента": len(lat),
            "Медиана задержки, с": round(statistics.median(lat), 2) if lat else None,
            "Макс. задержка, с": round(max(lat), 2) if lat else None,
            "Ошибка": d.get("error") or "",
        })
        n = 0
        for h in d.get("history") or []:
            if h.get("role") not in ("agent", "client"):
                continue
            n += 1
            turns.append({
                "Сценарий": d.get("scenario"), "Повтор": d.get("repeat"), "№": n,
                "Кто": "Агент" if h["role"] == "agent" else "Клиент",
                "Текст": h.get("text"),
                "Задержка, с": h.get("latency_s"),
                "Молчание": "да" if h.get("skip") else "",
                "Инструменты": _tools(h.get("tools")),
                "Побуждения платформы": "; ".join(h.get("nudges") or []),
                "Токенов входа": (h.get("llm") or {}).get("prompt_tokens"),
                "Чтение входа, с": (h.get("llm") or {}).get("prompt_s"),
                "Токенов ответа": (h.get("llm") or {}).get("gen_tokens"),
                "Генерация, с": (h.get("llm") or {}).get("gen_s"),
                "Ток/с": (h.get("llm") or {}).get("tok_per_s"),
                "До первого слова (модель), с": (h.get("llm") or {}).get("first_token_s"),
                "Загрузка модели, с": (h.get("llm") or {}).get("load_s"),
            })
    head = pd.DataFrame(run_header(run, dialogs, leads, full=True), columns=["Параметр", "Значение"])
    return {"Прогон": head, "Итоги": pd.DataFrame(summary), "Диалоги": pd.DataFrame(turns)}


def run_text(dialogs: list[dict], leads: set, title: str = "", run: dict | None = None) -> str:
    """Все диалоги прогона текстом: заголовок, реплики, вердикт судьи."""
    from core.io.parsers import to_text
    from core.metrics import dialog_passed
    head = [title] if title else []
    head += [f"{k}: {v}" for k, v in run_header(run, dialogs, leads)]
    parts = ["\n".join(head)] if head else []
    for d in dialogs:
        v = d.get("verdict") or {}
        mark = "✅" if dialog_passed(d, leads) else "❌"
        lines = [f"=== {mark} {d.get('scenario')} #{d.get('repeat')} · ожидалось: {d.get('expected')} · "
                 f"получилось: {v.get('outcome')} ===",
                 to_text(d.get("history") or [])]
        bad = [k for k, x in (v.get("violations") or {}).items() if x]
        if bad:
            lines.append("Нарушения: " + ", ".join(bad))
        lines += [f"— {p}" for p in v.get("problems") or []]
        if v.get("comment"):
            lines.append("Судья: " + v["comment"])
        if d.get("error"):
            lines.append("Ошибка: " + d["error"])
        parts.append("\n".join(lines))
    return "\n\n".join(parts) + "\n"
