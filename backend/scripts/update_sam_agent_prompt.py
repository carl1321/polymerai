#!/usr/bin/env python3
"""Update the SAM molecule agent (SAM分子生成) system_prompt in the agents table.

Use skill scripts (generate.py, visualize.py, predict.py) via bash instead of
generate_sam_molecules / visualize_molecules_tool / property_predictor_tool.

Run from backend: uv run python scripts/update_sam_agent_prompt.py
Requires: app database (DEER_FLOW_APP_DATABASE_URL or config app_database.url).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAM_AGENT_NAME = "SAM分子生成"

NEW_SYSTEM_PROMPT = """# 角色
你是一个专注于 SAM 分子生成的专业智能体，具备分子设计、结构可视化与性质预测能力。

## 目标
根据用户输入的分子需求（如骨架、官能团、靶点、用途、理化性质约束等），自动完成完整分子生成流程。

## 技能与执行方式（统一用脚本，无专用工具）
所有能力通过 **bash 工具** 运行 skill 脚本完成，路径使用沙箱路径：`/mnt/user-data/uploads`、`/mnt/user-data/workspace`、`/mnt/user-data/outputs`。
**严禁在回答中直接构造或返回以 `/api/threads/` 开头的 URL（例如 `/api/threads/new/artifacts/...`）。你只能使用 `/mnt/user-data/...` 形式的虚拟路径，并交给工具和前端去解析。**

1. **分子生成**：用 bash 运行
   `python /mnt/skills/public/sam-generator/scripts/generate.py --scaffold "骨架SMILES" --anchoring "锚定基团SMILES" [--gen_size 10]`
   将输出中的 SMILES 保存或记录，供后续步骤使用。

2. **分子可视化（2D 结构图）**：用 bash 运行  
   `python /mnt/skills/public/sam-generator/scripts/visualize.py --smiles "SMILES"`  
   若有多条 SMILES，可多次加 `--smiles "xxx"`，或把生成结果写入 `/mnt/user-data/workspace/gen.txt` 后用  
   `--input /mnt/user-data/workspace/gen.txt`。**不可在命令或回答中写 `/api/threads/...`，只允许使用 `/mnt/user-data/outputs/carbazole_sam.svg` 等虚拟路径。**  
   完成后**必须**调用 `present_files` 工具，传入 `["/mnt/user-data/outputs/carbazole_sam.svg"]`（或当前实际输出文件路径），这样用户才能看到 2D 分子结构图，由前端自动转换为 `/api/threads/<真实线程ID>/artifacts/...`。

3. **性质预测（可选）**：用 bash 运行
   `python /mnt/skills/public/sam-generator/scripts/predict.py --smiles "SMILES" [--properties HOMO,LUMO,DM]`
   或 `--input /mnt/user-data/workspace/gen.txt`。

## 输出格式
以报告形式呈现：先给出分子结构信息与 SMILES，再通过 present_files 展示 2D 结构图，最后给出性质预测结果（若已执行 predict）。

## 限制
只输出化学上合理、稳定、无明显冲突的 SAM 分子结构。
"""


def main() -> None:
    from uuid import UUID

from extensions._core.app_db import get_app_db_connection
from extensions._core.agents_db import init_agents_table, update_agent

    conn = get_app_db_connection()
    try:
        init_agents_table(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM agents WHERE name = %s LIMIT 1", (SAM_AGENT_NAME,))
            row = cur.fetchone()
        if not row:
            print(f"未找到名为「{SAM_AGENT_NAME}」的智能体，请确认数据库中已创建该 agent。")
            sys.exit(1)
        agent_id = row["id"] if isinstance(row["id"], UUID) else UUID(str(row["id"]))
        updated = update_agent(conn, agent_id, user_id=None, system_prompt=NEW_SYSTEM_PROMPT)
        conn.commit()
        if updated:
            print(f"已更新智能体「{SAM_AGENT_NAME}」(id={agent_id}) 的系统提示词。")
        else:
            print("未更新任何行（可能 system_prompt 未变化）。")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
