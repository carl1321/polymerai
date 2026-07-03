"""Tests for runtime.user_context — contextvar three-state semantics.

These tests opt out of the autouse contextvar fixture (added in
commit 6) because they explicitly test the cases where the contextvar
is set or unset.
"""

from types import SimpleNamespace

import pytest

from deerflow.runtime.user_context import (
    DEFAULT_USER_ID,
    CurrentUser,
    get_current_user,
    get_effective_user_id,
    require_current_user,
    reset_current_user,
    resolve_fs_user_id_for_thread,
    set_current_user,
)


@pytest.mark.no_auto_user
def test_default_is_none():
    """Before any set, contextvar returns None."""
    assert get_current_user() is None


@pytest.mark.no_auto_user
def test_set_and_reset_roundtrip():
    """set_current_user returns a token that reset restores."""
    user = SimpleNamespace(id="user-1")
    token = set_current_user(user)
    try:
        assert get_current_user() is user
    finally:
        reset_current_user(token)
    assert get_current_user() is None


@pytest.mark.no_auto_user
def test_require_current_user_raises_when_unset():
    """require_current_user raises RuntimeError if contextvar is unset."""
    assert get_current_user() is None
    with pytest.raises(RuntimeError, match="without user context"):
        require_current_user()


@pytest.mark.no_auto_user
def test_require_current_user_returns_user_when_set():
    """require_current_user returns the user when contextvar is set."""
    user = SimpleNamespace(id="user-2")
    token = set_current_user(user)
    try:
        assert require_current_user() is user
    finally:
        reset_current_user(token)


@pytest.mark.no_auto_user
def test_protocol_accepts_duck_typed():
    """CurrentUser is a runtime_checkable Protocol matching any .id-bearing object."""
    user = SimpleNamespace(id="user-3")
    assert isinstance(user, CurrentUser)


@pytest.mark.no_auto_user
def test_protocol_rejects_no_id():
    """Objects without .id do not satisfy CurrentUser Protocol."""
    not_a_user = SimpleNamespace(email="no-id@example.com")
    assert not isinstance(not_a_user, CurrentUser)


# ---------------------------------------------------------------------------
# get_effective_user_id / DEFAULT_USER_ID tests
# ---------------------------------------------------------------------------


def test_default_user_id_is_default():
    assert DEFAULT_USER_ID == "default"


@pytest.mark.no_auto_user
def test_effective_user_id_returns_default_when_no_user():
    """No user in context -> fallback to DEFAULT_USER_ID."""
    assert get_effective_user_id() == "default"


@pytest.mark.no_auto_user
def test_effective_user_id_returns_user_id_when_set():
    user = SimpleNamespace(id="u-abc-123")
    token = set_current_user(user)
    try:
        assert get_effective_user_id() == "u-abc-123"
    finally:
        reset_current_user(token)


@pytest.mark.no_auto_user
def test_effective_user_id_coerces_to_str():
    """User.id might be a UUID object; must come back as str."""
    import uuid

    uid = uuid.uuid4()

    user = SimpleNamespace(id=uid)
    token = set_current_user(user)
    try:
        assert get_effective_user_id() == str(uid)
    finally:
        reset_current_user(token)


@pytest.mark.no_auto_user
def test_resolve_fs_user_id_prefers_configurable_user_id(monkeypatch):
    """Graph config owner wins when HTTP context is missing (remote worker case)."""

    def fake_get_config():
        return {"configurable": {"user_id": "owner-from-run-config", "thread_id": "t1"}}

    monkeypatch.setattr("langgraph.config.get_config", fake_get_config)
    assert resolve_fs_user_id_for_thread() == "owner-from-run-config"


@pytest.mark.no_auto_user
def test_resolve_fs_user_id_falls_back_when_not_in_graph(monkeypatch):
    """Outside a LangGraph runnable, get_config raises — use effective user id."""

    def raise_no_context():
        raise RuntimeError("Called get_config outside of a runnable context")

    monkeypatch.setattr("langgraph.config.get_config", raise_no_context)
    assert resolve_fs_user_id_for_thread() == "default"


@pytest.mark.no_auto_user
def test_resolve_fs_user_id_config_overrides_http_context(monkeypatch):
    """Run-configurable user_id takes precedence over request-scoped user."""

    def fake_get_config():
        return {"configurable": {"user_id": "checkpoint-owner"}}

    monkeypatch.setattr("langgraph.config.get_config", fake_get_config)
    user = SimpleNamespace(id="http-session-user")
    token = set_current_user(user)
    try:
        assert resolve_fs_user_id_for_thread() == "checkpoint-owner"
    finally:
        reset_current_user(token)
