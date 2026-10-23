#!/usr/bin/env python3
"""Run unit and/or live SocketCAN integration suites and write summary.json."""

from __future__ import annotations

import argparse
import importlib.util
import signal
import socket
import sys
import time
from pathlib import Path

from automation_common import ROOT, discover_ctest, new_run_dir, run_command, utc_now, write_json_atomic

sys.path.insert(0, str(ROOT / "integration"))
import common as integration_common  # noqa: E402

SCENARIOS = ("normal", "warning", "critical", "radar_timeout", "invalid_signal")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suite", choices=("unit", "integration", "all"), default="all")
    p.add_argument("--scenario", action="append", choices=SCENARIOS)
    p.add_argument("--build-dir", type=Path, default=Path("build"))
    p.add_argument("--report-dir", type=Path)
    p.add_argument("--run-dir", type=Path, help=argparse.SUPPRESS)
    p.add_argument("--interface", default="vcan0")
    return p


def resolve(path: Path) -> Path:
    return (Path.cwd() / path).resolve() if not path.is_absolute() else path.resolve()


def integration_preflight(app: Path, interface: str) -> str | None:
    if not app.is_file() or not app.exists() or not app.stat().st_mode & 0o111:
        return f"app executable missing or not executable: {app}; build it with scripts/build.py"
    if importlib.util.find_spec("can") is None or importlib.util.find_spec("cantools") is None:
        return "missing python-can/cantools; activate the project venv and install requirements.txt"
    try:
        socket.if_nametoindex(interface)
        interface_type = int((Path("/sys/class/net") / interface / "type").read_text().strip())
        flags = int((Path("/sys/class/net") / interface / "flags").read_text().strip(), 16)
    except (OSError, ValueError) as error:
        return f"CAN interface {interface!r} is unavailable: {error}; configure an UP vcan interface first"
    if interface_type != 280:
        return f"interface {interface!r} is not vcan (ARPHRD_CAN=280)"
    if not flags & 1:
        return f"vcan interface {interface!r} is down"
    return None


