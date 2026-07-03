from __future__ import annotations

import asyncio
from types import SimpleNamespace

from deerflow.agents.lead_agent import agent as lead_agent_module
from deerflow.config.app_config import AppConfig
from deerflow.config.model_config import ModelConfig
from deerflow.config.sandbox_config import SandboxConfig
from deerflow.tools.builtins.delegate_db_agent_tool import build_delegate_db_agent_tool


def _make_app_config() -> AppConfig:
    return AppConfig(
        models=[
            ModelConfig(
                name="default-model",
                display_name="default-model",
                description=None,
                use="langchain_openai:ChatOpenAI",
                model="default-model",
                supports_thinking=True,
                supports_vision=False,
            )
        ],
        sandbox=SandboxConfig(use="deerflow.sandbox.local:LocalSandboxProvider"),
    )


def test_make_lead_agent_forces_plan_mode_for_swarm_by_default(monkeypatch):
    import deerflow.tools as tools_module
    import deerflow.tools.builtins as builtins_tools_module

    app_config = _make_app_config()
    captured: dict[str, object] = {}

    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: app_config)
    monkeypatch.setattr(lead_agent_module, "create_chat_model", lambda **kwargs: object())
    monkeypatch.setattr(lead_agent_module, "create_agent", lambda **kwargs: kwargs)
    monkeypatch.setattr(lead_agent_module, "make_rag_retrieve_tool", lambda kb_ids: None)
    monkeypatch.setattr(tools_module, "get_available_tools", lambda **kwargs: [])
    monkeypatch.setattr(builtins_tools_module, "build_delegate_db_agent_tool", lambda **kwargs: SimpleNamespace(name="delegate_agent"))

    def _fake_build_middlewares(config, model_name, agent_name=None, custom_middlewares=None):
        captured["middleware_config"] = config
        return []

    monkeypatch.setattr(lead_agent_module, "_build_middlewares", _fake_build_middlewares)
    monkeypatch.setattr(
        lead_agent_module,
        "_resolve_agent_from_context",
        lambda cfg: (
            "swarm-a",
            None,
            [],
            "base prompt",
            None,
            "swarm",
            ["11111111-1111-1111-1111-111111111111"],
            [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "name": "member-a",
                    "description": "member desc",
                }
            ],
        ),
    )
    def _fake_apply_prompt_template(**kwargs):
        captured["prompt_kwargs"] = kwargs
        return "PROMPT"

    monkeypatch.setattr(lead_agent_module, "apply_prompt_template", _fake_apply_prompt_template)

    result = lead_agent_module.make_lead_agent(
        {
            "configurable": {
                "agent_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "is_plan_mode": False,
            }
        }
    )

    assert captured["middleware_config"]["metadata"]["is_plan_mode"] is True
    middleware_cfg = captured["middleware_config"]["configurable"]
    assert middleware_cfg["is_plan_mode"] is True
    merged_prompt = captured["prompt_kwargs"]["db_system_prompt"]
    assert "member-a" in merged_prompt
    assert "write_todos" in merged_prompt


def test_make_lead_agent_respects_swarm_force_plan_mode_override(monkeypatch):
    import deerflow.tools as tools_module
    import deerflow.tools.builtins as builtins_tools_module

    app_config = _make_app_config()
    captured: dict[str, object] = {}

    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: app_config)
    monkeypatch.setattr(lead_agent_module, "create_chat_model", lambda **kwargs: object())
    monkeypatch.setattr(lead_agent_module, "create_agent", lambda **kwargs: kwargs)
    monkeypatch.setattr(lead_agent_module, "make_rag_retrieve_tool", lambda kb_ids: None)
    monkeypatch.setattr(tools_module, "get_available_tools", lambda **kwargs: [])
    monkeypatch.setattr(builtins_tools_module, "build_delegate_db_agent_tool", lambda **kwargs: SimpleNamespace(name="delegate_agent"))
    def _fake_build_middlewares(config, model_name, agent_name=None, custom_middlewares=None):
        captured["middleware_config"] = config
        return []

    monkeypatch.setattr(lead_agent_module, "_build_middlewares", _fake_build_middlewares)
    monkeypatch.setattr(
        lead_agent_module,
        "_resolve_agent_from_context",
        lambda cfg: ("swarm-a", None, [], None, None, "swarm", [], []),
    )
    monkeypatch.setattr(lead_agent_module, "apply_prompt_template", lambda **kwargs: "PROMPT")

    result = lead_agent_module.make_lead_agent(
        {
            "configurable": {
                "agent_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "is_plan_mode": False,
                "swarm_force_plan_mode": False,
            }
        }
    )

    assert captured["middleware_config"]["metadata"]["is_plan_mode"] is False
    middleware_cfg = captured["middleware_config"]["configurable"]
    assert middleware_cfg["is_plan_mode"] is False


