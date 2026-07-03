#!/usr/bin/env python3
"""Initialize application database (all agentic_workflow-related tables + seed users).

Creates: RBAC (organizations, departments, users, roles, permissions, user_roles,
role_permissions, menus, role_menus, user_sessions), workflows, workflow_drafts,
workflow_releases, workflow_runs, node_tasks, run_logs, chat_streams,
data_extraction_*, tool_run_history, sam_design_history, new_sam_execution_history,
async_tasks (对话长任务；DDL 见 scripts/sql/async_tasks_pg.sql，勿依赖网关运行时 create_all).
Seeds users: admin (superuser) and zxw, both password 123456.

Run from backend directory: uv run python scripts/init_app_database.py
Or from repo root: cd backend && uv run python scripts/init_app_database.py

Requires: PostgreSQL running; database must exist (e.g. createdb deerflow).
Config: DEER_FLOW_APP_DATABASE_URL or app_database.url in config.yaml.
"""

import logging
import os
import re
import sys
from pathlib import Path

# Ensure backend src is on path when run as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_SCRIPTS_DIR = Path(__file__).resolve().parent


def _execute_pg_sql_file(conn, sql_path: Path) -> None:
    """Run a PostgreSQL DDL file as semicolon-separated statements (no runtime ORM)."""
    raw = sql_path.read_text(encoding="utf-8")
    lines: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("--"):
            continue
        lines.append(line)
    text = "\n".join(lines)
    parts = [p.strip() for p in re.split(r"\s*;\s*", text) if p.strip()]
    with conn.cursor() as cur:
        for stmt in parts:
            cur.execute(stmt)
    conn.commit()


def create_async_tasks_tables(conn) -> None:
    """Create ``async_tasks`` and indexes (PostgreSQL only)."""
    sql_path = _SCRIPTS_DIR / "sql" / "async_tasks_pg.sql"
    if not sql_path.is_file():
        logger.warning("async_tasks DDL file missing: %s", sql_path)
        return
    _execute_pg_sql_file(conn, sql_path)
    logger.info("async_tasks table created (from %s).", sql_path.name)


def apply_workflow_skills_mapping(conn) -> None:
    """Extend workflow_runs / async_tasks / node_tasks for skills + detach."""
    sql_path = _SCRIPTS_DIR / "sql" / "workflow_skills_mapping.sql"
    if not sql_path.is_file():
        logger.warning("workflow_skills_mapping DDL missing: %s", sql_path)
        return
    _execute_pg_sql_file(conn, sql_path)
    logger.info("workflow skills mapping applied (from %s).", sql_path.name)


def get_connection_url() -> str:
    url = os.environ.get("DEER_FLOW_APP_DATABASE_URL")
    if url:
        return url
    try:
        from deerflow.config.app_config import get_app_config

        cfg = get_app_config()
        if cfg.app_database and cfg.app_database.url:
            return cfg.app_database.url
        database_cfg = getattr(cfg, "database", None)
        if database_cfg is not None and getattr(database_cfg, "backend", None) == "postgres":
            postgres_url = getattr(database_cfg, "postgres_url", "")
            if isinstance(postgres_url, str) and postgres_url.strip():
                return postgres_url
        checkpointer = getattr(cfg, "checkpointer", None)
        if checkpointer is not None and getattr(checkpointer, "type", None) == "postgres":
            conn_str = getattr(checkpointer, "connection_string", "") or ""
            if conn_str.strip():
                return conn_str
    except Exception as e:
        logger.warning("Could not load config: %s", e)
    return "postgresql://localhost:5432/deerflow"


