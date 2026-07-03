"""SCNet (Sugon/曙光) API executor — pure REST backend.

Implements the documented OpenAPI v2 flow:
  1. POST https://api.scnet.cn/api/user/v3/tokens   (AK/SK + HMAC-SHA256 signature)
  2. GET  {ingressUrls}/ac/openapi/v2/center        (list authorized regions)
  3. GET  {hpcUrls}/hpc/openapi/v2/cluster          (resolve JobManagerID)
  4. file / job submission / polling under hpc + efile URLs

The executor accepts ``cluster_name`` (preferred) or ``cluster_id`` to pin a
specific authorized region; otherwise the first non-platform region is used.
Legacy callers that pass ``hpc_url`` / ``efile_url`` / ``cluster_id`` directly
still work — those values short-circuit the discovery step.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import posixpath
import sys
import time
from pathlib import Path
from typing import Any

from .base import Executor, ExecutionResult, JobHandle, JobState
from ..runtime import append_event, write_progress

try:
    import requests

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


_AUTH_BASE_DEFAULT = "https://api.scnet.cn"        # POST /api/user/v3/tokens
_INGRESS_BASE_DEFAULT = "https://www.scnet.cn"     # GET  /ac/openapi/v2/center  (different host!)


def _hmac_sha256_hex(secret: str, message: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().lower()


def _scnet_signature_payload(access_key: str, timestamp: str, user: str) -> str:
    # SCNet 文档明确"按字典序拼接"，使用 sort_keys 而非依赖 dict 插入顺序。
    payload = {"accessKey": access_key, "timestamp": timestamp, "user": user}
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True)


def _first_enabled_url(entries: list[dict[str, Any]] | None) -> str | None:
    for entry in entries or []:
        if str(entry.get("enable", "true")).lower() == "true":
            url = entry.get("url")
            if url:
                return url.rstrip("/")
    return None


class SCNetExecutor(Executor):
    STATUS_MAP = {
        "statR": JobState.RUNNING,
        "statQ": JobState.PENDING,
        "statH": JobState.PENDING,
        "statS": JobState.RUNNING,
        "statC": JobState.COMPLETED,
        "statE": JobState.FAILED,
        "statW": JobState.PENDING,
        "statX": JobState.UNKNOWN,
        "statDE": JobState.CANCELLED,
        "statD": JobState.FAILED,
        "statT": JobState.FAILED,
        "statN": JobState.FAILED,
        "statRQ": JobState.PENDING,
    }

    def __init__(
        self,
        api_base: str | None = None,
        hpc_url: str | None = None,
        efile_url: str | None = None,
        ingress_url: str | None = None,
        cluster_id: str | None = None,
        cluster_name: str | None = None,
        username: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        token: str | None = None,
        remote_root: str = "/public/home",
        queue: str = "normal",
        nodes: int = 1,
        cores: int = 32,
        walltime: str = "24:00:00",
        vasp_cmd: str = "mpirun vasp_std",
        timeout: int = 60,
        poll_interval: int = 60,
        **_: Any,
    ):
        if not _HAS_REQUESTS:
            raise ImportError("requests is required for SCNet executor: pip install requests")

        self.auth_base = (api_base or _AUTH_BASE_DEFAULT).rstrip("/")
        self.ingress_url = (ingress_url or _INGRESS_BASE_DEFAULT).rstrip("/")
        self.hpc_url = (hpc_url or "").rstrip("/") or None
        self.efile_url = (efile_url or "").rstrip("/") or None
        self.cluster_id = str(cluster_id) if cluster_id else ""
        self.cluster_name = cluster_name or ""
        self.username = username or ""
        self.access_key = access_key or ""
        self.secret_key = secret_key or ""
        self.remote_root = remote_root
        self.queue = queue
        self.nodes = nodes
        self.cores = cores
        self.walltime = walltime
        self.vasp_cmd = vasp_cmd
        self.timeout = timeout
        self.poll_interval = poll_interval

        self._token: str | None = token
        self._token_expiry: float = time.time() + 3600 if token else 0
        self._job_manager_id: str | None = None

    def _ensure_credentials(self) -> None:
        missing = [
            k
            for k, v in {
                "username": self.username,
                "access_key": self.access_key,
                "secret_key": self.secret_key,
            }.items()
            if not v
        ]
        if missing:
            raise RuntimeError(
                f"SCNet executor missing credentials: {', '.join(missing)}"
            )

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 300:
            return self._token
        return self._refresh_token()

    def _refresh_token(self) -> str:
        self._ensure_credentials()
        timestamp = str(int(time.time()))
        signature = _hmac_sha256_hex(
            self.secret_key,
            _scnet_signature_payload(self.access_key, timestamp, self.username),
        )
        headers = {
            "user": self.username,
            "accessKey": self.access_key,
            "signature": signature,
            "timestamp": timestamp,
            "Content-Type": "application/json",
        }
        resp = requests.post(
            f"{self.auth_base}/api/user/v3/tokens",
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("code")) != "0":
            raise RuntimeError(f"SCNet token request failed: {data.get('msg')}")
        regions = [r for r in (data.get("data") or []) if r.get("token")]
        region = self._select_region(regions)
        self._token = region["token"]
        self._token_expiry = time.time() + 3600
        if not self.cluster_id and region.get("clusterId"):
            self.cluster_id = str(region["clusterId"])
        if not self.cluster_name and region.get("clusterName"):
            self.cluster_name = str(region["clusterName"])
        if not self.hpc_url or not self.efile_url:
            self._discover_region_urls()
        return self._token

    def _select_region(self, regions: list[dict[str, Any]]) -> dict[str, Any]:
        if not regions:
            raise RuntimeError("SCNet token response had no usable regions")
        if self.cluster_id:
            for r in regions:
                if str(r.get("clusterId")) == str(self.cluster_id):
                    return r
        if self.cluster_name:
            for r in regions:
                if r.get("clusterName") == self.cluster_name:
                    return r
        for r in regions:
            cid = str(r.get("clusterId") or "")
            if cid and cid != "0":
                return r
        return regions[0]

    def _discover_region_urls(self) -> None:
        resp = requests.get(
            f"{self.ingress_url}/ac/openapi/v2/center",
            headers={"token": self._token, "Content-Type": "application/json"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("code")) != "0":
            raise RuntimeError(f"SCNet center discovery failed: {data.get('msg')}")
        payload = data.get("data") or {}
        regions = payload if isinstance(payload, list) else [payload]
        chosen = None
        for region in regions:
            if self.cluster_id and str(region.get("id")) == str(self.cluster_id):
                chosen = region
                break
            if self.cluster_name and region.get("name") == self.cluster_name:
                chosen = region
                break
        chosen = chosen or (regions[0] if regions else {})
        hpc = _first_enabled_url(chosen.get("hpcUrls"))
        efile = _first_enabled_url(chosen.get("efileUrls"))
        if not hpc or not efile:
            raise RuntimeError("SCNet center response missing hpcUrls/efileUrls")
        self.hpc_url = hpc.removesuffix("/hpc")
        # SCNet returns efileUrls already including "/efile" suffix; strip so
        # downstream "/efile/openapi/v2/..." concatenation doesn't duplicate it.
        self.efile_url = efile.removesuffix("/efile")
        if not self.cluster_id and chosen.get("id"):
            self.cluster_id = str(chosen["id"])
        if not self.cluster_name and chosen.get("name"):
            self.cluster_name = str(chosen["name"])
        cluster_user = chosen.get("clusterUserInfo") or {}
        if cluster_user.get("homePath"):
            self.remote_root = cluster_user["homePath"]
        if cluster_user.get("userName"):
            self.username = self.username or cluster_user["userName"]

    def _ensure_runtime_endpoints(self) -> None:
        self._get_token()
        if not self.hpc_url or not self.efile_url:
            self._discover_region_urls()

    def _headers(self) -> dict[str, str]:
        return {"token": self._get_token(), "Content-Type": "application/json"}

    def _efile_headers(self) -> dict[str, str]:
        return {"token": self._get_token()}

    def _hpc_request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        self._ensure_runtime_endpoints()
        url = f"{self.hpc_url}/hpc/openapi/v2{endpoint}"
        resp = requests.request(method, url, headers=self._headers(), timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("code")) != "0":
            raise RuntimeError(f"SCNet HPC API error: {data.get('msg')}")
        return data.get("data")

    def _efile_request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        self._ensure_runtime_endpoints()
        url = f"{self.efile_url}/efile/openapi/v2{endpoint}"
        resp = requests.request(method, url, headers=self._efile_headers(), timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("code")) != "0":
            raise RuntimeError(f"SCNet efile API error: {data.get('msg')}")
        return data.get("data")

    def _resolve_job_manager_id(self) -> str:
        if self._job_manager_id:
            return self._job_manager_id
        clusters = self._hpc_request("GET", "/cluster") or []
        if not isinstance(clusters, list):
            clusters = [clusters]
        if not clusters:
            raise RuntimeError("SCNet /hpc/openapi/v2/cluster returned no entries")
        chosen = clusters[0]
        for entry in clusters:
            text = entry.get("text") or ""
            if self.cluster_name and text == self.cluster_name:
                chosen = entry
                break
        self._job_manager_id = str(chosen.get("id"))
        return self._job_manager_id

    @staticmethod
    def _check_efile_response(resp: "requests.Response", action: str) -> None:
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            return
        code = str(data.get("code", "0"))
        if code == "0":
            return
        if code == "911021" and action.startswith("mkdir"):
            return  # idempotent: directory already exists
        raise RuntimeError(f"SCNet efile {action} failed: code={code} msg={data.get('msg')}")

    def _mkdir(self, remote_path: str) -> None:
        self._ensure_runtime_endpoints()
        resp = requests.post(
            f"{self.efile_url}/efile/openapi/v2/file/mkdir",
            params={"path": remote_path, "createParents": "true"},
            headers=self._efile_headers(),
            timeout=self.timeout,
        )
        self._check_efile_response(resp, f"mkdir {remote_path}")

    # Files that must arrive on the cluster with LF line endings. VASP refuses
    # CRLF on INCAR/KPOINTS/POSCAR with IERR=5 ("Error reading item ... from
    # file INCAR"). Bash/Slurm scripts also break on CRLF.
    _TEXT_NAMES = {"INCAR", "KPOINTS", "POSCAR", "CONTCAR", "POTCAR",
                   "submit.sh", "job.sh", "stderr.txt"}
    _TEXT_SUFFIXES = {".sh", ".txt", ".yaml", ".yml", ".gjf", ".com", ".py"}

    def _upload_file(self, local_path: Path, remote_dir: str) -> None:
        self._ensure_runtime_endpoints()
        if local_path.name in self._TEXT_NAMES or local_path.suffix.lower() in self._TEXT_SUFFIXES:
            payload: tuple[str, Any, str] = (
                local_path.name,
                local_path.read_bytes().replace(b"\r\n", b"\n"),
                "application/octet-stream",
            )
            resp = requests.post(
                f"{self.efile_url}/efile/openapi/v2/file/upload",
                headers=self._efile_headers(),
                data={"path": remote_dir, "cover": "cover"},
                files=[("file", payload)],
                timeout=max(self.timeout, 300),
            )
        else:
            with open(local_path, "rb") as fh:
                resp = requests.post(
                    f"{self.efile_url}/efile/openapi/v2/file/upload",
                    headers=self._efile_headers(),
                    data={"path": remote_dir, "cover": "cover"},
                    files=[("file", (local_path.name, fh, "application/octet-stream"))],
                    timeout=max(self.timeout, 300),
                )
        self._check_efile_response(resp, f"upload {local_path.name} → {remote_dir}")

    def _upload_dir(self, local_dir: Path, remote_dir: str) -> None:
        self._mkdir(remote_dir)
        for entry in local_dir.iterdir():
            if entry.name.startswith("."):
                continue
            remote = posixpath.join(remote_dir, entry.name)
            if entry.is_dir():
                self._upload_dir(entry, remote)
            else:
                self._upload_file(entry, remote_dir)

    def _download_file(self, remote_path: str, local_path: Path) -> None:
        self._ensure_runtime_endpoints()
        resp = requests.get(
            f"{self.efile_url}/efile/openapi/v2/file/download",
            params={"path": remote_path},
            headers=self._efile_headers(),
            timeout=max(self.timeout, 300),
            stream=True,
        )
        resp.raise_for_status()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                fh.write(chunk)

    def _list_dir(self, remote_dir: str) -> list[dict[str, Any]]:
        try:
            data = self._efile_request(
                "GET",
                "/file/list",
                params={"path": remote_dir, "start": 0, "limit": 500},
            )
            return data.get("fileList", []) if data else []
        except Exception:
            return []

    def _resolve_remote_work(self, local_work_dir: Path) -> str:
        parts = local_work_dir.resolve().parts
        suffix = "_".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
        if self.remote_root.endswith(self.username):
            base = self.remote_root
        else:
            base = posixpath.join(self.remote_root, self.username)
        return posixpath.join(base, "vasp_skills_runs", suffix)

    def _submit_job(self, remote_dir: str, cmd: str, job_name: str = "vasp") -> str:
        manager_id = self._resolve_job_manager_id()
        payload = {
            "strJobManagerID": manager_id,
            "mapAppJobInfo": {
                "GAP_CMD_FILE": cmd,
                "GAP_NNODE": str(self.nodes),
                "GAP_NODE_STRING": "",
                "GAP_SUBMIT_TYPE": "cmd",
                "GAP_JOB_NAME": job_name,
                "GAP_WORK_DIR": remote_dir,
                "GAP_QUEUE": self.queue,
                "GAP_PPN": str(self.cores),
                "GAP_NPROC": "",
                "GAP_NGPU": "",
                "GAP_NDCU": "",
                "GAP_WALL_TIME": self.walltime,
                "GAP_EXCLUSIVE": "",
                "GAP_APPNAME": "VASP",
                "GAP_MULTI_SUB": "",
                "GAP_STD_OUT_FILE": f"{remote_dir}/vasp_%j.out",
                "GAP_STD_ERR_FILE": f"{remote_dir}/vasp_%j.err",
                "GAP_CLUSTER_ID": self.cluster_id,
                "advance": False,
            },
        }
        result = self._hpc_request("POST", "/apptemplates/BASIC/BASE/job", json=payload)
        return str(result)

    def _poll_job(self, job_id: str) -> str:
        manager_id = self._resolve_job_manager_id()
        try:
            data = self._hpc_request(
                "GET",
                f"/jobs/{job_id}",
                params={"strJobManagerID": manager_id},
            )
            if isinstance(data, dict) and data.get("jobStatus"):
                return self.STATUS_MAP.get(data["jobStatus"], "UNKNOWN")
        except Exception:
            pass
        try:
            data = self._hpc_request(
                "GET",
                "/jobs",
                params={
                    "strClusterIDList": manager_id,
                    "strJobId": job_id,
                },
            )
            if data and data.get("list"):
                return self.STATUS_MAP.get(data["list"][0].get("jobStatus"), "UNKNOWN")
        except Exception:
            pass
        try:
            data = self._hpc_request("GET", f"/historyjobs/{manager_id}/{job_id}")
            if isinstance(data, dict):
                js = data.get("jobState")
                if js is None:
                    return JobState.UNKNOWN
                return self.STATUS_MAP.get(js, JobState.UNKNOWN)
        except Exception:
            return "UNKNOWN"
        return "UNKNOWN"

    def _read_remote_file(self, remote_path: str, pages: int = 1) -> str:
        try:
            self._ensure_runtime_endpoints()
            resp = requests.post(
                f"{self.hpc_url}/hpc/openapi/v2/file/content",
                headers={"token": self._get_token(), "Content-Type": "application/x-www-form-urlencoded"},
                data={"dirPath": remote_path, "triggerNum": pages, "rollDirection": "UP"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return data.get("data", "")
        except Exception:
            return ""

    def run(self, work_dir: Path, command: str, timeout: int | None = None) -> ExecutionResult:
        remote_wd = self._resolve_remote_work(work_dir)
        self._upload_dir(work_dir, remote_wd)
        job_id = self._submit_job(remote_wd, command, job_name="vasp-run")
        handle = JobHandle(
            job_id=job_id, backend="scnet", remote_work_dir=remote_wd,
            submitted_at=time.time(),
        )
        state = self._wait_one(handle, work_dir)
        self.fetch(remote_wd, work_dir, patterns=None)
        rc = 0 if state == JobState.COMPLETED else 1
        stdout = self._read_remote_file(posixpath.join(remote_wd, "vasp.out"))
        return ExecutionResult(rc, stdout, "", remote_work_dir=remote_wd, job_id=job_id)

    # ----------------------------------------------------- detached API
    def enqueue(self, work_dir: Path, submit_script: str, job_name: str = "vasp") -> JobHandle:
        remote_wd = self._resolve_remote_work(work_dir)
        (work_dir / "submit.sh").write_text(
            submit_script.replace("\r\n", "\n"),
            encoding="utf-8",
            newline="\n",
        )
        self._upload_dir(work_dir, remote_wd)
        cmd = f"cd {remote_wd} && bash submit.sh"
        job_id = self._submit_job(remote_wd, cmd, job_name=job_name)
        return JobHandle(
            job_id=job_id,
            backend="scnet",
            remote_work_dir=remote_wd,
            submitted_at=time.time(),
        )

    def poll(self, handle: JobHandle) -> str:
        return self._poll_job(handle.job_id)

    def cancel(self, handle: JobHandle) -> None:
        """Delete via official batch endpoint.

        SCNet doc: DELETE {hpcUrls}/hpc/openapi/v2/jobs
            form params: jobMethod=5
                         strJobInfoMap=<managerId>,<user>:<jobId>:;...
        """
        if not handle.job_id:
            return
        manager_id = self._resolve_job_manager_id()
        info = f"{manager_id},{self.username}:{handle.job_id}:"
        try:
            self._ensure_runtime_endpoints()
            requests.delete(
                f"{self.hpc_url}/hpc/openapi/v2/jobs",
                headers={
                    "token": self._get_token(),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"jobMethod": "5", "strJobInfoMap": info},
                timeout=self.timeout,
            )
        except Exception:
            pass

    def _initial_poll_interval(self, work_dir: Path) -> tuple[int, int]:
        return self.poll_interval, min(self.poll_interval * 10, 900)

    def _read_remote_stdout(self, handle: JobHandle, work_dir: Path) -> str:
        return self._read_remote_file(posixpath.join(handle.remote_work_dir, "vasp.out"))

    def fetch(self, remote_work_dir: str, local_work_dir: Path,
              patterns: list[str] | None = None) -> None:
        local_work_dir.mkdir(parents=True, exist_ok=True)
        entries = self._list_dir(remote_work_dir)
        wanted = set(patterns) if patterns else None
        for entry in entries:
            name = entry.get("name", "")
            if not name or entry.get("isDirectory"):
                continue
            if wanted and name not in wanted:
                continue
            remote_path = entry.get("path") or posixpath.join(remote_work_dir, name)
            try:
                self._download_file(remote_path, local_work_dir / name)
            except Exception as e:
                print(f"  [scnet] download {name} failed: {e}", file=sys.stderr, flush=True)

    def close(self) -> None:
        pass
