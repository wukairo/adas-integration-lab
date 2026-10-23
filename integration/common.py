"""Shared process lifecycle and assertions for Phase 6 SocketCAN scenarios."""

from __future__ import annotations

import argparse
import importlib.util
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP = ROOT / "build-phase6" / "adas_app"
DEFAULT_LOG_DIR = ROOT / "build-phase6" / "integration-logs"
SIMULATOR = ROOT / "scripts" / "simulate_can.py"
DBC = ROOT / "dbc" / "vehicle.dbc"
SCENARIOS = {"normal", "warning", "critical", "radar_timeout", "invalid_signal"}
TOTAL_TIMEOUT_S = 10.0
TEARDOWN_TIMEOUT_S = 4.0


class ScenarioFailure(RuntimeError):
    pass


@dataclass
class CapturedLine:
    source: str
    stream: str
    line: str
    wall_time: float


def parser(description: str) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=description)
    result.add_argument("--app", type=Path, default=DEFAULT_APP)
    result.add_argument("--interface", default="vcan0")
    result.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    return result


def _validate(args: argparse.Namespace) -> tuple[Path, Path]:
    app = args.app if args.app.is_absolute() else Path.cwd() / args.app
    app = app.resolve()
    if not app.is_file() or not os.access(app, os.X_OK):
        raise ScenarioFailure(f"app executable not found or not executable: {app}")
    if not SIMULATOR.is_file() or not DBC.is_file():
        raise ScenarioFailure("simulator or DBC file is missing from the repository")
    if importlib.util.find_spec("can") is None or importlib.util.find_spec("cantools") is None:
        raise ScenarioFailure("missing python-can/cantools; use .venv/bin/python after installing requirements.txt")
    if not args.interface or len(args.interface) >= 16 or "/" in args.interface:
        raise ScenarioFailure(f"invalid interface name: {args.interface!r}")
    try:
        socket.if_nametoindex(args.interface)
    except OSError as error:
        raise ScenarioFailure(f"CAN interface {args.interface!r} does not exist: {error}") from error
    try:
        interface_type = int((Path("/sys/class/net") / args.interface / "type").read_text().strip())
        flags = int((Path("/sys/class/net") / args.interface / "flags").read_text().strip(), 16)
    except (OSError, ValueError) as error:
        raise ScenarioFailure(f"unable to inspect interface {args.interface!r}: {error}") from error
    if interface_type != 280:
        raise ScenarioFailure(f"interface {args.interface!r} is not vcan (ARPHRD_CAN=280, got {interface_type})")
    if not flags & 1:
        raise ScenarioFailure(f"interface {args.interface!r} is down")
    return app, args.log_dir if args.log_dir.is_absolute() else Path.cwd() / args.log_dir


def _event(line: str) -> dict[str, str] | None:
    if not line.startswith("ADAS_STATE "):
        return None
    fields: dict[str, str] = {}
    for token in line.split()[1:]:
        if "=" in token:
            key, value = token.split("=", 1)
            fields[key] = value
    return fields


def _terminate(process: subprocess.Popen[str] | None, name: str) -> tuple[bool, str]:
    if process is None or process.poll() is not None:
        return False, ""
    forced = False
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        forced = True
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            return True, f"{name} could not be reaped after SIGKILL"
    except ProcessLookupError:
        process.wait(timeout=1.0)
    return forced, f"{name} required SIGKILL" if forced else ""


