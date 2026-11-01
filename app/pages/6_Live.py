import time

import streamlit as st

from app.ui import render_turn
from core.engine import JOBS

st.title("📡 Live")

if not JOBS:
    st.info("Сейчас нет запущенных прогонов. Запустите прогон на странице «Запуск».")
    st.stop()

ids = sorted(JOBS, reverse=True)
cur = st.session_state.get("job_id")
job_id = st.selectbox("Прогон", ids, index=ids.index(cur) if cur in ids else 0,
                      format_func=lambda i: f"№{i} · {JOBS[i].mode} · {JOBS[i].status}")
show_tools = st.sidebar.toggle("Показывать инструменты и побуждения", False)
only_current = st.sidebar.toggle("Только текущий диалог", True)


@st.fragment(run_every=1)
def live_view():
    job = JOBS[job_id]
    elapsed = int(time.time() - job.started)
    st.progress(job.done / max(job.total, 1),
                text=f"{job.done}/{job.total} · {job.status} · {elapsed // 60}:{elapsed % 60:02d} · {job.current}")
    if job.status == "running":
        if st.button("⏹ Остановить прогон"):
            job.stop()
    else:
        st.success(f"Прогон завершён: {job.status}. Смотрите «Результаты».")
        if job.error:
            st.code(job.error)
    log = job.log
    if only_current and job.status == "running":
        sid = job.current.split(" #")[0]
        log = [h for h in log if h.get("scenario") == sid]
    for h in log[-60:]:
        render_turn({**h, "text": (f"[{h['scenario']}] " if not only_current and h.get("scenario") else "") + h["text"]},
                    show_tools)


live_view()