def upgrade_users_harness_auth_columns(conn) -> None:
    """Add DeerFlow harness auth columns to the shared ``users`` table (idempotent).

    Extensions RBAC uses ``username`` / ``is_superuser``; gateway local auth reads
    ``system_role``, ``oauth_*``, ``needs_setup``, and ``token_version`` via UserRow.
    """
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS system_role VARCHAR(16)")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider VARCHAR(32)")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_id VARCHAR(128)")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS needs_setup BOOLEAN")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER")
        cur.execute(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'is_superuser'
              ) THEN
                UPDATE users
                SET system_role = 'admin'
                WHERE is_superuser = true
                  AND (system_role IS NULL OR system_role = 'user');
              END IF;
            END
            $$;
            """
        )
        cur.execute("UPDATE users SET system_role = 'user' WHERE system_role IS NULL")
        cur.execute("UPDATE users SET needs_setup = FALSE WHERE needs_setup IS NULL")
        cur.execute("UPDATE users SET token_version = 0 WHERE token_version IS NULL")
        cur.execute(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'oauth_provider'
              ) AND EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'oauth_id'
              ) THEN
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_oauth_identity
                ON users (oauth_provider, oauth_id)
                WHERE oauth_provider IS NOT NULL AND oauth_id IS NOT NULL;
              END IF;
            END
            $$;
            """
        )
    conn.commit()
    logger.info("users harness auth columns upgraded (system_role, oauth_*, needs_setup, token_version).")


def create_user_tables(conn) -> None:
    """Create organizations, users, departments, roles, permissions, user_roles, role_permissions, user_sessions.
    Order avoids circular FK: orgs -> users (org_id only) -> departments (manager_id -> users) -> ALTER users dept_id.
    """
    with conn.cursor() as cur:
        # 1. organizations
        cur.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code VARCHAR(100) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                parent_id UUID,
                sort_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                FOREIGN KEY (parent_id) REFERENCES organizations(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_organizations_code ON organizations(code);
            CREATE INDEX IF NOT EXISTS idx_organizations_parent_id ON organizations(parent_id);
        """)

        # 2. users (only org FK; department_id column added later to avoid circular FK)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                username VARCHAR(255) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                real_name VARCHAR(255),
                phone VARCHAR(50),
                organization_id UUID,
                department_id UUID,
                is_superuser BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                data_permission_level VARCHAR(20) DEFAULT 'self',
                last_login_at TIMESTAMP WITH TIME ZONE,
                ragflow_key TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_organization_id ON users(organization_id);
            CREATE INDEX IF NOT EXISTS idx_users_department_id ON users(department_id);
        """)

        # 3. departments (manager_id -> users)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS departments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code VARCHAR(100) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                organization_id UUID NOT NULL,
                parent_id UUID,
                manager_id UUID,
                sort_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES departments(id) ON DELETE SET NULL,
                FOREIGN KEY (manager_id) REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_departments_code ON departments(code);
            CREATE INDEX IF NOT EXISTS idx_departments_organization_id ON departments(organization_id);
            CREATE INDEX IF NOT EXISTS idx_departments_parent_id ON departments(parent_id);
        """)

        # 4. users.department_id FK (add if not exists)
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE table_name = 'users' AND constraint_name = 'users_department_id_fkey'
                ) THEN
                    ALTER TABLE users ADD CONSTRAINT users_department_id_fkey
                    FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL;
                END IF;
            END $$;
        """)

        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'ragflow_key'
                ) THEN
                    ALTER TABLE users ADD COLUMN ragflow_key TEXT;
                END IF;
            END $$;
        """)

        # 5. roles
        cur.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code VARCHAR(100) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                organization_id UUID,
                data_permission_level VARCHAR(20) DEFAULT 'self',
                is_system BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_roles_code ON roles(code);
            CREATE INDEX IF NOT EXISTS idx_roles_organization_id ON roles(organization_id);
        """)

        # 6. permissions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS permissions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code VARCHAR(100) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                resource VARCHAR(100) NOT NULL,
                action VARCHAR(50) NOT NULL,
                description TEXT,
                is_system BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_permissions_code ON permissions(code);
            CREATE INDEX IF NOT EXISTS idx_permissions_resource_action ON permissions(resource, action);
        """)

        # 7. user_roles
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL,
                role_id UUID NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                UNIQUE(user_id, role_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_roles_role_id ON user_roles(role_id);
        """)

        # 8. role_permissions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                role_id UUID NOT NULL,
                permission_id UUID NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                UNIQUE(role_id, permission_id),
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
                FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_role_permissions_role_id ON role_permissions(role_id);
            CREATE INDEX IF NOT EXISTS idx_role_permissions_permission_id ON role_permissions(permission_id);
        """)

        # 8b. menus (from agentic_workflow)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS menus (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code VARCHAR(100) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                path VARCHAR(500),
                icon VARCHAR(100),
                component VARCHAR(255),
                menu_type VARCHAR(50) DEFAULT 'menu',
                permission_code VARCHAR(100),
                is_visible BOOLEAN DEFAULT TRUE,
                is_system BOOLEAN DEFAULT FALSE,
                parent_id UUID,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                FOREIGN KEY (parent_id) REFERENCES menus(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_menus_code ON menus(code);
            CREATE INDEX IF NOT EXISTS idx_menus_parent_id ON menus(parent_id);
            CREATE INDEX IF NOT EXISTS idx_menus_permission_code ON menus(permission_code);
        """)

        # 8c. role_menus (from agentic_workflow)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS role_menus (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                role_id UUID NOT NULL,
                menu_id UUID NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                UNIQUE(role_id, menu_id),
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
                FOREIGN KEY (menu_id) REFERENCES menus(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_role_menus_role_id ON role_menus(role_id);
            CREATE INDEX IF NOT EXISTS idx_role_menus_menu_id ON role_menus(menu_id);
        """)

        # 9. user_sessions (token blacklist / logout)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL,
                token_jti VARCHAR(255) NOT NULL UNIQUE,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_sessions_token_jti ON user_sessions(token_jti);
            CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at);
        """)

    conn.commit()
    logger.info("Application database (user/auth/menus) tables created.")


