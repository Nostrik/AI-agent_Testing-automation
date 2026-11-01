"""Отрисовка ленты: пузыри агента/клиента, ⏱ задержка, служебные строки
(▸ TOOL_CALL, 🔇 побуждение, Dialog created/closed), вердикт судьи.
"""
import html

import streamlit as st


def llm_caption(s: dict) -> str:
    """Тайминги локальной модели под репликой агента."""
    parts = [f"🧮 вход {s.get('prompt_tokens', 0):,} ток за {s.get('prompt_s', 0):.2f} с".replace(",", " "),
             f"ответ {s.get('gen_tokens', 0)} ток за {s.get('gen_s', 0):.2f} с"
             + (f" ({s['tok_per_s']} ток/с)" if s.get("tok_per_s") else ""),
             f"до первого слова ≈ {s.get('first_token_s', 0):.2f} с"]
    if s.get("load_s", 0) >= 0.5:
        parts.append(f"⚠ загрузка модели {s['load_s']:.1f} с")
    return " · ".join(parts)


def render_turn(h: dict, show_tools=True):
    role = h.get("role")
    if role == "system":
        st.caption(h["text"])
        return
    if role == "agent":
        with st.chat_message("assistant", avatar="🤖"):
            lat = h.get("latency_s")
            st.markdown(html.escape(h["text"]) + (f"  `⏱ {lat:.2f} с`" if lat is not None else ""))
    else:
        with st.chat_message("user", avatar="🙂"):
            st.markdown(html.escape(h["text"]))
    if role == "agent" and h.get("llm"):
        st.caption(llm_caption(h["llm"]))
    if show_tools:
        for t in h.get("tools") or []:
            st.caption(f"▸ TOOL_CALL: {t.get('name')} {t.get('args') or ''}")
        for n in h.get("nudges") or []:
            st.caption(f"🔇 {n}")


def render_verdict(v: dict | None, error: str | None = None):
    if error:
        st.error(f"Ошибка: {error}")
    if not v:
        return
    bad = [k for k, x in (v.get("violations") or {}).items() if x]
    st.markdown(f"**Исход:** `{v.get('outcome')}` · **Нарушения:** {', '.join(bad) or 'нет'} · "
                f"**Естественность:** {v.get('naturalness', '—')} · **Вежливость:** {v.get('politeness', '—')}")
    for p in v.get("problems") or []:
        st.markdown(f"- {p}")
    if v.get("comment"):
        st.caption(v["comment"])
    if v.get("checks"):
        st.caption("Проверки без LLM: " + ", ".join(f"{k}={x}" for k, x in v["checks"].items()))
