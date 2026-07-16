import ast
import errno
import json
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.gateway.deps import get_config
from app.gateway.path_utils import resolve_thread_virtual_path
from deerflow.agents.lead_agent.prompt import refresh_skills_system_prompt_cache_async
from deerflow.config.app_config import AppConfig
from deerflow.config.extensions_config import ExtensionsConfig, SkillStateConfig, get_extensions_config, reload_extensions_config
from deerflow.skills import Skill, load_skills
from deerflow.skills.installer import SkillAlreadyExistsError
from deerflow.skills.manager import (
    append_history,
    atomic_write,
    custom_skill_exists,
    ensure_custom_skill_is_editable,
    get_custom_skill_dir,
    get_custom_skill_file,
    get_skill_history_file,
    read_custom_skill_content,
    read_history,
    validate_skill_markdown_content,
)
from deerflow.skills.security_scanner import scan_skill_content
from deerflow.skills.storage import get_or_new_skill_storage
from deerflow.skills.types import SKILL_MD_FILE, SkillCategory
from extensions._core.app_db import get_app_db_connection
from extensions._core.db_errors import is_undefined_table
from extensions._core.llms.llm import get_llm_by_type
from extensions._core.skills_db import (
    create_skill_metadata,
    get_visible_skill,
    init_skills_tables,
    list_visible_skills,
    replace_skill_bindings,
    update_skill_metadata,
)

try:
    from extensions.auth.dependencies import CurrentUser, get_current_user_optional
except Exception:  # pragma: no cover
    CurrentUser = Any  # type: ignore[misc,assignment]

    async def get_current_user_optional():  # type: ignore[no-redef]
        return None


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["skills"])

_UPLOAD_SKILL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class SkillResponse(BaseModel):
    """Response model for skill information."""

    id: str | None = Field(default=None, description="Database id for toolbox skill metadata")
    name: str = Field(..., description="Name of the skill")
    description: str = Field(..., description="Description of what the skill does")
    laber_name: str | None = Field(default=None, description="Chinese display name")
    laber_description: str | None = Field(default=None, description="Chinese display description")
    license: str | None = Field(None, description="License information")
    category: SkillCategory = Field(..., description="Category of the skill (public or custom)")
    enabled: bool = Field(default=True, description="Whether this skill is enabled")
    group: str | None = Field(None, description="Optional display group for UI (e.g. vaspagent)")
    tool_names: list[str] | None = Field(
        default=None,
        description="Optional list of tool names exposed by this skill (used for agent tool binding UI).",
    )
    visibility: str | None = Field(default=None, description="Visibility scope: user or org")
    user_id: str | None = Field(default=None, description="Skill owner user id")
    organization_id: str | None = Field(default=None, description="Owner organization id")
    group_name: str | None = Field(default=None, description="Primary category for toolbox display")
    agent_ids: list[str] | None = Field(default=None, description="Associated agent ids")


class SkillsListResponse(BaseModel):
    """Response model for listing all skills."""

    skills: list[SkillResponse]


class SkillUpdateRequest(BaseModel):
    """Request model for updating a skill."""

    enabled: bool = Field(..., description="Whether to enable or disable the skill")


class SkillInstallRequest(BaseModel):
    """Request model for installing a skill from a .skill file."""

    thread_id: str = Field(..., description="The thread ID where the .skill file is located")
    path: str = Field(..., description="Virtual path to the .skill file (e.g., mnt/user-data/outputs/my-skill.skill)")


class SkillInstallResponse(BaseModel):
    """Response model for skill installation."""

    success: bool = Field(..., description="Whether the installation was successful")
    skill_name: str = Field(..., description="Name of the installed skill")
    message: str = Field(..., description="Installation result message")


_TOOL_NAMES_CACHE: dict[Path, list[str]] = {}


