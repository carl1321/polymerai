#!/usr/bin/env python3
"""Backfill Chinese label fields for existing toolbox skills metadata."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deerflow.config.app_config import get_app_config
from deerflow.skills import load_skills
from extensions._core.app_db import get_app_db_connection
from extensions._core.llms.llm import get_llm_by_model_name
from extensions._core.skills_db import init_skills_tables

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _row_needs_backfill(row: dict, *, only_empty: bool) -> bool:
    """When only_empty: treat default INSERT (laber_name = skill id) as needing labels too."""
    if not only_empty:
        return True
    name = (row.get("name") or "").strip()
    laber_name = (row.get("laber_name") or "").strip()
    laber_desc = (row.get("laber_description") or "").strip()
    if not laber_name or not laber_desc:
        return True
    if laber_name.lower() == name.lower():
        return True
    return False


def _translate(skill_name: str, skill_md: str) -> tuple[str, str]:
    prompt = (
        "你是技能信息翻译助手。请根据给定的 SKILL.md 内容，输出中文技能名称和中文简介。"
        "返回严格 JSON，格式："
        '{"laber_name":"...","laber_description":"..."}。'
        "laber_name 不超过 20 字，laber_description 不超过 120 字。不要输出其他内容。"
    )
    content = (skill_md or "").strip()
    if len(content) > 6000:
        content = content[:6000]
    model_name = get_app_config().models[0].name
    llm = get_llm_by_model_name(model_name)
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
    if not isinstance(data, dict):
        return skill_name, ""
    name = str(data.get("laber_name") or "").strip() or skill_name
    desc = str(data.get("laber_description") or "").strip()
    return name, desc


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Chinese skill labels into toolbox_skills")
    parser.add_argument(
        "--only-empty",
        action="store_true",
        help=(
            "Only update rows that still look unlocalized: empty laber fields, or "
            "laber_name equals skill name (metadata init English placeholder)."
        ),
    )
    args = parser.parse_args()

    runtime_map = {s.name: s for s in load_skills(enabled_only=False)}
    conn = get_app_db_connection()
    try:
        init_skills_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, description, laber_name, laber_description
                FROM toolbox_skills
                ORDER BY updated_at DESC
                """
            )
            rows = cur.fetchall()

        updated = 0
        for row in rows:
            skill_name = row["name"]
            if not _row_needs_backfill(row, only_empty=args.only_empty):
                continue
            runtime_skill = runtime_map.get(skill_name)
            if not runtime_skill:
                continue
            skill_md_path = Path(runtime_skill.skill_dir) / "SKILL.md"
            if not skill_md_path.exists():
                continue
            skill_md = skill_md_path.read_text(encoding="utf-8")
            try:
                laber_name, laber_description = _translate(skill_name, skill_md)
            except Exception as e:
                logger.warning("Skip %s: translate failed: %s", skill_name, e)
                continue

            if args.only_empty:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE toolbox_skills
                        SET laber_name = %s,
                            laber_description = %s,
                            updated_at = now()
                        WHERE id = %s
                          AND (
                            COALESCE(TRIM(laber_name), '') = ''
                            OR COALESCE(TRIM(laber_description), '') = ''
                            OR LOWER(TRIM(COALESCE(laber_name, ''))) = LOWER(TRIM(name))
                          )
                        """,
                        (laber_name, laber_description, row["id"]),
                    )
                    changed = cur.rowcount > 0
            else:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE toolbox_skills
                        SET laber_name = %s,
                            laber_description = %s,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (laber_name, laber_description, row["id"]),
                    )
                    changed = cur.rowcount > 0
            conn.commit()
            if changed:
                updated += 1
                logger.info("Updated labels for skill: %s", skill_name)

        logger.info("Backfill complete. updated=%s", updated)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
