"""
Database Query Skill — read-only NL2SQL executor for an external PostgreSQL DB.

The conversation agent's main LLM generates the SQL; this script only:
  - resolves the connection string from config.yaml (db_query.dsn)
  - inspects schema (tables / columns / keys / row estimates / samples)
  - executes a SINGLE read-only SELECT/WITH query behind four guardrails

It never generates SQL and never performs writes. See SKILL.md for usage.
"""

import argparse
import logging
import os
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# --- dependency bootstrap (shared skill venv is bare; mirrors data-analysis) ---
try:
    import psycopg
except ImportError:
    logger.info("psycopg not installed. Installing psycopg[binary]...")
    import subprocess

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "psycopg[binary]", "-q"], check=True
    )
    import psycopg


DEFAULT_MAX_ROWS = 1000
DEFAULT_STATEMENT_TIMEOUT_MS = 15000

# Only these leading keywords are allowed (read-only). Checked after stripping
# comments/whitespace. WITH is allowed because CTEs are common in analytics.
_ALLOWED_LEADING = ("select", "with")

# Hard-blocked keywords anywhere as a statement-initial token (defense in depth;
# the read-only transaction is the real enforcement).
_BLOCKED = (
    "insert", "update", "delete", "drop", "alter", "truncate",
    "grant", "revoke", "create", "replace", "merge", "call",
    "copy", "vacuum", "analyze", "comment", "set", "reset",
)


# --------------------------------------------------------------------------- #
# Config / connection
# --------------------------------------------------------------------------- #
def _resolve_config_path() -> str | None:
    """Locate config.yaml via the same env var the Gateway is started with."""
    path = os.environ.get("DEER_FLOW_CONFIG_PATH")
    if path and os.path.isfile(path):
        return path
    # Fallbacks: common repo layouts (best-effort, non-fatal).
    for candidate in ("config.yaml", "../config.yaml", "../../config.yaml"):
        if os.path.isfile(candidate):
            return candidate
    return None


