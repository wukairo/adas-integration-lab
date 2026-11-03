#!/usr/bin/env python3
"""Run the real regression gate through a disposable Git bisect history."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
THRESHOLD_SOURCE = Path("src/collision_warning.cpp")
GOOD_THRESHOLD = "relative_velocity_mps, 2.0, 4.0"
BAD_THRESHOLD = "relative_velocity_mps, 2.1, 4.0"


def run(
    command: list[str], cwd: Path, *, check: bool = True, timeout: float = 30
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if check and result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}"
        )
    return result


def commit(repo: Path, message: str) -> str:
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-m", message], repo)
    return run(["git", "rev-parse", "HEAD"], repo).stdout.strip()


def copy_reports(source: Path, destination: Path) -> list[str]:
    copied: list[str] = []
    if not source.exists():
        return copied
    for report in sorted(source.glob("regression-*/summary.json")):
        target = destination / report.parent.name
        shutil.copytree(report.parent, target, dirs_exist_ok=True)
        try:
            copied.append(str(target.relative_to(ROOT)))
        except ValueError:
            copied.append(str(target))
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used by regression_test.sh (default: this interpreter)",
    )
    parser.add_argument(
        "--evidence-dir", type=Path, default=ROOT / "build-bisect-demo" / "reports"
    )
    args = parser.parse_args()
    evidence_root = (
        args.evidence_dir
        if args.evidence_dir.is_absolute()
        else ROOT / args.evidence_dir
    )
    evidence_root = evidence_root.resolve()
    evidence_dir = evidence_root / datetime.now(timezone.utc).strftime(
        "run-%Y%m%dT%H%M%S.%fZ"
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, object] = {
        "schema_version": 1,
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "failed",
        "gate": "scripts/regression_test.sh --suite quick --bisect",
        "mutation": {
            "file": str(THRESHOLD_SOURCE),
            "good": GOOD_THRESHOLD,
            "bad": BAD_THRESHOLD,
        },
    }
    work_parent = Path(tempfile.mkdtemp(prefix="adas-bisect-demo-"))
    repo = work_parent / "repo"
    bisect_active = False
    try:
        repo.mkdir()
        import tarfile
        import io

        archive = subprocess.run(
            ["git", "archive", "--format=tar", "HEAD"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            tar.extractall(repo)

        run(["git", "init", "-q"], repo)
        run(["git", "config", "user.name", "Bisect Demo"], repo)
        run(["git", "config", "user.email", "bisect-demo@example.invalid"], repo)
        good = commit(repo, "known good baseline")

        readme = repo / "README.md"
        readme.write_text(
            readme.read_text() + "\nBisect demo intermediate history marker.\n"
        )
        intermediate = commit(repo, "harmless intermediate change")

        source = repo / THRESHOLD_SOURCE
        contents = source.read_text()
        if contents.count(GOOD_THRESHOLD) != 1:
            raise RuntimeError(
                f"expected one collision threshold in {THRESHOLD_SOURCE}"
            )
        source.write_text(contents.replace(GOOD_THRESHOLD, BAD_THRESHOLD))
        bad = commit(repo, "regress critical collision threshold")

        setup = run(["git", "log", "--oneline", "--reverse"], repo).stdout.strip()
        report.update(
            {
                "commits": {"good": good, "intermediate": intermediate, "bad": bad},
                "history": setup,
            }
        )
        requested_python = Path(args.python)
        if requested_python.is_absolute():
            python_bin = str(requested_python)
        elif requested_python.parent != Path("."):
            python_bin = str((ROOT / requested_python).absolute())
        else:
            python_bin = shutil.which(args.python) or args.python
        env = os.environ.copy()
        env["PYTHON"] = python_bin
        gate_observations: dict[str, dict[str, object]] = {}
        for label, revision, expected_code in (("good", good, 0), ("bad", bad, 1)):
            run(["git", "checkout", "-q", revision], repo)
            gate_build = repo / f"build-bisect-demo-{label}"
            gate_result = subprocess.run(
                [
                    "bash",
                    "scripts/regression_test.sh",
                    "--suite",
                    "quick",
                    "--bisect",
                    "--build-dir",
                    str(gate_build),
                ],
                cwd=repo,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=300,
            )
            gate_observations[label] = {
                "exit_code": gate_result.returncode,
                "expected_exit_code": expected_code,
                "passed_expectation": gate_result.returncode == expected_code,
                "output": gate_result.stdout,
                "reports": copy_reports(
                    Path(str(gate_build) + "-reports"), evidence_dir / label
                ),
            }
        report["gate_observations"] = gate_observations
        run(["git", "checkout", "-q", bad], repo)
        run(["git", "bisect", "start"], repo)
        bisect_active = True
        run(["git", "bisect", "bad", bad], repo)
        run(["git", "bisect", "good", good], repo)

        build_dir = repo / "build-bisect-demo"
        command = [
            "git",
            "bisect",
            "run",
            "env",
            f"PYTHON={python_bin}",
            "bash",
            "scripts/regression_test.sh",
            "--suite",
            "quick",
            "--bisect",
            "--build-dir",
            str(build_dir),
        ]
        result = subprocess.run(
            command,
            cwd=repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=900,
        )
        report["bisect_output"] = result.stdout
        # Identify the culprit from bisect's final summary.
        final_lines = [
            line.strip()
            for line in result.stdout.splitlines()
            if "is the first bad commit" in line
        ]
        found = final_lines[-1].split()[0] if final_lines else None
        report["found_commit"] = found
        report["bisect_exit_code"] = result.returncode
        report["regression_reports"] = copy_reports(
            Path(str(build_dir) + "-reports"), evidence_dir
        )
        report["status"] = (
            "passed"
            if result.returncode == 0
            and found == bad
            and all(item["passed_expectation"] for item in gate_observations.values())
            else "failed"
        )
        reset = run(["git", "bisect", "reset"], repo, check=False)
        bisect_active = False
        report["reset_output"] = reset.stdout
        report["reset_succeeded"] = (
            run(["git", "rev-parse", "HEAD"], repo).stdout.strip() == bad
        )
        if not report["reset_succeeded"]:
            report["status"] = "failed"
        return 0 if report["status"] == "passed" else 1
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        return_code = 1
    finally:
        if bisect_active and repo.exists():
            try:
                reset = run(["git", "bisect", "reset"], repo, check=False, timeout=30)
                report["reset_output"] = reset.stdout
                report["reset_succeeded"] = reset.returncode == 0
            except Exception as cleanup_error:
                report["cleanup_error"] = (
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
        report["ended_at"] = (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        (evidence_dir / "demo-summary.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        shutil.rmtree(work_parent, ignore_errors=True)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
