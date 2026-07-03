# 会话 thread_id / user_id 与数据表对应关系

## 核心概念

| 字段 | 含义 |
|------|------|
| **`thread_id`** | 一条聊天会话的全局主键（UUID 字符串）。前端路由 `/workspace/chats/{thread_id}` 即此值。 |
| **`user_id`** | 该会话归属的登录用户，必须与扩展认证写入的 **`users.id`**（字符串形式的 UUID）一致。 |

所有「聊天链路」表通过 **相同的 `thread_id`** 指向同一会话；通过 **`user_id`** 做租户隔离（列表与部分查询会按当前用户过滤）。

## 表与用途（`public` schema，不含 workflow_ckpt）

| 存储 | 作用 |
|------|------|
| **`threads_meta`** | 会话列表来源：`thread_id` PK，`user_id` 列表示所有者；`metadata_json` / `display_name` 等为展示字段。 |
| **`checkpoints`** | LangGraph 状态：`thread_id` + `checkpoint_ns`（聊天默认为 `''`）+ `checkpoint_id`。对话消息在 **`checkpoint` JSON 的 `channel_values.messages`**。`metadata` JSON 里需有 **`user_id`**，供网关做归属校验（Postgres 加载时不会在 `config.configurable` 里带 `user_id`）。 |
| **`store`** | LangGraph Store：`prefix = 'threads'`（对应代码里 namespace `("threads",)`），**`key = thread_id`**。`value.metadata.user_id` 参与归属判断。 |
| **`runs`** | 每次 **run** 一条记录：`run_id` PK，**`thread_id`** 外联会话。**`GET /api/threads/{id}/runs` 会执行 `WHERE thread_id = ? AND user_id = 当前用户`**；若 **`runs.user_id` 为 NULL 或与当前用户不一致，列表为空**（仍返回 200 + `[]`）。 |
| **`run_events`** | 运行过程事件流（历史消息条目的另一来源）；同样按 **`thread_id` / `user_id`** 过滤；NULL `user_id` 会导致按用户查询时拿不到数据。 |

## 为何「接口 200 但 runs / history 为空」

1. **`runs` / `run_events` 的 `user_id` 为 NULL 或与登录用户不一致**  
   SQL 过滤使用等值比较，`NULL` 永远不会匹配当前用户 UUID → **`/runs` 为空数组**。

2. **`threads_meta.user_id` 为空**  
   依赖 `threads_meta` 作为权威的回填脚本无法推导所有者 → 需先从 **`checkpoints.metadata->user_id`** 等指标回填 **`threads_meta.user_id`**，再统一其它表。

3. **checkpoint 侧 `metadata.user_id` 与 Store 不一致**  
   可能导致归属校验失败或行为异常；应对齐到与 **`threads_meta.user_id`** 一致。

4. **`POST .../history` 与 checkpoint**  
   若库中 **不存在** 该 `thread_id` 的 checkpoint 行，history 返回 **200 + `[]`**（无报错）。

## 运维脚本

在项目根目录执行（连接与 `config.yaml` 中 `database.postgres_url` 一致的数据库）：

```bash
cd backend && uv run python scripts/normalize_chat_owner_from_threads_meta.py --dry-run
uv run python scripts/normalize_chat_owner_from_threads_meta.py
```

脚本会先尝试用 **`checkpoints.metadata.user_id`** 补 **`threads_meta.user_id`**（仅当该列为空），再把 **checkpoints / store / runs / run_events** 上的 `user_id` 与 **`threads_meta`** 对齐。

若 **`threads_meta` 与 `checkpoints.metadata` 都没有可用 `user_id`**，需先在 `threads_meta` 手工写入与 `users.id` 一致的所有者，再执行脚本做全表传播。