def create_workflow_tables(conn) -> None:
    """Create workflow tables (from agentic_workflow)."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                description TEXT,
                status VARCHAR(50) DEFAULT 'draft',
                created_by VARCHAR(36) NOT NULL,
                organization_id UUID,
                department_id UUID,
                workspace_id UUID,
                current_draft_id UUID,
                current_release_id UUID,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL,
                FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workflows_created_by ON workflows(created_by);
            CREATE INDEX IF NOT EXISTS idx_workflows_organization_id ON workflows(organization_id);
            CREATE INDEX IF NOT EXISTS idx_workflows_department_id ON workflows(department_id);
            CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status);
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workflow_drafts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                workflow_id UUID NOT NULL,
                spec JSONB,
                version INTEGER NOT NULL,
                is_autosave BOOLEAN DEFAULT FALSE,
                graph JSONB NOT NULL,
                validation JSONB,
                created_by VARCHAR(36) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                UNIQUE(workflow_id, version),
                FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_drafts_workflow_id ON workflow_drafts(workflow_id);
        """)
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'workflow_drafts' AND column_name = 'spec'
                ) THEN
                    ALTER TABLE workflow_drafts ADD COLUMN spec JSONB;
                END IF;
            END $$;
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workflow_releases (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                workflow_id UUID NOT NULL,
                release_version VARCHAR(50) NOT NULL,
                source_draft_id UUID,
                spec JSONB NOT NULL,
                checksum VARCHAR(64),
                created_by VARCHAR(36) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                UNIQUE(workflow_id, release_version),
                FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
                FOREIGN KEY (source_draft_id) REFERENCES workflow_drafts(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_releases_workflow_id ON workflow_releases(workflow_id);
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workflow_runs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                workflow_id UUID NOT NULL,
                release_id UUID NOT NULL,
                status VARCHAR(50) DEFAULT 'queued',
                input JSONB,
                output JSONB,
                error JSONB,
                started_at TIMESTAMP WITH TIME ZONE,
                finished_at TIMESTAMP WITH TIME ZONE,
                heartbeat_at TIMESTAMP WITH TIME ZONE,
                created_by VARCHAR(36) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
                FOREIGN KEY (release_id) REFERENCES workflow_releases(id) ON DELETE RESTRICT
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow_id ON workflow_runs(workflow_id);
            CREATE INDEX IF NOT EXISTS idx_workflow_runs_release_id ON workflow_runs(release_id);
            CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);
            CREATE INDEX IF NOT EXISTS idx_workflow_runs_created_at ON workflow_runs(created_at);
            CREATE INDEX IF NOT EXISTS idx_workflow_runs_heartbeat_at ON workflow_runs(heartbeat_at);
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS node_tasks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                run_id UUID NOT NULL,
                node_id VARCHAR(255) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                attempt INTEGER DEFAULT 1,
                input JSONB,
                output JSONB,
                error JSONB,
                metrics JSONB,
                started_at TIMESTAMP WITH TIME ZONE,
                finished_at TIMESTAMP WITH TIME ZONE,
                parent_task_id UUID,
                branch_id VARCHAR(255),
                iteration INTEGER,
                loop_node_id VARCHAR(255),
                run_seq INTEGER,
                timeout_seconds INTEGER,
                retry_delay_seconds INTEGER,
                FOREIGN KEY (run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_task_id) REFERENCES node_tasks(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_node_tasks_run_id ON node_tasks(run_id);
            CREATE INDEX IF NOT EXISTS idx_node_tasks_node_id ON node_tasks(node_id);
            CREATE INDEX IF NOT EXISTS idx_node_tasks_status ON node_tasks(status);
            CREATE INDEX IF NOT EXISTS idx_node_tasks_run_seq ON node_tasks(run_id, run_seq);
            CREATE INDEX IF NOT EXISTS idx_node_tasks_started_at ON node_tasks(started_at);
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS run_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                run_id UUID NOT NULL,
                seq INTEGER NOT NULL,
                level VARCHAR(20) NOT NULL,
                event VARCHAR(100) NOT NULL,
                payload JSONB,
                node_id VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                UNIQUE(run_id, seq),
                FOREIGN KEY (run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_run_logs_run_id ON run_logs(run_id);
            CREATE INDEX IF NOT EXISTS idx_run_logs_seq ON run_logs(run_id, seq);
            CREATE INDEX IF NOT EXISTS idx_run_logs_event ON run_logs(event);
            CREATE INDEX IF NOT EXISTS idx_run_logs_node_id ON run_logs(node_id);
            CREATE INDEX IF NOT EXISTS idx_run_logs_created_at ON run_logs(created_at);
        """)
    conn.commit()
    logger.info("Workflow tables created.")


def create_chat_tables(conn) -> None:
    """Create chat tables (from agentic_workflow)."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_streams (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                thread_id VARCHAR(255) NOT NULL UNIQUE,
                title VARCHAR(255) NOT NULL DEFAULT '新对话',
                messages JSONB NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_chat_streams_thread_id ON chat_streams(thread_id);
            CREATE INDEX IF NOT EXISTS idx_chat_streams_created_at ON chat_streams(created_at);
            CREATE INDEX IF NOT EXISTS idx_chat_streams_updated_at ON chat_streams(updated_at);
        """)
    conn.commit()
    logger.info("Chat tables created.")


def create_data_extraction_tables(conn) -> None:
    """Create data extraction tables (from agentic_workflow)."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS data_extraction_files (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                task_id UUID NOT NULL UNIQUE,
                task_name VARCHAR(255),
                extraction_type VARCHAR(50) NOT NULL,
                file_name VARCHAR(255),
                file_size BIGINT,
                file_base64 TEXT,
                pdf_url TEXT,
                model_name VARCHAR(100),
                metadata JSONB,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_data_extraction_files_task_id ON data_extraction_files(task_id);
            CREATE INDEX IF NOT EXISTS idx_data_extraction_files_created_at ON data_extraction_files(created_at DESC);
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS data_extraction_categories (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                task_id UUID NOT NULL UNIQUE,
                categories JSONB NOT NULL,
                result_json TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                FOREIGN KEY (task_id) REFERENCES data_extraction_files(task_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_data_extraction_categories_task_id ON data_extraction_categories(task_id);
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS data_extraction_data (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                task_id UUID NOT NULL UNIQUE,
                selected_categories JSONB NOT NULL,
                table_data JSONB NOT NULL,
                result_json TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                FOREIGN KEY (task_id) REFERENCES data_extraction_files(task_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_data_extraction_data_task_id ON data_extraction_data(task_id);
        """)
    conn.commit()
    logger.info("Data extraction tables created.")


def create_tool_run_history_tables(conn) -> None:
    """Create tool run history table (from agentic_workflow)."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tool_run_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tool_id VARCHAR(64) NOT NULL,
                params_json JSONB,
                result_json TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_tool_run_history_tool_id ON tool_run_history(tool_id);
            CREATE INDEX IF NOT EXISTS idx_tool_run_history_created_at ON tool_run_history(created_at DESC);
        """)
    conn.commit()
    logger.info("Tool run history table created.")


def create_sam_design_tables(conn) -> None:
    """Create SAM design history tables (from agentic_workflow)."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sam_design_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL,
                name VARCHAR(255) NOT NULL,
                objective JSONB NOT NULL,
                constraints JSONB NOT NULL,
                execution_result JSONB NOT NULL,
                molecules JSONB NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_sam_design_history_user_id ON sam_design_history(user_id);
            CREATE INDEX IF NOT EXISTS idx_sam_design_history_created_at ON sam_design_history(created_at DESC);
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS new_sam_execution_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                run_id UUID NOT NULL,
                workflow_id UUID NOT NULL,
                user_id UUID NOT NULL,
                name VARCHAR(255) NOT NULL,
                objective JSONB NOT NULL,
                constraints JSONB NOT NULL,
                execution_state VARCHAR(20) NOT NULL,
                started_at TIMESTAMP WITH TIME ZONE,
                finished_at TIMESTAMP WITH TIME ZONE,
                execution_logs JSONB,
                node_outputs JSONB,
                iteration_node_outputs JSONB,
                iteration_snapshots JSONB,
                workflow_graph JSONB,
                iteration_analytics JSONB,
                candidate_molecules JSONB,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                FOREIGN KEY (run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE,
                FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_new_sam_exec_history_run_id ON new_sam_execution_history(run_id);
            CREATE INDEX IF NOT EXISTS idx_new_sam_exec_history_workflow_id ON new_sam_execution_history(workflow_id);
            CREATE INDEX IF NOT EXISTS idx_new_sam_exec_history_user_id ON new_sam_execution_history(user_id);
            CREATE INDEX IF NOT EXISTS idx_new_sam_exec_history_created_at ON new_sam_execution_history(created_at DESC);
        """)
    conn.commit()
    logger.info("SAM design tables created.")


def seed_initial_users(conn) -> None:
    """Create initial users: admin (superuser) and zxw, password 123456."""
    from extensions.auth.password import hash_password

    password_hash = hash_password("123456")
    with conn.cursor() as cur:
        for username, email, real_name, is_superuser in [
            ("admin", "admin@example.com", "Administrator", True),
            ("zxw", "zxw@example.com", "ZXW", False),
        ]:
            cur.execute(
                """
                INSERT INTO users (username, email, password_hash, real_name, is_superuser, is_active, system_role, needs_setup, token_version)
                VALUES (%s, %s, %s, %s, %s, true, %s, false, 0)
                ON CONFLICT (username) DO UPDATE SET
                    email = EXCLUDED.email,
                    password_hash = EXCLUDED.password_hash,
                    real_name = EXCLUDED.real_name,
                    is_superuser = EXCLUDED.is_superuser,
                    is_active = EXCLUDED.is_active,
                    system_role = EXCLUDED.system_role,
                    needs_setup = false,
                    updated_at = NOW()
                """,
                (username, email, password_hash, real_name, is_superuser, "admin" if is_superuser else "user"),
            )
        conn.commit()
    logger.info("Initial users created/updated: admin, zxw (password: 123456).")


def main() -> None:
    from extensions._core.app_db import get_app_db_connection

    url = get_connection_url()
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgres://", 1)
    logger.info("Connecting to app database...")
    conn = get_app_db_connection(url)
    try:
        create_user_tables(conn)
        upgrade_users_harness_auth_columns(conn)
        create_workflow_tables(conn)
        try:
            from extensions._core.workflow_tools.db import init_workflow_tools_table

            init_workflow_tools_table(conn)
        except Exception as e:
            logger.warning("Failed to init workflow_tools table: %s", e)
        # Agents table (DB-backed custom agents, from agentic_workflow)
        try:
            from extensions._core.agents_db import init_agents_table

            init_agents_table(conn)
        except Exception as e:
            logger.warning("Failed to init agents table: %s", e)
        try:
            from extensions._core.skills_db import init_skills_tables

            init_skills_tables(conn)
        except Exception as e:
            logger.warning("Failed to init skills metadata tables: %s", e)
        create_chat_tables(conn)
        create_data_extraction_tables(conn)
        create_tool_run_history_tables(conn)
        create_sam_design_tables(conn)
        create_async_tasks_tables(conn)
        apply_workflow_skills_mapping(conn)
        seed_initial_users(conn)
    finally:
        conn.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
