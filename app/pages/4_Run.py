import hashlib
import streamlit as st

from app.ui import MODES, pick_project
from core import storage
from core.engine import Job
from core.platforms.registry import ADAPTERS

st.title("▶️ Запуск")
project = pick_project()
if not project:
    st.stop()
conns = storage.list_("connections")
if not conns:
    st.error("Нет подключений — создайте его на странице «Подключения».")
    st.stop()
ids = [c["id"] for c in conns]
default = ids.index(project["connection_id"]) if project.get("connection_id") in ids else 0
conn_id = st.selectbox("Агент (подключение)", ids, index=default,
                       format_func=lambda i: next(c["name"] for c in conns if c["id"] == i),
                       help="Например, локальная копия Елены для отладки или настоящая Елена в TWIN.")
conn = storage.get("connections", conn_id)
settings = storage.get_settings()

mode = st.radio("Режим", list(MODES), format_func=MODES.get, horizontal=True)
scen = storage.project_scenarios(project["id"])
if mode in ("scripted", "guided"):
    scen = [s for s in scen if s.get("script")]
    st.caption("Показаны сценарии, у которых заполнены шаблонные реплики.")
elif mode == "judge_only":
    scen = [s for s in scen if s.get("golden")]
    st.caption("Показаны сценарии с эталонным диалогом. Агенту никто не звонит — оценивается только текст.")
if not scen:
    st.warning("Нет подходящих сценариев для этого режима.")
    st.stop()

chosen = st.multiselect("Сценарии", [s["id"] for s in scen], default=[s["id"] for s in scen],
                        format_func=lambda i: next(s["sid"] for s in scen if s["id"] == i))
c1, c2 = st.columns(2)
repeats = c1.number_input("Повторов каждого сценария", 1, 10, 1)
label = c2.text_input("Метка прогона", placeholder="например: gemma-4-31b, t=0.2, ожидание 5 с")

with st.expander("Конфигурация агента (для таблицы сравнения)"):
    k1, k2, k3, k4 = st.columns(4)
    cfg = {"provider": k1.text_input("Поставщик LLM"), "model": k2.text_input("Модель"),
           "temperature": k3.text_input("Температура"), "timeout": k4.text_input("Макс. ожидание, с"),
           "note": st.text_input("Комментарий")}

params = conn.get("params") or {}
prompt = params.get("system_prompt") or project.get("agent_prompt") or ""
cfg.update({
    "connection": conn["name"],
    "conn_type": ADAPTERS.get(conn["type"], {}).get("title", conn["type"]),
    "agent_model": params.get("model") or cfg.get("model") or "",
    "judge_model": settings.get("judge_model"),
    "client_model": settings.get("client_model") if mode in ("guided", "simulated") else None,
    "prompt_id": f"{len(prompt)} симв., #{hashlib.md5(prompt.encode()).hexdigest()[:6]}",
    "scenarios": [s["sid"] for s in scen if s["id"] in chosen],
    "repeats": int(repeats),
})

n = len(chosen) * repeats
st.caption(f"Будет диалогов: {n}. Агент: {conn['name']}. Судья: {settings['judge_model']}.")
if st.button("▶ Запустить", type="primary", disabled=not chosen):
    run_id = storage.save("runs", {"project_id": project["id"], "mode": mode, "label": label, "status": "running",
                                   "created": storage.now(), "config": cfg, "metrics": {}})
    Job(run_id, project, conn, settings, [s for s in scen if s["id"] in chosen], mode, int(repeats)).start()
    st.session_state["job_id"] = run_id
    st.switch_page("pages/6_Live.py")
