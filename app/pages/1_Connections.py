import streamlit as st

from core import storage
from core.platforms import ADAPTERS, build_adapter

from app.ui import flash

st.title("🔌 Подключения")
st.caption("Куда тестер звонит/пишет: платформа и учётные данные агента.")

conns = storage.list_("connections")
options = [None] + [c["id"] for c in conns]
sel = st.selectbox("Подключение", options,
                   format_func=lambda i: "➕ Новое подключение" if i is None else
                   next(f"{c['name']} ({ADAPTERS[c['type']]['title']})" for c in conns if c["id"] == i))
cur = storage.get("connections", sel) if sel else {"name": "", "type": "twin_agent", "params": {}}

types = list(ADAPTERS)
ctype = st.selectbox("Тип", types, index=types.index(cur["type"]), format_func=lambda t: ADAPTERS[t]["title"],
                     disabled=bool(sel))
name = st.text_input("Название", cur["name"])
params = {}
for key, label, ftype, default in ADAPTERS[ctype]["fields"]:
    val = (cur.get("params") or {}).get(key, default)
    if ftype == "password":
        params[key] = st.text_input(label, val, type="password")
    elif ftype == "number":
        params[key] = st.number_input(label, value=float(val or 0), step=0.5)
    elif ftype == "textarea":
        params[key] = st.text_area(label, val, height=200)
    else:
        params[key] = st.text_input(label, val)

c1, c2, c3 = st.columns(3)
if c1.button("💾 Сохранить", type="primary", disabled=not name):
    cid = storage.save("connections", {"id": sel, "name": name, "type": ctype, "params": params})
    flash(f"Подключение «{name}» сохранено")
    st.rerun()

if c2.button("🧪 Проверить"):
    with st.spinner("Пробный диалог…"):
        try:
            a = build_adapter({"type": ctype, "params": params}, storage.get_settings())
            turn = a.start()
            meta = a.finish()
            st.success(f"Агент ответил за {turn['latency_s'] or 0:.2f} с")
            st.info(turn["text"] or "(молчание)")
            st.json(meta)
        except Exception as e:  # noqa: BLE001
            st.error(f"Не удалось: {e}")

if sel and c3.button("🗑 Удалить"):
    storage.delete("connections", sel)
    flash("Подключение удалено", "🗑")
    st.rerun()
