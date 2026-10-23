#!/usr/bin/env python3
"""Send deterministic ADAS scenario traffic over a Linux SocketCAN interface."""

from __future__ import annotations

import argparse
import math
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

try:
    import can
except ImportError as error:
    can = None
    _CAN_IMPORT_ERROR = error
else:
    _CAN_IMPORT_ERROR = None

try:
    import cantools
except ImportError as error:
    cantools = None
    _CANTOOLS_IMPORT_ERROR = error
else:
    _CANTOOLS_IMPORT_ERROR = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DBC = ROOT / "dbc" / "vehicle.dbc"
SCENARIOS = ("normal", "warning", "critical", "radar_timeout", "invalid_signal")


class SimulatorError(Exception):
    """A runtime or configuration error that should exit with status 1."""


@dataclass(frozen=True)
class Scenario:
    vehicle: dict[str, float | int]
    radar: dict[str, float | int]
    invalid_vehicle: bool = False


@dataclass(frozen=True)
class Config:
    scenario: str
    interface: str
    dbc_path: Path
    period_ms: float
    duration_s: float
    warmup_s: float | None


SCENARIO_DATA = {
    "normal": Scenario(
        {"VehicleSpeed": 50, "SteeringAngle": 0, "BrakeStatus": 0},
        {"ObjectDistance": 100, "RelativeVelocity": 0, "ObjectValid": 1},
    ),
    "warning": Scenario(
        {"VehicleSpeed": 80, "SteeringAngle": 0, "BrakeStatus": 0},
        {"ObjectDistance": 20, "RelativeVelocity": 7, "ObjectValid": 1},
    ),
    "critical": Scenario(
        {"VehicleSpeed": 80, "SteeringAngle": 0, "BrakeStatus": 0},
        {"ObjectDistance": 10, "RelativeVelocity": 10, "ObjectValid": 1},
    ),
    "radar_timeout": Scenario(
        {"VehicleSpeed": 50, "SteeringAngle": 0, "BrakeStatus": 0},
        {"ObjectDistance": 100, "RelativeVelocity": 0, "ObjectValid": 1},
    ),
    "invalid_signal": Scenario(
        {"VehicleSpeed": 301, "SteeringAngle": 0, "BrakeStatus": 0},
        {"ObjectDistance": 100, "RelativeVelocity": 0, "ObjectValid": 1},
        invalid_vehicle=True,
    ),
}

EXPECTED_MESSAGES = {
    "VehicleState": (0x100, 8, False, False),
    "RadarObject": (0x200, 8, False, False),
}

EXPECTED_SIGNALS = {
    "VehicleSpeed": ("VehicleState", 0, 16, "little_endian", False, 0.1, 0, 0, 300),
    "SteeringAngle": ("VehicleState", 16, 16, "little_endian", True, 0.1, 0, -720, 720),
    "BrakeStatus": ("VehicleState", 32, 1, "little_endian", False, 1, 0, 0, 1),
    "ObjectDistance": ("RadarObject", 0, 16, "little_endian", False, 0.1, 0, 0, 500),
    "RelativeVelocity": ("RadarObject", 16, 16, "little_endian", True, 0.01, 0, -100, 100),
    "ObjectValid": ("RadarObject", 32, 1, "little_endian", False, 1, 0, 0, 1),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, choices=SCENARIOS)
    parser.add_argument("--interface", default="vcan0")
    parser.add_argument("--dbc", type=Path, default=DEFAULT_DBC)
    parser.add_argument("--period-ms", type=float, default=100)
    parser.add_argument("--duration-s", type=float, default=3)
    parser.add_argument("--warmup-s", type=float)
    return parser


