#!/usr/bin/env python3
"""从本地 agentic_workflow 库中读取工作流配置，插入当前 deer-flow 数据库。

支持：
  - 单个 JSON 文件：内容为单个工作流 { "name", "description?", "graph": { "nodes", "edges" } }
    或工作流数组 [ { "name", "description?", "graph": { "nodes", "edges" } }, ... ]
  - 目录：遍历目录下所有 .json 文件，每个文件视为一个工作流（文件名可作为 name 备选）

图结构：graph 可为 { "nodes": [], "edges": [] } 或直接 { "nodes": [], "edges": [] } 在顶层。

用法（在 backend 目录下）:
  uv run python scripts/import_workflows_from_agentic.py --source /path/to/agentic_workflow
  uv run python scripts/import_workflows_from_agentic.py --source /path/to/workflows.json
  uv run python scripts/import_workflows_from_agentic.py --source /path/to/agentic_workflow --user-id <uuid>

依赖：DEER_FLOW_APP_DATABASE_URL 或 config.yaml 中 app_database.url；users 表至少有一条用户。
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    except Exception as e:
        logger.warning("Could not load config: %s", e)
    return "postgresql://localhost:5432/deerflow"


def normalize_graph(obj: dict) -> dict:
    """从对象中取出 graph：支持 graph 键或顶层 nodes/edges。"""
    if "graph" in obj and isinstance(obj["graph"], dict):
        g = obj["graph"]
    else:
        g = obj
    nodes = g.get("nodes")
    edges = g.get("edges")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    return {"nodes": nodes, "edges": edges}


def collect_workflows_from_path(source: Path) -> list[dict]:
    """从文件或目录收集工作流列表。每项为 { "name", "description?", "graph" }。"""
    out = []
    if source.is_file():
        with open(source, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list):
            for i, item in enumerate(raw):
                if not isinstance(item, dict):
                    logger.warning("Skip non-object item at index %s in %s", i, source)
                    continue
                graph = normalize_graph(item)
                name = item.get("name") or item.get("workflow_name") or source.stem
                if isinstance(name, str):
                    name = name.strip() or source.stem
                else:
                    name = source.stem
                out.append({
                    "name": name,
                    "description": item.get("description") or item.get("workflow_description"),
                    "graph": graph,
                })
        else:
            graph = normalize_graph(raw)
            name = raw.get("name") or raw.get("workflow_name") or source.stem
            if isinstance(name, str):
                name = name.strip() or source.stem
            else:
                name = source.stem
            out.append({
                "name": name,
                "description": raw.get("description") or raw.get("workflow_description"),
                "graph": graph,
            })
        return out

    if source.is_dir():
        # 常见工作流存放位置（优先）；再回退到目录下所有 .json（排除已知非工作流文件）
        skip_names = {"package.json", "package-lock.json", "pnpm-lock.yaml", "tsconfig.json", "thread.json"}
        candidates: list[Path] = []
        for sub in ("workflows", "data/workflows", "data", "frontend/public/workflows"):
            d = source / sub
            if d.is_dir():
                candidates.extend(d.glob("*.json"))
        if not candidates:
            for p in source.rglob("*.json"):
                if p.name.lower() in skip_names:
                    continue
                candidates.append(p)
        seen = set()
        for p in sorted(set(candidates)):
            if p in seen:
                continue
            seen.add(p)
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception as e:
                logger.warning("Skip %s: %s", p, e)
                continue
            if not isinstance(raw, dict):
                logger.warning("Skip %s: not a JSON object", p)
                continue
            graph = normalize_graph(raw)
            if not graph["nodes"] and not graph["edges"]:
                logger.debug("Skip %s: empty nodes and edges", p)
                continue
            name = raw.get("name") or raw.get("workflow_name") or p.stem
            if isinstance(name, str):
                name = name.strip() or p.stem
            else:
                name = p.stem
            out.append({
                "name": name,
                "description": raw.get("description") or raw.get("workflow_description"),
                "graph": graph,
            })
        return out

    logger.error("Source is not a file or directory: %s", source)
    return []


def get_first_user_id(conn) -> UUID | None:
    """返回 users 表中第一个用户的 id。"""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")
        row = cur.fetchone()
    if row:
        return row["id"]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Import workflows from agentic_workflow into deer-flow DB")
    parser.add_argument("--source", required=True, type=Path, help="Path to agentic_workflow repo root or a JSON file/dir of workflows")
    parser.add_argument("--user-id", type=str, help="UUID of user as created_by (default: first user in users table)")
    parser.add_argument("--dry-run", action="store_true", help="Only list workflows that would be imported, do not write DB")
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.exists():
        logger.error("Source does not exist: %s", source)
        sys.exit(1)

    workflows = collect_workflows_from_path(source)
    if not workflows:
        logger.warning("No workflows found under %s", source)
        sys.exit(0)

    logger.info("Found %d workflow(s) to import.", len(workflows))
    if args.dry_run:
        for w in workflows:
            logger.info("  - %s (nodes=%d, edges=%d)", w["name"], len(w["graph"]["nodes"]), len(w["graph"]["edges"]))
        return

    url = get_connection_url()
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgres://", 1)
    from extensions._core.app_db import get_app_db_connection
    from extensions._core.workflow.runtime import db as wf_db

    conn = get_app_db_connection(url)
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
            logger.error("No user in database. Run init_app_database.py to seed users, or pass --user-id.")
            sys.exit(1)

        for w in workflows:
            name = w["name"]
            description = (w.get("description") or "").strip() or None
            graph = w["graph"]
            try:
                workflow_id = wf_db.create_workflow(
                    conn, name=name, description=description, created_by=user_id
                )
                wf_db.save_draft(conn, workflow_id=workflow_id, graph=graph, created_by=user_id)
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
