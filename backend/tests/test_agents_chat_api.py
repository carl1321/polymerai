"""Unit tests for DB agent simple chat helper."""

from extensions.agents_db.router import (
    AgentChatRequest,
    _extract_answer_from_channel_values,
    _runtime_context_from_chat_body,
)


def test_extract_answer_plain_string() -> None:
    v = {
        "messages": [
            {"type": "human", "content": "hi"},
            {"type": "ai", "content": "Hello."},
        ]
    }
    assert _extract_answer_from_channel_values(v) == "Hello."


def test_extract_answer_multipart_content() -> None:
    v = {
        "messages": [
            {
                "type": "ai",
                "content": [
                    {"type": "text", "text": "A"},
                    {"type": "text", "text": "B"},
                ],
            }
        ]
    }
    assert _extract_answer_from_channel_values(v) == "AB"


def test_extract_answer_prefers_last_assistant() -> None:
    v = {
        "messages": [
            {"type": "ai", "content": "first"},
            {"type": "ai", "content": "last"},
        ]
    }
    assert _extract_answer_from_channel_values(v) == "last"


def test_runtime_context_pro_mode_matches_ui_semantics() -> None:
    body = AgentChatRequest(
        message="x",
        model_name="doubao-seed-2.0",
        mode="pro",
    )
    ctx = _runtime_context_from_chat_body(body, agent_id="agent-uuid")
    assert ctx["agent_id"] == "agent-uuid"
    assert ctx["model_name"] == "doubao-seed-2.0"
    assert ctx["thinking_enabled"] is True
    assert ctx["is_plan_mode"] is True
    assert ctx["subagent_enabled"] is False
    assert ctx["reasoning_effort"] == "medium"


def test_runtime_context_explicit_overrides_mode() -> None:
    body = AgentChatRequest(
        message="x",
        mode="pro",
        is_plan_mode=False,
        reasoning_effort="low",
    )
    ctx = _runtime_context_from_chat_body(body, agent_id="a")
    assert ctx["is_plan_mode"] is False
    assert ctx["reasoning_effort"] == "low"
