import sys
import types
import unittest
import can
from cantools.database.errors import EncodeError
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import simulate_can  # noqa: E402


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeBus:
    def __init__(self, clock=None, fail=False):
        self.messages = []
        self.sent_times = []
        self.clock = clock
        self.fail = fail
        self.closed = False

    def send(self, message, timeout=None):
        if self.fail:
            raise OSError("injected send failure")
        self.messages.append((message.arbitration_id, bytes(message.data)))
        self.sent_times.append(self.clock.now if self.clock is not None else 0.0)

    def shutdown(self):
        self.closed = True


class SimulatorContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = simulate_can.load_and_validate_dbc(ROOT / "dbc" / "vehicle.dbc")

    def test_scenario_payload_oracles(self):
        expected = {
            "normal": ("F401000000000000", "E803000001000000"),
            "warning": ("2003000000000000", "C800BC0201000000"),
            "critical": ("2003000000000000", "6400E80301000000"),
            "radar_timeout": ("F401000000000000", "E803000001000000"),
            "invalid_signal": ("C20B000000000000", "E803000001000000"),
        }
        for scenario, payloads in expected.items():
            with self.subTest(scenario=scenario):
                vehicle, radar = simulate_can.encode_scenario(self.db, scenario)
                self.assertEqual(vehicle.hex().upper(), payloads[0])
                self.assertEqual(radar.hex().upper(), payloads[1])
                self.assertEqual((len(vehicle), len(radar)), (8, 8))
                self.assertEqual(vehicle[4:] and vehicle[4] & 0xFE, 0)
                self.assertEqual(radar[4:] and radar[4] & 0xFE, 0)

    def test_signed_little_endian_vectors(self):
        vehicle = self.db.get_message_by_name("VehicleState").encode(
            {"VehicleSpeed": 80, "SteeringAngle": -12.5, "BrakeStatus": 0}
        )
        radar = self.db.get_message_by_name("RadarObject").encode(
            {"ObjectDistance": 20, "RelativeVelocity": -7, "ObjectValid": 1}
        )
        self.assertEqual(bytes(vehicle)[2:4].hex().upper(), "83FF")
        self.assertEqual(bytes(radar)[2:4].hex().upper(), "44FD")

    def test_happy_encoder_is_strict_and_fault_encoder_is_explicit(self):
        with self.assertRaises(EncodeError):
            self.db.get_message_by_name("VehicleState").encode(
                {"VehicleSpeed": 301, "SteeringAngle": 0, "BrakeStatus": 0}, strict=True
            )
        vehicle, _ = simulate_can.encode_scenario(self.db, "invalid_signal")
        self.assertEqual(vehicle.hex().upper(), "C20B000000000000")
        with self.assertRaises(EncodeError):
            self.db.get_message_by_name("VehicleState").encode(
                {"VehicleSpeed": 301, "SteeringAngle": 0, "BrakeStatus": 0}, strict=True
            )

    def test_dbc_contract_rejects_wrong_file(self):
        with self.assertRaises(simulate_can.SimulatorError):
            simulate_can.load_and_validate_dbc(ROOT / "does-not-exist.dbc")


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.can_module = types.SimpleNamespace(
            Message=lambda **kwargs: types.SimpleNamespace(**kwargs)
        )

    def schedule(self, config, sleep=None, fail=False):
        clock = FakeClock()
        bus = FakeBus(clock, fail)
        with mock.patch.object(simulate_can, "_message", side_effect=lambda frame_id, data: types.SimpleNamespace(
                arbitration_id=frame_id, data=data)), \
                mock.patch.object(simulate_can, "_log"):
            reason, vehicles, radars = simulate_can.run_schedule(
                config, b"\x00" * 8, b"\x01" * 8, bus,
                clock=clock.monotonic,
                sleep=sleep or clock.sleep,
            )
        return bus, (reason, vehicles, radars)

    def test_radar_stops_after_warmup_while_vehicle_continues(self):
        config = simulate_can.Config("radar_timeout", "vcan0", Path("unused"), 100, 1.3, 0.2)
        bus, summary = self.schedule(config)
        ids = [frame_id for frame_id, _ in bus.messages]
        self.assertEqual(ids[:4], [0x100, 0x200, 0x100, 0x200])
        self.assertGreater(ids.count(0x100), ids.count(0x200))
        self.assertEqual(ids.count(0x200), 2)
        self.assertEqual(summary, ("completed", 13, 2))

    def test_late_tick_skips_missed_periods_without_burst(self):
        config = simulate_can.Config("normal", "vcan0", Path("unused"), 100, 0.7, None)
        clock = FakeClock()
        calls = 0

        def delayed_sleep(seconds):
            nonlocal calls
            calls += 1
            clock.now += seconds + (0.35 if calls == 1 else 0)

        bus = FakeBus(clock)
        with mock.patch.object(simulate_can, "_message", side_effect=lambda frame_id, data: types.SimpleNamespace(
                arbitration_id=frame_id, data=data)):
            simulate_can.run_schedule(
                config, b"\0" * 8, b"\1" * 8, bus,
                clock=clock.monotonic, sleep=delayed_sleep,
            )
        vehicle_times = [
            bus.sent_times[i]
            for i in range(len(bus.messages))
            if bus.messages[i][0] == 0x100
        ]
        self.assertGreaterEqual(len(vehicle_times), 2)
        self.assertGreaterEqual(vehicle_times[1] - vehicle_times[0], 0.4)

    def test_send_failure_raises_and_runtime_closes_bus(self):
        config = simulate_can.Config("normal", "vcan0", Path("unused"), 100, 0.2, None)
        bus = FakeBus(fail=True)
        simulate_can.load_and_validate_dbc(ROOT / "dbc" / "vehicle.dbc")
        with mock.patch.object(can, "Bus", return_value=bus), \
                mock.patch.object(simulate_can, "_message", side_effect=lambda frame_id, data: types.SimpleNamespace(
                    arbitration_id=frame_id, data=data)):
            with self.assertRaises(simulate_can.SimulatorError):
                simulate_can.run(config, ROOT / "dbc" / "vehicle.dbc")
        self.assertTrue(bus.closed)


class CliValidationTests(unittest.TestCase):
    def test_timeout_cli_defaults_and_invalid_timing(self):
        config = simulate_can.parse_config(["--scenario", "radar_timeout"])
        self.assertEqual(config.warmup_s, 1.0)
        invalid_cases = [
            ["--scenario", "normal", "--period-ms", "0"],
            ["--scenario", "normal", "--period-ms", "-1"],
            ["--scenario", "normal", "--period-ms", "inf"],
            ["--scenario", "normal", "--period-ms", "1e-320"],
            ["--scenario", "normal", "--duration-s", "nan"],
            ["--scenario", "normal", "--duration-s", "-0.1"],
            ["--scenario", "radar_timeout", "--duration-s", "1"],
            ["--scenario", "normal", "--warmup-s", "0.5"],
            ["--scenario", "radar_timeout", "--duration-s", "3", "--warmup-s", "inf"],
            ["--scenario", "radar_timeout", "--duration-s", "3", "--warmup-s", "0"],
            ["--scenario", "radar_timeout", "--duration-s", "2", "--warmup-s", "1.1"],
        ]
        for args in invalid_cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                simulate_can.parse_config(args)

    def test_relative_default_dbc_is_script_independent(self):
        self.assertEqual(simulate_can.DEFAULT_DBC, ROOT / "dbc" / "vehicle.dbc")
        self.assertTrue(simulate_can.DEFAULT_DBC.is_absolute())


if __name__ == "__main__":
    unittest.main()
