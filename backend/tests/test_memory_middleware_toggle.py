from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

from deerflow.agents.middlewares.memory_middleware import MemoryMiddleware


def test_memory_middleware_skips_when_agent_memory_disabled(monkeypatch):
    queue_calls: list[dict] = []

    class _Queue:
        def add(self, **kwargs):
            queue_calls.append(kwargs)

    monkeypatch.setattr("deerflow.agents.middlewares.memory_middleware.get_memory_queue", lambda: _Queue())
    monkeypatch.setattr("deerflow.agents.middlewares.memory_middleware.is_memory_enabled_for_agent", lambda **_: False)
    monkeypatch.setattr(
        "deerflow.agents.middlewares.memory_middleware.get_config",
        lambda: {"configurable": {"thread_id": "t-1", "agent_id": "a-1", "agent_name": "agent-a"}},
    )

    middleware = MemoryMiddleware(agent_name="agent-a")
    state = {"messages": [HumanMessage(content="hi"), AIMessage(content="hello")]}
    runtime = SimpleNamespace(context={"thread_id": "t-1"})
    middleware.after_agent(state, runtime)

    assert queue_calls == []


def test_memory_middleware_enqueues_with_agent_id_memory_key(monkeypatch):
    queue_calls: list[dict] = []

    class _Queue:
        def add(self, **kwargs):
            queue_calls.append(kwargs)

    monkeypatch.setattr("deerflow.agents.middlewares.memory_middleware.get_memory_queue", lambda: _Queue())
    monkeypatch.setattr("deerflow.agents.middlewares.memory_middleware.is_memory_enabled_for_agent", lambda **_: True)
    monkeypatch.setattr(
        "deerflow.agents.middlewares.memory_middleware.get_config",
        lambda: {"configurable": {"thread_id": "t-1", "agent_id": "a-1", "agent_name": "agent-a"}},
    )

    middleware = MemoryMiddleware(agent_name=None)
    state = {"messages": [HumanMessage(content="hi"), AIMessage(content="hello")]}
    runtime = SimpleNamespace(context={"thread_id": "t-1"})
    middleware.after_agent(state, runtime)

    assert len(queue_calls) == 1
    assert queue_calls[0]["agent_name"] == "a-1"


def test_memory_middleware_skips_without_agent_key(monkeypatch):
    queue_calls: list[dict] = []

    class _Queue:
        def add(self, **kwargs):
            queue_calls.append(kwargs)

    monkeypatch.setattr("deerflow.agents.middlewares.memory_middleware.get_memory_queue", lambda: _Queue())
    monkeypatch.setattr("deerflow.agents.middlewares.memory_middleware.is_memory_enabled_for_agent", lambda **_: True)
    monkeypatch.setattr(
        "deerflow.agents.middlewares.memory_middleware.get_config",
        lambda: {"configurable": {"thread_id": "t-1"}},
    )

    middleware = MemoryMiddleware(agent_name=None)
    state = {"messages": [HumanMessage(content="hi"), AIMessage(content="hello")]}
    runtime = SimpleNamespace(context={"thread_id": "t-1"})
    middleware.after_agent(state, runtime)

    assert queue_calls == []
