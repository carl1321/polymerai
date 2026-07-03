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


def test_create_agent_persists_memory_enabled(monkeypatch):
    captured = {}
    fake_conn = _FakeConn()
    created_id = uuid4()

    monkeypatch.setattr(agents_router_module, "get_app_db_connection", lambda: fake_conn)

    def _create_agent(_conn, **kwargs):
        captured.update(kwargs)
        return created_id

    monkeypatch.setattr(agents_router_module, "db_create_agent", _create_agent)
    monkeypatch.setattr(
        agents_router_module,
        "db_get_agent",
        lambda conn, agent_id, user_id, organization_id: {
            "id": str(agent_id),
            "name": "memory-agent",
            "memory_enabled": False,
        },
    )

    app = FastAPI()
    app.include_router(agents_router_module.router)
    app.dependency_overrides[get_current_user_optional] = _make_user

    with TestClient(app) as client:
        resp = client.post("/api/agents", json={"name": "memory-agent", "memory_enabled": False})

    assert resp.status_code == 201
    assert captured["memory_enabled"] is False
    assert resp.json()["memory_enabled"] is False


def test_update_agent_persists_memory_enabled(monkeypatch):
    captured = {}
    fake_conn = _FakeConn()
    agent_id = uuid4()

    monkeypatch.setattr(agents_router_module, "get_app_db_connection", lambda: fake_conn)
    monkeypatch.setattr(
        agents_router_module,
        "db_get_agent",
        lambda conn, uid, user_id, organization_id: {"id": str(uid), "name": "memory-agent", "memory_enabled": True},
    )

    def _update_agent(conn, uid, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(agents_router_module, "db_update_agent", _update_agent)

    app = FastAPI()
    app.include_router(agents_router_module.router)
    app.dependency_overrides[get_current_user_optional] = _make_user

    with TestClient(app) as client:
        resp = client.put(f"/api/agents/{agent_id}", json={"memory_enabled": False})

    assert resp.status_code == 200
    assert captured["memory_enabled"] is False
    assert resp.json()["memory_enabled"] is True
