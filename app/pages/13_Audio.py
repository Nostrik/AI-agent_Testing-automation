"""Анализ аудио: загрузили запись звонка -> расшифровка по ролям, паузы между репликами, метрики."""
import hashlib
import html

import pandas as pd
import streamlit as st

from app.components.chat_view import render_verdict
from app.components.timeline import gaps_figure, timeline_figure
from app.components.waveform import waveform

from core import storage
from core.evaluation import judge_dialog
from core.io.export import to_xlsx
from core.io.parsers import to_text
from core.llm import LLM
from core.voice.analysis import VOICE_LABELS, analyze_audio, to_history, voice_metrics
from core.voice.transcribe import get_model
from core.voice.remote_whisper import RemoteWhisper
from core.notify.telegram import notify_audio

st.title("🎧 Анализ аудио")
st.caption("Запись звонка → кто что сказал и сколько длилась пауза перед каждым ответом агента. "
           "Лучше всего стерео-запись: агент и клиент на разных каналах.")

settings = storage.get_settings()
with st.sidebar:
    backend = st.radio("Распознавание", ["local", "remote"], horizontal=False,
                       format_func={"local": "на этом компьютере (CPU)", "remote": "удалённый Whisper (GPU)"}.get,
                       index=1 if settings.get("whisper_backend") == "remote" else 0)
    if backend == "remote":
        url = st.text_input("Адрес Whisper-WebUI", settings.get("whisper_url") or "http://100.110.207.76:7860/")
        size = st.selectbox("Модель на сервере", ["medium", "small", "large-v3-turbo", "large-v3"], index=0,
                            help="medium уже скачана на сервере. Более тяжёлые модели сначала скачиваются и могут занять очередь.")
        compute = st.selectbox("Тип вычислений", ["float32", "int8_float32", "int8"], index=0,
                               help="GTX 1070 не ускоряет float16 — float32 или int8.")
    else:
        url, compute = "", "int8"
        size = st.selectbox("Модель распознавания", ["small", "medium", "large-v3"], index=1,
                            help="medium — баланс скорости и точности для телефонных 8 кГц. Первый запуск скачивает модель.")
    if backend != settings.get("whisper_backend") or (url and url != settings.get("whisper_url")):
        storage.save_settings({"whisper_backend": backend, **({"whisper_url": url} if url else {})})
    agent_channel = st.radio("Агент в канале (стерео)", ["left", "right"],
                             format_func={"left": "левом", "right": "правом"}.get, horizontal=True)
    first = st.radio("Первым говорит (моно)", ["agent", "client"],
                     format_func={"agent": "агент", "client": "клиент"}.get, horizontal=True)
    slow_s = st.number_input("Долгая пауза, с", 0.5, 10.0, 1.5, 0.1)
    st.markdown("**Графики**")
    show_wave = st.checkbox("звуковая диаграмма", True)
    show_timeline = st.checkbox("ход разговора", False)
    show_gaps = st.checkbox("паузы перед ответами", False)

files = st.file_uploader("Аудиофайлы звонков", type=["wav", "mp3", "ogg", "m4a", "flac"], accept_multiple_files=True)
if not files:
    st.stop()

ss = st.session_state
ss.setdefault("audio_results", {})


@st.cache_resource(show_spinner="Загружаю модель распознавания (первый раз — скачивание)…")
def model_for(name):
    return get_model(name)


if st.button("🎧 Анализировать", type="primary"):
    if backend == "remote":
        model = RemoteWhisper(url, size, compute)
        try:
            with st.spinner("Подключаюсь к Whisper-WebUI…"):
                model.check()
        except Exception as e:  # noqa: BLE001
            st.error(f"Удалённый Whisper недоступен ({url}): {e}")
            st.stop()
    else:
        model = model_for(size)
    llm = LLM.from_settings(settings) if settings.get("llm_api_key") else None
    new, failed = 0, []
    for f in files:
        data = f.getvalue()
        key = f"{hashlib.md5(data).hexdigest()}|{backend}|{size}|{agent_channel}|{first}"
        if key in ss.audio_results:
            continue
        with st.status(f"{f.name}", expanded=False) as status:
            try:
                res = analyze_audio(data, model, agent_channel, first, llm, settings.get("judge_model"), slow_s,
                                    progress=status.write)
                res["name"] = f.name
                ss.audio_results[key] = res
                new += 1
                status.update(label=f"{f.name} — готово", state="complete")
            except Exception as e:  # noqa: BLE001
                status.update(label=f"{f.name} — ошибка: {e}", state="error")
                failed.append(f.name)
    if new or failed:
        done = [r for r in ss.audio_results.values() if r["name"] in {x.name for x in files}]
        why = notify_audio(done, slow_s, failed)
        if why and "не задан" not in why:
            st.warning(f"Telegram: {why}")

results = [r for k, r in ss.audio_results.items() if r["name"] in {f.name for f in files}]
if not results:
    st.stop()

if len(results) > 1:                                  # сводка по нескольким файлам
    st.subheader("Сводка")
    summary = pd.DataFrame([{"Файл": r["name"], **{VOICE_LABELS[k]: v for k, v in r["metrics"].items()}}
                            for r in results])
    st.dataframe(summary, hide_index=True, use_container_width=True)
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Скачать Excel", to_xlsx(summary, "Сводка"), file_name="audio_summary.xlsx")
    c2.download_button("⬇️ Скачать CSV для Excel",
                       summary.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name="audio_summary.csv", mime="text/csv")

