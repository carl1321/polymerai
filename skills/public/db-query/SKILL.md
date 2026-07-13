---
name: db-query
description: Use this skill when the user asks questions about data stored in the external business PostgreSQL database — for example "how many X are there", "list all Y", "top N Z by W", or any aggregation, filtering, or trend over the business tables. The skill connects to a pre-configured READ-ONLY PostgreSQL database, inspects its schema, and executes read-only SQL queries you write. Do NOT use this skill for user-uploaded Excel/CSV files (use the data-analysis skill instead), and do NOT use it for the application's own internal tables.
---

# Database Query Skill

## Overview

This skill answers natural-language questions about an **external business PostgreSQL database**. You (the assistant) inspect the schema, write read-only SQL, and the script executes it against a pre-configured, read-only connection. The connection string is read from `config.yaml` (`db_query.dsn`) — you never handle credentials.

The script **only executes** SQL; **you generate the SQL**. It enforces read-only access at the database level, so any write attempt will fail.

## When to use

- User asks about counts, lists, rankings, aggregations, or trends over business data that lives in the external database.
- User references entities/tables you can discover via `inspect`.

**When NOT to use:**
- User uploaded an Excel/CSV file → use the **data-analysis** skill.
- Question is about the app's own internal/system tables → not this skill.

## Workflow

Always follow **inspect → query**: understand the schema first, then write SQL against real table/column names. Never guess column names.

### Step 1: Inspect the schema

```bash
python /mnt/skills/public/db-query/scripts/query.py --action inspect
```

Optional — limit to one schema or one table (useful when the database has many tables):

```bash
python /mnt/skills/public/db-query/scripts/query.py --action inspect --schema public --table users
```

`inspect` returns, per table: columns (name, type, nullable, PK), foreign keys, an estimated row count, and 3 sample rows.

### Step 2: Run a read-only query

Write a single `SELECT` (or `WITH … SELECT`) based on the inspected schema:

```bash
python /mnt/skills/public/db-query/scripts/query.py --action query \
  --sql "SELECT role, COUNT(*) AS n FROM users GROUP BY role ORDER BY n DESC"
```

Optional — export results instead of printing (auto-detected from extension `.csv` / `.json` / `.md`):

```bash
python /mnt/skills/public/db-query/scripts/query.py --action query \
  --sql "SELECT * FROM orders WHERE amount > 1000" \
  --output-file /mnt/user-data/outputs/big-orders.csv
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--action` | Yes | `inspect` or `query` |
| `--sql` | For `query` | A single read-only SELECT/WITH statement |
| `--schema` | No | Schema to inspect (default: `public`) |
| `--table` | No | Inspect only this one table |
| `--max-rows` | No | Override the row cap (default 1000) |
| `--output-file` | No | Export results to `.csv` / `.json` / `.md` |

## Rules you MUST follow when writing SQL

1. **Read-only only.** Generate only `SELECT` or `WITH … SELECT`. Any `INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/GRANT/CREATE/...` will be **rejected** by the script and by the database's read-only transaction.
2. **One statement per call.** No `;`-separated multiple statements (the script rejects them).
3. **Inspect before querying.** If you are unsure of table or column names, run `--action inspect` first. Do not invent names.
4. **Self-correct on errors.** If a query fails, the script returns the error plus the list of available tables. Read it, fix the SQL, and call again.
5. **Mind the row cap.** Queries without an explicit `LIMIT` are auto-capped (default 1000 rows). For large tables, prefer aggregation (`COUNT`, `GROUP BY`) or an explicit small `LIMIT`.

> [!NOTE]
> Do NOT read the Python script; just call it with the parameters above.

## Presenting results

- Show query results in the conversation as a clear, formatted table.
- Explain findings in plain language; state the SQL you ran when it helps the user trust the answer.
- Offer to export (`--output-file`) when the result set is large or the user wants to keep it.
- Suggest sensible follow-up questions when patterns are interesting.

## Example

User: "Which 5 roles have the most users?"

1. Inspect to confirm the table/columns:
   ```bash
   python /mnt/skills/public/db-query/scripts/query.py --action inspect --table users
   ```
2. Query:
   ```bash
   python /mnt/skills/public/db-query/scripts/query.py --action query \
     --sql "SELECT role, COUNT(*) AS user_count FROM users GROUP BY role ORDER BY user_count DESC LIMIT 5"
   ```
3. Present the returned table and summarize the top roles in plain language.
