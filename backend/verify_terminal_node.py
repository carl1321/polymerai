# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""手动验证脚本：真实跑一遍带 output_parser 节点的工作流并检查三处保存。

用法（在 backend 目录）：
    PYTHONPATH=. DEER_FLOW_CONFIG_PATH="../config.yaml" \
    DEER_FLOW_APP_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/polymerai_agent" \
    uv run python verify_terminal_node.py

默认跑完会清理种下的测试数据；设置 KEEP=1 可保留以便自行在库里查看。
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid

from extensions._core.workflow.run_detail import build_run_detail_payload
from extensions._core.workflow.runtime.db import get_db_connection
from extensions._core.workflow.runtime.executor import get_workflow_executor


def seed(conn, work_root: str):
    wf_id, rel_id, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    spec = {
        "name": "__terminal_verify__",
        "nodes": [
            {"id": "start1", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "开始"}},
            {"id": "parser1", "type": "output_parser", "position": {"x": 200, "y": 0},
             "data": {"label": "终态解析", "saveAll": True}},
            {"id": "end1", "type": "end", "position": {"x": 400, "y": 0}, "data": {"label": "结束"}},
        ],
        "edges": [
            {"id": "e1", "source": "start1", "target": "parser1"},
            {"id": "e2", "source": "parser1", "target": "end1"},
        ],
    }
    inputs = {
        "input": "hello world",
        "work_root": work_root,
        "poscar_path": os.path.join(work_root, "POSCAR"),  # 让 start 节点产出一个文件引用
    }
    cur = conn.cursor()
    cur.execute("INSERT INTO workflows(id,name,created_by) VALUES(%s,%s,%s)", (wf_id, "__terminal_verify__", "tester"))
    cur.execute(
        "INSERT INTO workflow_releases(id,workflow_id,release_version,spec,created_by) VALUES(%s,%s,%s,%s,%s)",
        (rel_id, wf_id, 1, json.dumps(spec), "tester"),
    )
    cur.execute(
        "INSERT INTO workflow_runs(id,workflow_id,release_id,status,input,created_by,source) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (run_id, wf_id, rel_id, "queued", json.dumps(inputs), "tester", "test"),
    )
    conn.commit()
    return wf_id, rel_id, run_id


def inspect(conn, run_id):
    cur = conn.cursor()
    cur.execute("SELECT node_id,status,output FROM node_tasks WHERE run_id=%s ORDER BY run_seq", (run_id,))
    tasks = cur.fetchall()
    cur.execute("SELECT event FROM run_logs WHERE run_id=%s ORDER BY seq", (run_id,))
    events = [r["event"] for r in cur.fetchall()]
    cur.execute("SELECT status,output FROM workflow_runs WHERE id=%s", (run_id,))
    run = cur.fetchone()

    print("\n===== 验证结果 =====")
    print("run 状态:", run["status"])
    parser = next((t for t in tasks if t["node_id"] == "parser1"), None)
    nt_ok = bool(parser and parser["output"] and "__terminal__" in parser["output"])
    print("1) node_tasks[parser1].output 含 __terminal__ :", nt_ok)
    if nt_ok:
        term = parser["output"]["__terminal__"]
        print("     saved_node_ids:", term["saved_node_ids"], "| file_count:", term["file_count"])
        for n in term["nodes"]:
            print("     - 节点", n["node_id"], "类型", n["node_type"], "文件:", [f["filename"] + ("(存在)" if f["exists"] else "(缺失)") for f in n["files"]])
    print("2) run_logs 事件序列:", events, "| 含 terminal_output_parsed:", "terminal_output_parsed" in events)
    # workflow_runs.output 是按 node_id 索引的全量输出，解析结构位于 output[parser1].__terminal__
    wr_out = run["output"] or {}
    wr_ok = isinstance(wr_out.get("parser1"), dict) and "__terminal__" in wr_out["parser1"]
    print("3) workflow_runs.output[parser1] 含 __terminal__ :", wr_ok)

    detail = build_run_detail_payload(dict(run), None, [dict(t) for t in tasks], [])
    print("4) run_detail 节点数:", len(detail["nodes"]))
    print("\n==> 三处保存全部通过:", nt_ok and ("terminal_output_parsed" in events) and wr_ok)


def main():
    work_root = tempfile.mkdtemp(prefix="terminal_verify_")
    with open(os.path.join(work_root, "POSCAR"), "w") as f:
        f.write("sample structure\n")

    conn = get_db_connection()
    wf_id, rel_id, run_id = seed(conn, work_root)
    print("已种下测试数据 run_id =", run_id)
    print("正在执行工作流（真实 compile + graph run + DB 持久化）...")
    asyncio.run(get_workflow_executor().execute_run(run_id))
    inspect(conn, run_id)

    if os.environ.get("KEEP") == "1":
        print("\nKEEP=1，保留数据。run_id =", run_id)
    else:
        cur = conn.cursor()
        cur.execute("DELETE FROM workflows WHERE id=%s", (wf_id,))
        cur.execute("DELETE FROM workflow_releases WHERE id=%s", (rel_id,))
        conn.commit()
        print("\n已清理测试数据。")
    conn.close()


if __name__ == "__main__":
    main()
