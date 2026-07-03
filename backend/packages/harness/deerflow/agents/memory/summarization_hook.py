"""Hooks fired before summarization removes messages from state."""

from __future__ import annotations

from langgraph.config import get_config

from deerflow.agents.memory.enabled import is_memory_enabled_for_agent
from deerflow.agents.memory.message_processing import detect_correction, detect_reinforcement, filter_messages_for_memory
from deerflow.agents.memory.queue import get_memory_queue
from deerflow.agents.middlewares.summarization_middleware import SummarizationEvent
from deerflow.runtime.user_context import resolve_runtime_user_id


def memory_flush_hook(event: SummarizationEvent) -> None:
    """Flush messages about to be summarized into the memory queue."""
    configurable = {}
    try:
        configurable = get_config().get("configurable", {})
    except RuntimeError:
        configurable = {}
    runtime_context = event.runtime.context if event.runtime else {}
    agent_id = runtime_context.get("agent_id") or configurable.get("agent_id")
    agent_name = event.agent_name or runtime_context.get("agent_name") or configurable.get("agent_name")
    if not is_memory_enabled_for_agent(agent_id=agent_id, agent_name=agent_name) or not event.thread_id:
        return
    # Use agent_id as per-agent memory key when available.
    memory_key = agent_id or agent_name
    if not memory_key:
        return

    filtered_messages = filter_messages_for_memory(list(event.messages_to_summarize))
    user_messages = [message for message in filtered_messages if getattr(message, "type", None) == "human"]
    assistant_messages = [message for message in filtered_messages if getattr(message, "type", None) == "ai"]
    if not user_messages or not assistant_messages:
        return

    correction_detected = detect_correction(filtered_messages)
    reinforcement_detected = not correction_detected and detect_reinforcement(filtered_messages)
    user_id = resolve_runtime_user_id(event.runtime)
    queue = get_memory_queue()
    queue.add_nowait(
        thread_id=event.thread_id,
        messages=filtered_messages,
        agent_name=memory_key,
        user_id=user_id,
        correction_detected=correction_detected,
        reinforcement_detected=reinforcement_detected,
    )
