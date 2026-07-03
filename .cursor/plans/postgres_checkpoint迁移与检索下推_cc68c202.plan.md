---
name: Postgres checkpoint迁移与检索下推
overview: 将 checkpoint 持久化迁移到 PostgreSQL，并把线程检索改为基于服务端 CurrentUser.id 的存储层过滤/排序/分页；在线请求不再扫描 checkpointer，改为异步回填，确保现有功能行为不回退。
todos:
  - id: baseline-flow
    content: 梳理并冻结现有 thread/checkpoint 功能行为作为回归基线
    status: pending
  - id: switch-postgres
    content: 切换 checkpointer/store 到 PostgreSQL 并通过启动与连接验证
    status: pending
  - id: owner-consistency
    content: 确认 owner 写入统一为 CurrentUser.id 并覆盖所有入口
    status: pending
  - id: store-only-search
    content: 重构 /api/threads/search 为仅 Store 在线查询（过滤+排序+分页）
    status: pending
  - id: async-backfill
    content: 实现 checkpointer->store 异步回填任务及进度控制
    status: pending
  - id: deletion-guard
    content: 实现删除后防回填复活的 tombstone 或等效机制
    status: pending
  - id: regression-and-perf
    content: 执行功能回归与性能对比验收并准备发布
    status: pending
isProject: false
---

# PostgreSQL Checkpoint 与线程检索下推改造计划

## 目标与约束

- 目标：
  - 将 checkpointer 后端从 SQLite 切换为 PostgreSQL。
  - 线程列表查询改为“存储层按 owner + 更新时间排序 + 分页”，在线主路径不扫描 checkpointer。
  - checkpointer 仅用于运行态写入与异步回填。
- 约束：不影响现有功能（用户隔离、线程可见性、历史、重命名、删除、回滚语义保持）。

## 现状基线（关键代码）

- Runtime 初始化：[`/Users/carl/workspace/tools/deer-flow/backend/app/gateway/deps.py`]（`langgraph_runtime` 同时初始化 `checkpointer` 与 `store`）。
- Checkpointer provider：[`/Users/carl/workspace/tools/deer-flow/backend/packages/harness/deerflow/agents/checkpointer/async_provider.py`]（已支持 `postgres`）。
- Store provider：[`/Users/carl/workspace/tools/deer-flow/backend/packages/harness/deerflow/runtime/store/async_provider.py`]（与 checkpointer 同配置源）。
- 线程搜索主逻辑：[`/Users/carl/workspace/tools/deer-flow/backend/app/gateway/routers/threads.py`]（当前为 Store + checkpointer 在线补扫）。
- run 启动与 owner 写入：[`/Users/carl/workspace/tools/deer-flow/backend/app/gateway/services.py`]（`start_run` / `enforce_run_user_identity`）。
- 配置入口：[`/Users/carl/workspace/tools/deer-flow/config.yaml`]（`checkpointer` 段）。

## 实施步骤

### 1) PostgreSQL 持久化切换（先完成基础设施）

- 在 [`/Users/carl/workspace/tools/deer-flow/config.yaml`] 将 `checkpointer.type` 切到 `postgres`，设置 `connection_string`。
- 保持 `store` 继续跟随 `checkpointer` 配置（当前框架即如此），确保线程索引与 checkpoint 同后端。
- 启动期校验：确保 gateway/lifespan 能成功创建 `AsyncPostgresSaver` 与 `PostgresStore`。

### 2) 统一 owner 语义与写入入口（保持现有能力）

- 继续以服务端 `CurrentUser.id` 作为唯一 owner 权威来源。
- 保持 `start_run` 中对客户端 `user_id` 剥离与覆盖写入（checkpoint configurable + store metadata）。
- 对 `create_thread`、`update_thread_state`、rename/title 同步路径做回归，确保 owner 与标题等字段仍及时写入 store。

### 3) 线程搜索改为“仅 Store 在线查询”

- 重构 [`/Users/carl/workspace/tools/deer-flow/backend/app/gateway/routers/threads.py`] 的 `search_threads`：
  - 在线请求仅查询 store。
  - 过滤条件：owner（`CurrentUser.id`）、`status`、`metadata`。
  - 排序与分页在存储层或最小候选集内完成（避免全量扫 + 全量排序）。
- 保持返回结构与现有 API 响应兼容（字段不变、权限行为不变）。

### 4) 引入异步回填任务（替代在线补扫）

- 新增后台任务/作业：扫描 checkpointer，将缺失线程回填至 store（按 owner、title、updated_at 等最小必要字段）。
- 触发策略：
  - 启动后一次性回填（可分批）。
  - 周期增量回填（按时间窗/游标）。
- 幂等与安全：回填使用 upsert，避免重复写；记录进度游标。

### 5) 删除/回滚/历史一致性保护

- 删除线程后防止被回填“复活”：
  - 设计 tombstone（删除标记）或回填时跳过已删除 thread_id。
- 历史接口（`/history`）继续读取 checkpointer（功能保持），但列表接口不再依赖其在线扫描。
- rollback/cancel 流程保持原语义，仅验证后端切到 postgres 后行为一致。

### 6) 验证与发布

- 功能回归清单（必须全部通过）：
  - 登录后仅可见本人线程。
  - 新建线程、发消息、重命名、删除、回滚、历史查看。
  - Casdoor 场景 owner 一致性。
- 性能验收：
  - 对比 `/api/threads/search` 的 P50/P95、超时率、DB 查询耗时。
- 发布方式：
  - 先完成数据回填，再切换“在线仅 Store”路径，避免线程列表缺失窗口。

## 风险与兜底

- 风险：旧线程 owner 缺失、删除后复活、回填延迟导致短时不可见。
- 兜底：
  - 回填前做 owner 完整性审计；
  - 引入删除 tombstone；
  - 观察期强化日志与告警（回填失败、回填积压、search 结果异常降幅）。

## 验收标准

- 功能：与现网一致（不新增 4xx/5xx、权限隔离不退化）。
- 性能：`/api/threads/search` 明显降低长尾延迟。
- 可运维：PostgreSQL 持久化稳定，重启后线程与历史可持续访问。