def _translate_skill_label(skill_name: str, skill_md: str) -> tuple[str, str]:
    prompt = '你是技能信息翻译助手。请根据给定的 SKILL.md 内容，输出中文技能名称和中文简介。返回严格 JSON，格式：{"laber_name":"...","laber_description":"..."}。laber_name 不超过 20 字，laber_description 不超过 120 字。不要输出其他内容。'
    content = (skill_md or "").strip()
    if len(content) > 6000:
        content = content[:6000]
    try:
        llm = get_llm_by_type("basic")
        resp = llm.invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=f"skill_name: {skill_name}\n\nSKILL.md:\n{content}"),
            ]
        )
        text = getattr(resp, "content", "")
        if isinstance(text, list):
            text = "\n".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in text)
        data = json.loads(str(text).strip())
        if isinstance(data, dict):
            name = str(data.get("laber_name") or "").strip()
            desc = str(data.get("laber_description") or "").strip()
            if name or desc:
                return (name or skill_name, desc or "")
    except Exception as e:
        logger.warning("Translate skill label failed for %s: %s", skill_name, e)
    return (skill_name, "")


def _get_skill_tool_names(skill: Skill) -> list[str] | None:
    """Extract exposed tool names from <skill_dir>/tool.py without importing it.

    Why no import: tool.py may depend on heavy / optional deps; the skills
    listing API should stay fast and robust.

    Heuristic:
    - Parse tool.py AST
    - Return names of functions decorated with `@tool` or `@tool(...)`
    """
    tool_py = skill.skill_dir / "tool.py"
    if not tool_py.is_file():
        return None
    if tool_py in _TOOL_NAMES_CACHE:
        return _TOOL_NAMES_CACHE[tool_py]

    try:
        src = tool_py.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(tool_py))
        tool_names: set[str] = set()

        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                # @tool
                if isinstance(dec, ast.Name) and dec.id == "tool":
                    tool_names.add(node.name)
                    break
                # @tool(...)
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "tool":
                    tool_names.add(node.name)
                    break

        names = sorted(tool_names)
        _TOOL_NAMES_CACHE[tool_py] = names
        return names or None
    except Exception as e:
        logger.debug("Failed to parse tool.py for skill '%s' (%s): %s", skill.name, tool_py, e)
        return None


class CustomSkillContentResponse(SkillResponse):
    content: str = Field(..., description="Raw SKILL.md content")


class CustomSkillUpdateRequest(BaseModel):
    content: str = Field(..., description="Replacement SKILL.md content")


class CustomSkillHistoryResponse(BaseModel):
    history: list[dict]


class SkillRollbackRequest(BaseModel):
    history_index: int = Field(default=-1, description="History entry index to restore from, defaulting to the latest change.")


class SkillFolderUploadResponse(BaseModel):
    success: bool = Field(..., description="Whether upload was successful")
    skill_name: str = Field(..., description="Installed custom skill name")
    file_count: int = Field(..., description="Total files imported")
    message: str = Field(..., description="Result message")


class SkillMetadataUpdateRequest(BaseModel):
    visibility: str | None = Field(default=None, description="Visibility scope: user or org")
    group_name: str | None = Field(default=None, description="Primary category")
    agent_ids: list[str] | None = Field(default=None, description="Associated agents")
    enabled: bool | None = Field(default=None, description="Enabled state")


