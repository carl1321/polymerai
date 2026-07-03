from __future__ import annotations

import importlib
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from extensions.auth.dependencies import CurrentUser, get_current_user_optional

agents_router_module = importlib.import_module("extensions.agents_db.router")


class _FakeConn:
    def close(self) -> None:
        return None

    def commit(self) -> None:
        return None


def _make_user() -> CurrentUser:
    return CurrentUser(
        {
            "id": str(uuid4()),
            "username": "tester",
            "email": "tester@example.com",
            "organization_id": str(uuid4()),
            "department_id": None,
        },
        roles=[],
        permissions=[],
    )


def test_create_swarm_rejects_skill_names(monkeypatch):
    fake_conn = _FakeConn()
    monkeypatch.setattr(agents_router_module, "get_app_db_connection", lambda: fake_conn)

    app = FastAPI()
    app.include_router(agents_router_module.router)
    app.dependency_overrides[get_current_user_optional] = _make_user

    with TestClient(app) as client:
        resp = client.post(
            "/api/agents",
            json={"name": "swarm-a", "kind": "swarm", "skill_names": ["x"]},
        )

    assert resp.status_code == 422
    assert "swarm agent cannot bind skill_names" in resp.json()["detail"]


def test_replace_swarm_members_success(monkeypatch):
    fake_conn = _FakeConn()
    swarm_id = uuid4()
    child_id = uuid4()
    user = _make_user()
    stored_members: list[str] = []

    def _get_agent(conn, agent_id, user_id=None, organization_id=None):
        if str(agent_id) == str(swarm_id):
            return {"id": str(swarm_id), "name": "swarm-a", "kind": "swarm"}
        if str(agent_id) == str(child_id):
            return {"id": str(child_id), "name": "child-a", "kind": "dedicated"}
        return None

    monkeypatch.setattr(agents_router_module, "get_app_db_connection", lambda: fake_conn)
    monkeypatch.setattr(agents_router_module, "db_get_agent", _get_agent)
    monkeypatch.setattr(
        agents_router_module,
        "db_replace_swarm_members",
        lambda conn, _swarm_id, member_ids: stored_members.__setitem__(
            slice(None), [str(x) for x in member_ids]
        ),
    )
    monkeypatch.setattr(agents_router_module, "db_list_swarm_member_ids", lambda conn, _swarm_id: stored_members)

    app = FastAPI()
    app.include_router(agents_router_module.router)
    app.dependency_overrides[get_current_user_optional] = lambda: user

    with TestClient(app) as client:
        resp = client.put(
            f"/api/agents/{swarm_id}/members",
            json={"member_dedicated_ids": [str(child_id)]},
        )

    assert resp.status_code == 200
    assert resp.json()["member_dedicated_ids"] == [str(child_id)]


def test_generate_prompt_rejects_swarm(monkeypatch):
    fake_conn = _FakeConn()
    swarm_id = uuid4()

    monkeypatch.setattr(agents_router_module, "get_app_db_connection", lambda: fake_conn)
    monkeypatch.setattr(
        agents_router_module,
        "db_get_agent",
        lambda conn, agent_id, user_id=None, organization_id=None: {
            "id": str(agent_id),
            "name": "swarm-a",
            "description": "desc",
            "kind": "swarm",
        },
    )

    app = FastAPI()
    app.include_router(agents_router_module.router)
    app.dependency_overrides[get_current_user_optional] = _make_user

    with TestClient(app) as client:
        resp = client.post(f"/api/agents/{swarm_id}/generate-prompt", json={})

    assert resp.status_code == 422
    assert "only supported for dedicated" in resp.json()["detail"]
