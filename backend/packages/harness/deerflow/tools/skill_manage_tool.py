"""Tool for creating and evolving custom skills."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from weakref import WeakValueDictionary

import yaml
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.typing import ContextT

from deerflow.agents.lead_agent.prompt import refresh_skills_system_prompt_cache_async
from deerflow.skills.security_scanner import scan_skill_content
from deerflow.skills.storage import get_or_new_skill_storage
from deerflow.skills.storage.skill_storage import SkillStorage
from deerflow.skills.types import SKILL_MD_FILE
from deerflow.tools.sync import make_sync_tool_wrapper
from deerflow.tools.types import Runtime
from extensions._core.app_db import get_app_db_connection
from extensions._core.llms.llm import get_llm_by_type
from extensions._core.skills_db import create_skill_metadata, init_skills_tables

logger = logging.getLogger(__name__)

_skill_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def _get_lock(name: str) -> asyncio.Lock:
    lock = _skill_locks.get(name)
    if lock is None:
        lock = asyncio.Lock()
        _skill_locks[name] = lock
    return lock


def _get_thread_id(runtime: Runtime | None) -> str | None:
    if runtime is None:
        return None
    if runtime.context and runtime.context.get("thread_id"):
        return runtime.context.get("thread_id")
    return runtime.config.get("configurable", {}).get("thread_id")


def _get_runtime_user_id(runtime: ToolRuntime[ContextT, ThreadState] | None) -> str | None:
    if runtime is None:
        return None
    if runtime.context and runtime.context.get("user_id"):
        return str(runtime.context.get("user_id"))
    cfg = runtime.config.get("configurable", {})
    uid = cfg.get("user_id") if isinstance(cfg, dict) else None
    return str(uid) if uid else None


def _extract_description_from_skill_md(content: str) -> str:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return ""
    try:
        metadata = yaml.safe_load(match.group(1))
    except Exception:
        return ""
    if not isinstance(metadata, dict):
        return ""
    desc = metadata.get("description")
    return desc.strip() if isinstance(desc, str) else ""


def _translate_skill_label(name: str, content: str) -> tuple[str, str]:
    prompt = '你是技能信息翻译助手。请根据给定的 SKILL.md 内容，输出中文技能名称和中文简介。返回严格 JSON，格式：{"laber_name":"...","laber_description":"..."}。laber_name 不超过 20 字，laber_description 不超过 120 字。不要输出其他内容。'
    body = (content or "").strip()
    if len(body) > 6000:
        body = body[:6000]
    try:
        llm = get_llm_by_type("basic")
        resp = llm.invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=f"skill_name: {name}\n\nSKILL.md:\n{body}"),
            ]
        )
        text = getattr(resp, "content", "")
        if isinstance(text, list):
            text = "\n".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in text)
        data = json.loads(str(text).strip())
        if isinstance(data, dict):
            laber_name = str(data.get("laber_name") or "").strip()
            laber_description = str(data.get("laber_description") or "").strip()
            if laber_name or laber_description:
                return (laber_name or name, laber_description or "")
    except Exception as e:
        logger.warning("Translate skill label failed for '%s': %s", name, e)
    return (name, "")


def _upsert_skill_metadata_from_chat(*, name: str, content: str, user_id: str | None) -> None:
    if not user_id:
        logger.warning("Skip skill metadata upsert for '%s': missing runtime user_id", name)
        return
    conn = get_app_db_connection()
    try:
        init_skills_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM toolbox_skills
                WHERE name = %s AND user_id = %s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (name, user_id),
            )
            row = cur.fetchone()
            description = _extract_description_from_skill_md(content)
            laber_name, laber_description = _translate_skill_label(name, content)
            skill_dir = str(get_custom_skill_dir(name))
            if row:
                cur.execute(
                    """
                    UPDATE toolbox_skills
                    SET description = %s,
                        laber_name = %s,
                        laber_description = %s,
                        skill_dir = %s,
                        enabled = TRUE,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (description, laber_name, laber_description, skill_dir, row["id"]),
                )
                conn.commit()
                return
        create_skill_metadata(
            conn,
            name=name,
            description=description,
            laber_name=laber_name,
            laber_description=laber_description,
            visibility="user",
            user_id=user_id,
            organization_id=None,
            group_name=None,
            skill_dir=skill_dir,
            enabled=True,
        )
    finally:
        conn.close()


