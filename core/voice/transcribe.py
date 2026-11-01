"""Распознавание речи faster-whisper (локально, CPU): время каждого слова.
Стерео-запись делится на каналы, каждый распознаётся отдельно; «стерео» с одинаковыми каналами = моно.
"""
import io
from functools import lru_cache

import numpy as np

SR = 16000


@lru_cache(maxsize=2)
def get_model(size: str = "medium", device: str = "cpu", compute_type: str = "int8"):
    """Модель скачивается с Hugging Face при первом вызове и кэшируется (на диске и в памяти)."""
    from faster_whisper import WhisperModel
    return WhisperModel(size, device=device, compute_type=compute_type)


def _decode(data: bytes) -> np.ndarray:
    """Декодирование через PyAV напрямую -> массив (2, n) float32, 16 кГц.
    Своя функция вместо faster_whisper.decode_audio: та передаёт в av.open() параметр metadata_errors,
    которого нет в новых версиях PyAV."""
    import av
    chunks = []
    with av.open(io.BytesIO(data), mode="r") as container:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=SR)
        for frame in container.decode(stream):
            chunks += [f.to_ndarray() for f in resampler.resample(frame)]
        chunks += [f.to_ndarray() for f in resampler.resample(None)]      # остаток буфера
    if not chunks:
        raise ValueError("В файле нет аудиоданных")
    return np.concatenate(chunks, axis=1).astype(np.float32)


def load_audio(data: bytes) -> tuple[list[np.ndarray], float]:
    """Файл (wav/mp3/ogg/m4a) -> ([канал] или [левый, правый], длительность, с). 16 кГц, float32."""
    left, right = _decode(data)
    duration = len(left) / SR
    if np.allclose(left, right, atol=1e-3):          # моно или «стерео» с одинаковыми каналами
        return [(left + right) / 2], duration
    return [left, right], duration


def transcribe(model, audio: np.ndarray, language: str = "ru", vad_filter: bool = True) -> tuple[
        list[dict], list[dict]]:
    """-> (слова [{start, end, text}], фразы [{start, end, text}])."""
    from core.voice.remote_whisper import RemoteWhisper
    if isinstance(model, RemoteWhisper):
        return model.transcribe_array(audio)
    segments, _ = model.transcribe(audio, language=language, word_timestamps=True, vad_filter=vad_filter,
                                   vad_parameters={"threshold": 0.35, "min_silence_duration_ms": 300},
                                   beam_size=5, condition_on_previous_text=False)
    words, phrases = [], []
    for seg in segments:
        phrases.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
        for w in seg.words or []:
            words.append({"start": w.start, "end": w.end, "text": w.word.strip()})
    return words, phrases