@router.put("/skills/{skill_id}/metadata", response_model=SkillResponse, summary="Update Skill Metadata")
async def update_skill_metadata_api(
    skill_id: str,
    request: SkillMetadataUpdateRequest,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> SkillResponse:
    user = _require_user(current_user)
    try:
        uid = UUID(skill_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="skill_id must be UUID") from exc

    conn = get_app_db_connection()
    try:
        init_skills_tables(conn)
        row = get_visible_skill(
            conn,
            skill_id=uid,
            user_id=str(user.id),
            organization_id=str(user.organization_id) if user.organization_id else None,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Skill not found")
        update_skill_metadata(
            conn,
            skill_id=uid,
            visibility=request.visibility if request.visibility in {"user", "org"} else None,
            group_name=request.group_name,
            enabled=request.enabled,
        )
        if request.agent_ids is not None:
            replace_skill_bindings(conn, skill_id=uid, agent_ids=request.agent_ids, created_by=str(user.id))
        refreshed = get_visible_skill(
            conn,
            skill_id=uid,
            user_id=str(user.id),
            organization_id=str(user.organization_id) if user.organization_id else None,
        )
        if not refreshed:
            raise HTTPException(status_code=404, detail="Skill not found")
        runtime_skills = load_skills(enabled_only=False)
        skill_obj = next((s for s in runtime_skills if s.name == refreshed.get("name")), None)
        return _db_skill_to_response(refreshed, _get_skill_tool_names(skill_obj) if skill_obj else None)
    finally:
        conn.close()


def _validate_uploaded_skill_name(name: str) -> str:
    normalized = (name or "").strip()
    if not _UPLOAD_SKILL_NAME_PATTERN.fullmatch(normalized):
        raise ValueError("Skill name must start with a lowercase letter and contain only lowercase letters, digits, hyphens, or underscores.")
    return normalized


def _safe_relative_path(path: str) -> Path:
    rel = Path(path.replace("\\", "/").lstrip("/"))
    if not rel.parts:
        raise ValueError("File path is empty.")
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError("Invalid file path in upload.")
    return rel


def _derive_skill_name(relative_paths: list[str]) -> str:
    roots = {_safe_relative_path(p).parts[0] for p in relative_paths if p}
    if not roots:
        raise ValueError("No files were uploaded.")
    if len(roots) != 1:
        raise ValueError("Uploaded files must belong to a single root folder.")
    return _validate_uploaded_skill_name(next(iter(roots)))


def _extract_skill_md(relative_paths: list[str], files: list[UploadFile], skill_name: str) -> str:
    target = f"{skill_name}/SKILL.md"
    for rel, file in zip(relative_paths, files, strict=False):
        if rel.replace("\\", "/") == target:
            content = file.file.read().decode("utf-8")
            if not content.strip():
                raise ValueError("SKILL.md is empty.")
            return content
    raise ValueError("Missing SKILL.md at the root of the uploaded skill folder.")


def _write_uploaded_skill_atomic(
    skill_name: str,
    relative_paths: list[str],
    files: list[UploadFile],
) -> int:
    custom_root = get_custom_skill_dir(skill_name).parent
    final_dir = get_custom_skill_dir(skill_name)
    if final_dir.exists():
        raise FileExistsError(f"Custom skill '{skill_name}' already exists.")

    with tempfile.TemporaryDirectory(dir=str(custom_root)) as tmp:
        staged_root = Path(tmp) / skill_name
        staged_root.mkdir(parents=True, exist_ok=True)
        count = 0
        for rel_str, upload in zip(relative_paths, files, strict=False):
            rel = _safe_relative_path(rel_str)
            if rel.parts[0] != skill_name:
                raise ValueError("Uploaded files must stay under the root skill folder.")
            dest = staged_root / Path(*rel.parts[1:])
            dest.parent.mkdir(parents=True, exist_ok=True)
            upload.file.seek(0)
            data = upload.file.read()
            dest.write_bytes(data)
            count += 1

        # Atomic move into skills/custom/<skill_name>
        staged_root.replace(final_dir)
        return count


def _skill_to_response(skill: Skill) -> SkillResponse:
    """Convert a Skill object to a SkillResponse."""
    return SkillResponse(
        id=None,
        name=skill.name,
        description=skill.description,
        laber_name=skill.name,
        laber_description=skill.description,
        license=skill.license,
        category=skill.category,
        enabled=skill.enabled,
        group=getattr(skill, "group", None),
        tool_names=_get_skill_tool_names(skill),
        visibility=None,
        user_id=None,
        organization_id=None,
        group_name=getattr(skill, "group", None),
        agent_ids=None,
    )


def _require_user(user: CurrentUser | None) -> CurrentUser:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _db_skill_to_response(row: dict[str, Any], tool_names: list[str] | None) -> SkillResponse:
    return SkillResponse(
        id=str(row.get("id")) if row.get("id") else None,
        name=row.get("name") or "",
        description=row.get("description") or "",
        laber_name=row.get("laber_name") or row.get("name") or "",
        laber_description=row.get("laber_description") or row.get("description") or "",
        license=None,
        category="custom",
        enabled=bool(row.get("enabled", True)),
        group=row.get("group_name") or "未分类",
        tool_names=tool_names,
        visibility=row.get("visibility") or "user",
        user_id=row.get("user_id"),
        organization_id=row.get("organization_id"),
        group_name=row.get("group_name") or "未分类",
        agent_ids=row.get("agent_ids") or [],
    )


@router.get(
    "/skills",
    response_model=SkillsListResponse,
    summary="List All Skills",
    description="Retrieve a list of all available skills from both public and custom directories.",
)
async def list_skills(current_user: CurrentUser | None = Depends(get_current_user_optional)) -> SkillsListResponse:
    try:
        user = _require_user(current_user)
        runtime_skills = load_skills(enabled_only=False)
        skill_map = {s.name: s for s in runtime_skills}
        conn = get_app_db_connection()
        rows: list[dict[str, Any]] = []
        try:
            init_skills_tables(conn)
            conn.commit()
            rows = list_visible_skills(
                conn,
                user_id=str(user.id),
                organization_id=str(user.organization_id) if user.organization_id else None,
            )
            if not rows:
                from extensions._core.app_schema_bootstrap import sync_toolbox_skills_from_disk

                sync_toolbox_skills_from_disk(conn)
                rows = list_visible_skills(
                    conn,
                    user_id=str(user.id),
                    organization_id=str(user.organization_id) if user.organization_id else None,
                )
        except Exception as e:
            if is_undefined_table(e):
                logger.warning("toolbox_skills missing, falling back to disk skills: %s", e)
                rows = []
            else:
                raise
        finally:
            conn.close()
        if not rows and runtime_skills:
            return SkillsListResponse(skills=[_skill_to_response(s) for s in runtime_skills if s.category in ("public", "custom")])
        db_skills: list[SkillResponse] = []
        for row in rows:
            skill_obj = skill_map.get(row.get("name", ""))
            tool_names = _get_skill_tool_names(skill_obj) if skill_obj else None
            db_skills.append(_db_skill_to_response(row, tool_names))
        return SkillsListResponse(skills=db_skills)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load skills: {str(e)}")


@router.post(
    "/skills/install",
    response_model=SkillInstallResponse,
    summary="Install Skill",
    description="Install a skill from a .skill file (ZIP archive) located in the thread's user-data directory.",
)
async def install_skill(request: SkillInstallRequest, config: AppConfig = Depends(get_config)) -> SkillInstallResponse:
    try:
        skill_file_path = resolve_thread_virtual_path(request.thread_id, request.path)
        result = await get_or_new_skill_storage(app_config=config).ainstall_skill_from_archive(skill_file_path)
        await refresh_skills_system_prompt_cache_async()
        return SkillInstallResponse(**result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SkillAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to install skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to install skill: {str(e)}")


@router.get("/skills/custom", response_model=SkillsListResponse, summary="List Custom Skills")
async def list_custom_skills() -> SkillsListResponse:
    try:
        skills = [skill for skill in load_skills(enabled_only=False) if skill.category == SkillCategory.CUSTOM]
        return SkillsListResponse(skills=[_skill_to_response(skill) for skill in skills])
    except Exception as e:
        logger.error("Failed to list custom skills: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list custom skills: {str(e)}")


@router.post(
    "/skills/custom/upload",
    response_model=SkillFolderUploadResponse,
    summary="Upload Custom Skill Folder",
)
async def upload_custom_skill_folder(
    files: list[UploadFile] = File(..., description="Skill folder files"),
    relative_paths: list[str] = Form(..., description="Relative paths aligned to files[]"),
    visibility: str = Form("user", description="Visibility scope: user or org"),
    group_name: str | None = Form(None, description="Primary category"),
    agent_ids: list[str] | None = Form(None, description="Associated agent ids"),
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> SkillFolderUploadResponse:
    try:
        user = _require_user(current_user)
        if not files:
            raise HTTPException(status_code=400, detail="No files were uploaded.")
        if len(files) != len(relative_paths):
            raise HTTPException(status_code=400, detail="files and relative_paths length mismatch.")

        skill_name = _derive_skill_name(relative_paths)
        if custom_skill_exists(skill_name):
            raise HTTPException(status_code=409, detail=f"Custom skill '{skill_name}' already exists.")

        skill_md = _extract_skill_md(relative_paths, files, skill_name)
        validate_skill_markdown_content(skill_name, skill_md)
        scan = await scan_skill_content(
            skill_md,
            executable=False,
            location=f"{skill_name}/SKILL.md",
        )
        if scan.decision == "block":
            raise HTTPException(status_code=400, detail=f"Security scan blocked upload: {scan.reason}")

        file_count = _write_uploaded_skill_atomic(skill_name, relative_paths, files)
        laber_name, laber_description = _translate_skill_label(skill_name, skill_md)
        conn = get_app_db_connection()
        try:
            init_skills_tables(conn)
            skill_id = create_skill_metadata(
                conn,
                name=skill_name,
                description=skill_md[:500],
                laber_name=laber_name,
                laber_description=laber_description,
                visibility="org" if visibility == "org" else "user",
                user_id=str(user.id),
                organization_id=str(user.organization_id) if user.organization_id else None,
                group_name=(group_name or "").strip() or None,
                skill_dir=str(get_custom_skill_dir(skill_name)),
                enabled=True,
            )
            replace_skill_bindings(
                conn,
                skill_id=skill_id,
                agent_ids=agent_ids or [],
                created_by=str(user.id),
            )
        finally:
            conn.close()
        append_history(
            skill_name,
            {
                "action": "human_upload",
                "author": "human",
                "thread_id": None,
                "file_path": "SKILL.md",
                "prev_content": None,
                "new_content": skill_md,
                "scanner": {"decision": scan.decision, "reason": scan.reason},
                "file_count": file_count,
            },
        )
        await refresh_skills_system_prompt_cache_async()
        return SkillFolderUploadResponse(
            success=True,
            skill_name=skill_name,
            file_count=file_count,
            message=f"Skill '{skill_name}' uploaded successfully.",
        )
    except HTTPException:
        raise
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="SKILL.md must be UTF-8 encoded text.")
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to upload custom skill folder: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload custom skill folder: {str(e)}")


@router.get("/skills/custom/{skill_name}", response_model=CustomSkillContentResponse, summary="Get Custom Skill Content")
async def get_custom_skill(skill_name: str) -> CustomSkillContentResponse:
    try:
        skill_name = skill_name.replace("\r\n", "").replace("\n", "")
        skills = load_skills(enabled_only=False)
        skill = next((s for s in skills if s.name == skill_name and s.category == SkillCategory.CUSTOM), None)
        if skill is None:
            raise HTTPException(status_code=404, detail=f"Custom skill '{skill_name}' not found")
        return CustomSkillContentResponse(**_skill_to_response(skill).model_dump(), content=read_custom_skill_content(skill_name))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get custom skill %s: %s", skill_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get custom skill: {str(e)}")


@router.put("/skills/custom/{skill_name}", response_model=CustomSkillContentResponse, summary="Edit Custom Skill")
async def update_custom_skill(skill_name: str, request: CustomSkillUpdateRequest, config: AppConfig = Depends(get_config)) -> CustomSkillContentResponse:
    try:
        skill_name = skill_name.replace("\r\n", "").replace("\n", "")
        ensure_custom_skill_is_editable(skill_name)
        validate_skill_markdown_content(skill_name, request.content)
        scan = await scan_skill_content(
            request.content,
            executable=False,
            location=f"{skill_name}/{SKILL_MD_FILE}",
            app_config=config,
        )
        if scan.decision == "block":
            raise HTTPException(status_code=400, detail=f"Security scan blocked the edit: {scan.reason}")
        skill_file = get_custom_skill_dir(skill_name) / SKILL_MD_FILE
        prev_content = skill_file.read_text(encoding="utf-8")
        atomic_write(skill_file, request.content)
        append_history(
            skill_name,
            {
                "action": "human_edit",
                "author": "human",
                "thread_id": None,
                "file_path": SKILL_MD_FILE,
                "prev_content": prev_content,
                "new_content": request.content,
                "scanner": {"decision": scan.decision, "reason": scan.reason},
            },
        )
        await refresh_skills_system_prompt_cache_async()
        return await get_custom_skill(skill_name)
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to update custom skill %s: %s", skill_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update custom skill: {str(e)}")


@router.delete("/skills/custom/{skill_name}", summary="Delete Custom Skill")
async def delete_custom_skill(skill_name: str) -> dict[str, bool]:
    try:
        skill_name = skill_name.replace("\r\n", "").replace("\n", "")
        ensure_custom_skill_is_editable(skill_name)
        skill_dir = get_custom_skill_dir(skill_name)
        prev_content = read_custom_skill_content(skill_name)
        try:
            append_history(
                skill_name,
                {
                    "action": "human_delete",
                    "author": "human",
                    "thread_id": None,
                    "file_path": SKILL_MD_FILE,
                    "prev_content": prev_content,
                    "new_content": None,
                    "scanner": {"decision": "allow", "reason": "Deletion requested."},
                },
            )
        except OSError as e:
            if not isinstance(e, PermissionError) and e.errno not in {errno.EACCES, errno.EPERM, errno.EROFS}:
                raise
            logger.warning("Skipping delete history write for custom skill %s due to readonly/permission failure; continuing with skill directory removal: %s", skill_name, e)
        shutil.rmtree(skill_dir)
        await refresh_skills_system_prompt_cache_async()
        return {"success": True}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to delete custom skill %s: %s", skill_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete custom skill: {str(e)}")


