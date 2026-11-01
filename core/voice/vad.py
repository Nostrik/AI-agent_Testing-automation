"""Границы речи. Время реплик берётся из детектора речи (Silero VAD, входит в faster-whisper),
текст — из слов whisper, попавших в интервал. Так тихий канал не «пропадает», даже если whisper
его не распознал: реплика будет «(неразборчиво)», но пауза посчитается.
"""
import numpy as np

from core.voice.transcribe import SR


def normalize(audio: np.ndarray, target_peak: float = 0.5, max_gain: float = 30.0) -> np.ndarray:
    """Выравнивание громкости канала: в записях TWIN клиент бывает в 10+ раз тише агента."""
    ref = float(np.percentile(np.abs(audio), 99.9)) if audio.size else 0.0
    if ref <= 1e-6:
        return audio
    return (audio * min(target_peak / ref, max_gain)).astype(np.float32)


def speech_intervals(audio: np.ndarray, threshold: float = 0.35, min_silence_ms: int = 300) -> list[tuple[float, float]]:
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    ts = get_speech_timestamps(audio, VadOptions(threshold=threshold, min_silence_duration_ms=min_silence_ms,
                                                 speech_pad_ms=0))
    return [(t["start"] / SR, t["end"] / SR) for t in ts]


def energy_intervals(audio: np.ndarray, frame_s: float = 0.02, min_len: float = 0.3,
                     bridge_s: float = 0.3) -> list[tuple[float, float]]:
    """Запасной детектор по громкости: порог = 4× «тишина» (20-й перцентиль), не ниже 2% от пика."""
    n = int(SR * frame_s)
    k = len(audio) // n
    if not k:
        return []
    rms = np.sqrt((audio[: k * n].reshape(k, n) ** 2).mean(1))
    thr = max(float(np.percentile(rms, 20)) * 4, float(rms.max()) * 0.02, 1e-4)
    spans, start = [], None
    for i, active in enumerate(np.append(rms > thr, False)):
        if active and start is None:
            start = i
        elif not active and start is not None:
            spans.append((start * frame_s, i * frame_s))
            start = None
    return [(a, b) for a, b in _merge(spans, bridge_s) if b - a >= min_len]


def detect_speech(audio: np.ndarray, threshold: float = 0.35,
                  min_silence_ms: int = 300) -> tuple[list[tuple[float, float]], str]:
    """Silero VAD; если он нашёл заметно меньше речи, чем есть громких участков
    (бывает на «пережатом» канале клиента), — берём детектор по громкости."""
    vad = speech_intervals(audio, threshold, min_silence_ms)
    energy = energy_intervals(audio)
    dur = lambda xs: sum(e - s for s, e in xs)  # noqa: E731
    if dur(energy) > 1.0 and dur(vad) < 0.5 * dur(energy):
        return energy, "energy"
    return vad, "vad"


def _merge(spans: list[tuple[float, float]], max_gap: float) -> list[list[float]]:
    out = []
    for s, e in sorted(spans):
        if out and s - out[-1][1] < max_gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def utterances(intervals: list[tuple[float, float]], words: list[dict], role: str,
               max_gap: float = 1.2, min_len: float = 0.08) -> list[dict]:
    """Интервалы речи (VAD) ∪ слова whisper -> реплики роли; текст — слова внутри интервала."""
    spans = list(intervals) + [(w["start"], w["end"]) for w in words]
    utts = []
    for s, e in _merge(spans, max_gap):
        if e - s < min_len:
            continue
        ws = [w for w in words if s - 0.2 <= (w["start"] + w["end"]) / 2 <= e + 0.2]
        utts.append({"role": role, "start": s, "end": e, "n_words": len(ws),
                     "text": " ".join(w["text"] for w in ws) or "(неразборчиво)"})
    return utts


# --- для моно: фразы whisper с ролями, границы подтягиваются к VAD
def snap(utts: list[dict], intervals: list[tuple[float, float]], tol: float = 0.5) -> list[dict]:
    for u in utts:
        near = [(s, e) for s, e in intervals if e >= u["start"] - tol and s <= u["end"] + tol]
        if near:
            u["start"] = max(min(s for s, _ in near), u["start"] - tol)
            u["end"] = min(max(e for _, e in near), u["end"] + tol)
    return utts