def main(argv: list[str] | None = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    if args.scenario and args.suite == "unit":
        p.error("--scenario is only valid with --suite integration or all")
    if args.scenario and len(set(args.scenario)) != len(args.scenario):
        p.error("scenario selections must not contain duplicates")
    build_dir = resolve(args.build_dir)
    report_root = resolve(args.report_dir) if args.report_dir else build_dir / "reports"
    try:
        run_dir = resolve(args.run_dir) if args.run_dir else new_run_dir(report_root)
        run_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(f"test runner: unable to create report directory: {error}", file=sys.stderr)
        return 1

    started_at, started = utc_now(), time.monotonic()
    selected_scenarios = args.scenario or list(SCENARIOS)
    results: list[dict] = []
    interrupted = False
    interrupt_signal: int | None = None
    stop_integration = False
    print(f"Test report: {run_dir}", flush=True)

    previous_handlers = {}
    def interrupt(signum, _frame):
        nonlocal interrupt_signal
        interrupt_signal = signum
        raise KeyboardInterrupt(f"received signal {signum}")
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[sig] = signal.signal(sig, interrupt)

    try:
        if args.suite in ("unit", "all"):
            if not (build_dir / "CMakeCache.txt").is_file():
                results.append({"name": "ctest", "stage": "unit", "status": "error", "exit_code": 1,
                                "reason": f"configured build directory not found: {build_dir}; run scripts/build.py first"})
            else:
                discovery = discover_ctest(build_dir, run_dir)
                discovery.update(stage="unit")
                results.append(discovery)
                if discovery["status"] == "passed":
                    try:
                        ctest = run_command(["ctest", "--output-on-failure"], build_dir, run_dir, "ctest", timeout=180)
                    except KeyboardInterrupt:
                        results.append({"name": "ctest", "stage": "unit", "status": "error", "exit_code": 130,
                                        "reason": "interrupted while CTest was running; its process group was stopped"})
                        raise
                    ctest.update(stage="unit")
                    results.append(ctest)
            try:
                py = run_command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
                                 ROOT, run_dir, "python-tests", timeout=180)
            except KeyboardInterrupt:
                results.append({"name": "python-tests", "stage": "unit", "status": "error", "exit_code": 130,
                                "reason": "interrupted while Python tests were running; their process group was stopped"})
                raise
            py.update(stage="unit")
            results.append(py)

        if args.suite in ("integration", "all"):
            app = build_dir / "adas_app"
            problem = integration_preflight(app, args.interface)
            if problem:
                results.append({"name": "integration_preflight", "stage": "integration", "status": "error",
                                "exit_code": 1, "reason": problem})
                results.extend({"name": name, "stage": "integration", "status": "not_run",
                                "exit_code": None, "reason": "shared integration prerequisite failed"}
                               for name in selected_scenarios)
                stop_integration = True
            else:
                for name in selected_scenarios:
                    try:
                        scenario = integration_common.run_scenario(
                            name, app_path=app, interface=args.interface,
                            log_root=run_dir / "integration")
                        item = {"name": name, "stage": "integration", "status": scenario.status,
                                "duration_s": round(scenario.duration_s, 6),
                                "exit_code": 0 if scenario.status == "passed" else 1,
                                "reason": scenario.reason,
                                "artifacts": scenario.artifacts,
                                "app_exit_code": scenario.app_exit_code,
                                "simulator_exit_code": scenario.simulator_exit_code}
                        results.append(item)
                        if scenario.interrupted:
                            interrupted = True
                            interrupt_signal = interrupt_signal or (signal.SIGTERM if scenario.interrupt_exit_code == 143 else signal.SIGINT)
                            stop_integration = True
                        if scenario.status == "error" and scenario.reason and "cleanup" in scenario.reason.lower():
                            stop_integration = True
                    except KeyboardInterrupt:
                        interrupted = True
                        interrupt_signal = interrupt_signal or signal.SIGINT
                        stop_integration = True
                        results.append({"name": name, "stage": "integration", "status": "error",
                                        "exit_code": 130, "reason": "interrupted during scenario cleanup"})
                    if stop_integration:
                        break
                done = {item["name"] for item in results if item.get("stage") == "integration"}
                results.extend({"name": name, "stage": "integration", "status": "not_run",
                                "exit_code": None, "reason": "suite stopped before this scenario"}
                               for name in selected_scenarios if name not in done)
    except KeyboardInterrupt:
        interrupted = True
        done = {item["name"] for item in results}
        for name in ("ctest", "python-tests"):
            if args.suite in ("unit", "all") and name not in done:
                results.append({"name": name, "stage": "unit", "status": "not_run", "exit_code": None,
                                "reason": "interrupted before command launch"})
        for name in selected_scenarios:
            if args.suite in ("integration", "all") and name not in done:
                results.append({"name": name, "stage": "integration", "status": "not_run", "exit_code": None,
                                "reason": "interrupted before scenario launch"})
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)

    if interrupted:
        interrupt_code = 143 if interrupt_signal == signal.SIGTERM else 130
        results.append({"name": "runner", "stage": "runner", "status": "error", "exit_code": interrupt_code,
                        "reason": "interrupted by SIGINT or SIGTERM"})
    status = "passed" if results and all(item["status"] == "passed" for item in results) else "failed"
    code = interrupt_code if interrupted else (0 if status == "passed" else 1)
    report = {"schema_version": 1, "run_id": run_dir.name, "started_at": started_at,
              "ended_at": utc_now(), "duration_s": round(time.monotonic() - started, 6),
              "suite": args.suite, "selected_scenarios": selected_scenarios if args.suite != "unit" else [],
              "build_dir": str(build_dir), "interface": args.interface,
              "status": status, "results": results}
    try:
        write_json_atomic(run_dir / "summary.json", report)
    except OSError as error:
        print(f"test runner: could not write summary: {error}", file=sys.stderr)
        return 1
    print(f"Tests {status}; report: {run_dir}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
