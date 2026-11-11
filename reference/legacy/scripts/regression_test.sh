#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
PYTHON_BIN="${PYTHON:-python3}"
SUITE="full"
BISECT=0
BUILD_DIR=""
INTERFACE="vcan0"

usage() {
    cat <<'EOF'
Usage: regression_test.sh [--suite quick|full] [--bisect] [--build-dir PATH] [--interface NAME]
EOF
}

while (($#)); do
    case "$1" in
        --suite)
            (($# >= 2)) || { usage >&2; exit 2; }
            SUITE="$2"; shift 2 ;;
        --bisect) BISECT=1; shift ;;
        --build-dir)
            (($# >= 2)) || { usage >&2; exit 2; }
            BUILD_DIR="$2"; shift 2 ;;
        --interface)
            (($# >= 2)) || { usage >&2; exit 2; }
            INTERFACE="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

[[ "$SUITE" == quick || "$SUITE" == full ]] || { printf 'Invalid suite: %s\n' "$SUITE" >&2; exit 2; }
if [[ -z "$BUILD_DIR" ]]; then
    [[ $BISECT -eq 1 ]] && BUILD_DIR="$ROOT/build-bisect" || BUILD_DIR="$ROOT/build"
fi
case "$BUILD_DIR" in /*) ;; *) BUILD_DIR="$(pwd -P)/$BUILD_DIR" ;; esac
REPORT_ROOT="$BUILD_DIR/reports"
if [[ $BISECT -eq 1 ]]; then REPORT_ROOT="${BUILD_DIR}-reports"; fi
mkdir -p -- "$REPORT_ROOT" || exit 1
RUN_ID="regression-$(date -u +%Y%m%dT%H%M%S.%N)-$$"
RUN_DIR="$REPORT_ROOT/$RUN_ID"
mkdir -- "$RUN_DIR" || exit 1
printf 'Regression report: %s\n' "$RUN_DIR" >&2

interrupted=0
trap 'interrupted=130' INT
trap 'interrupted=143' TERM
start_epoch="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
start_duration="$SECONDS"

preflight_error=""
command -v "$PYTHON_BIN" >/dev/null 2>&1 || preflight_error="Python executable not found: $PYTHON_BIN"
for tool in cmake ctest cppcheck c++ make; do
    if [[ -z "$preflight_error" ]] && ! command -v "$tool" >/dev/null 2>&1; then
        preflight_error="required tool not found: $tool"
    fi
done
if [[ -z "$preflight_error" ]]; then
    if ! "$PYTHON_BIN" -c 'import can, cantools' >/dev/null 2>&1; then
        preflight_error="missing python-can/cantools for the selected Python: $PYTHON_BIN"
    elif ! "$PYTHON_BIN" -c 'import pathlib, subprocess, tempfile; d=tempfile.TemporaryDirectory(); p=pathlib.Path(d.name); (p/"CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.16)\nproject(phase7_prerequisite_check LANGUAGES CXX)\nfind_package(GTest CONFIG REQUIRED)\n"); r=subprocess.run(["cmake", "-S", str(p), "-B", str(p/"build")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); d.cleanup(); raise SystemExit(r.returncode)' >/dev/null 2>&1; then
        preflight_error="C++ compiler or GoogleTest CMake package is unavailable"
    elif [[ "$SUITE" == full ]]; then
        if ! command -v ip >/dev/null 2>&1; then
            preflight_error="required tool not found: ip (iproute2)"
        else
            link_info="$(ip -details -o link show dev "$INTERFACE" 2>/dev/null || true)"
            if [[ -z "$link_info" || "$link_info" != *vcan* || "$link_info" != *UP* ]]; then
                preflight_error="interface '$INTERFACE' is missing, not vcan, or down; configure an UP vcan interface"
            fi
        fi
    fi
fi

declare -A stage_status=([preflight]=passed [build]=not_run [static_analysis]=not_run [tests]=not_run)
declare -A stage_reason=()
exit_code=0
if [[ -n "$preflight_error" ]]; then
    stage_status[preflight]=error
    stage_reason[preflight]="$preflight_error"
    if [[ $BISECT -eq 1 ]]; then exit_code=125; else exit_code=1; fi
else
    stage_status[preflight]=passed
fi

write_report() {
    "$PYTHON_BIN" - "$RUN_DIR" "$RUN_ID" "$SUITE" "$BUILD_DIR" "$INTERFACE" "$start_epoch" \
        "$((SECONDS - start_duration))" \
        "${stage_status[preflight]}" "${stage_reason[preflight]:-}" \
        "${stage_status[build]}" "${stage_reason[build]:-}" \
        "${stage_status[static_analysis]}" "${stage_reason[static_analysis]:-}" \
        "${stage_status[tests]}" "${stage_reason[tests]:-}" <<'PY'
import json, os, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
run_dir, run_id, suite, build_dir, interface, started, duration, *stages = sys.argv[1:]
names = ("preflight", "build", "static_analysis", "tests")
results = []
for i, name in enumerate(names):
    status, reason = stages[i * 2:i * 2 + 2]
    child = Path(run_dir) / ("build" if name == "build" else "static_analysis" if name == "static_analysis" else "tests") / ("summary.json" if name == "build" else "static_analysis.json" if name == "static_analysis" else "summary.json")
    detail = {}
    if child.is_file():
        try: detail = json.loads(child.read_text())
        except (OSError, ValueError): detail = {}
    results.append({"name": name, "stage": name, "status": status, "reason": reason or None,
                    "results": detail.get("results", []), "report": str(child) if child.is_file() else None})
overall = "passed" if all(r["status"] == "passed" for r in results) else "failed"
payload = {"schema_version": 1, "run_id": run_id, "started_at": started,
           "ended_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
           "duration_s": float(duration),
           "suite": suite, "build_dir": build_dir, "interface": interface,
           "status": overall, "results": results}
fd, name = tempfile.mkstemp(prefix=".summary.", suffix=".tmp", dir=run_dir)
with os.fdopen(fd, "w") as f:
    json.dump(payload, f, indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
os.replace(name, Path(run_dir) / "summary.json")
PY
}

if [[ $exit_code -eq 0 && $interrupted -eq 0 ]]; then
    build_args=("$ROOT/scripts/build.py" --build-type Debug --build-dir "$BUILD_DIR" --skip-tests --run-dir "$RUN_DIR/build")
    [[ $BISECT -eq 1 ]] && build_args+=(--clean)
    "$PYTHON_BIN" "${build_args[@]}"
    rc=$?
    if ((rc == 0)); then stage_status[build]=passed
    elif ((rc >= 128)); then stage_status[build]=error; stage_reason[build]="interrupted (exit $rc)"; exit_code=$rc
    else stage_status[build]=failed; stage_reason[build]="build failed (exit $rc)"; exit_code=1
    fi
fi

if [[ $exit_code -eq 0 && $interrupted -eq 0 && "${stage_status[build]}" == passed ]]; then
    "$PYTHON_BIN" "$ROOT/scripts/static_analysis.py" --run-dir "$RUN_DIR/static_analysis"
    rc=$?
    if ((rc == 0)); then stage_status[static_analysis]=passed
    elif ((rc >= 128)); then stage_status[static_analysis]=error; stage_reason[static_analysis]="interrupted (exit $rc)"; exit_code=$rc
    else stage_status[static_analysis]=failed; stage_reason[static_analysis]="cppcheck quality gate failed (exit $rc)"; exit_code=1
    fi
fi

if [[ $exit_code -eq 0 && $interrupted -eq 0 && "${stage_status[static_analysis]}" == passed ]]; then
    test_suite=unit
    [[ "$SUITE" == full ]] && test_suite=all
    "$PYTHON_BIN" "$ROOT/scripts/run_tests.py" --suite "$test_suite" --build-dir "$BUILD_DIR" \
        --interface "$INTERFACE" --run-dir "$RUN_DIR/tests"
    rc=$?
    if ((rc == 0)); then stage_status[tests]=passed
    elif ((rc >= 128)); then stage_status[tests]=error; stage_reason[tests]="interrupted (exit $rc)"; exit_code=$rc
    else stage_status[tests]=failed; stage_reason[tests]="selected tests failed (exit $rc)"; exit_code=1
    fi
fi

if ((interrupted != 0)); then
    if ((exit_code == 0)); then exit_code=$interrupted; fi
    for stage in build static_analysis tests; do
        if [[ "${stage_status[$stage]}" == not_run ]]; then
            stage_status[$stage]=not_run
            stage_reason[$stage]="not run after interrupt"
        fi
    done
fi

write_report || { printf 'Unable to write regression summary in %s\n' "$RUN_DIR" >&2; exit 1; }
printf 'Regression %s; report: %s\n' "$([[ $exit_code -eq 0 ]] && printf passed || printf failed)" "$RUN_DIR"
exit "$exit_code"
