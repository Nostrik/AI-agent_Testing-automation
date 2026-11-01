"""Аудио звонка -> реплики с временем, паузы перед ответом агента, перебивания, метрики.

Пауза (gap_s) = начало реплики − конец предыдущей реплики собеседника. Отрицательная — перебивание.
Короткое «ага/да» собеседника внутри чужой реплики — поддакивание (backchannel), ход не прерывает.
"""
import math
import time
import statistics as st

from core.voice.roles import MIN_SEPARATION, acoustic_roles, label_roles
from core.voice.transcribe import load_audio, transcribe
from core.voice.vad import detect_speech, normalize, snap, utterances
from core.voice.remote_whisper import RemoteWhisper


def _inside(u, other, tol=0.1):
    return other["role"] != u["role"] and other["start"] - tol <= u["start"] and u["end"] <= other["end"] + tol


def build_turns(utts: list[dict], backchannel_max_s: float = 2.0, backchannel_max_words: int = 3,
                same_role_merge_s: float = 1.5) -> list[dict]:
    """Реплики -> ходы. Подряд идущие реплики одной роли склеиваются, только если пауза между ними короткая;
    после долгой тишины без ответа собеседника — новый ход (after = роль предыдущего хода)."""
    utts = sorted(utts, key=lambda u: u["start"])
    for u in utts:
        short = u["end"] - u["start"] <= backchannel_max_s and u.get("n_words", 99) <= backchannel_max_words
        u["backchannel"] = short and any(_inside(u, o) for o in utts if o is not u)
    turns = []
    for u in (x for x in utts if not x["backchannel"]):
        if turns and turns[-1]["role"] == u["role"] and u["start"] - turns[-1]["end"] < same_role_merge_s:
            turns[-1]["end"] = max(turns[-1]["end"], u["end"])
            turns[-1]["text"] += " " + u["text"]
        else:
            turns.append({k: u[k] for k in ("role", "start", "end", "text")})
    for i, t in enumerate(turns):
        t["gap_s"] = round(t["start"] - turns[i - 1]["end"], 2) if i else None
        t["after"] = turns[i - 1]["role"] if i else None
        t["start"], t["end"] = round(t["start"], 2), round(t["end"], 2)
    backs = [{"role": u["role"], "start": round(u["start"], 2), "end": round(u["end"], 2), "text": u["text"]}
             for u in utts if u["backchannel"]]
    return turns + [{**b, "backchannel": True} for b in backs]


def voice_metrics(turns: list[dict], duration: float, slow_s: float = 1.5, interrupt_s: float = -0.3) -> dict:
    main = [t for t in turns if not t.get("backchannel")]
    agent_gaps = [t["gap_s"] for t in main if t["role"] == "agent" and t.get("after") == "client"]
    client_gaps = [t["gap_s"] for t in main if t["role"] == "client" and t.get("after") == "agent"]
    pos = sorted(g for g in agent_gaps if g >= 0)
    talk = lambda r: sum(t["end"] - t["start"] for t in main if t["role"] == r)  # noqa: E731
    return {
        "duration_s": round(duration, 1),
        "agent_turns": sum(t["role"] == "agent" for t in main),
        "agent_gap_median_s": round(st.median(pos), 2) if pos else None,
        "agent_gap_p95_s": round(pos[math.ceil(len(pos) * .95) - 1], 2) if pos else None,
        "agent_gap_max_s": round(max(pos), 2) if pos else None,
        "agent_slow_pct": round(100 * sum(g > slow_s for g in pos) / len(pos)) if pos else 0,
        "agent_interruptions": sum(g < interrupt_s for g in agent_gaps),
        "client_gap_median_s": round(st.median([g for g in client_gaps if g >= 0]), 2)
        if any(g >= 0 for g in client_gaps) else None,
        "backchannels": sum(bool(t.get("backchannel")) for t in turns),
        "agent_after_silence": sum(1 for t in main if t["role"] == "agent" and t.get("after") == "agent"),
        "agent_talk_pct": round(100 * talk("agent") / max(talk("agent") + talk("client"), 1e-9)),
    }