@router.get("/skills/custom/{skill_name}/history", response_model=CustomSkillHistoryResponse, summary="Get Custom Skill History")
async def get_custom_skill_history(skill_name: str) -> CustomSkillHistoryResponse:
    try:
        skill_name = skill_name.replace("\r\n", "").replace("\n", "")
        if not custom_skill_exists(skill_name) and not get_skill_history_file(skill_name).exists():
            raise HTTPException(status_code=404, detail=f"Custom skill '{skill_name}' not found")
        return CustomSkillHistoryResponse(history=read_history(skill_name))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to read history for %s: %s", skill_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read history: {str(e)}")


@router.post("/skills/custom/{skill_name}/rollback", response_model=CustomSkillContentResponse, summary="Rollback Custom Skill")
async def rollback_custom_skill(skill_name: str, request: SkillRollbackRequest, config: AppConfig = Depends(get_config)) -> CustomSkillContentResponse:
    try:
        skill_name = skill_name.replace("\r\n", "").replace("\n", "")
        if not custom_skill_exists(skill_name) and not get_skill_history_file(skill_name).exists():
            raise HTTPException(status_code=404, detail=f"Custom skill '{skill_name}' not found")
        history = read_history(skill_name)
        if not history:
            raise HTTPException(status_code=400, detail=f"Custom skill '{skill_name}' has no history")
        record = history[request.history_index]
        target_content = record.get("prev_content")
        if target_content is None:
            raise HTTPException(status_code=400, detail="Selected history entry has no previous content to roll back to")
        validate_skill_markdown_content(skill_name, target_content)
        scan = await scan_skill_content(
            target_content,
            executable=False,
            location=f"{skill_name}/{SKILL_MD_FILE}",
            app_config=config,
        )
        skill_file = get_custom_skill_file(skill_name)
        current_content = skill_file.read_text(encoding="utf-8") if skill_file.exists() else None
        history_entry = {
            "action": "rollback",
            "author": "human",
            "thread_id": None,
            "file_path": SKILL_MD_FILE,
            "prev_content": current_content,
            "new_content": target_content,
            "rollback_from_ts": record.get("ts"),
            "scanner": {"decision": scan.decision, "reason": scan.reason},
        }
        if scan.decision == "block":
            append_history(skill_name, history_entry)
            raise HTTPException(status_code=400, detail=f"Rollback blocked by security scanner: {scan.reason}")
        atomic_write(skill_file, target_content)
        append_history(skill_name, history_entry)
        await refresh_skills_system_prompt_cache_async()
        return await get_custom_skill(skill_name)
    except HTTPException:
        raise
    except IndexError:
        raise HTTPException(status_code=400, detail="history_index is out of range")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to roll back custom skill %s: %s", skill_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to roll back custom skill: {str(e)}")