def resolve_dsn() -> str:
    """Read db_query.dsn from config.yaml. Raises SystemExit with guidance if missing."""
    cfg_path = _resolve_config_path()
    if not cfg_path:
        _fatal(
            "Cannot locate config.yaml (DEER_FLOW_CONFIG_PATH not set and no local "
            "config.yaml found). Configure db_query.dsn in config.yaml."
        )

    try:
        import yaml
    except ImportError:
        import subprocess

        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyyaml", "-q"], check=True
        )
        import yaml

    try:
        with open(cfg_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        _fatal(f"Failed to read config.yaml at {cfg_path}: {e}")

    section = config.get("db_query") or {}
    dsn = (section.get("dsn") or "").strip()
    # Detect the unfilled template rather than any "<" — a real password may contain "<".
    placeholders = ("<readonly_user>", "<password>", "<host>", "<database>", "<user>", "<db>")
    if not dsn or any(tok in dsn for tok in placeholders):
        _fatal(
            "db_query.dsn is not configured in config.yaml. Add a section:\n"
            "  db_query:\n"
            "    dsn: postgresql://<readonly_user>:<password>@<host>:5432/<database>"
        )
    return dsn


def _config_int(key: str, default: int) -> int:
    """Read an optional int override from the db_query config section."""
    cfg_path = _resolve_config_path()
    if not cfg_path:
        return default
    try:
        import yaml

        with open(cfg_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        val = (config.get("db_query") or {}).get(key)
        return int(val) if val is not None else default
    except Exception:
        return default


def connect(dsn: str):
    """Open a read-only connection with a statement timeout.

    The read-only transaction default is the primary guardrail: the PostgreSQL
    server rejects any write regardless of application-level checks.
    """
    timeout_ms = _config_int("statement_timeout_ms", DEFAULT_STATEMENT_TIMEOUT_MS)
    conn = psycopg.connect(
        dsn,
        autocommit=True,
        options=f"-c default_transaction_read_only=on -c statement_timeout={timeout_ms}",
    )
    return conn


# --------------------------------------------------------------------------- #
# Guardrails
# --------------------------------------------------------------------------- #
def _strip_sql(sql: str) -> str:
    """Remove line/block comments and collapse whitespace for keyword checks."""
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    no_line = re.sub(r"--[^\n]*", " ", no_block)
    return no_line.strip()


def validate_sql(sql: str) -> tuple[bool, str]:
    """Apply statement guardrails. Returns (ok, error_message)."""
    stripped = _strip_sql(sql)
    if not stripped:
        return False, "Empty SQL."

    # Guardrail: single statement only (reject trailing statements after ';').
    # Allow a single optional trailing semicolon.
    body = stripped.rstrip(";").strip()
    if ";" in body:
        return False, "Only a single SQL statement is allowed (no ';' separators)."

    lowered = body.lower()
    first = lowered.split(None, 1)[0] if lowered.split() else ""

    # Guardrail: leading keyword whitelist.
    if first not in _ALLOWED_LEADING:
        return False, (
            f"Only read-only SELECT/WITH queries are allowed (got '{first}'). "
            "Write operations are rejected."
        )

    # Guardrail: blocked keyword as the leading token (redundant w/ whitelist,
    # but explicit for clarity and future-proofing).
    if first in _BLOCKED:
        return False, f"Statement type '{first}' is not permitted."

    return True, ""


def apply_row_limit(sql: str, max_rows: int) -> str:
    """Wrap queries lacking an explicit LIMIT so result size is bounded."""
    body = _strip_sql(sql).rstrip(";").strip()
    if re.search(r"\blimit\b\s+\d+", body, flags=re.IGNORECASE):
        return body
    return f"SELECT * FROM (\n{body}\n) AS _capped LIMIT {max_rows}"


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
def action_inspect(conn, schema: str, table: str | None) -> str:
    """List tables (or one table): columns, types, PK/FK, row estimate, samples."""
    out: list[str] = []

    if table:
        tables = [table]
    else:
        rows = _query(
            conn,
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (schema,),
        )
        tables = [r[0] for r in rows]

    if not tables:
        return f"No tables found in schema '{schema}'."

    for tname in tables:
        out.append("\n" + "=" * 60)
        out.append(f"Table: {schema}.{tname}")
        out.append("=" * 60)

        cols = _query(
            conn,
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, tname),
        )
        if not cols:
            out.append("  (no columns / not found)")
            continue

        pk_cols = {
            r[0]
            for r in _query(
                conn,
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = %s AND tc.table_name = %s
                """,
                (schema, tname),
            )
        }

        out.append(f"\nColumns ({len(cols)}):")
        out.append(f"  {'Name':<28} {'Type':<20} {'Null':<6} {'Key'}")
        out.append(f"  {'-'*28} {'-'*20} {'-'*6} {'-'*3}")
        for name, dtype, nullable in cols:
            key = "PK" if name in pk_cols else ""
            out.append(f"  {name:<28} {dtype:<20} {nullable:<6} {key}")

        # Foreign keys
        fks = _query(
            conn,
            """
            SELECT kcu.column_name, ccu.table_name, ccu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = %s AND tc.table_name = %s
            """,
            (schema, tname),
        )
        if fks:
            out.append("\nForeign keys:")
            for col, ref_tbl, ref_col in fks:
                out.append(f"  {col} -> {ref_tbl}.{ref_col}")

        # Row estimate (fast; from planner stats, not COUNT(*))
        est = _query(
            conn,
            "SELECT reltuples::bigint FROM pg_class "
            "WHERE oid = (quote_ident(%s) || '.' || quote_ident(%s))::regclass",
            (schema, tname),
        )
        if est and est[0][0] is not None:
            out.append(f"\nEstimated rows: {est[0][0]:,}")

        # Sample (first 3 rows)
        try:
            sample_cols, sample_rows = _query_with_cols(
                conn, f'SELECT * FROM "{schema}"."{tname}" LIMIT 3'
            )
            out.append("\nSample (first 3 rows):")
            out.append(_format_table(sample_cols, sample_rows))
        except Exception as e:
            out.append(f"\n(sample unavailable: {e})")

    result = "\n".join(out)
    print(result)
    return result


def action_query(conn, sql: str, max_rows: int, output_file: str | None) -> str:
    """Validate + row-limit + execute a read-only query; format/export results."""
    ok, err = validate_sql(sql)
    if not ok:
        msg = f"Rejected: {err}"
        print(msg)
        return msg

    capped = apply_row_limit(sql, max_rows)

    try:
        columns, rows = _query_with_cols(conn, capped)
    except Exception as e:
        # On error, return available table names so the LLM can self-correct.
        msg = f"SQL Error: {e}\n\n" + _available_tables_hint(conn)
        print(msg)
        return msg

    if output_file:
        return _export_results(columns, rows, output_file)

    truncated_note = ""
    if len(rows) >= max_rows:
        truncated_note = f"\n[Note: result capped at {max_rows} rows; refine with aggregation or an explicit smaller LIMIT.]"
    result = _format_table(columns, rows) + truncated_note
    print(result)
    return result


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _query(conn, sql: str, params: tuple = ()) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _query_with_cols(conn, sql: str, params: tuple = ()) -> tuple[list[str], list[tuple]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [d.name for d in cur.description] if cur.description else []
        rows = cur.fetchall() if cur.description else []
        return columns, rows


def _available_tables_hint(conn) -> str:
    try:
        rows = _query(
            conn,
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
            LIMIT 100
            """,
        )
        if not rows:
            return "Available tables: (none visible to this user)"
        listed = ", ".join(f"{s}.{t}" for s, t in rows)
        return f"Available tables: {listed}"
    except Exception:
        return "Available tables: (could not enumerate)"


def _format_table(columns: list[str], rows: list) -> str:
    """Render results as a readable fixed-width table (mirrors data-analysis)."""
    if not columns:
        return "(no columns)"
    if not rows:
        return "Query returned 0 rows."

    max_width = 40
    widths = [len(str(c)) for c in columns]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))
    widths = [min(w, max_width) for w in widths]

    parts = []
    header = " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(columns))
    sep = "-+-".join("-" * widths[i] for i in range(len(columns)))
    parts.append(header)
    parts.append(sep)
    for row in rows:
        parts.append(
            " | ".join(str(v)[:max_width].ljust(widths[i]) for i, v in enumerate(row))
        )
    parts.append(f"\n({len(rows)} rows)")
    return "\n".join(parts)


