---
name: SSE 断线重连
overview: 产品定调——async_task 不需要 SSE 流式更新；以「跟进任务」（非实时流、按需 GET）为信号，再重连/挂载 Run 对话 SSE（joinStream、跟新 follow-up run）；thread 级 async_tasks/stream 可弱化或下线前端消费。
todos:
  - id: product-no-async-task-sse-stream
    content: 明确前端不依赖 async_task_update 的流式推送；任务状态以 GET /async_tasks 或进房/可见性触发刷新即可
    status: completed
  - id: follow-task-then-join-run
    content: 跟进任务后触发 joinStream：对齐现有 hooks 中 runs 列表找 running/pending + join(active.run_id)；覆盖「等待时断 Run、跟随后再挂上」流程
    status: completed
  - id: run-sse-reconnect-backoff
    content: Run 侧 SSE 断线重连（SDK/封装层或 join 重试、Last-Event-ID 若适用）；与 async_task 专线解耦
    status: completed
  - id: optional-remove-async-tasks-sse
    content: 评估移除或关闭 consumeThreadAsyncTasksSse 订阅；后端 _publish_update 仍可保留给其他客户端或后续再用
    status: completed
  - id: doc-async-vs-run-bridge
    content: STREAMING/API 短文说明：无流式诉求时为何可不订 async_task channel；follow-up run 与 join 的关系
    status: completed
  - id: doc-industry-alignment
    content: 将本节「业界续接」摘要并入 backend/docs/STREAMING.md 或 API 文档交叉链
    status: completed
isProject: true
---

# 定调：async_task 不要流式；跟进任务后重连 Run 会话

## 产品结论（按你最新表述）

- **async_task 不需要「流式更新」**：不要求用 **`GET …/async_tasks/stream`** 把每次 poll 推到前端；任务卡片/状态用 **拉取**（`GET …/async_tasks`）即可，粒度可以是 **进房一次、切回前台、用户点开任务区、或较长间隔的一次刷新**——**不是**用 SSE 模拟实时，也**不是**秒级列表「逼近」。
- **真正要的是 Run 对话会话**：在等待/断开后，**跟进任务**（知道有新进展、或有新的 `running` run）之后，**重新挂上 LangGraph 的 Run SSE**（`joinStream` / attach 已有逻辑），继续收 **follow-up run** 或 **仍在进行的 run** 的事件。

## 与旧计划的关系

- 先前强调的 **async_tasks SSE 断线重连 + Last-Event-ID**：在你当前定调下 **降级为可选**（仅当仍保留该订阅时才需要）；**主路径改为 Run 重连 + 按需 GET 任务列表**。
- **`async_task_started` 仍走 Run 的 `custom`**（见 [`async_task_capture_middleware.py`](backend/packages/harness/deerflow/agents/middlewares/async_task_capture_middleware.py)）：任务刚创建时若 Run 仍活跃，**一窗内**仍能收到，无需 thread SSE。
- **终态后的续对话**：后端已有 [`_start_terminal_followup`](backend/app/gateway/async_task_dispatcher.py) **新建 `lead_agent` run**；前端侧关键是 **runs 列表里发现新的 `running`/`pending` 后 `joinStream(run_id)`**——与现有 [`hooks.ts`](frontend/src/core/threads/hooks.ts) 里「无 lg:stream key 时拉 runs 再 join」同源，需把 **「跟进任务」** 明确接到这条链上（例如 GET 列表后发现新 run 或状态变化 → 调 `join`）。

## 实现要点（不写代码，仅边界）

| 环节 | 建议 |
|------|------|
| **跟进任务** | 用 **`GET /api/threads/{id}/async_tasks`**（或等价列表接口），触发条件：**进入线程、visibilitychange 回前台、手动刷新、或低频定时器（间隔可配得很大）**；满足「非流式、非逼近」。 |
| **重连 Run** | 依赖 **`run_id` + join**：同一活跃 run 断线 → `joinStream` + `Last-Event-ID`（若 SDK/网关支持）；**新 follow-up run** → 从 runs 列表取 `running` 再 join。 |
| **thread 级 `_publish_update`** | 可保留给网关/其它消费者；**前端可不订阅** `/async_tasks/stream`，从面向上减少一条长连接。 |

