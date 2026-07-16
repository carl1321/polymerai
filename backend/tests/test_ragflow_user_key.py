"""Unit tests for RAGFlow user key fetch parsing."""

from unittest.mock import MagicMock

from extensions._core.ragflow_user_key import parse_api_key_from_fetch_response


def test_parse_json_api_key():
    r = MagicMock()
    r.status_code = 200
    r.headers = {"Content-Type": "application/json"}
    r.text = '{"api_key": "secret"}'
    r.json.return_value = {"api_key": "secret"}
    assert parse_api_key_from_fetch_response(r) == "secret"


def test_parse_json_nested_data():
    r = MagicMock()
    r.status_code = 200
    r.headers = {"Content-Type": "application/json"}
    r.json.return_value = {"data": {"api_key": "nested"}}
    assert parse_api_key_from_fetch_response(r) == "nested"


def test_parse_plain_text():
    r = MagicMock()
    r.status_code = 200
    r.headers = {"Content-Type": "text/plain"}
    r.text = "  plain-key  "
    assert parse_api_key_from_fetch_response(r) == "plain-key"


def test_parse_error_status():
    r = MagicMock()
    r.status_code = 500
    r.text = "err"
    assert parse_api_key_from_fetch_response(r) is None
