#!/usr/bin/env python3
"""Configure, build, and optionally run CTest with isolated logs."""

from __future__ import annotations

import argparse
import os
import re
import signal
import shutil
import sys
import time
from pathlib import Path

from automation_common import ROOT, discover_ctest, new_run_dir, run_command, utc_now, write_json_atomic


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build-type", choices=("Debug", "Release"), default="Debug")
    p.add_argument("--clean", action="store_true")
    p.add_argument("--build-dir", type=Path, default=Path("build"))
    p.add_argument("--report-dir", type=Path)
    p.add_argument("--run-dir", type=Path, help=argparse.SUPPRESS)
    p.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    p.add_argument("--skip-tests", action="store_true")
    return p


def resolve_from_cwd(path: Path) -> Path:
    return (Path.cwd() / path).resolve() if not path.is_absolute() else path.resolve()


def validate_clean_target(build_arg: Path, build_dir: Path) -> None:
    if build_arg.is_symlink():
        raise ValueError("refusing to clean a symlink build directory")
    if build_dir == Path(build_dir.anchor) or build_dir == ROOT or build_dir in ROOT.parents:
        raise ValueError(f"refusing to clean protected directory: {build_dir}")
    source_roots = {ROOT / name for name in ("src", "include", "tests", "scripts", "integration", "dbc", "docs", "config")}
    if any(build_dir == source or source in build_dir.parents for source in source_roots):
        raise ValueError(f"refusing to clean a project source directory: {build_dir}")
    if any((build_dir / source).exists() for source in ("src", "include", "tests", "scripts", "integration", "dbc", "docs")):
        raise ValueError(f"refusing to clean a directory containing project source: {build_dir}")
    if build_dir.exists() and any(path.name == ".git" for path in build_dir.rglob(".git")):
        raise ValueError(f"refusing to clean a directory containing .git: {build_dir}")
    cache = build_dir / "CMakeCache.txt"
    if build_dir.exists():
        if not cache.is_file():
            raise ValueError("--clean requires a CMakeCache.txt for this repository or a non-existing directory")
        content = cache.read_text(errors="replace")
        match = re.search(r"^CMAKE_HOME_DIRECTORY:INTERNAL=(.*)$", content, re.MULTILINE)
        if not match or Path(match.group(1)).resolve() != ROOT:
            raise ValueError("refusing to clean: CMake cache does not belong to this repository")


def _on_sigterm(_signum, _frame):
    raise KeyboardInterrupt("received SIGTERM")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.jobs <= 0:
        parser().error("--jobs must be greater than zero")
    build_dir = resolve_from_cwd(args.build_dir)
    report_root = resolve_from_cwd(args.report_dir) if args.report_dir else build_dir / "reports"
    if args.clean:
        try:
            validate_clean_target(args.build_dir, build_dir)
        except (OSError, ValueError) as error:
            print(f"build: {error}", file=sys.stderr)
            return 1
    try:
        if args.clean and build_dir.exists():
            shutil.rmtree(build_dir)
        run_dir = resolve_from_cwd(args.run_dir) if args.run_dir else new_run_dir(report_root)
        run_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(f"build: unable to create report directory: {error}", file=sys.stderr)
        return 1

    started_at = utc_now()
    started = time.monotonic()
    results: list[dict] = []
    print(f"Build report: {run_dir}", flush=True)
    previous_sigterm = signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        build_dir.parent.mkdir(parents=True, exist_ok=True)
        stages = [
            ("configure", ["cmake", "-S", str(ROOT), "-B", str(build_dir),
                            f"-DCMAKE_BUILD_TYPE={args.build_type}", "-DBUILD_TESTING=ON"]),
            ("build", ["cmake", "--build", str(build_dir), "--parallel", str(args.jobs)]),
        ]
        for name, command in stages:
            print(f"[{name}] {' '.join(command)}", flush=True)
            result = run_command(command, ROOT, run_dir, name)
            results.append(result)
            if result["status"] != "passed":
                print(f"[{name}] failed: {result.get('reason', 'command failure')}", file=sys.stderr)
                break
        if results and results[-1]["status"] == "passed" and not args.skip_tests:
            print("[ctest] discovering tests", flush=True)
            discovery = discover_ctest(build_dir, run_dir)
            discovery.update(stage="ctest")
            results.append(discovery)
            if discovery["status"] != "passed":
                print(f"[ctest] failed: {discovery.get('reason', 'test discovery failed')}", file=sys.stderr)
            else:
                print("[ctest] running discovered tests", flush=True)
                result = run_command(["ctest", "--output-on-failure"], build_dir, run_dir, "ctest", timeout=180)
                result.update(stage="ctest")
                results.append(result)
    except KeyboardInterrupt as error:
        interrupt_code = 143 if "SIGTERM" in str(error) else 130
        results.append({"name": "build", "stage": "build", "status": "error",
                        "exit_code": interrupt_code, "reason": f"interrupted: {error or 'SIGINT'}"})
    except Exception as error:
        results.append({"name": "build", "stage": "build", "status": "error",
                        "exit_code": 1, "reason": f"wrapper error: {type(error).__name__}: {error}"})
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)

    status = "passed" if results and all(item["status"] == "passed" for item in results) else "failed"
    code = 0 if status == "passed" else next((item.get("exit_code") or 1 for item in results if item["status"] != "passed"), 1)
    report = {"schema_version": 1, "run_id": run_dir.name, "started_at": started_at,
              "ended_at": utc_now(), "duration_s": round(time.monotonic() - started, 6),
              "build_type": args.build_type, "build_dir": str(build_dir), "status": status,
              "results": results}
    try:
        write_json_atomic(run_dir / "summary.json", report)
    except OSError as error:
        print(f"build: could not write summary: {error}", file=sys.stderr)
        return 1
    print(f"Build {status}; report: {run_dir}", flush=True)
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
