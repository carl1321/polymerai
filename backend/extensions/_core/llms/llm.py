# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Compatibility layer for agentic_workflow tools expecting `src.llms.llm`.

deer-flow uses the harness model factory (deerflow.models.create_chat_model) which
reads models from config.yaml. This adapter lets workflow tools use it without
the full agentic_workflow LLM stack.
"""

import logging

from langchain_core.language_models import BaseChatModel

from deerflow.models import create_chat_model
from extensions._core.config.agents import LLMType

logger = logging.getLogger(__name__)


def get_llm_by_type(llm_type: LLMType) -> BaseChatModel:
    """Return a chat model instance for the given type.

    deer-flow does not distinguish model types in the same way as agentic_workflow.
    We map all types to `create_chat_model()` (first configured model) by default.
    """
    # In future we can support per-type mapping via config if needed.
    return create_chat_model()


def get_llm_by_model_name(model_name: str) -> BaseChatModel:
    """Return a chat model by name (must exist in deer-flow `config.yaml`)."""
    return create_chat_model(name=model_name)


def get_model_supports_thinking(model_name: str) -> bool:
    """Compatibility: return whether a configured model supports thinking."""
    try:
        from deerflow.config import get_app_config

        cfg = get_app_config()
        m = cfg.get_model_config(model_name)
        return bool(m.supports_thinking) if m is not None else False
    except Exception:
        return False
