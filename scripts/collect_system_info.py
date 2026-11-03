#!/usr/bin/env python3
"""Write a point-in-time snapshot of host and build toolchain information."""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from automation_common import ROOT, write_json_atomic


def command_version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if output else None


def git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


def cpu_metrics() -> dict[str, Any]:
    result: dict[str, Any] = {"logical_count": os.cpu_count()}
    try:
        model = None
        with Path("/proc/cpuinfo").open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if line.lower().startswith(("model name", "hardware")) and ":" in line:
                    model = line.split(":", 1)[1].strip()
                    if model:
                        break
        result["model"] = model
    except OSError:
        result["model"] = None
    try:
        first = _cpu_times()
        time.sleep(0.1)
        second = _cpu_times()
        total_delta = sum(second) - sum(first)
        idle_delta = (second[3] + second[4]) - (first[3] + first[4])
        result["utilization_percent"] = (
            round(100.0 * (total_delta - idle_delta) / total_delta, 2)
            if total_delta > 0
            else None
        )
    except (OSError, ValueError, IndexError):
        result["utilization_percent"] = None
    return result


def _cpu_times() -> list[int]:
    with Path("/proc/stat").open(encoding="ascii") as stream:
        fields = stream.readline().split()[1:]
    # Linux appends guest and guest_nice counters, which are already counted
    # in user and nice. Exclude them to avoid double-counting CPU time.
    return [int(value) for value in fields[:8]]


def memory_metrics() -> dict[str, Any]:
    values: dict[str, int] = {}
    try:
        with Path("/proc/meminfo").open(encoding="ascii") as stream:
            for line in stream:
                match = re.match(r"^(MemTotal|MemAvailable):\s+(\d+)\s+kB", line)
                if match:
                    values[match.group(1)] = int(match.group(2)) * 1024
    except OSError:
        pass
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    used = (
        max(total - available, 0)
        if total is not None and available is not None
        else None
    )
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": used,
        "utilization_percent": round(100.0 * used / total, 2)
        if total and used is not None
        else None,
    }


def disk_metrics(path: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return {
            "path": str(path),
            "total_bytes": None,
            "used_bytes": None,
            "free_bytes": None,
            "utilization_percent": None,
        }
    used = usage.total - usage.free
    return {
        "path": str(path),
        "total_bytes": usage.total,
        "used_bytes": used,
        "free_bytes": usage.free,
        "utilization_percent": round(100.0 * used / usage.total, 2)
        if usage.total
        else None,
    }


def load_average() -> dict[str, Any]:
    try:
        values = os.getloadavg()
    except (AttributeError, OSError):
        values = None
    return {
        "1_min": round(values[0], 2) if values else None,
        "5_min": round(values[1], 2) if values else None,
        "15_min": round(values[2], 2) if values else None,
    }


def collect(build_dir: Path, output_path: Path) -> dict[str, Any]:
    cache = build_dir / "CMakeCache.txt"
    cache_values: dict[str, str] = {}
    if cache.is_file():
        for line in cache.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"^([^#/:][^:]*):[^=]*=(.*)$", line)
            if match:
                cache_values[match.group(1)] = match.group(2)
    cxx = cache_values.get("CMAKE_CXX_COMPILER") or shutil.which("c++") or "c++"
    compiler_version = command_version([cxx, "--version"])
    loadavg = load_average()
    return {
        "schema_version": 1,
        "captured_at_utc": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "snapshot": True,
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "cpu": cpu_metrics(),
        "memory": memory_metrics(),
        "disk": disk_metrics(output_path.parent),
        "load_average": loadavg,
        "toolchain": {
            "cxx_compiler": cxx,
            "cxx_compiler_version": compiler_version,
            "cmake": command_version(["cmake", "--version"]),
            "git": command_version(["git", "--version"]),
            "cmake_build_type": cache_values.get("CMAKE_BUILD_TYPE"),
            "git_commit": git_commit(),
        },
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=Path("system_info.json"))
    p.add_argument("--build-dir", type=Path, default=Path("build"))
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    output = args.output if args.output.is_absolute() else Path.cwd() / args.output
    build_dir = (
        args.build_dir if args.build_dir.is_absolute() else Path.cwd() / args.build_dir
    )
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = collect(build_dir.resolve(), output.resolve())
        write_json_atomic(output, payload)
    except (OSError, ValueError) as error:
        print(f"collect_system_info: {error}", file=sys.stderr)
        return 1
    print(f"System information: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
