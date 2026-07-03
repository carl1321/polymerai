import logging

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from deerflow.config.agents_config import validate_agent_name
from deerflow.tools.types import Runtime
from extensions._core.agent_request import AgentCreate
from extensions._core.agents_db import create_agent as db_create_agent
from extensions._core.app_db import get_app_db_connection

logger = logging.getLogger(__name__)


@tool(parse_docstring=True)
def setup_agent(
    soul: str,
    description: str,
    runtime: Runtime,
    skills: list[str] | None = None,
) -> Command:
    """Setup a custom DeerFlow agent (DB-backed).

    This is typically invoked from the /workspace/agents/new conversational
    bootstrap flow. It creates a new row in the `agents` table using the
    provided SOUL and description.

    Args:
        soul: Full SOUL.md content defining the agent's personality and behavior.
        description: One-line description of what the agent does.
        skills: Optional list of skill names this agent should use. None means use all enabled skills, empty list means no skills.
    """

    agent_name: str | None = runtime.context.get("agent_name") if runtime.context else None
    if not agent_name:
        logger.error("[agent_creator] agent_name missing from runtime context")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="Error: agent_name missing from context; cannot create agent.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    try:
        agent_name = validate_agent_name(agent_name)
        payload = AgentCreate(
            name=agent_name,
            description=description or None,
            system_prompt=soul or None,
            skill_names=skills,
        )

        conn = get_app_db_connection()
        try:
            agent_id = db_create_agent(
                conn,
                user_id=None,
                organization_id=None,
                department_id=None,
                name=payload.name,
                description=payload.description,
                system_prompt=payload.system_prompt,
                user_prompt_template=payload.user_prompt_template,
                prompt_variables=payload.prompt_variables,
                opener=payload.opener,
                suggested_questions=payload.suggested_questions,
                knowledge_base_ids=payload.knowledge_base_ids,
                skill_names=payload.skill_names,
                tool_names=payload.tool_names,
                workflow_ids=payload.workflow_ids,
                default_workflow_id=None,
                model_name=payload.model_name,
                model_parameters=payload.model_parameters,
                avatar=payload.avatar,
                run_mode=payload.run_mode,
                kind="dedicated",
                requires_plan_confirmation=payload.requires_plan_confirmation,
            )
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:  # pragma: no cover
                pass

        logger.info("[agent_creator] Created agent '%s' with id=%s", agent_name, agent_id)
        return Command(
            update={
                "created_agent_name": agent_name,
                "created_agent_id": str(agent_id),
                "messages": [
                    ToolMessage(
                        content=f"Agent '{agent_name}' created successfully!",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except Exception as e:
        logger.error("[agent_creator] Failed to create agent '%s': %s", agent_name, e, exc_info=True)
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Error creating agent '{agent_name}': {e}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )
