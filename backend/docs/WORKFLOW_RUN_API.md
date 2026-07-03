# 工作流执行接口 · 测试文档

本文档说明如何通过 HTTP 接口**创建运行、轮询状态、查看节点结果**，供联调与自动化测试使用。

实现位置：`backend/extensions/workflows/router.py`

---

## 1. 基础信息

| 项 | 说明 |
|----|------|
| 本地网关（Nginx） | `http://localhost:2026` |
| Gateway 直连 | `http://localhost:18084` |
| API 前缀 | `/api` |
| Content-Type | `application/json`（上传文件除外） |
| 认证 | `Authorization: Bearer <token>` |

> 推荐经 Nginx 访问：`http://localhost:2026/api/...`

### 认证

除部分只读接口外，**执行类接口必须登录**。请求头：

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

未登录返回 `401 Authentication required`；无权限访问他人工作流返回 `403`。

### 前置条件

1. **工作流已发布**：`workflows.current_release_id` 不为空（编辑器里点「发布」）。
2. **Workflow Worker 已启动**：`make start-with-nginx` 会启动 worker，日志见 `logs/workflow-worker.log`。
3. 创建运行后状态为 **`queued`**，由 worker 异步拉取并执行，变为 `running` → `success` / `failed`。

---

## 2. 接口一览（执行相关）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/workflows/{workflow_id}/runs` | **推荐** 创建一次运行（UI 同款） |
| `POST` | `/api/workflows/execute` | 兼容接口，创建运行 |
| `POST` | `/api/workflows/execute/stream` | 创建运行 + SSE 流式日志 |
| `GET` | `/api/workflows/{workflow_id}/runs` | 运行列表 |
| `GET` | `/api/workflows/{workflow_id}/runs/{run_id}` | 运行概要 |
| `GET` | `/api/workflows/{workflow_id}/runs/{run_id}/detail` | **推荐** 节点级详情（输入/输出） |
| `GET` | `/api/workflows/{workflow_id}/runs/{run_id}/tasks` | 节点任务列表 |
| `GET` | `/api/workflows/{workflow_id}/runs/{run_id}/logs` | 运行日志 |
| `GET` | `/api/workflows/{workflow_id}/runs/{run_id}/async-tasks` | 异步外部任务（VASP detach 等） |
| `POST` | `/api/workflows/{workflow_id}/runs/{run_id}/inputs` | 上传输入文件到 `work_root/inputs/` |
| `PATCH` | `/api/workflows/{workflow_id}/runs/{run_id}/input` | 合并更新 run.input |
| `POST` | `/api/workflows/{workflow_id}/runs/{run_id}/cancel` | 取消 |
| `POST` | `/api/workflows/{workflow_id}/runs/{run_id}/retry` | 重试（重置为 queued） |

---

## 3. 创建运行

### 3.1 标准接口（编辑器 / 前端使用）

```http
POST /api/workflows/{workflow_id}/runs
Content-Type: application/json
Authorization: Bearer <token>
```

**请求体**

```json
{
  "inputs": {
    "smiles": "*CC(*)c1ccccc1"
  },
  "source": "api",
  "thread_id": null
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `inputs` | object | 否 | 开始节点输入，键名与画布「开始节点」配置的字段一致（如 `smiles`、`poscar_path`） |
| `source` | string | 否 | 来源标识，默认 `ui`；传 `thread_id` 时默认 `chat` |
| `thread_id` / `threadId` | string | 否 | 关联对话线程 |

**成功响应 `200`**

```json
{
  "run_id": "f38c2f3b-e4b3-4e93-8fc5-db405a27216c",
  "status": "queued",
  "work_root": "/path/to/.deer-flow/users/{user_id}/workflow-runs/{run_id}"
}
```

**常见错误**

| HTTP | detail | 原因 |
|------|--------|------|
| 400 | `Workflow has no current_release_id; publish a release first` | 未发布 |
| 404 | `Workflow not found` | workflow_id 错误 |
| 401 | `Authentication required` | 未带 token |

**curl 示例**

```bash
export BASE=http://localhost:2026
export TOKEN="your-jwt-token"
export WF_ID="04bddde8-4881-478d-9847-93abdbccca90"

