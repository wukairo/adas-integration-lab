#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != Linux ]]; then
    echo "ERROR: Phase 0 verification must run inside the Linux guest." >&2
    exit 1
fi
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
git --version
python3 --version
g++ --version
cmake --version
cppcheck --version
command -v candump
command -v cansend
dpkg-query -W libgtest-dev
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel "$(nproc)"
actual_output="$(./build/adas_app)"
printf '%s\n' "$actual_output"
if [[ "$actual_output" != "Hello ADAS" ]]; then
    echo "ERROR: Expected Hello ADAS." >&2
    exit 1
fi
echo "PASS: Linux toolchain and Hello ADAS verified. GitHub/clean clone must be checked separately."
