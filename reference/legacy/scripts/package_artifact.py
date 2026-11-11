#!/usr/bin/env python3
"""Package an already-built Release binary with traceability metadata."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from automation_common import ROOT


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
BUILD_NUMBER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def read_cache(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^([^#/:][^:]*):[^=]*=(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def read_metadata(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def git_output(*args: str, cwd: Path = ROOT) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip()


def create_package(
    build_dir: Path,
    output_dir: Path,
    commit: str | None,
    build_number: str,
    version_override: str | None = None,
) -> tuple[Path, Path]:
    if not BUILD_NUMBER_RE.fullmatch(build_number) or ".." in build_number:
        raise ValueError(
            "--build-number must be a safe identifier (letters, digits, ._-)"
        )

    build_dir = build_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve()
    binary = build_dir / "adas_app"
    dbc = ROOT / "dbc" / "vehicle.dbc"
    config = ROOT / "config" / "adas.yaml"
    cache_path = build_dir / "CMakeCache.txt"
    metadata_path = build_dir / "build_metadata.txt"
    if not cache_path.is_file():
        raise ValueError(f"CMake cache is missing: {cache_path}")
    if not metadata_path.is_file():
        raise ValueError(f"CMake build provenance is missing: {metadata_path}")
    if not binary.is_file() or binary.is_symlink():
        raise ValueError(f"built application is missing or unsafe: {binary}")
    if not os.access(binary, os.X_OK):
        raise ValueError(f"built application is not executable: {binary}")
    if not dbc.is_file() or dbc.is_symlink():
        raise ValueError(f"DBC file is missing or unsafe: {dbc}")
    if not config.is_file() or config.is_symlink():
        raise ValueError(f"runtime configuration is missing or unsafe: {config}")

    cache = read_cache(cache_path)
    if cache.get("CMAKE_BUILD_TYPE") != "Release":
        raise ValueError("build directory must have CMAKE_BUILD_TYPE=Release")
    source_dir = cache.get("CMAKE_HOME_DIRECTORY")
    if not source_dir or Path(source_dir).resolve() != ROOT:
        raise ValueError("CMake cache does not belong to this repository")
    metadata = read_metadata(metadata_path)
    compiler_path = metadata.get("compiler") or cache.get("CMAKE_CXX_COMPILER")
    compiler_version = metadata.get("compiler_version")
    compiler_id = metadata.get("compiler_id")
    if not compiler_path or not compiler_version or not compiler_id:
        raise ValueError(
            "CMake build provenance is missing configured compiler identity"
        )
    if compiler_path != cache.get("CMAKE_CXX_COMPILER"):
        raise ValueError("build provenance compiler does not match the CMake cache")
    if metadata.get("build_type") != cache.get("CMAKE_BUILD_TYPE"):
        raise ValueError("build provenance build type does not match the CMake cache")
    actual_commit = git_output("rev-parse", "HEAD")
    commit = commit or actual_commit
    if not COMMIT_RE.fullmatch(commit):
        raise ValueError("--commit must be a full 40-character lowercase Git SHA")
    if actual_commit != commit:
        raise ValueError(
            f"requested commit {commit} does not match checkout HEAD {actual_commit}"
        )
    if metadata.get("git_commit") != commit:
        raise ValueError("build provenance Git SHA does not match the requested commit")
    if metadata.get("source_dirty") != "false":
        raise ValueError("refusing to package a build configured from dirty source")
    if metadata.get("build_type") != "Release":
        raise ValueError("build provenance does not identify a Release build")
    dirty = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            "HEAD",
            "--",
            "src",
            "include",
            "CMakeLists.txt",
            "dbc",
            "config",
        ],
        cwd=ROOT,
        check=False,
        timeout=10,
    )
    if dirty.returncode != 0:
        raise ValueError(
            "tracked build inputs have changed since the recorded Git commit"
        )
    # Ensure the supplied SHA resolves in this checkout even if it is not HEAD.
    git_output("cat-file", "-e", f"{commit}^{{commit}}")

    try:
        tag = git_output("describe", "--tags", "--exact-match", "HEAD")
    except subprocess.SubprocessError:
        tag = None
    version = version_override or tag or commit[:7]
    if not BUILD_NUMBER_RE.fullmatch(version) or ".." in version:
        raise ValueError("version must be a safe identifier (letters, digits, ._-)")
    artifact_stem = f"adas-app-{commit[:7]}-{build_number}"
    archive_name = f"adas-app-{tag}.tar.gz" if tag else f"{artifact_stem}.tar.gz"
    archive_path = output_dir / archive_name
    checksum_path = output_dir / f"{archive_path.name}.sha256"
    if archive_path.exists() or checksum_path.exists():
        raise ValueError(f"refusing to overwrite existing artifact: {archive_path}")

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    version = (
        f"version={version}\n"
        f"git_commit={commit}\n"
        f"build_number={build_number}\n"
        f"timestamp_utc={timestamp}\n"
        f"build_type=Release\n"
        f"compiler_id={compiler_id}\n"
        f"cxx_compiler={compiler_path}\n"
        f"compiler_version={compiler_version}\n"
    )
    package_root = "release"
    archive_created = False
    checksum_created = False
    try:
        with tarfile.open(archive_path, "x:gz") as archive:
            archive_created = True
            archive.add(binary, arcname=f"{package_root}/bin/adas_app")
            archive.add(dbc, arcname=f"{package_root}/dbc/vehicle.dbc")
            archive.add(config, arcname=f"{package_root}/config/adas.yaml")
            info = tarfile.TarInfo(f"{package_root}/version.txt")
            encoded = version.encode("utf-8")
            info.size = len(encoded)
            info.mode = 0o644
            import io

            archive.addfile(info, io.BytesIO(encoded))

        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        with checksum_path.open("x", encoding="ascii") as stream:
            checksum_created = True
            stream.write(f"{digest}  {archive_path.name}\n")
        validate_package(archive_path, checksum_path, binary, package_root)
    except Exception:
        if archive_created:
            archive_path.unlink(missing_ok=True)
        if checksum_created:
            checksum_path.unlink(missing_ok=True)
        raise
    return archive_path, checksum_path


def validate_package(
    archive_path: Path, checksum_path: Path, source_binary: Path, package_root: str
) -> None:
    expected_digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_parts = checksum_path.read_text(encoding="ascii").strip().split()
    if checksum_parts != [expected_digest, archive_path.name]:
        raise ValueError("generated SHA-256 checksum does not match the archive")

    required = {
        f"{package_root}/bin/adas_app",
        f"{package_root}/dbc/vehicle.dbc",
        f"{package_root}/config/adas.yaml",
        f"{package_root}/version.txt",
    }
    with tempfile.TemporaryDirectory(prefix="adas-package-check-") as temp:
        extract_root = Path(temp)
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            names = {member.name for member in members}
            if (
                names != required
                or len(members) != len(required)
                or any(not member.isfile() for member in members)
            ):
                raise ValueError(
                    "package archive has an unexpected or incomplete layout"
                )
            # Member names/types are checked against a fixed allowlist above.
            archive.extractall(extract_root)
        extracted_binary = extract_root / package_root / "bin" / "adas_app"
        extracted_binary.chmod(0o755)
        if (
            hashlib.sha256(extracted_binary.read_bytes()).digest()
            != hashlib.sha256(source_binary.read_bytes()).digest()
        ):
            raise ValueError("packaged binary differs from the built binary")
        result = subprocess.run(
            [str(extracted_binary), "50", "100", "0"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0 or "WarningLevel=NONE" not in result.stdout:
            raise ValueError(
                "unpacked application smoke test failed: "
                f"exit={result.returncode}, stdout={result.stdout.strip()!r}, "
                f"stderr={result.stderr.strip()!r}"
            )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--commit")
    p.add_argument("--build-number", required=True)
    p.add_argument("--version")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    build_dir = (
        (Path.cwd() / args.build_dir).resolve()
        if not args.build_dir.is_absolute()
        else args.build_dir
    )
    output_dir = (
        (Path.cwd() / args.output_dir).resolve()
        if not args.output_dir.is_absolute()
        else args.output_dir
    )
    try:
        archive, checksum = create_package(
            build_dir, output_dir, args.commit, args.build_number, args.version
        )
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(f"package_artifact: {error}", file=sys.stderr)
        return 1
    print(f"Package: {archive}")
    print(f"SHA-256: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