## 仍须对齐的细节（实现时核对）

- **「跟进」到「有可 join 的 run」的时差**：follow-up 创建后 runs API 何时可见；是否需在 GET 任务列表后 **invalidate 或顺带拉 runs**。
- **用户主动断开 Run 等待任务**：断开后仅靠 GET 跟进时，**何时**自动 `join`（例如仅当检测到新 run 或任务终态且 metadata 表明已有 follow-up）。

## 业界「会话续上 / 流式续接」常见做法（调研摘要）

**共识：「会话」= 持久状态（thread / conversation id）；「流」= 某个具体执行（run / completion）上的事件管道。** 续接很少指「抽象会话 socket」，而是 **对同一条仍活跃的 run 流重新订阅**，或 **发现新 run 再订阅**。

| 体系 | 常见做法 | 与 DeerFlow 的对应 |
|------|----------|-------------------|
| **LangGraph Platform / SDK** | HTTP **SSE**；事件带 **id**；断线后用 **`Last-Event-ID`** 再连同一资源；**`joinStream(threadId, runId)`** 订阅已有 run；JS SDK侧有 **自动重试 + lastEventId** 一类模式（`streamWithRetry` 等）。 | 网关已实现 **SSE + `format_sse` 带 event id**、[`sse_consumer` 读 `Last-Event-ID`](backend/app/gateway/services.py)、[`GET …/runs/{run_id}/join`](backend/app/gateway/routers/thread_runs.py)。前端用 **`@langchain/langgraph-sdk`** 的 `runs.stream` / `runs.joinStream`（见 [`api-client.ts`](frontend/src/core/api/api-client.ts) 包装）。文档已写 **Gateway 断连恢复 = Last-Event-ID**（[`STREAMING.md`](backend/docs/STREAMING.md) L28）。 |
| **经典 OpenAI Chat Completions 流** | **不支持**官方「断线从上一字节续传」；断了一般 **重试整次请求** 或 **放弃本次流、用非流式/历史拉齐**。 | 不适用「同一 completion id 续 SSE」；长任务场景应依赖 **checkpoint + 新 run / join**。 |
| **OpenAI Responses / WebSocket 等** | 用 **`previous_response_id`** 等把多轮执行链成会话；偏 **新请求续状态** 而非 TCP 式续流。 | 类似 **新 follow-up run** 仍挂在 **同一 `thread_id`**。 |
| **长后台 + 聊天 UI** | 后台任务状态用 **轮询/推送**；**模型输出**仍走 **单独一次 stream** 或 **新 run**。 | 与当前定调一致：**卡片 GET** + **Run SSE**；poll 驱动 **新 run** 时靠 **runs 列表 + join**。 |

**操作层建议（与主流对齐）：**

1. **同一 `run_id` 仍在 `running`**：优先 **SDK/浏览器自动重连 SSE + `Last-Event-ID`**（若 `useStream` 已持久化 last id）；网关侧缓冲见 `MemoryStreamBridge` 上限。  
2. **`run_id` 已结束、但有新 run**（含 poll/follow-up）：**不要用 Last-Event-ID 绑旧 run**；应 **`GET …/runs` → 选 active → `joinStream`**（与 [hooks 无 `lg:stream` 时的 attach](frontend/src/core/threads/hooks.ts) 一致）。  
3. **希望关页后同一 run 仍跑、回来还能收字**：服务端该 run 创建用 **`on_disconnect: continue`**；若用 **`cancel`**，则只能依赖 **新 run** 或 **用户再发**，与 LangGraph「可续订」语义一致。  
4. **async_tasks/thread SSE**：主流 **不把**「后台任务 poll」和 **「模型 token SSE」**绑成一条物理连接；本仓库维持 **Run 专线** 为主即可。

## 验证

- 关前端 async_tasks SSE（若实施）：长任务从 submitted → terminal → follow-up run 出现，**仅 GET + join** 是否仍能接上流式回复。  
- Run SSE 断网恢复：是否仍能 `joinStream` 续收同一 run 缓冲内事件（若有）。  
