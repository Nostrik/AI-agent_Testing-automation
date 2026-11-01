"""Локальный бэкенд Ollama через нативный /api/chat: think=False для Qwen3 (иначе модель тратит
лимит токенов на скрытые рассуждения и отвечает пустотой), format=json для JSON-режима."""
import requests


def is_ollama(base_url: str) -> bool:
    return ":11434" in (base_url or "")


def ollama_chat(base_url, model, messages, temperature=0.3, max_tokens=800, json_mode=False) -> str:
    root = base_url.rstrip("/").removesuffix("/v1")
    payload = {"model": model, "messages": messages, "stream": False, "think": False,
               "options": {"temperature": temperature, "num_predict": max_tokens}}
    if json_mode:
        payload["format"] = "json"
    r = requests.post(f"{root}/api/chat", json=payload, timeout=300)
    if r.status_code == 400 and "think" in r.text:      # модель без режима рассуждений
        payload.pop("think")
        r = requests.post(f"{root}/api/chat", json=payload, timeout=300)
    r.raise_for_status()
    return r.json()["message"]["content"]
