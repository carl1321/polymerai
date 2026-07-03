"""SSH executor stub — full implementation to be ported from
legacy `gaussian_agent.executors.ssh` in a later phase.

Planned surface:
    class SSHExecutor:
        def __init__(self, host, username, key_path, work_dir, gaussian_module, scheduler)
        def submit(self, input_path) -> job_id
        def poll(self, job_id) -> status
        def fetch(self, job_id, local_dir) -> log_path
"""


class SSHExecutor:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "SSHExecutor will be ported from gaussian_agent in Step 5 of PLAN.md."
        )
