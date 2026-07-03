# 工具 stdout JSON 信封（异步长任务）

工具在沙箱内完成「提交异步作业」后，应在 **stdout 的最后一行**（或可扫描到的最后一行 JSON 对象）输出下列契约之一。网关中间件 `AsyncTaskCaptureMiddleware` 会解析并写入 `async_tasks`。

## 轮询模式（`poll_command` 非空）

```json
{
  "status": "submitted",
  "task_kind": "vasp_relax",
  "external_ref": "113289082",
  "poll_interval_seconds": 1800,
  "poll_command": "python -m deerflow.vasp_skills_lib.cli poll --external-ref 113289082",
  "display_name": "Fe relax",
  "first_poll_delay_seconds": 0
}
```

- `status` 必须为 `"submitted"`。
- `task_kind` 必填（机器可读）。
- `poll_interval_seconds`：两次沙箱轮询之间的最小间隔（秒），默认 1800。
- `poll_command`：在 **该会话沙箱内** 可执行的完整 shell 命令；网关调度器只负责执行，不解析领域逻辑。  
  VASP 弛豫示例：`python /mnt/skills/public/vasp-relax/scripts/poll.py --work-dir <绝对路径> [--config ...]`
- `defer`: 若为 `false`，中间件**不**登记长任务（可选）。

## Webhook 模式（无沙箱轮询）

```json
{
  "status": "submitted",
  "task_kind": "vendor_xyz",
  "external_ref": "req_abc",
  "poll_interval_seconds": 604800,
  "poll_command": null,
  "callback_secret": "单次令牌"
}
```

- `poll_command` 为空或省略时，行状态记为 `awaiting_callback`；`next_poll_at` 用作回调截止时间（由 `poll_interval_seconds` 推导，默认 7 天量级）。
- 外部系统在作业完成后向网关  
  `POST /api/threads/{thread_id}/async_tasks/{task_id}/callback`  
  提交终态，并在启用密钥时携带 `callback_secret`。

## Poll 命令 stdout（网关解析最后一行 JSON）

| `status` / `phase`（poll 输出） | 写入 `async_tasks.status` |
|--------------------------------|---------------------------|
| submitted / running / pending  | running                   |
| completed / succeeded          | succeeded                 |
| failed                           | failed                    |
| cancelled                        | cancelled                 |
| timeout                          | timeout                   |

实现见 `deerflow.runtime.async_tasks.poll_status`。
