"""Tests for async task envelope parsing and poll status mapping."""

from deerflow.runtime.async_tasks.envelope import (
    redact_poll_command_from_submitted_envelope_text,
    resolve_submit_envelope,
    tool_message_content_to_text,
)
from deerflow.runtime.async_tasks.poll_status import extract_poll_json, map_poll_dict_to_task_status


def test_resolve_submit_last_line():
    raw = 'logs...\n{"status": "submitted", "task_kind": "t", "external_ref": "1"}\n'
    env = resolve_submit_envelope(raw)
    assert env is not None
    assert env["task_kind"] == "t"


def test_resolve_submit_defer_false():
    raw = '{"status":"submitted","task_kind":"x","external_ref":"1","defer":false}'
    assert resolve_submit_envelope(raw) is None


def test_poll_mapping():
    stdout = 'noise\n{"status":"completed","result":{"ok":true}}\n'
    d = extract_poll_json(stdout)
    assert d is not None
    status, err = map_poll_dict_to_task_status(d)
    assert status == "succeeded"
    assert err is None


def test_tool_multipart_content():
    text = tool_message_content_to_text([{"type": "text", "text": '{"status":"submitted","task_kind":"k","external_ref":"z"}'}])
    assert resolve_submit_envelope(text) is not None


def test_merged_bash_stderr_envelope_last():
    merged = 'some stdout\nStd Error:\n[vasp-relax] submitting\n{"status":"submitted","task_kind":"vasp_relax","external_ref":"123","poll_interval_seconds":60,"poll_command":"python x"}'
    env = resolve_submit_envelope(merged)
    assert env is not None
    assert env["task_kind"] == "vasp_relax"


def test_redact_poll_command_from_submitted_line():
    raw = 'out\n{"status":"submitted","task_kind":"k","external_ref":"1","poll_command":"PYTHONPATH=x python y"}\n'
    red = redact_poll_command_from_submitted_envelope_text(raw)
    assert "poll_command" not in red
    assert resolve_submit_envelope(red) is not None
