import pandas as pd
import streamlit as st

from core import storage
from core.platforms import ADAPTERS

from app.ui import flash

st.title("📁 Проект")
st.caption("Что тестируем: подключение, промпт агента, правила оценки, исходы и нарушения.")

projects = storage.list_("projects")
options = [None] + [p["id"] for p in projects]
cur_id = st.session_state.get("project_id")
sel = st.selectbox("Проект", options, index=options.index(cur_id) if cur_id in options else 0,
                   format_func=lambda i: "➕ Новый проект" if i is None else next(p["name"] for p in projects if p["id"] == i))
p = storage.get("projects", sel) if sel else {
    "name": "", "connection_id": None, "agent_prompt": "", "judge_rules": "",
    "outcomes": storage.DEFAULT_OUTCOMES, "violations": storage.DEFAULT_VIOLATIONS}

conns = storage.list_("connections")
name = st.text_input("Название проекта", p["name"])
conn_ids = [c["id"] for c in conns]
connection_id = st.selectbox("Подключение к агенту", conn_ids,
                             index=conn_ids.index(p["connection_id"]) if p["connection_id"] in conn_ids else 0,
                             format_func=lambda i: next(f"{c['name']} ({ADAPTERS[c['type']]['title']})"
                                                        for c in conns if c["id"] == i)) if conns else None
if not conns:
    st.warning("Сначала добавьте подключение.")

tab1, tab2, tab3, tab4 = st.tabs(["Промпт агента", "Правила оценки", "Исходы", "Нарушения"])
with tab1:
    agent_prompt = st.text_area("Полный промпт агента (для аналитика и режима «LLM по промпту»)",
                                p["agent_prompt"] or "", height=420)
with tab2:
    judge_rules = st.text_area("Правила для судьи: что агент обязан делать, что считается нарушением, "
                               "особенности платформы (например, «приветствие говорит платформа»)",
                               p["judge_rules"] or "", height=420)
with tab3:
    st.caption("lead = исход считается заявкой (такие исходы взаимозаменяемы при сравнении с ожидаемым).")
    outcomes = st.data_editor(pd.DataFrame(p["outcomes"] or storage.DEFAULT_OUTCOMES), num_rows="dynamic",
                              use_container_width=True, key="outcomes",
                              column_config={"code": "Код", "desc": "Описание", "lead": st.column_config.CheckboxColumn("Заявка")})
with tab4:
    violations = st.data_editor(pd.DataFrame(p["violations"] or storage.DEFAULT_VIOLATIONS), num_rows="dynamic",
                                use_container_width=True, key="violations",
                                column_config={"code": "Код", "desc": "Описание"})

c1, c2 = st.columns(2)
if c1.button("💾 Сохранить проект", type="primary", disabled=not name or not conns):
    pid = storage.save("projects", {
        "id": sel, "name": name, "connection_id": connection_id, "agent_prompt": agent_prompt,
        "judge_rules": judge_rules,
        "outcomes": [r for r in outcomes.fillna("").to_dict("records") if r.get("code")],
        "violations": [r for r in violations.fillna("").to_dict("records") if r.get("code")]})
    st.session_state["project_id"] = pid
    flash("Проект сохранён")
    st.rerun()
if sel and c2.button("🗑 Удалить проект"):
    storage.delete("projects", sel)
    st.session_state.pop("project_id", None)
    flash("Проект удалён", "🗑")
    st.rerun()
