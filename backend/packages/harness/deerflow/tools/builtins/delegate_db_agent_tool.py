import logging
from uuid import UUID

from langchain.tools import ToolRuntime, tool
from langchain_core.runnables import RunnableConfig
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from extensions._core.agents_db import get_agent as db_get_agent
from extensions._core.agents_db import list_swarm_member_ids
from extensions._core.app_db import get_app_db_connection

logger = logging.getLogger(__name__)


def build_delegate_db_agent_tool(*, swarm_agent_id: str):
    @tool("delegate_agent", parse_docstring=True)
    async def delegate_agent(
        runtime: ToolRuntime[ContextT, ThreadState],
        description: str,
        prompt: str,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> str:
        """Delegate a task to a dedicated child agent.

        Args:
            description: Short description of delegated subtask.
            prompt: Full prompt passed to child agent.
            agent_id: Dedicated agent id that belongs to current swarm.
            agent_name: Optional dedicated member name. If provided, it resolves to a member id.
        """
        if not prompt.strip():
            return "Error: prompt is required"
        if not agent_id and not agent_name:
            return "Error: either agent_id or agent_name is required"

        try:
            swarm_uid = UUID(swarm_agent_id)
        except Exception:
            return f"Error: invalid swarm id '{swarm_agent_id}'"

        child_uid: UUID | None = None
        if agent_id:
            try:
                child_uid = UUID(agent_id)
            except Exception:
                return f"Error: invalid agent id '{agent_id}'"

        conn = get_app_db_connection()
        try:
            allowed = set(list_swarm_member_ids(conn, swarm_uid))
            if child_uid is None and agent_name:
                for member_id in allowed:
                    member = db_get_agent(conn, UUID(member_id), user_id=None, organization_id=None)
                    if member and str(member.get("name") or "").strip() == agent_name.strip():
                        child_uid = UUID(member_id)
                        break
                if child_uid is None:
                    return f"Error: member agent with name '{agent_name}' is not in swarm {swarm_agent_id}"

            if child_uid is None:
                return "Error: unable to resolve delegated member"
            if str(child_uid) not in allowed:
                return f"Error: agent {str(child_uid)} is not a member of swarm {swarm_agent_id}"
            child = db_get_agent(conn, child_uid, user_id=None, organization_id=None)
            if not child:
                return f"Error: member agent {str(child_uid)} not found"
            if str(child.get("kind") or "dedicated").lower() != "dedicated":
                return f"Error: member agent {str(child_uid)} is not dedicated"
        finally:
            conn.close()

        from deerflow.agents.lead_agent.agent import make_lead_agent

        parent_config = runtime.config or {}
        configurable = dict(parent_config.get("configurable", {}) or {})
        context = dict(parent_config.get("context", {}) or {})
        cfg: dict = {
            "configurable": configurable,
            "context": context,
        }
        recursion_limit = parent_config.get("recursion_limit")
        if isinstance(recursion_limit, int):
            cfg["recursion_limit"] = recursion_limit
        metadata = parent_config.get("metadata")
        if isinstance(metadata, dict):
            cfg["metadata"] = dict(metadata)

        parent_thread = context.get("thread_id") or configurable.get("thread_id") or runtime.context.get("thread_id") if runtime.context else None
        child_id_str = str(child_uid)
        child_thread = f"{parent_thread}/delegate/{child_id_str}" if parent_thread else f"delegate/{child_id_str}"
        configurable["thread_id"] = child_thread
        configurable["agent_id"] = child_id_str
        configurable["agent_name"] = None
        context["thread_id"] = child_thread
        context["agent_id"] = child_id_str
        context["agent_name"] = None
        cfg["configurable"] = configurable
        cfg["context"] = context

        child_agent = make_lead_agent(RunnableConfig(**cfg))
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ]
        }
        try:
            result = await child_agent.ainvoke(payload, config=RunnableConfig(**cfg))
        except Exception as exc:
            logger.exception("delegate_agent failed: swarm=%s child=%s", swarm_agent_id, child_id_str)
            return f"Error: delegated run failed for {child_id_str}: {exc}"

        messages = result.get("messages") if isinstance(result, dict) else None
        if isinstance(messages, list) and messages:
            last = messages[-1]
            content = getattr(last, "content", None)
            if isinstance(content, str) and content.strip():
                return f"[{description}] {content.strip()}"
        return f"[{description}] delegated task completed by {child_id_str}"

    return delegate_agent
