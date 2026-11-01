"""Анализ аудио без моделей: разбор SRT от Whisper-WebUI, ходы, паузы, перебивания."""
import pytest

from core.voice.analysis import build_turns, voice_metrics
from core.voice.remote_whisper import parse_srt, phrases_to_words

SRT = """1
00:00:01,000 --> 00:00:02,500
Добрый день!

2
00:00:03,000 --> 00:00:04,000
Алло

3
00:00:05,000 --> 00:00:05,500
"""


def test_parse_srt_skips_empty_blocks():
    assert parse_srt(SRT) == [{"start": 1.0, "end": 2.5, "text": "Добрый день!"},
                              {"start": 3.0, "end": 4.0, "text": "Алло"}]


def test_phrases_to_words_split_by_letters():
    words = phrases_to_words([{"start": 0.0, "end": 1.0, "text": "аа аааааа"}])
    assert [w["text"] for w in words] == ["аа", "аааааа"]
    assert words[0]["end"] == pytest.approx(0.25) and words[1]["end"] == pytest.approx(1.0)


def u(role, start, end, text, n_words=None):
    return {"role": role, "start": start, "end": end, "text": text, "n_words": n_words or len(text.split())}


def test_build_turns_merge_backchannel_and_gaps():
    utts = [u("agent", 0.0, 3.0, "Добрый день, закупаете топливо?"),
            u("client", 4.0, 5.0, "Да, дизель"),
            u("agent", 7.5, 12.0, "Подскажите, какой объём нужен в месяц?"),
            u("client", 9.0, 9.4, "ага"),                              # поддакивание внутри реплики агента
            u("agent", 12.5, 13.0, "Примерно"),                         # склеится: пауза 0,5 с
            u("client", 12.8, 15.0, "Тонн двадцать")]                    # перебивание
    turns = build_turns(utts)
    main = [t for t in turns if not t.get("backchannel")]
    assert [t["role"] for t in main] == ["agent", "client", "agent", "client"]
    assert main[2]["text"].endswith("Примерно") and main[2]["gap_s"] == 2.5
    assert main[3]["gap_s"] == -0.2
    assert [t["text"] for t in turns if t.get("backchannel")] == ["ага"]

    m = voice_metrics(turns, duration=15.0, slow_s=1.5)
    assert m["agent_turns"] == 2 and m["agent_gap_median_s"] == 2.5 and m["agent_slow_pct"] == 100
    assert m["backchannels"] == 1 and m["agent_interruptions"] == 0
    assert m["client_gap_median_s"] == 1.0


def test_agent_after_silence_is_new_turn():
    turns = build_turns([u("agent", 0, 2, "Алло?"), u("agent", 6, 8, "Вы меня слышите?")])
    assert len(turns) == 2 and turns[1]["after"] == "agent"
    assert voice_metrics(turns, 8)["agent_after_silence"] == 1