def test_delegate_agent_resolves_member_by_name(monkeypatch):
    swarm_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    member_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    class _FakeConn:
        def close(self):
            return None

    monkeypatch.setattr("deerflow.tools.builtins.delegate_db_agent_tool.get_app_db_connection", lambda: _FakeConn())
    monkeypatch.setattr("deerflow.tools.builtins.delegate_db_agent_tool.list_swarm_member_ids", lambda conn, swarm_uid: [member_id])
    monkeypatch.setattr(
        "deerflow.tools.builtins.delegate_db_agent_tool.db_get_agent",
        lambda conn, uid, user_id=None, organization_id=None: {
            "id": str(uid),
            "name": "制度查询",
            "kind": "dedicated",
        },
    )

    class _FakeChildAgent:
        async def ainvoke(self, payload, config=None):
            return {"messages": [SimpleNamespace(content="ok from child")]}

    monkeypatch.setattr("deerflow.agents.lead_agent.agent.make_lead_agent", lambda cfg: _FakeChildAgent())

    runtime = SimpleNamespace(
        config={"configurable": {"thread_id": "thread-1"}, "context": {"thread_id": "thread-1"}},
        context={"thread_id": "thread-1"},
        state={},
    )

    delegate_tool = build_delegate_db_agent_tool(swarm_agent_id=swarm_id)

    result = asyncio.run(
        delegate_tool.coroutine(
            runtime=runtime,
            agent_id=None,
            agent_name="制度查询",
            description="查询制度",
            prompt="请查询制度条款",
        )
    )

    assert "ok from child" in result


def test_delegate_agent_does_not_deepcopy_runtime_config(monkeypatch):
    swarm_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    member_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    class _FakeConn:
        def close(self):
            return None

    monkeypatch.setattr("deerflow.tools.builtins.delegate_db_agent_tool.get_app_db_connection", lambda: _FakeConn())
    monkeypatch.setattr("deerflow.tools.builtins.delegate_db_agent_tool.list_swarm_member_ids", lambda conn, swarm_uid: [member_id])
    monkeypatch.setattr(
        "deerflow.tools.builtins.delegate_db_agent_tool.db_get_agent",
        lambda conn, uid, user_id=None, organization_id=None: {
            "id": str(uid),
            "name": "制度查询",
            "kind": "dedicated",
        },
    )

    captured: dict[str, object] = {}

    class _FakeChildAgent:
        async def ainvoke(self, payload, config=None):
            return {"messages": [SimpleNamespace(content="ok from child")]}

    def _fake_make_lead_agent(cfg):
        captured["cfg"] = cfg
        return _FakeChildAgent()

    monkeypatch.setattr("deerflow.agents.lead_agent.agent.make_lead_agent", _fake_make_lead_agent)

    class _NonCopyable:
        def __deepcopy__(self, memo):
            raise TypeError("should not deepcopy")

    runtime = SimpleNamespace(
        config={
            "configurable": {"thread_id": "thread-1"},
            "context": {"thread_id": "thread-1"},
            "metadata": {"trace_id": "trace-1"},
            "danger": _NonCopyable(),
        },
        context={"thread_id": "thread-1"},
        state={},
    )

    delegate_tool = build_delegate_db_agent_tool(swarm_agent_id=swarm_id)

    result = asyncio.run(
        delegate_tool.coroutine(
            runtime=runtime,
            agent_id=member_id,
            description="查询制度",
            prompt="请查询制度条款",
        )
    )

    assert "ok from child" in result
    child_cfg = captured["cfg"]
    assert child_cfg["context"]["thread_id"].startswith("thread-1/delegate/")
