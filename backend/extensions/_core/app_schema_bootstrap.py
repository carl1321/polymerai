"""Bootstrap extension tables (agents, workflows, toolbox_skills) on gateway startup."""

from __future__ import annotations

import logging
from pathlib import Path

from deerflow.skills import load_skills
from extensions._core.agents_db import init_agents_table
from extensions._core.skills_db import init_skills_tables, slugify_name

logger = logging.getLogger(__name__)


def _infer_group_name(skill_name: str) -> str:
    if skill_name.startswith("vasp-"):
        return "vasp"
    if skill_name.startswith("gaussian-"):
        return "gaussian"
    if skill_name == "polymer-build" or skill_name.startswith("polymer-"):
        return "polymer"
    if skill_name == "modeling":
        return "modeling"
    return "通用"


def _is_under_root(skill_dir: Path, root: Path) -> bool:
    try:
        sdr = skill_dir.resolve()
        rr = root.resolve()
    except OSError:
        return False
    return sdr == rr or rr in sdr.parents


def _upsert_toolbox_skill(
    conn,
    *,
    name: str,
    description: str,
    skill_dir: str,
    group_name: str = "通用",
) -> None:
    slug = slugify_name(name)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM toolbox_skills
            WHERE name = %s
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (name,),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE toolbox_skills
                SET visibility = 'org',
                    group_name = %s,
                    skill_dir = %s,
                    description = %s,
                    enabled = TRUE,
                    updated_at = now()
                WHERE id = %s
                """,
                (group_name, skill_dir, description, row["id"]),
            )
            return
        cur.execute(
            """
            INSERT INTO toolbox_skills (
                name, slug, description, laber_name, laber_description,
                visibility, user_id, organization_id, group_name, skill_dir, enabled
            ) VALUES (%s, %s, %s, %s, %s, 'org', NULL, NULL, %s, %s, TRUE)
            """,
            (name, slug, description, name, description, group_name, skill_dir),
        )


def sync_toolbox_skills_from_disk(conn) -> int:
    """Populate toolbox_skills from skills/public and skills/custom on disk."""
    runtime_skills = load_skills(enabled_only=False)
    repo_root = Path(__file__).resolve().parents[3]
    public_root = repo_root / "skills" / "public"
    custom_root = repo_root / "skills" / "custom"
    count = 0
    with conn.cursor() as cur:
        cur.execute("DELETE FROM toolbox_skills WHERE name = %s", ("vaspagent",))
    for skill in runtime_skills:
        sd = Path(skill.skill_dir)
        if skill.category == "public" and _is_under_root(sd, public_root):
            _upsert_toolbox_skill(
                conn,
                name=skill.name,
                description=skill.description or "",
                skill_dir=str(skill.skill_dir),
                group_name=_infer_group_name(skill.name),
            )
            count += 1
        elif skill.category == "custom" and _is_under_root(sd, custom_root):
            _upsert_toolbox_skill(
                conn,
                name=skill.name,
                description=skill.description or "",
                skill_dir=str(skill.skill_dir),
                group_name="通用",
            )
            count += 1
    conn.commit()
    return count


def bootstrap_app_extension_schema() -> None:
    """Idempotent schema + skills seed for agents/workflows/skills APIs."""
    from extensions._core.app_db import get_app_db_connection
    from scripts.init_app_database import create_workflow_tables
    from extensions._core.workflow_tools.db import init_workflow_tools_table

    conn = get_app_db_connection()
    try:
        init_agents_table(conn)
        conn.commit()
        create_workflow_tables(conn)
        conn.commit()
        init_workflow_tools_table(conn)
        conn.commit()
        init_skills_tables(conn)
        conn.commit()
        n = sync_toolbox_skills_from_disk(conn)
        logger.info("App extension schema ready (toolbox_skills synced: %d)", n)
    except Exception:
        logger.exception("App extension schema bootstrap failed")
        conn.rollback()
        raise
    finally:
        conn.close()