def _delete_skill_metadata_from_chat(*, name: str, user_id: str | None) -> None:
    if not user_id:
        return
    conn = get_app_db_connection()
    try:
        init_skills_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM toolbox_skills WHERE name = %s AND user_id = %s",
                (name, user_id),
            )
        conn.commit()
    finally:
        conn.close()


def _history_record(*, action: str, file_path: str, prev_content: str | None, new_content: str | None, thread_id: str | None, scanner: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": action,
        "author": "agent",
        "thread_id": thread_id,
        "file_path": file_path,
        "prev_content": prev_content,
        "new_content": new_content,
        "scanner": scanner,
    }


async def _scan_or_raise(content: str, *, executable: bool, location: str) -> dict[str, str]:
    result = await scan_skill_content(content, executable=executable, location=location)
    if result.decision == "block":
        raise ValueError(f"Security scan blocked the write: {result.reason}")
    if executable and result.decision != "allow":
        raise ValueError(f"Security scan rejected executable content: {result.reason}")
    return {"decision": result.decision, "reason": result.reason}


async def _to_thread(func, /, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


async def _skill_manage_impl(
    runtime: Runtime,
    action: str,
    name: str,
    content: str | None = None,
    path: str | None = None,
    find: str | None = None,
    replace: str | None = None,
    expected_count: int | None = None,
) -> str:
    """Manage custom skills under skills/custom/.

    Args:
        action: One of create, patch, edit, delete, write_file, remove_file.
        name: Skill name in hyphen-case.
        content: New file content for create, edit, or write_file.
        path: Supporting file path for write_file or remove_file.
        find: Existing text to replace for patch.
        replace: Replacement text for patch.
        expected_count: Optional expected number of replacements for patch.
    """
    name = SkillStorage.validate_skill_name(name)
    lock = _get_lock(name)
    thread_id = _get_thread_id(runtime)
    user_id = _get_runtime_user_id(runtime)
    skill_storage = get_or_new_skill_storage()

    async with lock:
        if action == "create":
            if await _to_thread(skill_storage.custom_skill_exists, name):
                raise ValueError(f"Custom skill '{name}' already exists.")
            if content is None:
                raise ValueError("content is required for create.")
            await _to_thread(skill_storage.validate_skill_markdown_content, name, content)
            scan = await _scan_or_raise(content, executable=False, location=f"{name}/{SKILL_MD_FILE}")
            await _to_thread(skill_storage.write_custom_skill, name, SKILL_MD_FILE, content)
            await _to_thread(
                skill_storage.append_history,
                name,
                _history_record(action="create", file_path=SKILL_MD_FILE, prev_content=None, new_content=content, thread_id=thread_id, scanner=scan),
            )
            await _to_thread(_upsert_skill_metadata_from_chat, name=name, content=content, user_id=user_id)
            await refresh_skills_system_prompt_cache_async()
            return f"Created custom skill '{name}'."

        if action == "edit":
            await _to_thread(skill_storage.ensure_custom_skill_is_editable, name)
            if content is None:
                raise ValueError("content is required for edit.")
            await _to_thread(skill_storage.validate_skill_markdown_content, name, content)
            scan = await _scan_or_raise(content, executable=False, location=f"{name}/{SKILL_MD_FILE}")
            skill_file = skill_storage.get_custom_skill_file(name)
            prev_content = await _to_thread(skill_file.read_text, encoding="utf-8")
            await _to_thread(skill_storage.write_custom_skill, name, SKILL_MD_FILE, content)
            await _to_thread(
                skill_storage.append_history,
                name,
                _history_record(action="edit", file_path=SKILL_MD_FILE, prev_content=prev_content, new_content=content, thread_id=thread_id, scanner=scan),
            )
            await _to_thread(_upsert_skill_metadata_from_chat, name=name, content=content, user_id=user_id)
            await refresh_skills_system_prompt_cache_async()
            return f"Updated custom skill '{name}'."

        if action == "patch":
            await _to_thread(skill_storage.ensure_custom_skill_is_editable, name)
            if find is None or replace is None:
                raise ValueError("find and replace are required for patch.")
            skill_file = skill_storage.get_custom_skill_file(name)
            prev_content = await _to_thread(skill_file.read_text, encoding="utf-8")
            occurrences = prev_content.count(find)
            if occurrences == 0:
                raise ValueError("Patch target not found in SKILL.md.")
            if expected_count is not None and occurrences != expected_count:
                raise ValueError(f"Expected {expected_count} replacements but found {occurrences}.")
            replacement_count = expected_count if expected_count is not None else 1
            new_content = prev_content.replace(find, replace, replacement_count)
            await _to_thread(skill_storage.validate_skill_markdown_content, name, new_content)
            scan = await _scan_or_raise(new_content, executable=False, location=f"{name}/{SKILL_MD_FILE}")
            await _to_thread(skill_storage.write_custom_skill, name, SKILL_MD_FILE, new_content)
            await _to_thread(
                skill_storage.append_history,
                name,
                _history_record(action="patch", file_path=SKILL_MD_FILE, prev_content=prev_content, new_content=new_content, thread_id=thread_id, scanner=scan),
            )
            await _to_thread(_upsert_skill_metadata_from_chat, name=name, content=new_content, user_id=user_id)
            await refresh_skills_system_prompt_cache_async()
            return f"Patched custom skill '{name}' ({replacement_count} replacement(s) applied, {occurrences} match(es) found)."

        if action == "delete":
            await _to_thread(
                skill_storage.delete_custom_skill,
                name,
                history_meta=_history_record(
                    action="delete",
                    file_path=SKILL_MD_FILE,
                    prev_content=None,
                    new_content=None,
                    thread_id=thread_id,
                    scanner={"decision": "allow", "reason": "Deletion requested."},
                ),
            )
            await _to_thread(_delete_skill_metadata_from_chat, name=name, user_id=user_id)
            await refresh_skills_system_prompt_cache_async()
            return f"Deleted custom skill '{name}'."

        if action == "write_file":
            await _to_thread(skill_storage.ensure_custom_skill_is_editable, name)
            if path is None or content is None:
                raise ValueError("path and content are required for write_file.")
            target = await _to_thread(skill_storage.ensure_safe_support_path, name, path)
            exists = await _to_thread(target.exists)
            prev_content = await _to_thread(target.read_text, encoding="utf-8") if exists else None
            executable = "scripts/" in path or path.startswith("scripts/")
            scan = await _scan_or_raise(content, executable=executable, location=f"{name}/{path}")
            await _to_thread(skill_storage.write_custom_skill, name, path, content)
            await _to_thread(
                skill_storage.append_history,
                name,
                _history_record(action="write_file", file_path=path, prev_content=prev_content, new_content=content, thread_id=thread_id, scanner=scan),
            )
            return f"Wrote '{path}' for custom skill '{name}'."

        if action == "remove_file":
            await _to_thread(skill_storage.ensure_custom_skill_is_editable, name)
            if path is None:
                raise ValueError("path is required for remove_file.")
            target = await _to_thread(skill_storage.ensure_safe_support_path, name, path)
            if not await _to_thread(target.exists):
                raise FileNotFoundError(f"Supporting file '{path}' not found for skill '{name}'.")
            prev_content = await _to_thread(target.read_text, encoding="utf-8")
            await _to_thread(target.unlink)
            await _to_thread(
                skill_storage.append_history,
                name,
                _history_record(action="remove_file", file_path=path, prev_content=prev_content, new_content=None, thread_id=thread_id, scanner={"decision": "allow", "reason": "Deletion requested."}),
            )
            return f"Removed '{path}' from custom skill '{name}'."

        if await _to_thread(skill_storage.public_skill_exists, name):
            raise ValueError(f"'{name}' is a built-in skill. To customise it, create a new skill with the same name under skills/custom/.")
        raise ValueError(f"Unsupported action '{action}'.")


@tool("skill_manage", parse_docstring=True)
async def skill_manage_tool(
    runtime: Runtime,
    action: str,
    name: str,
    content: str | None = None,
    path: str | None = None,
    find: str | None = None,
    replace: str | None = None,
    expected_count: int | None = None,
) -> str:
    """Manage custom skills under skills/custom/.

    Args:
        action: One of create, patch, edit, delete, write_file, remove_file.
        name: Skill name in hyphen-case.
        content: New file content for create, edit, or write_file.
        path: Supporting file path for write_file or remove_file.
        find: Existing text to replace for patch.
        replace: Replacement text for patch.
        expected_count: Optional expected number of replacements for patch.
    """
    return await _skill_manage_impl(
        runtime=runtime,
        action=action,
        name=name,
        content=content,
        path=path,
        find=find,
        replace=replace,
        expected_count=expected_count,
    )


skill_manage_tool.func = make_sync_tool_wrapper(_skill_manage_impl, "skill_manage")
