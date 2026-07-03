# Backend tests

## Unit tests (default)

```bash
cd backend && make test
# or: uv run pytest
```

No database required. Covers envelope parsing, capture middleware, todo middleware, etc.

## Integration tests (`@pytest.mark.integration`)

Long-task poll + SSE + terminal follow-up paths need **PostgreSQL** with the `async_tasks` table.

### Environment

1. **PostgreSQL** reachable from the test host.
2. **`DATABASE_URL`** — async SQLAlchemy URL, e.g.  
   `postgresql+asyncpg://USER:PASS@127.0.0.1:5432/DBNAME`  
   If you only have `postgresql://...`, tests normalize to `postgresql+asyncpg://...`.
3. **DDL**: run once (or let tests create idempotently):  
   `psql "$DATABASE_URL" -f backend/scripts/sql/async_tasks_pg.sql`  
   or `python backend/scripts/init_app_database.py` (includes `async_tasks`).
4. **Dispatcher tick** (manual runs only): optional `DEER_FLOW_ASYNC_TASK_DISPATCH_TICK_SECONDS=2` for faster polling in dev.
5. **Sandbox**: integration tests **mock** the sandbox provider; a real gateway still needs a working sandbox image for production polling.

When `DATABASE_URL` is unset, integration tests **skip** (default CI unit job stays green).

### Run integration tests locally

```bash
export DATABASE_URL="postgresql+asyncpg://..."
cd backend && uv run pytest -m integration -q
```

### CI (GitHub Actions)

Workflow `.github/workflows/backend-integration-tests.yml` runs `pytest -m integration` with a Postgres 15 service on pushes/PRs that change `backend/**`.

## Manual SSE check (thread-level `async_task_update`)

With gateway running and auth as usual:

```bash
BASE="http://127.0.0.1:18084"   # or your gateway / nginx URL
THREAD_ID="your-thread-uuid"
curl -N -H "Authorization: Bearer YOUR_JWT" \
  "${BASE}/api/threads/${THREAD_ID}/async_tasks/stream"
```

Trigger a due poll (e.g. insert a row with `next_poll_at` in the past and valid `poll_command`, or wait for dispatcher). You should see SSE lines `event: custom` with JSON containing `"type":"async_task_update"`.

## UI / product note (polling visibility)

- **`async_task_started`** is published on the **run** channel (same SSE stream as the active chat); the web app shows a toast via `onCustomEvent` in `frontend/src/core/threads/hooks.ts`.
- **`async_task_update`** (each poll) is published on **`async_task:{thread_id}`**, consumed by `GET /api/threads/{thread_id}/async_tasks/stream`. The main chat stream does **not** subscribe to that URL today; showing live poll progress in the conversation pane would require wiring that stream (or merging events into the run stream).
