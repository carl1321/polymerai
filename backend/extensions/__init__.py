"""Extensions package: auth, workflows, toolbox, agents_db.

When app_database is configured, the gateway mounts these routers via
register_extensions(app). Isolating them here simplifies upstream deer-flow
upgrades: replace core, keep this package and the single call in app.py.
"""

import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def register_extensions(app: FastAPI) -> None:
    """Register extension routers (auth, admin users, toolbox, workflows, agents).

    Call this from gateway app.py when app_database is configured.
    """
    from extensions.auth.routes import router as auth_router
    from extensions.auth.admin import router as admin_users_router
    from extensions.agents_db.router import router as agents_db_router
    from extensions.new_sam.router import router as new_sam_router, workflows_alias_router as new_sam_workflows_alias_router
    from extensions.public_agent.router import router as public_agent_router
    from extensions.workflows.router import router as workflows_router
    from extensions.toolbox.routes import router as toolbox_router

    app.include_router(auth_router)
    app.include_router(admin_users_router)
    app.include_router(agents_db_router)
    app.include_router(new_sam_router)
    app.include_router(new_sam_workflows_alias_router)
    app.include_router(public_agent_router)
    app.include_router(workflows_router)
    app.include_router(toolbox_router)
    logger.info(
        "Extensions registered: /api/auth, /api/admin/users, /api/agents, /api/new-sam, "
        "/api/workflows/new-sam, /api/public, /api/workflows (incl. tool-catalog), toolbox"
    )
