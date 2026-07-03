-- Workflow skills / thread mapping + async_tasks workflow columns.
-- Applied by init_app_database.py after base workflow tables exist.

ALTER TABLE workflow_runs
  ADD COLUMN IF NOT EXISTS thread_id VARCHAR(64),
  ADD COLUMN IF NOT EXISTS source VARCHAR(32) NOT NULL DEFAULT 'ui';

CREATE INDEX IF NOT EXISTS ix_workflow_runs_thread_id
  ON workflow_runs (thread_id, created_at DESC)
  WHERE thread_id IS NOT NULL;

ALTER TABLE async_tasks
  ADD COLUMN IF NOT EXISTS workflow_run_id UUID REFERENCES workflow_runs(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS workflow_node_id VARCHAR(255);

CREATE INDEX IF NOT EXISTS ix_async_tasks_workflow_run
  ON async_tasks (workflow_run_id, status, created_at DESC)
  WHERE workflow_run_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_async_tasks_workflow_node_attempt
  ON async_tasks (workflow_run_id, workflow_node_id, source_tool_call_id)
  WHERE workflow_run_id IS NOT NULL AND source_tool_call_id IS NOT NULL;

ALTER TABLE node_tasks
  ADD COLUMN IF NOT EXISTS async_task_id UUID REFERENCES async_tasks(id) ON DELETE SET NULL;
