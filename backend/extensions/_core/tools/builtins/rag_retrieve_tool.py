"""RAG retrieval tool: query agent-linked knowledge bases via RAGFlow."""

import logging
from typing import Annotated
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg, tool

from extensions._core.agents_db import get_agent as db_get_agent
from extensions._core.app_db import get_app_db_connection
from extensions._core.rag_flow import retrieve as rag_retrieve
from extensions.auth.db import UserDB

logger = logging.getLogger(__name__)


def _api_key_for_configurable(config: RunnableConfig | None) -> str | None:
    if not config:
        return None
    cfg = config.get("configurable") or {}

    # Public agent mode: prefer the creator's ragflow_key so shared agents can
    # consistently retrieve from their bound datasets across different users.
    agent_id_raw = cfg.get("agent_id")
    if agent_id_raw is not None:
        try:
            agent_id = UUID(str(agent_id_raw).strip())
        except (ValueError, TypeError):
            agent_id = None
        if agent_id is not None:
            conn = get_app_db_connection()
            try:
                row = db_get_agent(conn, agent_id, user_id=None, organization_id=None)
            finally:
                conn.close()
            if row and str(row.get("visibility") or "").strip().lower() == "org":
                owner_raw = row.get("user_id")
                if owner_raw:
                    try:
                        owner_id = UUID(str(owner_raw).strip())
                    except (ValueError, TypeError):
                        owner_id = None
                    if owner_id is not None:
                        owner = UserDB.get_by_id(owner_id)
                        if owner:
                            owner_key = (owner.get("ragflow_key") or "").strip()
                            if owner_key:
                                logger.info(
                                    "knowledge_base_search using owner ragflow_key for public agent_id=%s",
                                    agent_id,
                                )
                                return owner_key

    uid = cfg.get("user_id") or cfg.get("deerflow_user_id")
    if uid is None:
        return None
    try:
        user_id = UUID(str(uid).strip())
    except (ValueError, TypeError):
        return None
    row = UserDB.get_by_id(user_id)
    if not row:
        return None
    key = (row.get("ragflow_key") or "").strip()
    return key or None


def make_rag_retrieve_tool(dataset_ids: list[str]):
    """Create a tool that retrieves from the given RAGFlow dataset IDs.

    Used when an agent has knowledge_base_ids; the tool is added to the agent's tools
    so the model can query the knowledge base.
    """
    if not dataset_ids:
        return None

    @tool
    def knowledge_base_search(
        query: str,
        runtime_config: Annotated[RunnableConfig, InjectedToolArg()],
    ) -> str:
        """Search the agent's linked knowledge base(s) for relevant information.

        Use this when you need to look up facts, documentation, or context from
        the knowledge bases associated with this agent. Input should be a clear
        search query or question.
        """
        override = _api_key_for_configurable(runtime_config)
        chunks = rag_retrieve(
            question=query.strip(),
            dataset_ids=dataset_ids,
            top_k=10,
            similarity_threshold=0.2,
            api_key=override,
        )
        if not chunks:
            return "No relevant results found in the knowledge base."
        parts = []
        for i, c in enumerate(chunks, 1):
            content = (c.get("content") or "").strip()
            if content:
                parts.append(f"[{i}] {content}")
        return "\n\n".join(parts) if parts else "No relevant results found in the knowledge base."

    knowledge_base_search.name = "knowledge_base_search"
    return knowledge_base_search
