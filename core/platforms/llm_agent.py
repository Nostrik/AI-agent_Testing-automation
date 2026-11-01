"""Совместимость со старым импортом: LLM-агент теперь живёт в openai_compat.py."""
from core.platforms.openai_compat import END_MARK, OpenAICompatAdapter as LLMAgentAdapter

__all__ = ["END_MARK", "LLMAgentAdapter"]
