# Backend Extensions

This package registers **extension** routers with the DeerFlow gateway when `app_database` is configured. Isolating them here makes upstream upgrades easier: replace core, keep this package and the single call in `gateway/app.py`.

## What is registered

- **Auth**: `/api/auth` (login, logout, me, refresh, public-key)
- **Admin users**: `/api/admin/users`
- **Toolbox**: `/api/tool-history`, `/api/tools`, `/api/tools/execute`
- **Workflows**: `/api/workflows` (list, create, get, update, delete, run, drafts)

Implementation lives in:

- `src.auth` (routes, admin, dependencies, jwt, db)
- `extensions.toolbox` (routes, agentic_tools)
- `src.gateway.routers.workflows`

This package only **mounts** them in one place: `register_extensions(app)`.

## Upgrade workflow

1. Pull new deer-flow upstream; overwrite core (e.g. gateway, agents, tools) but **keep** `src/extensions/`.
2. Ensure `gateway/app.py` still contains, in the `app_db_url` branch: `from extensions import register_extensions; register_extensions(app)`.
3. If upstream changed router APIs or paths, adapt imports inside `src/extensions/__init__.py` only.
4. Keep `config.yaml` extension-related sections: `tool_groups` (e.g. `agentic`), extension `tools`, `app_database`.
