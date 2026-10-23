#!/usr/bin/env python3
"""Run the Phase 7 cppcheck quality gate."""

from __future__ import annotations

import argparse
import shutil
import signal
import sys
import time
from pathlib import Path

from automation_common import ROOT, new_run_dir, run_command, utc_now, write_json_atomic


def _on_sigterm(_signum, _frame):
    raise KeyboardInterrupt("received SIGTERM")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report-dir", type=Path)
    p.add_argument("--run-dir", type=Path, help=argparse.SUPPRESS)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report_root = (Path.cwd() / args.report_dir).resolve() if args.report_dir and not args.report_dir.is_absolute() else (args.report_dir.resolve() if args.report_dir else ROOT / "build" / "reports")
    try:
        run_dir = ((Path.cwd() / args.run_dir).resolve() if args.run_dir and not args.run_dir.is_absolute() else args.run_dir.resolve()) if args.run_dir else new_run_dir(report_root)
        run_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(f"static analysis: unable to create report directory: {error}", file=sys.stderr)
        return 1
    started_at, started = utc_now(), time.monotonic()
    results: list[dict] = []
    interrupted = False
    tool = shutil.which("cppcheck")
    version_text = None
    print(f"Static analysis report: {run_dir}", flush=True)
    previous_sigterm = signal.signal(signal.SIGTERM, _on_sigterm)
    if not tool:
        results.append({"name": "cppcheck", "stage": "static_analysis", "status": "error",
                        "exit_code": 1, "reason": "cppcheck is not installed; install it with the system package manager"})
        version = None
    else:
        command = [tool, "--enable=warning,performance", "--std=c++17", "--language=c++",
                   "--error-exitcode=1", "-I", str(ROOT / "include"), str(ROOT / "src"), str(ROOT / "include")]
        try:
            version_result = run_command([tool, "--version"], ROOT, run_dir, "cppcheck-version")
            version = version_result["status"]
            version_path = run_dir / "cppcheck-version.stdout.log"
            version_text = version_path.read_text(errors="replace").strip() if version_path.exists() else ""
            if version_result["status"] != "passed":
                results.append({"name": "cppcheck", "stage": "static_analysis", "status": "error",
                                "exit_code": 1, "reason": "unable to obtain cppcheck version"})
            else:
                result = run_command(command, ROOT, run_dir, "cppcheck")
                result.update(stage="static_analysis", tool_version=version_text)
                results.append(result)
        except KeyboardInterrupt as error:
            interrupted = True
            results.append({"name": "cppcheck", "stage": "static_analysis", "status": "error",
                            "exit_code": 143 if "SIGTERM" in str(error) else 130,
                            "reason": f"interrupted; child process group was stopped ({error})"})
    status = "passed" if results and all(item["status"] == "passed" for item in results) else "failed"
    code = next((item["exit_code"] for item in results if item.get("exit_code") in (130, 143)), 130) if interrupted else (0 if status == "passed" else 1)
    report = {"schema_version": 1, "run_id": run_dir.name, "started_at": started_at,
              "ended_at": utc_now(), "duration_s": round(time.monotonic() - started, 6),
              "stage": "static_analysis", "tool": "cppcheck", "tool_version": version_text if tool else None,
              "platform": "host default; Linux SocketCAN conditional paths analyzed only when host predefines select them",
              "status": status, "results": results}
    try:
        write_json_atomic(run_dir / "static_analysis.json", report)
    except OSError as error:
        print(f"static analysis: could not write report: {error}", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
    print(f"Static analysis {status}; report: {run_dir}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
