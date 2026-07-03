"""Tests for public agent share path rules and token handling."""

from app.gateway.csrf_middleware import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from extensions._core.public_agent_links import verify_link_token
from extensions.public_agent.router import (
    _inject_upstream_csrf,
    _merge_csrf_into_cookie_header,
    _patch_run_payload,
    _public_path_forbidden,
)


def test_public_path_blocks_thread_search() -> None:
    assert _public_path_forbidden("threads/search", "POST") is not None


def test_public_path_blocks_stateless_runs() -> None:
    assert _public_path_forbidden("runs/stream", "POST") is not None
    assert _public_path_forbidden("runs", "POST") is not None


def test_public_path_allows_thread_run_stream() -> None:
    assert (
        _public_path_forbidden(
            "threads/550e8400-e29b-41d4-a716-446655440000/runs/stream",
            "POST",
        )
        is None
    )


def test_public_path_blocks_thread_delete() -> None:
    assert (
        _public_path_forbidden(
            "threads/550e8400-e29b-41d4-a716-446655440000",
            "DELETE",
        )
        is not None
    )


def test_patch_run_payload_forces_agent_and_public_flags() -> None:
    body: dict = {
        "input": {},
        "context": {"agent_id": "wrong", "subagent_enabled": True},
        "config": {"recursion_limit": 1000},
    }
    out = _patch_run_payload(body, "correct-agent-uuid")
    assert out["context"]["agent_id"] == "correct-agent-uuid"
    assert out["context"]["deerflow_public_share"] is True
    assert out["context"]["subagent_enabled"] is True


def test_verify_link_token() -> None:
    from extensions._core.public_agent_links import _hash_token

    plain = "test-secret-token"
    row = {"token_hash": _hash_token(plain)}
    assert verify_link_token(row, plain) is True
    assert verify_link_token(row, "wrong") is False


def test_merge_csrf_into_cookie_header_replaces_existing_csrf() -> None:
    merged = _merge_csrf_into_cookie_header("csrf_token=old; other=1", "newcsrf")
    assert "csrf_token=newcsrf" in merged
    assert "old" not in merged
    assert "other=1" in merged


def test_inject_upstream_csrf_sets_matching_pair() -> None:
    headers: dict[str, str] = {}
    _inject_upstream_csrf(headers, "POST")
    assert CSRF_HEADER_NAME in headers
    assert headers[CSRF_HEADER_NAME]
    assert headers["Cookie"].startswith(f"{CSRF_COOKIE_NAME}=")
    assert headers[CSRF_HEADER_NAME] in headers["Cookie"]


def test_inject_upstream_csrf_skips_get() -> None:
    headers = {"Cookie": "a=b"}
    _inject_upstream_csrf(headers, "GET")
    assert CSRF_HEADER_NAME not in headers
