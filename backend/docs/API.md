# API Reference

This document provides a complete reference for the DeerFlow backend APIs.

## Overview

DeerFlow backend exposes two sets of APIs:

1. **LangGraph-compatible API** - Agent interactions, threads, and streaming (`/api/langgraph/*`)
2. **Gateway API** - Models, MCP, skills, uploads, and artifacts (`/api/*`)

All APIs are accessed through the Nginx reverse proxy at port 2026.

## LangGraph-compatible API

Base URL: `/api/langgraph`

The public LangGraph-compatible API follows LangGraph SDK conventions. In the unified nginx deployment, Gateway owns `/api/langgraph/*` and translates those paths to its native `/api/*` run, thread, and streaming routers.

### Threads

#### Create Thread

```http
POST /api/langgraph/threads
Content-Type: application/json
```

**Request Body:**
```json
{
  "metadata": {}
}
```

**Response:**
```json
{
  "thread_id": "abc123",
  "created_at": "2024-01-15T10:30:00Z",
  "metadata": {}
}
```

#### Get Thread State

```http
GET /api/langgraph/threads/{thread_id}/state
```

**Response:**
```json
{
  "values": {
    "messages": [...],
    "sandbox": {...},
    "artifacts": [...],
    "thread_data": {...},
    "title": "Conversation Title"
  },
  "next": [],
  "config": {...}
}
```

### Runs

#### Create Run

Execute the agent with input.

```http
POST /api/langgraph/threads/{thread_id}/runs
Content-Type: application/json
```

**Request Body:**
```json
{
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "Hello, can you help me?"
      }
    ]
  },
  "config": {
    "recursion_limit": 100,
    "configurable": {
      "model_name": "gpt-4",
      "thinking_enabled": false,
      "is_plan_mode": false
    }
  },
  "stream_mode": ["values", "messages-tuple", "custom"]
}
```

**Stream Mode Compatibility:**
- Use: `values`, `messages-tuple`, `custom`, `updates`, `events`, `debug`, `tasks`, `checkpoints`
- Do not use: `tools` (deprecated/invalid in current `langgraph-api` and will trigger schema validation errors)

**Recursion Limit:**

`config.recursion_limit` caps the number of graph steps LangGraph will execute
in a single run. The unified Gateway path defaults to `100` in
`build_run_config` (see `backend/app/gateway/services.py`), which is a safer
starting point for plan-mode or subagent-heavy runs. Clients can still set
`recursion_limit` explicitly in the request body; increase it if you run deeply
nested subagent graphs.

**Configurable Options:**
- `model_name` (string): Override the default model
- `thinking_enabled` (boolean): Enable extended thinking for supported models
- `is_plan_mode` (boolean): Enable TodoList middleware for task tracking

**Response:** Server-Sent Events (SSE) stream

```
event: values
data: {"messages": [...], "title": "..."}

event: messages
data: {"content": "Hello! I'd be happy to help.", "role": "assistant"}

event: end
data: {}
```

#### Get Run History

```http
GET /api/langgraph/threads/{thread_id}/runs
```

