"""Роли для моно-записи (оба голоса на одной дорожке, например запись разговора на телефоне).

Основной способ — по звуку: голос «своего» микрофона и голос из телефонной сети звучат по-разному
(громкость, доля низких и высоких частот). Куски речи между паузами делятся на две группы
(k-means, k=2); группа, которая говорит первой, — first_speaker.
Если группы разделяются плохо — запасной способ: LLM размечает фразы по смыслу; без LLM — по очереди.
"""
import numpy as np

from core.llm import parse_json
from core.voice.transcribe import SR

MIN_SEPARATION = 2.0          # расстояние между центрами групп / разброс внутри групп


def _features(x: np.ndarray) -> list[float]:
    """Громкость, доля низких (<300 Гц) и высоких (>3.6 кГц) частот: «свой» микрофон и голос
    из телефонной сети заметно различаются по этим трём признакам."""
    sp = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    fr = np.fft.rfftfreq(len(x), 1 / SR)
    tot = sp.sum() + 1e-12
    return [20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9),                 # громкость, дБ
            100 * sp[fr < 300].sum() / tot,                                   # доля < 300 Гц, %
            float(np.log10(100 * sp[fr > 3600].sum() / tot + 1e-3))]         # доля > 3.6 кГц, лог


def _kmeans2(X: np.ndarray, iters: int = 50) -> np.ndarray:
    c = X[[int(np.argmin(X[:, 0])), int(np.argmax(X[:, 0]))]].copy()     # старт: самый тихий и самый громкий
    lab = np.zeros(len(X), dtype=int)
    for _ in range(iters):
        lab = np.argmin(((X[:, None, :] - c[None]) ** 2).sum(-1), axis=1)
        new = np.array([X[lab == k].mean(0) if (lab == k).any() else c[k] for k in (0, 1)])
        if np.allclose(new, c):
            break
        c = new
    return lab


def acoustic_roles(audio: np.ndarray, intervals: list[tuple[float, float]],
                   first_speaker: str = "agent") -> tuple[list[str], float]:
    """-> (роль для каждого интервала, качество разделения). Качество < MIN_SEPARATION — не доверять."""
    segs = [audio[int(s * SR):int(e * SR)] for s, e in intervals]
    ok = [i for i, x in enumerate(segs) if len(x) >= int(0.15 * SR)]
    if len(ok) < 4:
        return [], 0.0
    F = np.array([_features(segs[i]) for i in ok])
    Z = (F - F.mean(0)) / (F.std(0) + 1e-9)
    lab = _kmeans2(Z)
    if lab.min() == lab.max():
        return [], 0.0
    c0, c1 = Z[lab == 0].mean(0), Z[lab == 1].mean(0)
    spread = np.sqrt(np.mean([((Z[lab == k] - Z[lab == k].mean(0)) ** 2).sum(1).mean() for k in (0, 1)]))
    quality = float(np.linalg.norm(c0 - c1) / (spread + 1e-9))
    first_cluster = lab[0]                                       # кто говорит первым
    other = "client" if first_speaker == "agent" else "agent"
    role_of = {first_cluster: first_speaker, 1 - first_cluster: other}
    roles = [""] * len(intervals)
    for i, k in zip(ok, lab):
        roles[i] = role_of[int(k)]
    cent = {role_of[k]: F[lab == k].mean(0) for k in (0, 1)}      # короткие куски — к ближайшему центру
    for i, x in enumerate(segs):
        if not roles[i]:
            f = np.array(_features(x)) if len(x) > 32 else None
            roles[i] = (min(cent, key=lambda r: np.linalg.norm((f - cent[r]) / (F.std(0) + 1e-9)))
                        if f is not None else other)
    return roles, quality


# ---------- запасной способ: по смыслу (LLM) или по очереди
ROLES_PROMPT = """Ниже фразы телефонного разговора по порядку. Звонит голосовой агент компании (продавец), отвечает клиент.
Первым, скорее всего, говорит: <<FIRST>>.
<<PHRASES>>
Определи, кто произносит каждую фразу. Верни только JSON: {"roles": ["agent" или "client", ... по одному на фразу]}"""


def label_roles(phrases: list[dict], first_speaker: str = "agent", llm=None,
                model: str | None = None) -> tuple[list[dict], str]:
    """-> (реплики с ролями, способ: "llm" | "alternate")."""
    roles, method = None, "alternate"
    if llm and model and phrases:
        text = "\n".join(f"{i}. {p['text']}" for i, p in enumerate(phrases))
        try:
            r = parse_json(llm.chat(model, [{"role": "system", "content": "Ты отвечаешь только JSON."},
                                            {"role": "user", "content": ROLES_PROMPT
                                             .replace("<<FIRST>>", "агент" if first_speaker == "agent" else "клиент")
                                             .replace("<<PHRASES>>", text)}],
                                    temperature=0, max_tokens=2000, json_mode=True))
            roles = r.get("roles")
            if roles and len(roles) == len(phrases):
                method = "llm"
        except Exception:  # noqa: BLE001
            roles = None
    if method != "llm":
        other = "client" if first_speaker == "agent" else "agent"
        roles = [first_speaker if i % 2 == 0 else other for i in range(len(phrases))]
    return [{"role": r if r in ("agent", "client") else "client", "start": p["start"], "end": p["end"],
             "text": p["text"], "n_words": len(p["text"].split())} for p, r in zip(phrases, roles)], method
