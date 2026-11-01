"""TWIN: разбор событий Centrifugo и сборка хода агента без сети."""
import base64
import json
import queue
import re

import pytest

from core.platforms.twin.agent_chat import DEFAULT_NUDGES, TwinAgentAdapter, decode_pub, short_error

SID = "dlg-1"


def push(answer=None, status=None, dialog=SID, error=None, event="BotAnswerSent"):
    data = {"dialogId": dialog, "answer": answer}
    if status:
        data["status"] = status
    if error:
        data["error"] = error
    raw = base64.b64encode(json.dumps({"event": event, "data": data}).encode()).decode()
    return {"push": {"pub": {"data": raw}}}


def tool(name, args=""):
    return {"type": "TOOL_CALL", "tool": {"funcName": name, "funcArgs": args}}


def adapter(*events, quiet=0.05):
    a = TwinAgentAdapter.__new__(TwinAgentAdapter)       # без __init__: ни сети, ни авторизации
    a.sid, a.ended, a.end_reason, a.first_word_s = SID, False, None, None
    a.quiet, a.turn_timeout = quiet, 2
    a.nudge_re = re.compile(DEFAULT_NUDGES, re.I)
    a.tools_all, a.nudges_all = [], []
    a.q = queue.Queue()
    for e in events:
        a.q.put(e)
    return a


def test_decode_pub():
    raw = base64.b64encode(json.dumps({"a": 1}).encode()).decode()
    assert decode_pub(raw) == {"a": 1}
    assert decode_pub({"b": 2}) == {"b": 2}
    assert decode_pub("не base64 !!!") is None


def test_short_error_keeps_status_and_message():
    err = 'HTTP/1.1 404 Not Found Content-Type: application/json {"error": {"message": "gemma-4-31b is archived"}}'
    assert short_error(err) == "404 Not Found — gemma-4-31b is archived"
    assert short_error({"message": "context deadline exceeded"}) == "context deadline exceeded"


def test_text_parts_joined():
    a = adapter(push("Добрый день!"), push("Удобно говорить?"))
    turn = a._collect(__import__("time").time())
    assert turn["text"] == "Добрый день! Удобно говорить?"
    assert turn["latency_s"] is not None and not a.ended


def test_end_conversation_with_reason():
    a = adapter(push("Всего доброго!"), push(tool("set_stage_no_need")),
                push(tool("END_CONVERSATION", '{"reason": "отказ"}')), push(status="STOP"))
    turn = a._collect(__import__("time").time())
    assert [t["name"] for t in turn["tools"]] == ["set_stage_no_need", "END_CONVERSATION"]
    assert a.ended and a.end_reason == "отказ"


def test_nudge_separated_from_text():
    a = adapter(push("Говорите, вас не слышно"), push("Алло?"))
    turn = a._collect(__import__("time").time())
    assert turn["nudges"] == ["Говорите, вас не слышно"]
    assert turn["text"] == "Алло?"


def test_other_dialogs_and_events_ignored():
    a = adapter(push("чужой", dialog="other"), push("служебное", event="Other"), {"id": 5}, push("свой"))
    assert a._collect(__import__("time").time())["text"] == "свой"


def test_platform_error_raises():
    a = adapter(push(error='HTTP/1.1 400 Bad Request X-Id: 1 {"message": "boom"}'))
    with pytest.raises(RuntimeError, match="boom"):
        a._collect(__import__("time").time())