curl -sS -X POST "$BASE/api/workflows/$WF_ID/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs":{"smiles":"*CC(*)c1ccccc1"},"source":"api"}' | jq .
```

### 3.2 兼容接口

```http
POST /api/workflows/execute
POST /api/workflow/execute
```

**请求体**

```json
{
  "workflowId": "04bddde8-4881-478d-9847-93abdbccca90",
  "inputs": {
    "smiles": "*CC(*)c1ccccc1"
  },
  "useDraft": false,
  "draftId": null,
  "threadId": null,
  "files": null
}
```

| 字段 | 说明 |
|------|------|
| `useDraft` | `true` 时用草稿图编译临时 release（不更新 current_release） |
| `draftId` | 指定草稿 ID；省略则用当前 draft |
| `files` | 文件路径列表，会写入 `inputs.files` |

**成功响应**

```json
{
  "success": true,
  "result": {
    "run_id": "f38c2f3b-e4b3-4e93-8fc5-db405a27216c"
  }
}
```

### 3.3 流式执行（SSE）

```http
POST /api/workflows/execute/stream
POST /api/workflows/execute/stream
```

请求体与 `/execute` 相同。响应 `Content-Type: text/event-stream`。

**SSE 事件类型**

| type | 说明 |
|------|------|
| `run_start` | 开始，`run_id` |
| `log` | 节点/工作流日志，`event` 如 `node_start`、`node_end`、`workflow_end` |
| `run_end` | 结束，`success`、`status`（`success` / `failed` / `canceled`） |

**curl 示例**

```bash
curl -N -X POST "$BASE/api/workflows/execute/stream" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"workflowId\":\"$WF_ID\",\"inputs\":{\"smiles\":\"*CC(*)c1ccccc1\"}}"
```

---

## 4. 查询运行状态与结果

### 4.1 运行概要

```http
GET /api/workflows/{workflow_id}/runs/{run_id}
```

**响应片段**

```json
{
  "run": {
    "id": "f38c2f3b-e4b3-4e93-8fc5-db405a27216c",
    "workflow_id": "04bddde8-4881-478d-9847-93abdbccca90",
    "status": "success",
    "input": { "smiles": "...", "work_root": "..." },
    "output": { },
    "created_at": "2026-05-28T10:37:18",
    "started_at": "...",
    "finished_at": "..."
  }
}
```

**运行状态**

| status | 含义 |
|--------|------|
| `queued` | 已入队，等待 worker |
| `running` | 执行中 |
| `success` | 成功 |
| `failed` | 失败 |
| `canceled` | 已取消 |

### 4.2 节点详情（测试验收推荐）

```http
GET /api/workflows/{workflow_id}/runs/{run_id}/detail
```

**响应结构**

```json
{
  "run": { "id": "...", "status": "success", ... },
  "release_spec": { "nodes": [...], "edges": [...] },
  "node_index": {
    "9hkJfls-E7adfLL7IgB1M": {
      "node_name": "llm",
      "display_name": "LLM",
      "type": "llm",
      "skill": "vasp-potcar"
    }
  },
  "nodes": [
    {
      "node_id": "9hkJfls-E7adfLL7IgB1M",
      "node_name": "llm",
      "node_type": "llm",
      "skill": "vasp-potcar",
      "status": "success",
      "duration_ms": 26770,
      "input": {
        "model": "doubao-seed-1.8",
        "prompt": "请根据上游输入处理任务：nodes/.../result.POSCAR"
      },
      "output": {
        "output": {
          "POTCAR": { "file": "nodes/9hkJfls-E7adfLL7IgB1M/POTCAR" }
        },
        "resolved_inputs": {
          "prompt": "请根据上游输入处理任务：nodes/.../result.POSCAR"
        }
      },
      "error": null
    }
  ],
  "async_tasks": []
}
```

> **说明**：File 类型输出为相对路径 `{"file":"nodes/<node_id>/..."}`，相对 `work_root`。宿主机绝对路径在 `run.input.work_root` 下拼接。

### 4.3 节点任务列表

```http
GET /api/workflows/{workflow_id}/runs/{run_id}/tasks
```

返回原始 `node_tasks` 行，字段与 `detail.nodes` 类似，但不含 release 里的节点名称映射。

### 4.4 日志

```http
GET /api/workflows/{workflow_id}/runs/{run_id}/logs
GET /api/workflows/{workflow_id}/runs/{run_id}/logs?node_id={node_id}
```

### 4.5 异步任务

```http
GET /api/workflows/{workflow_id}/runs/{run_id}/async-tasks
```

用于 VASP detach 等长时间外部任务轮询。

---

## 5. 上传输入文件（可选）

若开始节点需要 POSCAR 等文件：

**Step 1** 创建运行，拿到 `run_id` 与 `work_root`。

**Step 2** 上传

```http
POST /api/workflows/{workflow_id}/runs/{run_id}/inputs
Content-Type: multipart/form-data
```

表单字段名：`files`（可多个）。

**Step 3**（可选）写入 input 引用

```http
PATCH /api/workflows/{workflow_id}/runs/{run_id}/input
Content-Type: application/json

