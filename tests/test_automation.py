"""Failure-path checks for the local automation entrypoints."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "integration"))

import build  # noqa: E402
import common as integration_common  # noqa: E402
import static_analysis  # noqa: E402


class BuildAutomationTests(unittest.TestCase):
    def test_configure_failure_is_propagated_and_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            fake_bin = tmp / "bin"
            fake_bin.mkdir()
            cmake = fake_bin / "cmake"
            cmake.write_text("#!/bin/sh\nprintf 'injected configure failure\\n' >&2\nexit 9\n")
            cmake.chmod(0o755)
            with mock.patch.dict(os.environ, {"PATH": f"{fake_bin}:{os.environ['PATH']}"}):
                code = build.main(["--build-dir", str(tmp / "build"), "--report-dir", str(tmp / "reports"),
                                   "--skip-tests"])
            self.assertEqual(code, 9)
            runs = list((tmp / "reports").iterdir())
            self.assertEqual(len(runs), 1)
            report = json.loads((runs[0] / "summary.json").read_text())
            self.assertEqual(report["results"][0]["status"], "failed")
            self.assertIn("injected configure failure", (runs[0] / "configure.stderr.log").read_text())
            self.assertFalse((runs[0] / "build.stdout.log").exists())

    def test_clean_guard_rejects_source_tree_and_preserves_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "unsafe"
            source = target / "src"
            source.mkdir(parents=True)
            marker = source / "keep.txt"
            marker.write_text("keep")
            with self.assertRaises(ValueError):
                build.validate_clean_target(target, target.resolve())
            self.assertEqual(marker.read_text(), "keep")

    def test_clean_guard_rejects_cache_from_another_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "build"
            target.mkdir()
            (target / "CMakeCache.txt").write_text("CMAKE_HOME_DIRECTORY:INTERNAL=/different/repository\n")
            marker = target / "keep.txt"
            marker.write_text("keep")
            with self.assertRaisesRegex(ValueError, "does not belong"):
                build.validate_clean_target(target, target.resolve())
            self.assertEqual(marker.read_text(), "keep")


class ReportAndScenarioTests(unittest.TestCase):
    def test_cppcheck_finding_fails_quality_gate_and_is_logged(self):
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            fake_bin = tmp / "bin"
            fake_bin.mkdir()
            cppcheck = fake_bin / "cppcheck"
            cppcheck.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"--version\" ]; then echo 'Cppcheck 0.test'; exit 0; fi\n"
                "echo '[injected] (warning) controlled finding' >&2\nexit 1\n"
            )
            cppcheck.chmod(0o755)
            with mock.patch.dict(os.environ, {"PATH": f"{fake_bin}:{os.environ['PATH']}"}):
                code = static_analysis.main(["--report-dir", str(tmp / "reports")])
            self.assertEqual(code, 1)
            run_dir = next((tmp / "reports").iterdir())
            report = json.loads((run_dir / "static_analysis.json").read_text())
            self.assertEqual(report["results"][0]["status"], "failed")
            self.assertIn("controlled finding", (run_dir / "cppcheck.stderr.log").read_text())

    def test_missing_cppcheck_is_an_error_with_report(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(static_analysis.shutil, "which", return_value=None):
            code = static_analysis.main(["--report-dir", temp])
            self.assertEqual(code, 1)
            reports = list(Path(temp).iterdir())
            self.assertEqual(len(reports), 1)
            report = json.loads((reports[0] / "static_analysis.json").read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["results"][0]["status"], "error")

    def test_scenario_returns_structured_preflight_failure_after_log_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            result = integration_common.run_scenario(
                "normal", app_path=Path(temp) / "missing-app", interface="vcan0",
                log_root=Path(temp) / "logs")
            self.assertIn(result.status, {"failed", "error"})
            self.assertIn("app executable", result.reason or "")
            log_dir = Path(result.artifacts["log_dir"])
            self.assertTrue((log_dir / "summary.txt").is_file())
            self.assertIsNone(result.app_exit_code)
            self.assertIsNone(result.simulator_exit_code)


class InterruptionTests(unittest.TestCase):
    def test_sigterm_stops_build_child_and_writes_partial_report(self):
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            fake_bin = tmp / "bin"
            fake_bin.mkdir()
            ready = tmp / "child.pid"
            cmake = fake_bin / "cmake"
            cmake.write_text("#!/bin/sh\nsleep 30 &\nchild=$!\nprintf '%s\\n' \"$child\" > \"$PHASE7_CHILD_PID\"\nwait \"$child\"\n")
            cmake.chmod(0o755)
            report_root = tmp / "reports"
            env = os.environ.copy()
            env.update(PATH=f"{fake_bin}:{env['PATH']}", PHASE7_CHILD_PID=str(ready))
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "scripts" / "build.py"), "--build-dir", str(tmp / "build"),
                 "--report-dir", str(report_root), "--skip-tests"],
                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            try:
                self.assertIn("Build report:", process.stdout.readline())
                self.assertIn("[configure]", process.stdout.readline())
                deadline = time.monotonic() + 3
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(ready.exists(), "fake configure command did not start")
                child_pid = int(ready.read_text().strip())
                os.kill(process.pid, signal.SIGTERM)
                output, _ = process.communicate(timeout=8)
                self.assertEqual(process.returncode, 143, output)
                run_dir = next(report_root.iterdir())
                report = json.loads((run_dir / "summary.json").read_text())
                self.assertEqual(report["status"], "failed")
                self.assertTrue(any(item.get("exit_code") == 143 for item in report["results"]))
                try:
                    state = Path(f"/proc/{child_pid}/stat").read_text().split()[2]
                except FileNotFoundError:
                    state = None
                self.assertIn(state, (None, "Z"), "the configure child remained alive after SIGTERM cleanup")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