VOICE_LABELS = {
    "duration_s": "Длительность, с", "agent_turns": "Реплик агента",
    "agent_gap_median_s": "Пауза перед агентом, медиана, с", "agent_gap_p95_s": "Пауза, p95, с",
    "agent_gap_max_s": "Пауза, макс, с", "agent_slow_pct": "Долгих пауз, %",
    "agent_interruptions": "Перебиваний агентом", "client_gap_median_s": "Пауза клиента, медиана, с",
    "backchannels": "Поддакиваний", "agent_after_silence": "Агент заговорил снова без ответа",
    "agent_talk_pct": "Доля речи агента, %",
}


def analyze_audio(data: bytes, model, agent_channel: str = "left", first_speaker: str = "agent",
                  llm=None, llm_model: str | None = None, slow_s: float = 1.5, merge_gap: float = 1.2,
                  progress=None) -> dict:
    """progress(text) — необязательный колбэк для страницы."""
    say = progress or (lambda _t: None)
    remote = isinstance(model, RemoteWhisper)
    channels, duration = load_audio(data)
    utts, detectors = [], {}
    if len(channels) == 2:
        roles = ("agent", "client") if agent_channel == "left" else ("client", "agent")
        for audio, role in zip(channels, roles):
            audio = normalize(audio)
            intervals, method = detect_speech(audio)
            detectors[role] = method
            say(f"Распознаю канал: {'агент' if role == 'agent' else 'клиент'}"
                f"{' (речь найдена по громкости)' if method == 'energy' else ''}…")
            t0 = time.perf_counter()
            if remote:
                words, _ = model.words_for_intervals(audio, intervals)
            else:
                words, _ = transcribe(model, audio, vad_filter=method == "vad")
            say(f"…готово за {time.perf_counter() - t0:.1f} с, слов: {len(words)}")
            utts += utterances(intervals, words, role, merge_gap)
    else:
        audio = normalize(channels[0])
        intervals, detectors["mono"] = detect_speech(audio, min_silence_ms=250)
        say("Распознаю (моно)…")
        t0 = time.perf_counter()
        if remote:
            words, phrases = model.words_for_intervals(audio, intervals)
        else:
            words, phrases = transcribe(model, audio)
        say(f"…готово за {time.perf_counter() - t0:.1f} с, слов: {len(words)}")
        say("Определяю, кто говорит…")
        roles, quality = acoustic_roles(audio, intervals, first_speaker)
        detectors["separation"] = round(quality, 1)
        if roles and quality >= MIN_SEPARATION:
            detectors["roles"] = "acoustic"
            for role in ("agent", "client"):
                mine = [iv for iv, r in zip(intervals, roles) if r == role]
                inside = [w for w in words if any(s - 0.2 <= (w["start"] + w["end"]) / 2 <= e + 0.2 for s, e in mine)]
                role_utts = utterances(mine, [], role, merge_gap)
                _attach_text(role_utts, inside)
                utts += role_utts
        else:
            labeled, detectors["roles"] = label_roles(phrases, first_speaker, llm, llm_model)
            utts = snap(labeled, intervals)
    turns = build_turns(utts)
    return {"stereo": len(channels) == 2, "duration_s": duration, "turns": turns, "detectors": detectors,
            "metrics": voice_metrics(turns, duration, slow_s)}


def _attach_text(utts: list[dict], words: list[dict]):
    """Текст реплики = слова whisper, чей центр попал в реплику."""
    for u in utts:
        ws = [w for w in words if u["start"] - 0.2 <= (w["start"] + w["end"]) / 2 <= u["end"] + 0.2]
        u["n_words"] = len(ws)
        u["text"] = " ".join(w["text"] for w in ws) or "(неразборчиво)"


def to_history(turns: list[dict]) -> list[dict]:
    """Формат ходов движка (для судьи, эталона, шаблона реплик)."""
    return [{"role": t["role"], "text": t["text"]} for t in turns if not t.get("backchannel")]
