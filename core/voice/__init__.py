"""Анализ аудиозаписей звонков: распознавание, паузы между репликами, метрики."""
from core.voice.analysis import analyze_audio, build_turns, voice_metrics

__all__ = ["analyze_audio", "build_turns", "voice_metrics"]