def run_scenario(scenario: str, expected_level: str | None = None) -> int:
    if scenario not in SCENARIOS:
        print(f"FAIL: unknown scenario {scenario}", file=sys.stderr)
        return 2
    args = parser(f"Run the {scenario} SocketCAN end-to-end scenario.").parse_args()
    app_process: subprocess.Popen[str] | None = None
    simulator_process: subprocess.Popen[str] | None = None
    reader_threads: list[threading.Thread] = []
    records: list[CapturedLine] = []
    records_lock = threading.Lock()
    log_path = None
    failure: str | None = None
    cleanup_failure: str | None = None
    forced_kill = False
    app_ready = False
    sim_started = False
    sim_stopped = False
    sim_exit: int | None = None
    start_wall = time.monotonic()
    deadline = start_wall + TOTAL_TIMEOUT_S

    try:
        log_root = args.log_dir if args.log_dir.is_absolute() else Path.cwd() / args.log_dir
        log_root.mkdir(parents=True, exist_ok=True)
        log_path = log_root / f"{scenario}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}"
        log_path.mkdir()
        (log_path / "summary.txt").write_text(
            f"scenario={scenario}\ninterface={args.interface}\nexpected={expected_level or scenario}\n"
        )
        app, _ = _validate(args)
        commands = {
            "app": [str(app), "--adas", args.interface],
            "simulator": [sys.executable, str(SIMULATOR), "--scenario", scenario, "--interface", args.interface],
        }
        (log_path / "summary.txt").write_text(
            f"scenario={scenario}\nexpected={expected_level or scenario}\ninterface={args.interface}\n"
            f"app_command={commands['app']!r}\nsimulator_command={commands['simulator']!r}\n"
        )

        def start_reader(source: str, stream_name: str, stream, log_file) -> None:
            def read() -> None:
                try:
                    for raw in iter(stream.readline, ""):
                        record = CapturedLine(source, stream_name, raw.rstrip("\n"), time.monotonic())
                        log_file.write(record.line + "\n")
                        log_file.flush()
                        with records_lock:
                            records.append(record)
                finally:
                    stream.close()
                    log_file.close()
            thread = threading.Thread(target=read, name=f"{source}-{stream_name}-reader", daemon=True)
            thread.start()
            reader_threads.append(thread)

        app_process = subprocess.Popen(
            commands["app"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, start_new_session=True,
        )
        app_out = (log_path / "app.stdout.log").open("w", buffering=1)
        app_err = (log_path / "app.stderr.log").open("w", buffering=1)
        start_reader("app", "stdout", app_process.stdout, app_out)
        start_reader("app", "stderr", app_process.stderr, app_err)

        while not app_ready and time.monotonic() < min(deadline, start_wall + 2.0):
            if app_process.poll() is not None:
                raise ScenarioFailure(f"app exited before ADAS_READY (exit={app_process.returncode})")
            with records_lock:
                app_ready = any(r.source == "app" and r.line.startswith("ADAS_READY ") for r in records)
            time.sleep(0.005)
        if not app_ready:
            raise ScenarioFailure("app readiness timeout waiting for ADAS_READY (2 seconds)")

        sim_start_wall = time.monotonic()
        simulator_process = subprocess.Popen(
            commands["simulator"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, start_new_session=True,
        )
        sim_out = (log_path / "simulator.stdout.log").open("w", buffering=1)
        sim_err = (log_path / "simulator.stderr.log").open("w", buffering=1)
        start_reader("simulator", "stdout", simulator_process.stdout, sim_out)
        start_reader("simulator", "stderr", simulator_process.stderr, sim_err)

        while time.monotonic() < deadline:
            if app_process.poll() is not None:
                raise ScenarioFailure(f"app exited unexpectedly while scenario was active (exit={app_process.returncode})")
            with records_lock:
                sim_started = any(r.source == "simulator" and r.line.startswith("SIM_START ") for r in records)
                sim_stopped = any(r.source == "simulator" and r.line.startswith("SIM_STOP reason=completed") for r in records)
            if simulator_process.poll() is not None:
                sim_exit = simulator_process.returncode
                if sim_exit != 0:
                    raise ScenarioFailure(f"simulator exited with {sim_exit}")
                stop_deadline = min(deadline, time.monotonic() + 1.0)
                while time.monotonic() < stop_deadline:
                    with records_lock:
                        sim_stopped = any(r.source == "simulator" and r.line.startswith("SIM_STOP reason=completed") for r in records)
                    if sim_stopped:
                        break
                    time.sleep(0.005)
                if not sim_stopped:
                    raise ScenarioFailure("simulator exited without SIM_STOP reason=completed")
                break
            time.sleep(0.01)
        else:
            raise ScenarioFailure(f"scenario exceeded {TOTAL_TIMEOUT_S:.0f}s deadline")
        if not sim_started:
            raise ScenarioFailure("simulator did not emit SIM_START")
        if time.monotonic() - sim_start_wall > TOTAL_TIMEOUT_S:
            raise ScenarioFailure("simulator completed after the scenario deadline")
        time.sleep(0.05)

        with records_lock:
            app_records = [r for r in records if r.source == "app" and r.stream == "stdout"]
            app_lines = [(r, _event(r.line)) for r in app_records]
            events = [(r, e) for r, e in app_lines if e is not None]
            sim_records = [r for r in records if r.source == "simulator" and r.stream == "stdout"]
        sim_start = next((r.wall_time for r in sim_records if r.line.startswith("SIM_START ")), sim_start_wall)
        sim_stop = next((r.wall_time for r in sim_records if r.line.startswith("SIM_STOP reason=completed")), time.monotonic())
        active_events = [(r, e) for r, e in events if sim_start <= r.wall_time <= sim_stop]
        summary = [f"simulator_exit={sim_exit}", f"app_exit_at_assert={app_process.poll()}",
                   f"simulator_elapsed_s={sim_stop - sim_start:.3f}", f"app_events_in_window={len(active_events)}"]

        if scenario in {"normal", "warning", "critical"}:
            wanted = expected_level or {"normal": "NONE", "warning": "WARNING", "critical": "CRITICAL"}[scenario]
            accepted = [(r, e) for r, e in active_events if e.get("status") == "OK" and e.get("WarningLevel") == wanted]
            if not accepted:
                raise ScenarioFailure(f"expected application state OK/WarningLevel={wanted} during simulator traffic")
            forbidden = [(e.get("status"), e.get("WarningLevel"), e.get("reason")) for _, e in active_events
                         if e.get("status") in {"INVALID_INPUT", "RADAR_TIMEOUT", "VEHICLE_TIMEOUT"}
                         or (e.get("status") == "OK" and e.get("WarningLevel") in {"WARNING", "CRITICAL", "NONE"} and e.get("WarningLevel") != wanted)]
            if forbidden:
                raise ScenarioFailure(f"unexpected application states during traffic: {forbidden}")
            refs = {"WARNING": 20 / 7, "CRITICAL": 1.0, "NONE": None}
            summary.append(f"expected_level={wanted}")
            if refs[wanted] is not None:
                summary.append(f"reference_ttc_s={refs[wanted]:.6f}")
        elif scenario == "radar_timeout":
            no_object = [(r, e) for r, e in active_events if e.get("status") == "OK" and e.get("WarningLevel") == "NONE"]
            timeouts = [(r, e) for r, e in events if e.get("status") == "RADAR_TIMEOUT"]
            phases = [r for r in sim_records if r.line.startswith("SIM_PHASE ") and "phase=radar_silence" in r.line]
            post_phase_vehicle = [r for r in sim_records if r.line.startswith("SIM_TX ") and "id=0x100" in r.line and phases and r.wall_time > phases[0].wall_time]
            if not no_object or not phases or not post_phase_vehicle or not timeouts:
                raise ScenarioFailure("timeout sequence must prove NONE warmup, radar silence, continued vehicle TX, and RADAR_TIMEOUT")
            phase_at = phases[0].wall_time
            candidate = next(((r, e) for r, e in timeouts if r.wall_time >= phase_at), None)
            if candidate is None:
                raise ScenarioFailure("RADAR_TIMEOUT occurred before radar_silence phase")
            record, event = candidate
            age = float(event.get("radar_age_ms", "nan"))
            if not 500 <= age <= 800:
                raise ScenarioFailure(f"radar timeout age outside [500, 800] ms: {age}")
            last_radar_ms = float(event.get("last_radar_ms", "nan"))
            t_ms = float(event.get("t_ms", "nan"))
            if abs((t_ms - last_radar_ms) - age) > 1.5:
                raise ScenarioFailure(f"app timeout timestamps disagree: t={t_ms}, last={last_radar_ms}, age={age}")
            if any(r.wall_time > record.wall_time and e.get("status") == "OK" for r, e in events):
                raise ScenarioFailure("risk state returned while the radar remained silent")
            summary.extend([f"radar_timeout_age_ms={age:.3f}", f"last_radar_ms={last_radar_ms:.3f}",
                            f"vehicle_tx_after_silence={len(post_phase_vehicle)}"])
        else:
            invalid = [(r, e) for r, e in active_events if e.get("status") == "INVALID_INPUT"
                       and e.get("reason") == "OUT_OF_RANGE" and e.get("source") == "VehicleState"]
            diagnostics = [r.line for r in records if r.source == "app" and r.stream == "stderr"
                           and "INVALID_INPUT reason=OUT_OF_RANGE id=0x100" in r.line]
            if not invalid or not diagnostics:
                raise ScenarioFailure("expected INVALID_INPUT state and VehicleState 0x100 diagnostic")
            if any(e.get("status") == "OK" for _, e in active_events):
                raise ScenarioFailure("risk state emitted during invalid-signal traffic")
            summary.append("invalid_state=INVALID_INPUT source=VehicleState reason=OUT_OF_RANGE")

        if app_process.poll() is not None:
            raise ScenarioFailure(f"app exited before teardown (exit={app_process.returncode})")
        (log_path / "summary.txt").write_text(
            f"scenario={scenario}\n" + "\n".join(summary) + "\n" +
            f"app_command={commands['app']!r}\nsimulator_command={commands['simulator']!r}\n"
        )
    except ScenarioFailure as error:
        failure = str(error)
    except KeyboardInterrupt:
        failure = "interrupted by user"
    except Exception as error:
        failure = f"unexpected test error: {type(error).__name__}: {error}"
    finally:
        for process, name in ((simulator_process, "simulator"), (app_process, "app")):
            was_forced, message = _terminate(process, name)
            forced_kill = forced_kill or was_forced
            if message:
                cleanup_failure = f"{cleanup_failure}; {message}" if cleanup_failure else message
            if process is not None and process.returncode not in (None, 0):
                message = f"{name} exited with unexpected code {process.returncode}"
                cleanup_failure = f"{cleanup_failure}; {message}" if cleanup_failure else message
        join_deadline = time.monotonic() + TEARDOWN_TIMEOUT_S
        for thread in reader_threads:
            thread.join(timeout=max(0.0, join_deadline - time.monotonic()))
        if any(thread.is_alive() for thread in reader_threads):
            cleanup_failure = f"{cleanup_failure}; log reader did not stop" if cleanup_failure else "log reader did not stop"
        if forced_kill:
            cleanup_failure = f"{cleanup_failure}; forced process kill is a test failure" if cleanup_failure else "forced process kill is a test failure"
        if log_path and failure:
            with (log_path / "summary.txt").open("a") as output:
                output.write(f"failure={failure}\ncleanup_failure={cleanup_failure or 'none'}\n")

    if cleanup_failure:
        failure = f"{failure}; cleanup: {cleanup_failure}" if failure else f"cleanup failure: {cleanup_failure}"
    if failure:
        print(f"FAIL {scenario}: {failure}", file=sys.stderr)
        if log_path:
            print(f"Logs: {log_path}", file=sys.stderr)
        return 1
    print(f"PASS {scenario}; logs: {log_path}")
    return 0
