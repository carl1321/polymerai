#!/usr/bin/env python3
"""Initialize toolbox_skills metadata with an explicit visible allowlist.

Run:
  cd backend && uv run python scripts/init_toolbox_skills_metadata.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deerflow.skills import load_skills
from extensions._core.app_db import get_app_db_connection
from extensions._core.skills_db import init_skills_tables, slugify_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_connection_url() -> str:
    url = os.environ.get("DEER_FLOW_APP_DATABASE_URL")
    if url:
        return url
    try:
        from deerflow.config.app_config import get_app_config

        cfg = get_app_config()
        if cfg.app_database and cfg.app_database.url:
            return cfg.app_database.url
    except Exception:
        pass
    return "postgresql://localhost:5432/deerflow"


def _infer_group_name(skill_name: str) -> str:
    if skill_name.startswith("vasp-"):
        return "vasp"
    if skill_name.startswith("gaussian-"):
        return "gaussian"
    return "通用"


def _upsert_skill(conn, *, name: str, description: str, skill_dir: str, group_name: str = "通用") -> None:
    """Insert or refresh toolbox_skills.

    On UPDATE: refresh description/skill_dir/group only — do not overwrite laber_name /
    laber_description so existing Chinese labels and backfills stay intact.
    """
    slug = slugify_name(name)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM toolbox_skills
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
                name, slug, description, laber_name, laber_description, visibility, user_id, organization_id, group_name, skill_dir, enabled
            ) VALUES (%s, %s, %s, %s, %s, 'org', NULL, NULL, %s, %s, TRUE)
            """,
            (name, slug, description, name, description, group_name, skill_dir),
        )


def _is_under_root(skill_dir: Path, root: Path) -> bool:
    try:
        sdr = skill_dir.resolve()
        rr = root.resolve()
    except OSError:
        return False
    return sdr == rr or rr in sdr.parents


def main() -> None:
    """Sync toolbox_skills from disk-resolved runtime skills (public + custom).

    New skills get INSERTed; existing rows get description/skill_dir/group refreshed only,
    preserving laber_name / laber_description.
    """
    runtime_skills = load_skills(enabled_only=False)
    public_root = Path(__file__).resolve().parents[2] / "skills" / "public"
    custom_root = Path(__file__).resolve().parents[2] / "skills" / "custom"

    url = get_connection_url()
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgres://", 1)
    conn = get_app_db_connection(url)
    try:
        init_skills_tables(conn)

        with conn.cursor() as cur:
            cur.execute("DELETE FROM toolbox_skills WHERE name = %s", ("vaspagent",))

        for skill in runtime_skills:
            sd = Path(skill.skill_dir)
            if skill.category == "public" and _is_under_root(sd, public_root):
                group_name = _infer_group_name(skill.name)
                _upsert_skill(
                    conn,
                    name=skill.name,
                    description=skill.description or "",
                    skill_dir=str(skill.skill_dir),
                    group_name=group_name,
                )
            elif skill.category == "custom" and _is_under_root(sd, custom_root):
                _upsert_skill(
                    conn,
                    name=skill.name,
                    description=skill.description or "",
                    skill_dir=str(skill.skill_dir),
                    group_name="通用",
                )

        conn.commit()
        logger.info("Toolbox skills metadata initialized successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
