#!/usr/bin/env bash
set -euo pipefail

# One-shot runner for threads_meta migration + quick verification.
# Usage:
#   bash backend/scripts/run_threads_meta_migration_once.sh
#   bash backend/scripts/run_threads_meta_migration_once.sh --dry-run
#   bash backend/scripts/run_threads_meta_migration_once.sh --limit 100000
#   bash backend/scripts/run_threads_meta_migration_once.sh --checkpoints-db /path/checkpoints.db --app-db /path/deerflow.db
#   bash backend/scripts/run_threads_meta_migration_once.sh --target-pg-url postgresql://user:pass@host:5432/deerflow

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_PATH="$ROOT_DIR/backend/scripts/migrate_threads_meta_once.py"

CHECKPOINTS_DB_DEFAULT="$ROOT_DIR/backend/.deer-flow/checkpoints.db"
APP_DB_DEFAULT="$ROOT_DIR/backend/.deer-flow/data/deerflow.db"

CHECKPOINTS_DB="$CHECKPOINTS_DB_DEFAULT"
APP_DB="$APP_DB_DEFAULT"
TARGET_PG_URL=""
LIMIT="50000"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    --limit)
      LIMIT="${2:-}"
      shift 2
      ;;
    --checkpoints-db)
      CHECKPOINTS_DB="${2:-}"
      shift 2
      ;;
    --app-db)
      APP_DB="${2:-}"
      shift 2
      ;;
    --target-pg-url)
      TARGET_PG_URL="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "Migration script not found: $SCRIPT_PATH" >&2
  exit 1
fi

if [[ ! -f "$CHECKPOINTS_DB" ]]; then
  echo "checkpoints db not found: $CHECKPOINTS_DB" >&2
  exit 1
fi

if [[ -z "$TARGET_PG_URL" && ! -f "$APP_DB" ]]; then
  echo "app db not found: $APP_DB" >&2
  exit 1
fi

echo "=== threads_meta one-shot migration ==="
echo "root: $ROOT_DIR"
echo "checkpoints_db: $CHECKPOINTS_DB"
if [[ -n "$TARGET_PG_URL" ]]; then
  echo "target_pg_url: $TARGET_PG_URL"
else
  echo "app_db: $APP_DB"
fi
echo "limit: $LIMIT"
echo "dry_run: $DRY_RUN"
echo

CMD=(uv run python "$SCRIPT_PATH" --checkpoints-db "$CHECKPOINTS_DB" --limit "$LIMIT")
if [[ -n "$TARGET_PG_URL" ]]; then
  CMD+=(--target-pg-url "$TARGET_PG_URL")
else
  CMD+=(--app-db "$APP_DB")
fi
if [[ "$DRY_RUN" == "true" ]]; then
  CMD+=(--dry-run)
fi

"${CMD[@]}"

echo
echo "=== quick verify (threads_meta) ==="
if [[ "$DRY_RUN" == "true" ]]; then
  echo "skip quick verify in dry-run mode"
  echo
  echo "Migration finished."
  exit 0
fi
if [[ -n "$TARGET_PG_URL" ]]; then
  python - <<PY
import psycopg
url = """$TARGET_PG_URL"""
with psycopg.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT 'total_threads_meta', COUNT(*) FROM threads_meta")
        print("|".join(str(x) for x in cur.fetchone()))
        cur.execute("SELECT 'with_user_id', COUNT(*) FROM threads_meta WHERE user_id IS NOT NULL AND user_id <> ''")
        print("|".join(str(x) for x in cur.fetchone()))
        cur.execute("SELECT 'with_display_name', COUNT(*) FROM threads_meta WHERE display_name IS NOT NULL AND display_name <> ''")
        print("|".join(str(x) for x in cur.fetchone()))
        for tbl in ("checkpoints", "writes", "store", "runs", "run_events", "users", "feedback"):
            cur.execute(f"SELECT '{tbl}', COUNT(*) FROM {tbl}")
            print("|".join(str(x) for x in cur.fetchone()))
        cur.execute("SELECT thread_id, user_id, display_name, status, updated_at FROM threads_meta ORDER BY updated_at DESC LIMIT 10")
        for row in cur.fetchall():
            print("|".join("" if v is None else str(v) for v in row))
PY
else
  sqlite3 "$APP_DB" "SELECT 'total_threads_meta', COUNT(*) FROM threads_meta;"
  sqlite3 "$APP_DB" "SELECT 'with_user_id', COUNT(*) FROM threads_meta WHERE user_id IS NOT NULL AND user_id <> '';"
  sqlite3 "$APP_DB" "SELECT 'with_display_name', COUNT(*) FROM threads_meta WHERE display_name IS NOT NULL AND display_name <> '';"
  sqlite3 "$APP_DB" "SELECT thread_id, user_id, display_name, status, updated_at FROM threads_meta ORDER BY updated_at DESC LIMIT 10;"
fi

echo
echo "Migration finished."
