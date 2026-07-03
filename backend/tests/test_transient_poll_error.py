# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from deerflow.runtime.async_tasks.poll_status import is_transient_poll_error


def test_transient_connection_reset():
    assert is_transient_poll_error({"message": "('Connection aborted.', ConnectionResetError(54, 'Connection reset by peer'))"})


def test_non_transient_error():
    assert not is_transient_poll_error({"message": "missing job_id in .calc_runtime/job.json"})
