#!/usr/bin/env python3
"""从 agentic_workflow 数据库中读取工作流及草稿，插入到 deer-flow 数据库中。

源库（agentic_workflow）需有表：workflows、workflow_drafts，表结构与 deer-flow 一致或兼容。
每条工作流取 current_draft_id 对应的草稿，若无则取该 workflow_id 下最新一条 draft 的 graph 导入。

用法（在 backend 目录下）:
  uv run python scripts/import_workflows_from_agentic_db.py --source-db-url 'postgresql://user:pass@host:5432/agentic_db'
  uv run python scripts/import_workflows_from_agentic_db.py --source-db-url '...' --user-id <deer-flow用户UUID>
  uv run python scripts/import_workflows_from_agentic_db.py --source-db-url '...' --dry-run

依赖：deer-flow 使用 config.yaml 或 DEER_FLOW_APP_DATABASE_URL；users 表至少有一条用户（或通过 --user-id 指定）。
"""

import argparse
import json
import logging
import os
import sys
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_target_connection_url() -> str:
    """deer-flow 应用库连接 URL。"""
    url = os.environ.get("DEER_FLOW_APP_DATABASE_URL")
    if url:
        return url
    try:
        from deerflow.config.app_config import get_app_config
        cfg = get_app_config()
        if cfg.app_database and cfg.app_database.url:
            return cfg.app_database.url
    except Exception as e:
        logger.warning("Could not load config: %s", e)
    return "postgresql://localhost:5432/deerflow"


def _norm_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgres://", 1)
    return url


def load_workflows_from_source(source_conn) -> list[dict]:
    """
    从源库读取所有工作流及其要导入的草稿（current_draft 或最新 draft）。
    返回 [ { "name", "description", "status", "graph" }, ... ]
    """
    with source_conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, description, status, current_draft_id
            FROM workflows
            ORDER BY created_at
        """)
        workflows = [dict(row) for row in cur.fetchall()]

    out = []
    with source_conn.cursor() as cur:
        for w in workflows:
            wf_id = w["id"]
            draft_id = w.get("current_draft_id")
            if draft_id:
                cur.execute(
                    "SELECT id, graph FROM workflow_drafts WHERE id = %s",
                    (draft_id,),
                )
                row = cur.fetchone()
            else:
                row = None
            if not row:
                cur.execute("""
                    SELECT id, graph FROM workflow_drafts
                    WHERE workflow_id = %s
                    ORDER BY version DESC
                    LIMIT 1
                """, (wf_id,))
                row = cur.fetchone()
            if not row:
                logger.warning("Workflow %s (%s) has no draft, skip.", w.get("name"), wf_id)
                continue
            graph = row["graph"]
            if graph is None:
                graph = {}
            elif isinstance(graph, str):
                graph = json.loads(graph) if graph.strip() else {}
            elif not isinstance(graph, dict):
                graph = {}
            else:
                graph = dict(graph)
            nodes = graph.get("nodes") or []
            edges = graph.get("edges") or []
            out.append({
                "name": w.get("name") or "未命名工作流",
                "description": w.get("description"),
                "status": w.get("status") or "draft",
                "graph": {"nodes": nodes, "edges": edges},
            })
    return out


def get_first_user_id(conn) -> UUID | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")
        row = cur.fetchone()
    return row["id"] if row else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import workflows from agentic_workflow database into deer-flow database"
    )
    parser.add_argument(
        "--source-db-url",
        required=True,
        help="PostgreSQL URL of agentic_workflow database (e.g. postgresql://user:pass@host:5432/agentic_db)",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        help="deer-flow 中作为 created_by 的用户 UUID（默认取 users 表第一条）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list workflows that would be imported, do not write to deer-flow DB",
    )
    args = parser.parse_args()

    import psycopg
    from psycopg.rows import dict_row

    source_url = _norm_url(args.source_db_url.strip())
    logger.info("Connecting to source database (agentic_workflow)...")
    source_conn = psycopg.connect(source_url, row_factory=dict_row)
    try:
        workflows = load_workflows_from_source(source_conn)
    finally:
        source_conn.close()

    if not workflows:
        logger.warning("No workflows with drafts found in source database.")
        sys.exit(0)

    logger.info("Found %d workflow(s) to import.", len(workflows))
    if args.dry_run:
        for w in workflows:
            logger.info(
                "  - %s (status=%s, nodes=%d, edges=%d)",
                w["name"], w.get("status"), len(w["graph"]["nodes"]), len(w["graph"]["edges"]),
            )
        return

    target_url = _norm_url(get_target_connection_url())
    from extensions._core.app_db import get_app_db_connection
    from extensions._core.workflow.runtime import db as wf_db

    conn = get_app_db_connection(target_url)
    try:
        user_id = args.user_id
        if user_id:
            try:
                user_id = UUID(user_id)
            except ValueError:
                logger.error("Invalid --user-id UUID: %s", user_id)
                sys.exit(1)
        else:
            user_id = get_first_user_id(conn)
        if not user_id:
            logger.error(
                "No user in deer-flow database. Run init_app_database.py or pass --user-id."
            )
            sys.exit(1)

        for w in workflows:
            name = (w.get("name") or "未命名工作流").strip() or "未命名工作流"
            description = (w.get("description") or "").strip() or None
            graph = w["graph"]
            try:
                workflow_id = wf_db.create_workflow(
                    conn,
                    name=name,
                    description=description,
                    created_by=user_id,
                    status=w.get("status") or "draft",
                )
                wf_db.save_draft(
                    conn,
                    workflow_id=workflow_id,
                    graph=graph,
                    created_by=user_id,
                )
                conn.commit()
                logger.info("Imported workflow: %s (id=%s)", name, workflow_id)
            except Exception as e:
                conn.rollback()
                logger.exception("Failed to import workflow %s: %s", name, e)
                sys.exit(1)
    finally:
        conn.close()
    logger.info("Done. Imported %d workflow(s).", len(workflows))


if __name__ == "__main__":
    main()