**Response:**
```json
{
  "runs": [
    {
      "run_id": "run123",
      "status": "success",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

#### Stream Run

Stream responses in real-time.

```http
POST /api/langgraph/threads/{thread_id}/runs/stream
Content-Type: application/json
```

Same request body as Create Run. Returns SSE stream.

---

## Gateway API

Base URL: `/api`

### Agents — synchronous chat (database-backed extensions)

**Availability:** Requires `app_database` / Postgres so Gateway registers `extensions` (`register_extensions`). Only **dedicated** agents support this route (not swarm orchestrators).

Runs one agent turn **to completion** and returns the final assistant text. Behaviour aligns with `POST /api/threads/{thread_id}/runs/stream` (`assistant_id`, `input.messages`, `context`, `config.recursion_limit`), but uses blocking completion instead of SSE.

#### `POST /api/agents/{agent_id}/chat`

**Path parameters**

| Name | Description |
|------|-------------|
| `agent_id` | UUID of the agent row in the `agents` table (same id as in workspace agent management). |

**Authentication**

Same as other protected Gateway routes: valid session (`access_token` cookie) or Bearer token from your auth extensions. State-changing **POST** from the browser also requires CSRF (`csrf_token` cookie + `X-CSRF-Token` header). Machine-to-machine callers typically use Bearer auth.

**Request body (JSON)**

Either a short **message** or a full **messages** array must be provided.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | One of `message` / `messages` | User text for this turn. If `messages` is set, `message` is ignored. Internally converted to the same structure as the web UI: `type: human` + `content: [{ type: text, text: ... }]`. |
| `messages` | array | One of `message` / `messages` | Full LangGraph-style `input.messages` list (same shape as `POST .../runs/stream`). Use this when you need multimodal blocks or multiple turns in `input`. |
| `thread_id` | string | no | Existing conversation thread id for multi-turn memory. Omit to start a **new** thread (server generates an id). Return `thread_id` from the response on the next call. |
| `model_name` | string | no | Model id from `config.yaml` (e.g. `doubao-seed-2.0`). |
| `model` | string | no | Alias for `model_name` (lead_agent `configurable`). |
| `mode` | string | no | Workspace product mode: `flash`, `pro`, `ultra`, `thinking`. Expands runtime flags like the frontend (`hooks.ts`). Ignored pieces can be overridden explicitly (below). |
| `reasoning_effort` | string | no | Overrides mode-derived value when set. |
| `thinking_enabled` | boolean | no | Overrides mode-derived value when set. |
| `is_plan_mode` | boolean | no | Overrides mode-derived value when set. |
| `subagent_enabled` | boolean | no | Overrides mode-derived value when set. |
| `max_concurrent_subagents` | integer | no | 1–50 when subagents are enabled. |
| `recursion_limit` | integer | no | Default **1000** (same order as typical UI runs). Graph step limit for one run. |

**`mode` defaults** (when explicit booleans / `reasoning_effort` are omitted)

| `mode` | `thinking_enabled` | `is_plan_mode` | `subagent_enabled` | `reasoning_effort` |
|--------|--------------------|----------------|----------------------|---------------------|
| `flash` | false | false | false | — |
| `pro` | true | true | false | `medium` |
| `ultra` | true | true | true | `high` |
| `thinking` | true | false | false | `low` |

**Response (`200`)**

```json
{
  "answer": "<final assistant plain text extracted from checkpoint>",
  "thread_id": "<thread id used for this run>",
  "run_id": "<optional run id for debugging>"
}
```

**Errors**

| HTTP | Typical cause |
|------|----------------|
| `401` | Not authenticated. |
| `404` | Agent not found or not owned by the caller. |
| `422` | Invalid `agent_id`, swarm agent (`chat` only supports dedicated agents), or validation error on body. |
| `502` | Run failed, or checkpoint could not be read after success. |

**Inline “物料库” / large payloads**

There is no separate file field: put catalog tables or constraints in **`message`** or **`messages`**. The model only sees what fits in its **context window**; very large pasted corpora may truncate—prefer uploads + thread attachments for huge files when supported.

**Example**

```http
POST /api/agents/550e8400-e29b-41d4-a716-446655440000/chat
Content-Type: application/json
Cookie: access_token=...; csrf_token=...
X-CSRF-Token: <same as csrf_token>
```

```json
{
  "message": "在上述物料清单内推荐连续流工艺配比，约束：…\n\n<物料库正文…>",
  "model_name": "doubao-seed-2.0",
  "mode": "pro",
  "thread_id": "optional-for-follow-up"
}
```

### Models

#### List Models

Get all available LLM models from configuration.

```http
GET /api/models
```

**Response:**
```json
{
  "models": [
    {
      "name": "gpt-4",
      "display_name": "GPT-4",
      "supports_thinking": false,
      "supports_vision": true
    },
    {
      "name": "claude-3-opus",
      "display_name": "Claude 3 Opus",
      "supports_thinking": false,
      "supports_vision": true
    },
    {
      "name": "deepseek-v3",
      "display_name": "DeepSeek V3",
      "supports_thinking": true,
      "supports_vision": false
    }
  ]
}
```

#### Get Model Details

```http
GET /api/models/{model_name}
```

**Response:**
```json
{
  "name": "gpt-4",
  "display_name": "GPT-4",
  "model": "gpt-4",
  "max_tokens": 4096,
  "supports_thinking": false,
  "supports_vision": true
}
```

### MCP Configuration

#### Get MCP Config

Get current MCP server configurations.

```http
GET /api/mcp/config
```

**Response:**
```json
{
  "mcpServers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "***"
      },
      "description": "GitHub operations"
    }
  }
}
```

#### Update MCP Config

Update MCP server configurations.

```http
PUT /api/mcp/config
Content-Type: application/json
```

**Request Body:**
```json
{
  "mcpServers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "$GITHUB_TOKEN"
      },
      "description": "GitHub operations"
    }
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "MCP configuration updated"
}
```

### Skills

#### List Skills

Get all available skills.

```http
GET /api/skills
```

**Response:**
```json
{
  "skills": [
    {
      "name": "pdf-processing",
      "display_name": "PDF Processing",
      "description": "Handle PDF documents efficiently",
      "enabled": true,
      "license": "MIT",
      "path": "public/pdf-processing"
    },
    {
      "name": "frontend-design",
      "display_name": "Frontend Design",
      "description": "Design and build frontend interfaces",
      "enabled": false,
      "license": "MIT",
      "path": "public/frontend-design"
    }
  ]
}
```

#### Get Skill Details

```http
GET /api/skills/{skill_name}
```

**Response:**
```json
{
  "name": "pdf-processing",
  "display_name": "PDF Processing",
  "description": "Handle PDF documents efficiently",
  "enabled": true,
  "license": "MIT",
  "path": "public/pdf-processing",
  "allowed_tools": ["read_file", "write_file", "bash"],
  "content": "# PDF Processing\n\nInstructions for the agent..."
}
```

#### Enable Skill

```http
POST /api/skills/{skill_name}/enable
```

**Response:**
```json
{
  "success": true,
  "message": "Skill 'pdf-processing' enabled"
}
```

#### Disable Skill

```http
POST /api/skills/{skill_name}/disable
```

**Response:**
```json
{
  "success": true,
  "message": "Skill 'pdf-processing' disabled"
}
```

#### Install Skill

Install a skill from a `.skill` file.

```http
POST /api/skills/install
Content-Type: multipart/form-data
```

**Request Body:**
- `file`: The `.skill` file to install

**Response:**
```json
{
  "success": true,
  "message": "Skill 'my-skill' installed successfully",
  "skill": {
    "name": "my-skill",
    "display_name": "My Skill",
    "path": "custom/my-skill"
  }
}
```

### File Uploads

#### Upload Files

Upload one or more files to a thread.

```http
POST /api/threads/{thread_id}/uploads
Content-Type: multipart/form-data
```

**Request Body:**
- `files`: One or more files to upload

**Response:**
```json
{
  "success": true,
  "files": [
    {
      "filename": "document.pdf",
      "size": 1234567,
      "path": ".deer-flow/threads/abc123/user-data/uploads/document.pdf",
      "virtual_path": "/mnt/user-data/uploads/document.pdf",
      "artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf",
      "markdown_file": "document.md",
      "markdown_path": ".deer-flow/threads/abc123/user-data/uploads/document.md",
      "markdown_virtual_path": "/mnt/user-data/uploads/document.md",
      "markdown_artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.md"
    }
  ],
  "message": "Successfully uploaded 1 file(s)"
}
```

**Supported Document Formats** (auto-converted to Markdown):
- PDF (`.pdf`)
- PowerPoint (`.ppt`, `.pptx`)
- Excel (`.xls`, `.xlsx`)
- Word (`.doc`, `.docx`)

#### List Uploaded Files

```http
GET /api/threads/{thread_id}/uploads/list
```

**Response:**
```json
{
  "files": [
    {
      "filename": "document.pdf",
      "size": 1234567,
      "path": ".deer-flow/threads/abc123/user-data/uploads/document.pdf",
      "virtual_path": "/mnt/user-data/uploads/document.pdf",
      "artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf",
      "extension": ".pdf",
      "modified": 1705997600.0
    }
  ],
  "count": 1
}
```

#### Delete File

```http
DELETE /api/threads/{thread_id}/uploads/{filename}
```

**Response:**
```json
{
  "success": true,
  "message": "Deleted document.pdf"
}
```

### Thread Cleanup

Remove DeerFlow-managed local thread files under `.deer-flow/threads/{thread_id}` after the LangGraph thread itself has been deleted.

```http
DELETE /api/threads/{thread_id}
```

**Response:**
```json
{
  "success": true,
  "message": "Deleted local thread data for abc123"
}
```

**Error behavior:**
- `422` for invalid thread IDs
- `500` returns a generic `{"detail": "Failed to delete local thread data."}` response while full exception details stay in server logs

### Artifacts

#### Get Artifact

Download or view an artifact generated by the agent.

```http
GET /api/threads/{thread_id}/artifacts/{path}
```

**Path Examples:**
- `/api/threads/abc123/artifacts/mnt/user-data/outputs/result.txt`
- `/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf`

**Query Parameters:**
- `download` (boolean): If `true`, force download with Content-Disposition header

**Response:** File content with appropriate Content-Type

---

## Error Responses

All APIs return errors in a consistent format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**HTTP Status Codes:**
- `400` - Bad Request: Invalid input
- `404` - Not Found: Resource not found
- `422` - Validation Error: Request validation failed
- `500` - Internal Server Error: Server-side error

---

## Authentication

DeerFlow enforces authentication for all non-public HTTP routes. Public routes are limited to health/docs metadata and these public auth endpoints:

- `POST /api/v1/auth/initialize` creates the first admin account when no admin exists.
- `POST /api/v1/auth/login/local` logs in with email/password and sets an HttpOnly `access_token` cookie.
- `POST /api/v1/auth/register` creates a regular `user` account and sets the session cookie.
- `POST /api/v1/auth/logout` clears the session cookie.
- `GET /api/v1/auth/setup-status` reports whether the first admin still needs to be created.

The authenticated auth endpoints are:

- `GET /api/v1/auth/me` returns the current user.
- `POST /api/v1/auth/change-password` changes password, optionally changes email during setup, increments `token_version`, and reissues the cookie.

Protected state-changing requests also require the CSRF double-submit token: send the `csrf_token` cookie value as the `X-CSRF-Token` header. Login/register/initialize/logout are bootstrap auth endpoints: they are exempt from the double-submit token but still reject hostile browser `Origin` headers.

User isolation is enforced from the authenticated user context:

- Thread metadata is scoped by `threads_meta.user_id`; search/read/write/delete APIs only expose the current user's threads.
- Thread files live under `{base_dir}/users/{user_id}/threads/{thread_id}/user-data/` and are exposed inside the sandbox as `/mnt/user-data/`.
- Memory and custom agents are stored under `{base_dir}/users/{user_id}/...`.

Note: MCP outbound connections can still use OAuth for configured HTTP/SSE MCP servers; that is separate from DeerFlow API authentication.

---

## Rate Limiting

No rate limiting is implemented by default. For production deployments, configure rate limiting in Nginx:

```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

