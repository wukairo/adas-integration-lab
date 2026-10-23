"""Shared helpers for local build and test automation."""

from __future__ import annotations

import json
import os
import re
import signal
import signal
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_run_dir(report_root: Path, run_id: str | None = None) -> Path:
    report_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = report_root / (run_id or f"{stamp}-{os.getpid()}")
    run_dir.mkdir(parents=False, exist_ok=False)
    return run_dir.resolve()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def normalized_returncode(returncode: int) -> int:
    return returncode if returncode >= 0 else 128 + abs(returncode)


def run_command(command: list[str], cwd: Path, log_dir: Path, name: str,
                timeout: float | None = None) -> dict[str, Any]:
    """Run one command without a shell, preserving raw streams and a structured result."""
    started = time.monotonic()
    result: dict[str, Any] = {
        "name": name, "stage": name, "command": command, "status": "error",
        "exit_code": None, "duration_s": 0.0,
        "artifacts": {"stdout": str(log_dir / f"{name}.stdout.log"),
                      "stderr": str(log_dir / f"{name}.stderr.log")},
    }
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        with Path(result["artifacts"]["stdout"]).open("w") as stdout, \
                Path(result["artifacts"]["stderr"]).open("w") as stderr:
            process = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr,
                                       shell=False, start_new_session=True)
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=2)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                result.update(status="error", exit_code=124, reason=f"command timed out after {timeout}s")
                return result
            except KeyboardInterrupt:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=2)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                raise
        code = normalized_returncode(returncode)
        result["exit_code"] = code
        result["status"] = "passed" if code == 0 else "failed"
        if code:
            result["reason"] = f"command exited with status {code}"
    except OSError as error:
        result.update(status="error", exit_code=1, reason=f"unable to run command: {error}")
    finally:
        result["duration_s"] = round(time.monotonic() - started, 6)
    return result

def signal_exit_code(signum: int) -> int:
    return 128 + signum


def discover_ctest(build_dir: Path, log_dir: Path) -> dict[str, Any]:
    """Check that CTest actually discovered at least one test on old and new CTest versions."""
    result = run_command(["ctest", "-N"], build_dir, log_dir, "ctest-discovery", timeout=180)
    output_path = Path(result["artifacts"]["stdout"])
    output = output_path.read_text(errors="replace") if output_path.exists() else ""
    match = re.search(r"Total Tests:\s*(\d+)", output)
    count = int(match.group(1)) if match else None
    result["test_count"] = count
    if result["status"] == "passed" and count is None:
        result.update(status="error", exit_code=1, reason="could not read CTest discovered test count")
    elif result["status"] == "passed" and count == 0:
        result.update(status="error", exit_code=1, reason="CTest discovered no tests")
    return result