def parse_config(argv: Iterable[str] | None = None) -> Config:
    args = build_parser().parse_args(argv)
    period_s = args.period_ms / 1000.0
    for name, value in (("period-ms", args.period_ms), ("duration-s", args.duration_s)):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"--{name} must be finite and greater than zero")
    if period_s < time.get_clock_info("monotonic").resolution:
        raise ValueError("--period-ms is below the monotonic clock resolution")
    if not args.interface or len(args.interface) >= 16 or "/" in args.interface:
        raise ValueError("--interface must be a Linux interface name shorter than 16 characters")
    if args.scenario == "radar_timeout":
        warmup_s = 1.0 if args.warmup_s is None else args.warmup_s
        if not math.isfinite(warmup_s) or warmup_s <= 0:
            raise ValueError("--warmup-s must be finite and greater than zero")
        if warmup_s < period_s:
            raise ValueError("--warmup-s must be at least one --period-ms")
        if warmup_s >= args.duration_s:
            raise ValueError("--warmup-s must be less than --duration-s")
        if args.duration_s - warmup_s < 1.0:
            raise ValueError("radar_timeout requires at least 1 second of silence")
    elif args.warmup_s is not None:
        raise ValueError("--warmup-s is only valid for radar_timeout")
    return Config(
        args.scenario,
        args.interface,
        args.dbc,
        args.period_ms,
        args.duration_s,
        warmup_s if args.scenario == "radar_timeout" else None,
    )


def load_and_validate_dbc(path: Path):
    if cantools is None:
        raise SimulatorError(
            "missing Python dependency; create .venv and install requirements.txt"
        ) from _CANTOOLS_IMPORT_ERROR
    try:
        database = cantools.database.load_file(str(path), strict=True)
    except Exception as error:
        raise SimulatorError(f"unable to load DBC {path}: {error}") from error

    try:
        for name, expected in EXPECTED_MESSAGES.items():
            message = database.get_message_by_name(name)
            actual = (
                message.frame_id,
                message.length,
                message.is_extended_frame,
                message.is_fd,
            )
            if actual != expected:
                raise SimulatorError(f"DBC contract mismatch for {name}: expected {expected}, got {actual}")
        expected_by_message = {
            "VehicleState": {"VehicleSpeed", "SteeringAngle", "BrakeStatus"},
            "RadarObject": {"ObjectDistance", "RelativeVelocity", "ObjectValid"},
        }
        for message_name, expected_names in expected_by_message.items():
            message = database.get_message_by_name(message_name)
            actual_names = {signal_def.name for signal_def in message.signals}
            if actual_names != expected_names:
                raise SimulatorError(
                    f"DBC contract mismatch for {message_name} signals: "
                    f"expected {sorted(expected_names)}, got {sorted(actual_names)}"
                )
        for name, expected in EXPECTED_SIGNALS.items():
            message_name, start, length, byte_order, signed, scale, offset, minimum, maximum = expected
            message = database.get_message_by_name(message_name)
            signal_def = message.get_signal_by_name(name)
            actual = (
                signal_def.start,
                signal_def.length,
                signal_def.byte_order,
                signal_def.is_signed,
                signal_def.scale,
                signal_def.offset,
                signal_def.minimum,
                signal_def.maximum,
            )
            wanted = (start, length, byte_order, signed, scale, offset, minimum, maximum)
            if actual != wanted:
                raise SimulatorError(f"DBC contract mismatch for {name}: expected {wanted}, got {actual}")
    except KeyError as error:
        raise SimulatorError(f"DBC is missing message or signal {error}") from error
    return database


def encode_scenario(database, scenario_name: str) -> tuple[bytes, bytes]:
    """Encode a scenario using the DBC; only invalid_signal relaxes range checks."""
    scenario = SCENARIO_DATA[scenario_name]
    vehicle = database.get_message_by_name("VehicleState").encode(
        scenario.vehicle, strict=not scenario.invalid_vehicle
    )
    radar = database.get_message_by_name("RadarObject").encode(scenario.radar, strict=True)
    return bytes(vehicle), bytes(radar)


def _log(message: str, stream=None) -> None:
    if stream is None:
        stream = sys.stdout
    print(message, file=stream, flush=True)


def _elapsed_ms(start: float, clock: Callable[[], float]) -> int:
    return max(0, int((clock() - start) * 1000))