location /api/ {
    limit_req zone=api burst=20 nodelay;
    proxy_pass http://backend;
}
```

---

## Streaming Support

Gateway's LangGraph-compatible API streams run events with Server-Sent Events (SSE):

```http
POST /api/langgraph/threads/{thread_id}/runs/stream
Accept: text/event-stream
```

---

## SDK Usage

### Python (LangGraph SDK)

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:2026/api/langgraph")

# Create thread
thread = await client.threads.create()

# Run agent
async for event in client.runs.stream(
    thread["thread_id"],
    "lead_agent",
    input={"messages": [{"role": "user", "content": "Hello"}]},
    config={"configurable": {"model_name": "gpt-4"}},
    stream_mode=["values", "messages-tuple", "custom"],
):
    print(event)
```

### JavaScript/TypeScript

```typescript
// Using fetch for Gateway API
const response = await fetch('/api/models');
const data = await response.json();
console.log(data.models);

// Create a run and stream SSE events
const streamResponse = await fetch(`/api/langgraph/threads/${threadId}/runs/stream`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  },
  body: JSON.stringify({
    input: { messages: [{ role: "user", content: "Hello" }] },
    stream_mode: ["values", "messages-tuple", "custom"],
  }),
});

const reader = streamResponse.body?.getReader();
// Decode and parse SSE frames from reader in your client code.
```

### cURL Examples

```bash
# List models
curl http://localhost:2026/api/models

# Get MCP config
curl http://localhost:2026/api/mcp/config

# Upload file
curl -X POST http://localhost:2026/api/threads/abc123/uploads \
  -F "files=@document.pdf"

# Enable skill
curl -X POST http://localhost:2026/api/skills/pdf-processing/enable

# Create thread and run agent
curl -X POST http://localhost:2026/api/langgraph/threads \
  -H "Content-Type: application/json" \
  -d '{}'

curl -X POST http://localhost:2026/api/langgraph/threads/abc123/runs \
  -H "Content-Type: application/json" \
  -d '{
    "input": {"messages": [{"role": "user", "content": "Hello"}]},
    "config": {
      "recursion_limit": 100,
      "configurable": {"model_name": "gpt-4"}
    }
  }'
```

> The unified Gateway path defaults `config.recursion_limit` to 100 for
> plan-mode and subagent-heavy runs. Clients may still set
> `config.recursion_limit` explicitly — see the [Create Run](#create-run)
> section for details.