for i, r in enumerate(results):
    st.divider()
    st.subheader(r["name"])
    f = next((x for x in files if x.name == r["name"]), None)
    if f and show_wave:
        waveform(f.getvalue(), f.name, r["turns"], slow_s, r["stereo"], agent_channel)
    elif f:
        st.audio(f.getvalue())
    m = voice_metrics(r["turns"], r["duration_s"], slow_s)  # пересчёт под текущий порог, без распознавания
    st.caption("Стерео: роли по каналам" if r["stereo"] else "Моно: оба голоса на одной дорожке")
    det = r.get("detectors") or {}
    if not r["stereo"]:
        if det.get("roles") == "acoustic":
            st.caption(f"Роли определены по звучанию голосов (разделение {det.get('separation')}: "
                       "от 2 — надёжно, от 3 — уверенно).")
        elif det.get("roles") == "llm":
            st.warning(
                "Голоса по звучанию не разделились — роли расставлены по смыслу фраз (LLM). Проверьте расшифровку.")
        else:
            st.error("Роли не определены: голоса по звучанию не разделились, а LLM недоступен — реплики "
                     "расставлены по очереди. Паузы на этой записи недостоверны.")
    weak = [k for k, v in det.items() if v == "energy"]
    if weak:
        st.info("Речь на канале «" + ", ".join({"agent": "агент", "client": "клиент"}.get(k, k) for k in weak)
                + "» найдена по громкости: детектор речи её не распознал (тихий или искажённый канал). "
                  "Паузы посчитаны, но текст этих реплик может быть «(неразборчиво)».")
    keys = ["agent_gap_median_s", "agent_gap_p95_s", "agent_gap_max_s", "agent_slow_pct", "agent_interruptions",
            "duration_s"]
    for c, k in zip(st.columns(len(keys)), keys):
        c.metric(VOICE_LABELS[k], m.get(k))

    if show_timeline:
        st.markdown("**Ход разговора** · наведите на реплику, чтобы увидеть текст")
        st.plotly_chart(timeline_figure(r["turns"], slow_s), use_container_width=True, key=f"tl_{i}")
    if show_gaps:
        st.markdown("**Пауза перед каждым ответом агента**")
        st.plotly_chart(gaps_figure(r["turns"], slow_s), use_container_width=True, key=f"gp_{i}")

    dlg = st.expander(f"💬 Расшифровка разговора · {sum(not t.get('backchannel') for t in r['turns'])} реплик",
                      expanded=False)
    tab_chat, tab_table = dlg.tabs(["Расшифровка", "Таблица"])
    with tab_chat:
        for t in sorted(r["turns"], key=lambda x: x["start"]):
            if t.get("backchannel"):
                st.caption(f"↳ {t['start']:.1f} с · {'агент' if t['role'] == 'agent' else 'клиент'}: {t['text']}")
                continue
            g = t.get("gap_s")
            badge = ""
            if g is not None and t.get("after") == t["role"]:
                badge = f"  `↻ снова, без ответа собеседника, через {g:.1f} с`"
            elif g is not None:
                mark = "🔴" if g > slow_s or g < 0 else "🟢"
                badge = f"  `{mark} пауза {g:.1f} с`" if g >= 0 else f"  `{mark} перебил {abs(g):.1f} с`"
            with st.chat_message("assistant" if t["role"] == "agent" else "user",
                                 avatar="🤖" if t["role"] == "agent" else "🙂"):
                st.markdown(f"`{t['start']:.1f} с` " + html.escape(t["text"]) + badge)
    with tab_table:
        df = pd.DataFrame([{"Кто": "Агент" if t["role"] == "agent" else "Клиент", "Начало, с": t["start"],
                            "Конец, с": t["end"], "Пауза перед, с": t.get("gap_s"),
                            "Поддакивание": bool(t.get("backchannel")), "Текст": t["text"]}
                           for t in sorted(r["turns"], key=lambda x: x["start"])])
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.download_button("⬇️ Excel", to_xlsx(df, "Реплики"), file_name=f"{r['name']}.xlsx", key=f"x_{i}")

    projects = storage.list_("projects")
    if projects:
        with st.expander("⚖️ Судья и сохранение в сценарий"):
            pid = st.selectbox("Проект", [p["id"] for p in projects], key=f"p_{i}",
                               format_func=lambda x: next(p["name"] for p in projects if p["id"] == x))
            project = storage.get("projects", pid)
            hist = to_history(r["turns"])
            c1, c2, c3 = st.columns(3)
            if c1.button("⚖️ Оценить судьёй", key=f"j_{i}"):
                with st.spinner("Судья думает…"):
                    r["verdict"] = judge_dialog(LLM.from_settings(settings), settings, project,
                                                {"persona": "запись реального звонка", "expected": "—"},
                                                hist, "judge_only", {})
            scen = storage.project_scenarios(pid)
            if scen:
                target = c2.selectbox("Сценарий", [s["id"] for s in scen], key=f"s_{i}", label_visibility="collapsed",
                                      format_func=lambda x: next(s["sid"] for s in scen if s["id"] == x))
                if c3.button("⭐ Реплики клиента в шаблон", key=f"sv_{i}"):
                    storage.update("scenarios", target, script=[h["text"] for h in hist if h["role"] == "client"])
                    st.success("Реплики клиента сохранены в шаблон сценария")
                if c3.button("⭐ Сохранить как эталон", key=f"g_{i}"):
                    storage.update("scenarios", target, golden=to_text(hist))
                    st.success("Сохранено как эталон")
            if r.get("verdict"):
                render_verdict(r["verdict"])