@router.get(
    "/skills/{skill_name}",
    response_model=SkillResponse,
    summary="Get Skill Details",
    description="Retrieve detailed information about a specific skill by its name.",
)
async def get_skill(skill_name: str, current_user: CurrentUser | None = Depends(get_current_user_optional)) -> SkillResponse:
    try:
        skill_name = skill_name.replace("\r\n", "").replace("\n", "")
        # Try DB-backed id lookup first for toolbox dynamic list/detail.
        try:
            uid = UUID(skill_name)
            user = _require_user(current_user)
            conn = get_app_db_connection()
            try:
                init_skills_tables(conn)
                row = get_visible_skill(
                    conn,
                    skill_id=uid,
                    user_id=str(user.id),
                    organization_id=str(user.organization_id) if user.organization_id else None,
                )
                if row:
                    skills = load_skills(enabled_only=False)
                    skill_obj = next((s for s in skills if s.name == row.get("name")), None)
                    return _db_skill_to_response(row, _get_skill_tool_names(skill_obj) if skill_obj else None)
            finally:
                conn.close()
        except Exception:
            pass

        skills = load_skills(enabled_only=False)
        skill = next((s for s in skills if s.name == skill_name), None)

        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        return _skill_to_response(skill)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get skill: {str(e)}")


@router.put(
    "/skills/{skill_name}",
    response_model=SkillResponse,
    summary="Update Skill",
    description="Update a skill's enabled status by modifying the extensions_config.json file.",
)
async def update_skill(skill_name: str, request: SkillUpdateRequest, current_user: CurrentUser | None = Depends(get_current_user_optional)) -> SkillResponse:
    try:
        skill_name = skill_name.replace("\r\n", "").replace("\n", "")
        # DB metadata update by id (UUID path)
        try:
            uid = UUID(skill_name)
            user = _require_user(current_user)
            conn = get_app_db_connection()
            try:
                init_skills_tables(conn)
                row = get_visible_skill(
                    conn,
                    skill_id=uid,
                    user_id=str(user.id),
                    organization_id=str(user.organization_id) if user.organization_id else None,
                )
                if row:
                    update_skill_metadata(conn, skill_id=uid, enabled=request.enabled)
                    refreshed = get_visible_skill(
                        conn,
                        skill_id=uid,
                        user_id=str(user.id),
                        organization_id=str(user.organization_id) if user.organization_id else None,
                    )
                    if refreshed:
                        skills = load_skills(enabled_only=False)
                        skill_obj = next((s for s in skills if s.name == refreshed.get("name")), None)
                        return _db_skill_to_response(refreshed, _get_skill_tool_names(skill_obj) if skill_obj else None)
            finally:
                conn.close()
        except Exception:
            pass

        skills = load_skills(enabled_only=False)
        skill = next((s for s in skills if s.name == skill_name), None)

        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        config_path = ExtensionsConfig.resolve_config_path()
        if config_path is None:
            config_path = Path.cwd().parent / "extensions_config.json"
            logger.info(f"No existing extensions config found. Creating new config at: {config_path}")

        extensions_config = get_extensions_config()
        extensions_config.skills[skill_name] = SkillStateConfig(enabled=request.enabled)

        config_data = {
            "mcpServers": {name: server.model_dump() for name, server in extensions_config.mcp_servers.items()},
            "skills": {name: {"enabled": skill_config.enabled} for name, skill_config in extensions_config.skills.items()},
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Skills configuration updated and saved to: {config_path}")
        reload_extensions_config()
        await refresh_skills_system_prompt_cache_async()

        skills = load_skills(enabled_only=False)
        updated_skill = next((s for s in skills if s.name == skill_name), None)

        if updated_skill is None:
            raise HTTPException(status_code=500, detail=f"Failed to reload skill '{skill_name}' after update")

        logger.info(f"Skill '{skill_name}' enabled status updated to {request.enabled}")
        return _skill_to_response(updated_skill)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update skill: {str(e)}")
