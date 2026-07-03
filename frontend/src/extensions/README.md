# Frontend Extensions

This folder holds **extension** UI and config: login, agents, toolbox, workflows. Centralizing them here makes upstream deer-flow upgrades easier: replace core app/layout, keep this folder and the single reference points (sidebar config, auth hook).

## Contents

- **sidebar-entries.ts**: Sidebar nav entries (agents, toolbox, workflows). The workspace sidebar reads from `EXTENSION_SIDEBAR_ENTRIES` so adding/removing entries is done here.
- **auth/**: Auth-related extension logic.
  - **useRedirectOn401**: Hook that clears token and redirects to `/login` on 401/Unauthorized. Use in extension pages (e.g. agents management) instead of inline handling.

Login page, agents management, toolbox, and workflow pages remain under `app/` and `components/workspace/` but can be refactored over time to import from `@/extensions/*` so that only thin route shells stay in core.

## Upgrade workflow

1. Pull new deer-flow upstream; overwrite core (e.g. app routes, workspace layout) but **keep** `src/extensions/`.
2. Restore the single integration points: sidebar component should still import `EXTENSION_SIDEBAR_ENTRIES` from `@/extensions/sidebar-entries`; any page that needs 401 → login should use `useRedirectOn401` from `@/extensions/auth`.
3. If upstream changed layout or routing, update only the integration points; keep extension components and config unchanged where possible.
