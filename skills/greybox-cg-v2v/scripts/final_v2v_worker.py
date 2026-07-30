#!/usr/bin/env python3
"""Detached local worker for one greybox final V2V executor invocation."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AI_MODEL_INPUT_ENV = "AI_MODEL_CALLING_INPUT"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_write_json(path: Path, payload: dict[str, Any], *, attempts: int = 5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        for attempt in range(1, attempts + 1):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if attempt == attempts:
                    raise
                time.sleep(0.05 * (2 ** (attempt - 1)))
    finally:
        temp.unlink(missing_ok=True)


def load_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("worker request must be an object")
    argv = payload.get("argv")
    model_input = payload.get("model_input")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        raise ValueError("worker argv must be a non-empty string array")
    if not isinstance(model_input, dict):
        raise ValueError("worker model_input must be an object")
    for field in ("job_id", "status_path", "result_path", "stdout_path", "stderr_path"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise ValueError(f"worker request requires {field}")
    return payload


def run(request_path: Path) -> int:
    request: dict[str, Any] | None = None
    started_at = utc_now()
    try:
        request = load_request(request_path)
        status_path = Path(request["status_path"])
        result_path = Path(request["result_path"])
        stdout_path = Path(request["stdout_path"])
        stderr_path = Path(request["stderr_path"])
        stdout_path.parent.mkdir(parents=True, exist_ok=True)

        atomic_write_json(
            status_path,
            {
                "version": 1,
                "job_id": request["job_id"],
                "state": "worker_starting",
                "worker_pid": os.getpid(),
                "started_at": started_at,
            },
        )
        env = os.environ.copy()
        env.pop("GREYBOX_V2V_INPUT", None)
        env.pop(AI_MODEL_INPUT_ENV, None)
        env[AI_MODEL_INPUT_ENV] = json.dumps(request["model_input"], ensure_ascii=False, sort_keys=True)
        with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
            downstream = subprocess.Popen(
                request["argv"],
                shell=False,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                close_fds=True,
            )
            atomic_write_json(
                status_path,
                {
                    "version": 1,
                    "job_id": request["job_id"],
                    "state": "running",
                    "worker_pid": os.getpid(),
                    "downstream_pid": downstream.pid,
                    "started_at": started_at,
                },
            )
            returncode = downstream.wait()

        completed_at = utc_now()
        atomic_write_json(
            result_path,
            {
                "version": 1,
                "job_id": request["job_id"],
                "worker_pid": os.getpid(),
                "downstream_pid": downstream.pid,
                "returncode": returncode,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "started_at": started_at,
                "completed_at": completed_at,
            },
        )
        atomic_write_json(
            status_path,
            {
                "version": 1,
                "job_id": request["job_id"],
                "state": "completed",
                "worker_pid": os.getpid(),
                "downstream_pid": downstream.pid,
                "returncode": returncode,
                "started_at": started_at,
                "completed_at": completed_at,
                "result_path": str(result_path),
            },
        )
        return 0
    except Exception as exc:
        completed_at = utc_now()
        error = " ".join(str(exc).replace("\x00", "").split())[:1000]
        if request is not None:
            result_path = Path(request["result_path"])
            status_path = Path(request["status_path"])
            failure = {
                "version": 1,
                "job_id": request.get("job_id"),
                "worker_pid": os.getpid(),
                "returncode": 70,
                "worker_error": error,
                "stdout_path": request.get("stdout_path"),
                "stderr_path": request.get("stderr_path"),
                "started_at": started_at,
                "completed_at": completed_at,
            }
            try:
                atomic_write_json(result_path, failure)
                atomic_write_json(status_path, {**failure, "state": "worker_failed", "result_path": str(result_path)})
            except Exception:
                pass
        print(json.dumps({"success": False, "worker_error": error}), file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one persisted greybox final V2V worker request.")
    parser.add_argument("--request", required=True)
    args = parser.parse_args(argv)
    return run(Path(args.request))


if __name__ == "__main__":
    sys.exit(main())
