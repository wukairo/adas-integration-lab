"""Contract tests for system snapshots and release artifact packaging."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import collect_system_info  # noqa: E402
import package_artifact  # noqa: E402


class SystemInfoTests(unittest.TestCase):
    def test_collector_writes_snapshot_with_metrics_and_toolchain_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            build = temp_path / "build"
            build.mkdir()
            (build / "CMakeCache.txt").write_text(
                "CMAKE_BUILD_TYPE:STRING=Release\n"
                "CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/c++\n"
            )
            output = temp_path / "reports" / "system_info.json"
            code = collect_system_info.main(
                ["--output", str(output), "--build-dir", str(build)]
            )
            self.assertEqual(code, 0)
            payload = json.loads(output.read_text())
            self.assertEqual(payload["schema_version"], 1)
            self.assertTrue(payload["snapshot"])
            self.assertTrue(payload["captured_at_utc"].endswith("Z"))
            for group in ("cpu", "memory", "disk", "load_average", "toolchain"):
                self.assertIn(group, payload)
            self.assertIn("total_bytes", payload["memory"])
            self.assertIn("utilization_percent", payload["cpu"])
            self.assertEqual(payload["toolchain"]["cmake_build_type"], "Release")
            self.assertIn("git_commit", payload["toolchain"])


class PackagingTests(unittest.TestCase):
    def clean_checkout(self):
        original_run = package_artifact.subprocess.run

        def run(command, *args, **kwargs):
            if command[:3] == ["git", "diff", "--quiet"]:
                return subprocess.CompletedProcess(command, 0)
            return original_run(command, *args, **kwargs)

        return mock.patch.object(package_artifact.subprocess, "run", side_effect=run)

    def _build_fixture(self, root: Path, *, build_type: str = "Release") -> Path:
        build = root / "build"
        build.mkdir()
        (build / "CMakeCache.txt").write_text(
            f"CMAKE_BUILD_TYPE:STRING={build_type}\n"
            f"CMAKE_CXX_COMPILER:FILEPATH={sys.executable}\n"
            f"CMAKE_HOME_DIRECTORY:INTERNAL={ROOT}\n"
        )
        (build / "build_metadata.txt").write_text(
            f"git_commit={package_artifact.git_output('rev-parse', 'HEAD')}\n"
            "source_dirty=false\n"
            "compiler_id=FixtureCompiler\n"
            "compiler_version=fixture 1.0\n"
            f"compiler={sys.executable}\n"
            "build_type=Release\n"
        )
        binary = build / "adas_app"
        binary.write_text("#!/bin/sh\nprintf 'WarningLevel=NONE\\n'\n")
        binary.chmod(0o755)
        return build

    def test_package_contains_original_binary_metadata_and_portable_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            build = self._build_fixture(temp_path)
            output = temp_path / "artifacts"
            commit = package_artifact.git_output("rev-parse", "HEAD")
            with self.clean_checkout():
                archive, checksum = package_artifact.create_package(
                    build, output, commit, "ci-42", "test-version"
                )

            self.assertTrue(archive.is_file())
            self.assertTrue(checksum.is_file())
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(checksum.read_text(), f"{digest}  {archive.name}\n")
            with tempfile.TemporaryDirectory() as extracted:
                import tarfile

                with tarfile.open(archive, "r:gz") as package:
                    package.extractall(extracted)
                root_name = "release"
                packaged_binary = Path(extracted) / root_name / "bin" / "adas_app"
                self.assertEqual(
                    hashlib.sha256(packaged_binary.read_bytes()).digest(),
                    hashlib.sha256((build / "adas_app").read_bytes()).digest(),
                )
                metadata = (Path(extracted) / root_name / "version.txt").read_text()
                self.assertIn(f"git_commit={commit}\n", metadata)
                self.assertIn("build_type=Release\n", metadata)
                self.assertIn("version=test-version\n", metadata)
                self.assertIn("compiler_version=fixture 1.0", metadata)
                self.assertTrue(
                    (Path(extracted) / root_name / "config" / "adas.yaml").is_file()
                )

    def test_rejects_non_release_build_without_creating_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            build = self._build_fixture(temp_path, build_type="Debug")
            output = temp_path / "artifacts"
            with self.assertRaisesRegex(ValueError, "CMAKE_BUILD_TYPE=Release"):
                package_artifact.create_package(
                    build, output, package_artifact.git_output("rev-parse", "HEAD"), "8"
                )
            self.assertEqual(list(output.iterdir()), [])

    def test_refuses_to_overwrite_existing_archive_or_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            build = self._build_fixture(temp_path)
            output = temp_path / "artifacts"
            output.mkdir()
            commit = package_artifact.git_output("rev-parse", "HEAD")
            try:
                tag = package_artifact.git_output(
                    "describe", "--tags", "--exact-match", "HEAD"
                )
            except subprocess.SubprocessError:
                tag = None
            name = (
                f"adas-app-{tag}.tar.gz" if tag else f"adas-app-{commit[:7]}-8.tar.gz"
            )
            existing = output / name
            existing.write_bytes(b"preserve")
            with self.clean_checkout():
                with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                    package_artifact.create_package(build, output, commit, "8")
            self.assertEqual(existing.read_bytes(), b"preserve")

    def test_rejects_stale_commit_and_dirty_source_provenance(self):
        commit = package_artifact.git_output("rev-parse", "HEAD")
        with tempfile.TemporaryDirectory() as temp:
            build = self._build_fixture(Path(temp))
            metadata_path = build / "build_metadata.txt"
            metadata = metadata_path.read_text()
            metadata_path.write_text(metadata.replace(commit, "0" * 40))
            with self.assertRaisesRegex(ValueError, "provenance Git SHA"):
                package_artifact.create_package(build, Path(temp) / "out", commit, "1")

            metadata_path.write_text(
                metadata.replace("source_dirty=false", "source_dirty=true")
            )
            with self.assertRaisesRegex(ValueError, "dirty source"):
                package_artifact.create_package(build, Path(temp) / "out", commit, "1")

    def test_removes_partial_artifacts_when_validation_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            build = self._build_fixture(temp_path)
            output = temp_path / "artifacts"
            commit = package_artifact.git_output("rev-parse", "HEAD")
            with (
                self.clean_checkout(),
                mock.patch.object(
                    package_artifact,
                    "validate_package",
                    side_effect=ValueError("bad checksum"),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "bad checksum"):
                    package_artifact.create_package(build, output, commit, "ci-9")
            self.assertEqual(list(output.iterdir()), [])

    def test_rejects_bad_commit_and_path_like_build_number(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            build = self._build_fixture(temp_path)
            with self.assertRaisesRegex(ValueError, "full 40-character"):
                package_artifact.create_package(build, temp_path / "out", "abc", "1")
            with self.assertRaisesRegex(ValueError, "safe identifier"):
                package_artifact.create_package(
                    build,
                    temp_path / "out",
                    package_artifact.git_output("rev-parse", "HEAD"),
                    "../1",
                )


if __name__ == "__main__":
    unittest.main()