{
  "inputs": {
    "poscar_path": { "file": "inputs/POSCAR" }
  }
}
```

> 仅在 `status` 为 `queued` 或 `running` 时可上传/修改。

---

## 6. 取消与重试

```bash
# 取消
curl -X POST "$BASE/api/workflows/$WF_ID/runs/$RUN_ID/cancel" \
  -H "Authorization: Bearer $TOKEN"

# 重试（清空 output/error，status → queued）
curl -X POST "$BASE/api/workflows/$WF_ID/runs/$RUN_ID/retry" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 7. 完整测试流程（SMILES → POSCAR → POTCAR 链路）

以下假设工作流已配置：开始(SMILES) → 工具(smiles_build) → LLM(vasp-potcar) → …

```bash
export BASE=http://localhost:2026
export TOKEN="your-jwt-token"
export WF_ID="your-workflow-uuid"

# 1. 创建运行
RESP=$(curl -sS -X POST "$BASE/api/workflows/$WF_ID/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs":{"smiles":"*CC(*)c1ccccc1"},"source":"api"}')
echo "$RESP" | jq .
RUN_ID=$(echo "$RESP" | jq -r .run_id)

# 2. 轮询直到结束（每 2 秒）
while true; do
  STATUS=$(curl -sS "$BASE/api/workflows/$WF_ID/runs/$RUN_ID" \
    -H "Authorization: Bearer $TOKEN" | jq -r .run.status)
  echo "status=$STATUS"
  case "$STATUS" in success|failed|canceled) break ;; esac
  sleep 2
done

# 3. 查看节点详情
curl -sS "$BASE/api/workflows/$WF_ID/runs/$RUN_ID/detail" \
  -H "Authorization: Bearer $TOKEN" | jq '.nodes[] | {node_name, skill, status, output}'

# 4. 查看 worker 日志（本地）
# tail -f logs/workflow-worker.log
```

### 验收检查清单

| 检查项 | 期望 |
|--------|------|
| `run.status` | `success` |
| 工具节点 output | 仅配置字段，如 `POSCAR: {"file":"nodes/.../outputs/result.POSCAR"}` |
| LLM 节点 `resolved_inputs.prompt` | 含 `nodes/...` 相对路径，不含 `/Users/...` |
| LLM 节点 output（POTCAR） | `{"file":"nodes/<llm_node_id>/POTCAR"}` |
| 磁盘 | `{work_root}/nodes/<id>/POTCAR` 存在 |

---

## 8. 使用草稿试跑（未发布时）

```json
POST /api/workflows/execute
{
  "workflowId": "...",
  "inputs": { "smiles": "CCO" },
  "useDraft": true
}
```

会从当前 draft 临时生成 release 执行，**不会**更新 `current_release_id`。适合开发调试；生产环境请先正式发布。

---

## 9. 常见问题

### Q: 返回 400「no current_release_id」

画布保存草稿后需 **发布 Release**，或测试时使用 `"useDraft": true`。

### Q: 一直 queued

检查 workflow worker 是否在跑：`logs/workflow-worker.log` 应有 `Acquired run: <run_id>`。

### Q: 节点 success 但 output 有 errors

看 `detail.nodes[].output`：LLM+skill 节点可能 skill 未生成文件（如 POSCAR 含 `*` 元素，vasp-potcar 无法解析）。此时 `run.status` 仍可能为 `success`，需按节点 output 判断业务是否成功。

### Q: 两个创建接口有什么区别？

| 接口 | 典型用途 |
|------|----------|
| `POST .../runs` | 前端编辑器、标准 REST |
| `POST .../execute` | Agent/Chat 兼容、支持 useDraft |
| `POST .../execute/stream` | 需要 SSE 实时日志 |

三者最终都调用 `WorkflowExecutor.create_run`，由同一 worker 执行。

---

## 10. 相关文件

| 文件 | 说明 |
|------|------|
| `backend/extensions/workflows/router.py` | 路由定义 |
| `backend/extensions/_core/workflow/runtime/executor.py` | 创建运行、SSE |
| `backend/extensions/_core/workflow/run_detail.py` | `/detail` 聚合 |
| `frontend/src/core/api/workflows.ts` | 前端封装 |
| `logs/workflow-worker.log` | Worker 执行日志 |
