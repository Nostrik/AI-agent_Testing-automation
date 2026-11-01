"""Клиенты (кто говорит за клиента): A — скрипт, B — помощник по скрипту, свободный LLM-клиент."""
from core.clients.base import BYE, END_ANY, HANGUP, ClientDriver, dialog_text
from core.clients.guided import GuidedClient
from core.clients.scripted import ScriptedClient
from core.clients.simulated import SimulatedClient


def make_client(mode, scenario, llm, settings):
    if mode == "scripted":
        return ScriptedClient(scenario.get("script"))
    if mode == "guided":
        return GuidedClient(scenario.get("script"), llm, settings["client_model"])
    if mode == "simulated":
        return SimulatedClient(scenario, llm, settings["client_model"])
    raise ValueError(f"Неизвестный режим клиента: {mode}")


__all__ = ["BYE", "END_ANY", "HANGUP", "ClientDriver", "GuidedClient", "ScriptedClient", "SimulatedClient",
           "dialog_text", "make_client"]
