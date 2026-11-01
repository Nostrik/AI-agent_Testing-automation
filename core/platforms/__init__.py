"""Адаптеры тестируемых агентов. Реестр и сборка — в registry.py."""
from core.platforms.base import AgentAdapter, AgentTurn, ConfigControl
from core.platforms.registry import ADAPTERS, build_adapter

__all__ = ["ADAPTERS", "AgentAdapter", "AgentTurn", "ConfigControl", "build_adapter"]
