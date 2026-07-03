#!/usr/bin/env python3
"""Seed an example VASP band workflow (LLM + run_skill nodes). Run from backend/: uv run python scripts/seed_vasp_band_workflow.py"""

from __future__ import annotations

import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions._core.app_db import get_app_db_connection


def main() -> None:
    conn = get_app_db_connection()
    wf_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    user_id = "admin"
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"label": "开始", "nodeName": "开始"}},
            {
                "id": "relax",
                "type": "llm",
                "data": {
                    "label": "弛豫",
                    "nodeName": "弛豫",
                    "llmModel": "doubao-pro-32k",
                    "llmTools": ["run_skill"],
                    "llmSkill": "vasp-relax",
                    "llmPrompt": "对 {{开始.output.poscar_path}} 在 work_dir 下运行 vasp-relax，调用 run_skill。",
                    "outputFields": [
                        {"name": "contcar", "type": "string"},
                        {"name": "work_dir", "type": "string"},
                        {"name": "success", "type": "boolean"},
                    ],
                },
            },
            {"id": "end", "type": "end", "data": {"label": "结束", "nodeName": "结束"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "relax"},
            {"id": "e2", "source": "relax", "target": "end"},
        ],
    }
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workflows (id, name, description, status, created_by, updated_by)
                VALUES (%s, %s, %s, 'draft', %s, %s)
                """,
                (wf_id, "VASP 能带示例", "LLM+run_skill 示例（需发布后运行）", user_id, user_id),
            )
            cur.execute(
                """
                INSERT INTO workflow_drafts (id, workflow_id, graph, version, created_by, updated_by)
                VALUES (%s, %s, %s, 1, %s, %s)
                """,
                (draft_id, wf_id, json.dumps(graph), user_id, user_id),
            )
        conn.commit()
        print(f"Created workflow {wf_id} draft {draft_id}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