def run_schedule(
    config: Config,
    vehicle_payload: bytes,
    radar_payload: bytes,
    bus,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    stop_requested: Callable[[], bool] = lambda: False,
) -> tuple[str, int, int]:
    start = clock()
    duration = config.duration_s
    period = config.period_ms / 1000.0
    warmup = config.warmup_s
    vehicle_count = radar_count = 0
    next_tick = 0
    phase_logged = False
    scenario = config.scenario
    fault = " fault=VehicleSpeedOutOfRange" if scenario == "invalid_signal" else ""
    warmup_log = f" warmup_s={warmup:g}" if warmup is not None else ""
    _log(
        f"SIM_START scenario={scenario} interface={config.interface} "
        f"period_ms={config.period_ms:g} duration_s={duration:g}"
        f"{warmup_log}{fault}"
    )

    while not stop_requested():
        now = clock()
        elapsed = now - start
        if elapsed >= duration:
            break
        deadline = start + next_tick * period
        if next_tick > 0 and now > deadline:
            elapsed_tick = math.floor(elapsed / period)
            if elapsed_tick > next_tick:
                next_tick = elapsed_tick + 1
            deadline = start + next_tick * period
        if now < deadline:
            sleep(min(deadline - now, start + duration - now, 0.1))
            continue
        remaining = duration - elapsed
        timeout = min(1.0, remaining)
        try:
            bus.send(_message(0x100, vehicle_payload), timeout=timeout)
            vehicle_count += 1
            _log(
                f"SIM_TX t_ms={_elapsed_ms(start, clock)} scenario={scenario} "
                f"id=0x100 dlc=8 data={vehicle_payload.hex().upper()}"
            )
            elapsed = clock() - start
            if scenario != "radar_timeout" or (warmup is not None and elapsed < warmup):
                remaining = duration - elapsed
                if remaining > 0:
                    bus.send(_message(0x200, radar_payload), timeout=min(1.0, remaining))
                    radar_count += 1
                    _log(
                        f"SIM_TX t_ms={_elapsed_ms(start, clock)} scenario={scenario} "
                        f"id=0x200 dlc=8 data={radar_payload.hex().upper()}"
                    )
            elif not phase_logged:
                _log(f"SIM_PHASE t_ms={_elapsed_ms(start, clock)} phase=radar_silence")
                phase_logged = True
        except Exception as error:
            raise SimulatorError(f"CAN send failed: {error}") from error

        next_tick += 1

    reason = "interrupted" if stop_requested() else "completed"
    return reason, vehicle_count, radar_count


def _message(arbitration_id: int, payload: bytes):
    if can is None:
        raise SimulatorError(
            "missing Python dependency; create .venv and install requirements.txt"
        ) from _CAN_IMPORT_ERROR
    return can.Message(
        arbitration_id=arbitration_id,
        is_extended_id=False,
        is_remote_frame=False,
        is_error_frame=False,
        data=payload,
        check=True,
    )


def run(config: Config, dbc_path: Path) -> int:
    database = load_and_validate_dbc(dbc_path)
    try:
        vehicle_payload, radar_payload = encode_scenario(database, config.scenario)
    except Exception as error:
        raise SimulatorError(f"unable to encode scenario {config.scenario}: {error}") from error
    if can is None:
        raise SimulatorError(
            "missing Python dependency; create .venv and install requirements.txt"
        ) from _CAN_IMPORT_ERROR

    try:
        bus = can.Bus(interface="socketcan", channel=config.interface)
    except Exception as error:
        raise SimulatorError(f"unable to open SocketCAN interface {config.interface}: {error}") from error

    interrupted = False
    previous_handlers = {}

    def handle_stop(_signum, _frame):
        nonlocal interrupted
        interrupted = True

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, handle_stop)
        reason, vehicle_count, radar_count = run_schedule(
            config,
            vehicle_payload,
            radar_payload,
            bus,
            stop_requested=lambda: interrupted,
        )
        _log(
            f"SIM_STOP reason={reason} vehicle_sent={vehicle_count} radar_sent={radar_count}"
        )
        return 0
    except SimulatorError:
        raise
    except Exception as error:
        raise SimulatorError(f"simulator failed: {error}") from error
    finally:
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
        bus.shutdown()


def main(argv: Iterable[str] | None = None) -> int:
    try:
        config = parse_config(argv)
    except SystemExit as error:
        return int(error.code)
    except ValueError as error:
        _log(f"SIM_ERROR {error}", stream=sys.stderr)
        return 2
    try:
        dbc_path = config.dbc_path if config.dbc_path.is_absolute() else Path.cwd() / config.dbc_path
        return run(config, dbc_path.resolve())
    except SimulatorError as error:
        _log(f"SIM_ERROR {error}", stream=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