def _export_results(columns: list[str], rows: list, output_file: str) -> str:
    """Export results to .csv / .json / .md (auto-detected from extension)."""
    ext = os.path.splitext(output_file)[1].lower()
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    if ext == ".csv":
        import csv

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(columns)
            w.writerows(rows)
    elif ext == ".json":
        import json

        records = [
            {col: _jsonable(row[i]) for i, col in enumerate(columns)} for row in rows
        ]
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False, default=str)
    elif ext == ".md":
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("| " + " | ".join(columns) + " |\n")
            f.write("| " + " | ".join("---" for _ in columns) + " |\n")
            for row in rows:
                f.write(
                    "| "
                    + " | ".join(str(v).replace("|", "\\|") for v in row)
                    + " |\n"
                )
    else:
        msg = f"Unsupported output format: {ext}. Use .csv, .json, or .md"
        print(msg)
        return msg

    msg = f"Results exported to {output_file} ({len(rows)} rows)"
    print(msg)
    return msg


def _jsonable(val):
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if isinstance(val, (bytes, bytearray)):
        return val.hex()
    return val


def _fatal(msg: str) -> None:
    logger.error(msg)
    sys.exit(1)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only query tool for the external PostgreSQL database."
    )
    parser.add_argument("--action", required=True, choices=["inspect", "query"])
    parser.add_argument("--sql", type=str, default=None, help="Single SELECT/WITH query (for --action query)")
    parser.add_argument("--schema", type=str, default="public", help="Schema for inspect (default: public)")
    parser.add_argument("--table", type=str, default=None, help="Inspect only this table")
    parser.add_argument("--max-rows", type=int, default=None, help="Row cap (default from config or 1000)")
    parser.add_argument("--output-file", type=str, default=None, help="Export results to .csv/.json/.md")
    args = parser.parse_args()

    if args.action == "query" and not args.sql:
        parser.error("--sql is required for --action query")

    max_rows = args.max_rows or _config_int("max_rows", DEFAULT_MAX_ROWS)
    dsn = resolve_dsn()

    conn = connect(dsn)
    try:
        if args.action == "inspect":
            print(action_inspect(conn, args.schema, args.table))
        else:
            action_query(conn, args.sql, max_rows, args.output_file)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
