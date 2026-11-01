import pandas as pd
import streamlit as st

from app.ui import pick_project
from core import storage
from core.io.parsers import client_lines, parse_dialog, parse_run_log, to_text
from app.ui import flash

st.title("📜 Сценарии")
project = pick_project()
if not project:
    st.stop()
codes = [o["code"] for o in project.get("outcomes") or []]
codes += ["unclear|warm|callback"] + sorted({s.get("expected") for s in storage.project_scenarios(project["id"])
                                             if s.get("expected") and s["expected"] not in codes} - {"unclear|warm|callback"})

scen = storage.project_scenarios(project["id"])
st.subheader("Список сценариев")
st.caption("id, кто клиент, как себя ведёт, факты, что проверяем, ожидаемый исход. Строки можно добавлять и удалять.")
df = pd.DataFrame([{k: s.get(k) for k in ("id", "sid", "persona", "behavior", "facts", "check_text", "expected")}
                   for s in scen] or [{"id": None, "sid": "", "persona": "", "behavior": "", "facts": "",
                                       "check_text": "", "expected": codes[0] if codes else ""}])
edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, hide_index=True, key="scen_table",
                        column_config={
                            "id": None, "sid": "ID", "persona": "Персона", "behavior": "Поведение",
                            "facts": "Факты", "check_text": "Особая проверка",
                            "expected": st.column_config.SelectboxColumn("Ожидаемый исход", options=codes)})
if st.button("💾 Сохранить список", type="primary"):
    keep = set()
    old = {s["id"]: s for s in scen}
    for r in edited.to_dict("records"):
        if not r.get("sid"):
            continue
        base = old.get(r.get("id")) or {"script": [], "golden": ""}
        rid = r.get("id") if r.get("id") == r.get("id") and r.get("id") else None   # NaN -> None
        sid = storage.save("scenarios", {**base, **{k: r.get(k) or "" for k in
                                                    ("sid", "persona", "behavior", "facts", "check_text", "expected")},
                                         "id": int(rid) if rid else None, "project_id": project["id"]})
        keep.add(sid)
    for s in scen:
        if s["id"] not in keep:
            storage.delete("scenarios", s["id"])
    flash(f"Сохранено сценариев: {len(keep)}")
    st.rerun()

with st.expander("📥 Импорт реплик клиента из выгрузки прогона («[id] 🙂 Клиент: …»)"):
    st.caption("Реплики клиента попадут в шаблон сценария с тем же ID; если такого ID нет — сценарий будет создан.")
    log_txt = st.text_area("Выгрузка прогона", height=220, key="run_log")
    as_golden = st.checkbox("Сохранить весь диалог и как эталон (только если ответы агента в нём правильные)")
    if log_txt:
        parsed = parse_run_log(log_txt)
        st.write({k: f"клиент: {len(client_lines(v))} реплик" for k, v in parsed.items()})
        if st.button("📥 Импортировать", type="primary"):
            by_sid = {x["sid"]: x for x in scen}
            for k, turns in parsed.items():
                row = dict(by_sid.get(k) or {"sid": k, "persona": "", "behavior": "", "facts": "", "check_text": "",
                                             "expected": "", "golden": "", "project_id": project["id"]})
                row["script"] = client_lines(turns)
                if as_golden:
                    row["golden"] = to_text(turns)
                storage.save("scenarios", row)
            flash(f"Импортировано сценариев: {len(parsed)}")
            st.rerun()

st.divider()
st.subheader("Шаблонные реплики и эталонный диалог")
scen = storage.project_scenarios(project["id"])
if not scen:
    st.info("Сначала сохраните хотя бы один сценарий.")
    st.stop()
pick = st.selectbox("Сценарий", [s["id"] for s in scen], format_func=lambda i: next(s["sid"] for s in scen if s["id"] == i))
s = storage.get("scenarios", pick)

with st.expander("📥 Вставить готовый диалог текстом (выгрузка чата TWIN, «Клиент: … / Бот: …»)"):
    raw = st.text_area("Текст диалога", height=220, key=f"raw_{pick}")
    agent_name = st.text_input("Имя агента в тексте (если не «Бот»/«Агент»)", "", key=f"an_{pick}")
    if raw:
        many = parse_run_log(raw, agent_name)
        if len(many) > 1:                       # вставили выгрузку нескольких сценариев
            if s["sid"] in many:
                st.info(f"В тексте {len(many)} сценариев — беру только «{s['sid']}». "
                        "Чтобы загрузить все сразу, используйте «📥 Импорт реплик клиента из выгрузки прогона» выше.")
                turns = many[s["sid"]]
            else:
                st.warning(f"В тексте {len(many)} сценариев, а сценария «{s['sid']}» среди них нет. "
                           "Используйте «📥 Импорт реплик клиента из выгрузки прогона» выше.")
                turns = []
        else:
            turns = parse_run_log(raw, agent_name).get(next(iter(parse_run_log(raw, agent_name)), ""), []) \
                or parse_dialog(raw, agent_name)

c1, c2 = st.columns(2)
with c1:
    script_txt = st.text_area("Реплики клиента по порядку (одна строка — одна реплика)",
                              "\n".join(s.get("script") or []), height=300, key=f"script_{pick}")
with c2:
    golden_txt = st.text_area("Эталонный диалог (для калибровки и режима «Только судья»)",
                              s.get("golden") or "", height=300, key=f"golden_{pick}")
if st.button("💾 Сохранить реплики и эталон"):
    storage.update("scenarios", pick, script=[l.strip() for l in script_txt.splitlines() if l.strip()],
                   golden=golden_txt)
    flash("Реплики клиента сохранены в шаблон")
    st.success("Сохранено")
