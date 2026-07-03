-- DeerFlow: generic conversation-scoped async tasks (poll / webhook).
-- Apply via: backend/scripts/init_app_database.py (create_async_tasks_tables)
-- Or manually: psql "$DATABASE_URL" -f backend/scripts/sql/async_tasks_pg.sql

CREATE TABLE IF NOT EXISTS async_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(64) NOT NULL,
    thread_id VARCHAR(64) NOT NULL,
    source_run_id VARCHAR(64),
    source_tool_call_id VARCHAR(128),
    task_kind VARCHAR(64) NOT NULL,
    display_name VARCHAR(256),
    status VARCHAR(32) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    poll_command TEXT,
    poll_interval_seconds INTEGER NOT NULL DEFAULT 1800,
    next_poll_at TIMESTAMPTZ,
    external_ref VARCHAR(512),
    result JSONB,
    error JSONB,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 10,
    heartbeat_at TIMESTAMPTZ,
    resume_run_id VARCHAR(64),
    terminal_followup_done BOOLEAN NOT NULL DEFAULT FALSE,
    callback_secret VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    workflow_run_id UUID REFERENCES workflow_runs(id) ON DELETE CASCADE,
    workflow_node_id VARCHAR(255)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_async_tasks_source_tool
ON async_tasks (thread_id, source_run_id, source_tool_call_id)
WHERE source_tool_call_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_async_tasks_thread_status_created
ON async_tasks (thread_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_async_tasks_user_thread
ON async_tasks (user_id, thread_id);

CREATE INDEX IF NOT EXISTS ix_async_tasks_next_poll_active
ON async_tasks (next_poll_at)
WHERE status IN ('queued', 'running', 'awaiting_callback');

CREATE INDEX IF NOT EXISTS ix_async_tasks_workflow_run
ON async_tasks (workflow_run_id, status, created_at DESC)
WHERE workflow_run_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_async_tasks_workflow_node_attempt
ON async_tasks (workflow_run_id, workflow_node_id, source_tool_call_id)
WHERE workflow_run_id IS NOT NULL AND source_tool_call_id IS NOT NULL;
