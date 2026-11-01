"""Удалённое распознавание через Whisper-WebUI (Gradio API, эндпоинт /transcribe_file).

Канал режется на куски по разметке речи (VAD), все куски уходят отдельными файлами в ОДНОМ запросе;
текст каждого куска кладётся ровно в свой интервал. Так тексты разных реплик не склеиваются через паузу,
а модель на сервере загружается один раз на запрос.
"""
import os
import re
import shutil
import tempfile
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np

from core.voice.transcribe import SR

TIME_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")
HALLUCINATIONS = re.compile(r"продолжение следует|субтитр|спасибо за просмотр|подписывайтесь|редактор", re.I)
HOTWORDS = "дизель, бензин, топливо, поставщик, закуплено, закупаем, тонн, доставка, нефтебаза, Кузбасс нефте транс, КНТ"


@lru_cache(maxsize=4)
def _client(url: str):
    from gradio_client import Client
    return Client(url, verbose=False)


def _write_wav(path: str, audio: np.ndarray):
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def _sec(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(text: str) -> list[dict]:
    phrases = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            m = TIME_RE.search(line)
            if m:
                body = " ".join(lines[i + 1:]).strip()
                if body:
                    g = m.groups()
                    phrases.append({"start": _sec(*g[:4]), "end": _sec(*g[4:]), "text": body})
                break
    return phrases


def phrases_to_words(phrases: list[dict]) -> list[dict]:
    """Слова фразы распределяются по её длительности пропорционально числу букв."""
    words = []
    for p in phrases:
        toks = p["text"].split()
        total = sum(len(t) for t in toks) or 1
        t, dur = p["start"], max(p["end"] - p["start"], 0.01)
        for tok in toks:
            d = dur * len(tok) / total
            words.append({"start": t, "end": t + d, "text": tok})
            t += d
    return words


class RemoteWhisper:
    def __init__(self, url: str, model: str = "medium", compute_type: str = "float32",
                 device: str = "cuda", language: str = "russian", hotwords: str = HOTWORDS):
        self.url, self.model, self.compute_type = url.rstrip("/") + "/", model, compute_type
        self.device, self.language, self.hotwords = device, language, hotwords

    def check(self) -> None:
        _client(self.url)                                    # бросит исключение, если сервер недоступен

    def _predict(self, paths: list[str]):
        from gradio_client import handle_file
        return _client(self.url).predict(
            files=[handle_file(p) for p in paths], input_folder_path="", include_subdirectory=False,
            save_same_dir=False, file_format="SRT", add_timestamp=False,
            progress=self.model, param_7=self.language, param_8=False,
            param_9=5, param_10=-1, param_11=0.6, param_12=self.compute_type, param_13=5, param_14=1,
            param_15=False,                                   # condition_on_previous_text: выкл, меньше галлюцинаций
            param_16=0.5, param_17="", param_18=0, param_19=2.4, param_20=1, param_21=1, param_22=0,
            param_23="", param_24=True, param_25="[-1]", param_26=1, param_27=False,
            param_28="\"'“¿([{-", param_29="\"'.。,，!！?？:：”)]}、",
            param_30=None, param_31=30, param_32=None, param_33=self.hotwords, param_34=0.5, param_35=1,
            param_36=24, param_37=False,                      # не выгружать модель после запроса
            param_38=False, param_39=0.5, param_40=250, param_41=9999, param_42=1000, param_43=2000,
            param_44=False, param_45=self.device, param_46="", param_47=True,
            param_48=False, param_49="UVR-MDX-NET-Inst_HQ_4", param_50=self.device, param_51=256,
            param_52=False, param_53=True,
            api_name="/transcribe_file")

    def transcribe_chunks(self, chunks: list[np.ndarray]) -> list[str]:
        """Каждый кусок — отдельный файл chunk_NNNN.wav; ответ сопоставляется по номеру в имени файла."""
        if not chunks:
            return []
        tmp = tempfile.mkdtemp(prefix="whisper_")
        paths = []
        for i, x in enumerate(chunks):
            p = os.path.join(tmp, f"chunk_{i:04d}.wav")
            _write_wav(p, x)
            paths.append(p)
        try:
            res = self._predict(paths)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        files = res[1] if isinstance(res, (list, tuple)) and len(res) > 1 else None
        if not files:
            raise RuntimeError(f"Whisper-WebUI не вернул файлы субтитров: {str(res)[:300]}")
        if isinstance(files, str):
            files = [files]
        texts = [""] * len(chunks)
        for f in files:
            m = re.search(r"chunk_(\d{4})", Path(f).name)
            if not m or int(m.group(1)) >= len(texts):
                continue
            with open(f, encoding="utf-8") as fh:
                t = " ".join(p["text"] for p in parse_srt(fh.read())).strip()
            texts[int(m.group(1))] = "" if HALLUCINATIONS.search(t) else t
        return texts

    def words_for_intervals(self, audio: np.ndarray, intervals: list[tuple[float, float]],
                            pad: float = 0.25) -> tuple[list[dict], list[dict]]:
        """-> (слова, фразы); фраза = интервал речи с его текстом, слова лежат строго внутри интервала."""
        chunks = [audio[max(0, int((s - pad) * SR)):int((e + pad) * SR)] for s, e in intervals]
        texts = self.transcribe_chunks(chunks)
        phrases = [{"start": s, "end": e, "text": t} for (s, e), t in zip(intervals, texts) if t]
        return phrases_to_words(phrases), phrases

    def transcribe_array(self, audio: np.ndarray) -> tuple[list[dict], list[dict]]:
        """Запасной вариант: весь канал одним куском."""
        return self.words_for_intervals(audio, [(0.0, len(audio) / SR)], pad=0)
