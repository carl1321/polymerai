"""RAG resources API: proxy to RAGFlow for knowledge base list and retrieval.

Used by agent orchestration page and workflow editor to list datasets;
used by agents with knowledge_base_ids to retrieve chunks.
Config: config.yaml ragflow.api_url, ragflow.api_key.
"""

import logging
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from extensions._core.rag_flow import get_ragflow_config as _get_ragflow_config_from_client
from extensions._core.rag_flow import retrieve as rag_retrieve
from extensions._core.ragflow_user_key import ensure_user_ragflow_key
from extensions.auth.db import UserDB
from extensions.auth.dependencies import CurrentUser, get_current_user_optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["rag"])


class RAGResource(BaseModel):
    """Single knowledge base resource (dataset) for frontend."""

    uri: str = Field(..., description="e.g. rag://dataset/{id}")
    title: str = Field(..., description="Display name")
    description: str | None = Field(None, description="Optional description")


class RAGResourcesResponse(BaseModel):
    resources: list[RAGResource] = Field(default_factory=list)


class RAGRetrieveRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Search query")
    dataset_ids: list[str] = Field(..., min_length=1, description="RAGFlow dataset IDs (knowledge base IDs)")
    top_k: int = Field(10, ge=1, le=50, description="Max chunks to return")
    similarity_threshold: float = Field(0.2, ge=0, le=1, description="Min similarity score")


class RAGChunk(BaseModel):
    content: str = Field(..., description="Chunk text")
    similarity: float | None = Field(None, description="Similarity score")
    document_id: str | None = Field(None, description="Source document ID")
    id: str | None = Field(None, description="Chunk ID")


class RAGRetrieveResponse(BaseModel):
    chunks: list[RAGChunk] = Field(default_factory=list)


def _get_ragflow_config() -> dict[str, Any]:
    """Read ragflow section from config (for list resources)."""
    out = _get_ragflow_config_from_client()
    if out:
        logger.info("RAG: using config api_url=%s", out.get("api_url"))
    return out


def _effective_ragflow_api_key(current_user: CurrentUser) -> str:
    row = UserDB.get_by_id(current_user.id)
    if row:
        uk = (row.get("ragflow_key") or "").strip()
        if uk:
            return uk
        # Keep behavior consistent with login/me: lazily init key if empty.
        ensure_user_ragflow_key(dict(row), current_user.username)
        row2 = UserDB.get_by_id(current_user.id)
        if row2:
            uk2 = (row2.get("ragflow_key") or "").strip()
            if uk2:
                return uk2
    base = _get_ragflow_config()
    return (base.get("api_key") or "").strip()


def _require_user(user: CurrentUser | None) -> CurrentUser:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@router.get(
    "/rag/resources",
    response_model=RAGResourcesResponse,
    summary="List RAG resources (knowledge bases)",
    description="List datasets from RAGFlow (or configured RAG provider) for agent/workflow knowledge base selection.",
)
async def list_rag_resources(
    query: str = Query("", description="Optional filter by name"),
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> RAGResourcesResponse:
    """List knowledge base resources. Requires authentication."""
    user = _require_user(current_user)
    ragflow = _get_ragflow_config()
    api_url = (ragflow.get("api_url") or "").rstrip("/")
    api_key = _effective_ragflow_api_key(user)
    if not api_url or not api_key:
        logger.info("RAG resources skipped: ragflow.api_url or api_key not configured")
        return RAGResourcesResponse(resources=[])
    try:
        params: dict[str, str] = {}
        if query and query.strip():
            params["name"] = query.strip()
        url = f"{api_url}/api/v1/datasets"
        resp = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            params=params or None,
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning("RAGFlow list datasets failed: url=%s status=%s body=%s", url, resp.status_code, resp.text[:300])
            return RAGResourcesResponse(resources=[])
        data = resp.json()
        # RAGFlow returns { "code": 0, "data": [ ... ] }; only use data when code is 0
        code = data.get("code") if isinstance(data, dict) else None
        if code is not None and code != 0:
            logger.warning("RAGFlow returned code=%s message=%s", code, data.get("message", "")[:200])
            return RAGResourcesResponse(resources=[])
        raw_list = data.get("data") if isinstance(data, dict) else None
        if not isinstance(raw_list, list):
            logger.info("RAG: RAGFlow response has no list 'data', keys=%s", list(data.keys()) if isinstance(data, dict) else "not-dict")
            raw_list = []
        resources = []
        for item in raw_list:
            raw_id = item.get("id")
            ds_id = str(raw_id).strip() if raw_id is not None else ""
            if not ds_id:
                continue
            resources.append(
                RAGResource(
                    uri=f"rag://dataset/{ds_id}",
                    title=item.get("name") or ds_id,
                    description=item.get("description"),
                )
            )
        logger.info("RAG: loaded %d knowledge base(s) from RAGFlow", len(resources))
        return RAGResourcesResponse(resources=resources)
    except Exception as e:
        logger.exception("RAG resources request failed: %s", e)
        return RAGResourcesResponse(resources=[])


@router.post(
    "/rag/retrieve",
    response_model=RAGRetrieveResponse,
    summary="Retrieve chunks from knowledge bases",
    description="Query RAGFlow retrieval API with a question and dataset IDs. Used by agents with linked knowledge bases.",
)
async def retrieve_rag(
    body: RAGRetrieveRequest,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> RAGRetrieveResponse:
    """Retrieve relevant chunks from configured RAGFlow datasets. Requires authentication."""
    user = _require_user(current_user)
    user_key = (UserDB.get_by_id(user.id) or {}).get("ragflow_key") or ""
    user_key = user_key.strip() if isinstance(user_key, str) else ""
    raw = rag_retrieve(
        question=body.question,
        dataset_ids=body.dataset_ids,
        top_k=body.top_k,
        similarity_threshold=body.similarity_threshold,
        api_key=user_key or None,
    )
    chunks = [
        RAGChunk(
            content=c.get("content") or "",
            similarity=c.get("similarity"),
            document_id=c.get("document_id"),
            id=c.get("id"),
        )
        for c in raw
    ]
    return RAGRetrieveResponse(chunks=chunks)
