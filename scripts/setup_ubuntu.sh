#!/usr/bin/env bash
# Run inside the Ubuntu guest, not in Windows/Git Bash.
set -euo pipefail

if [[ ! -r /etc/os-release ]]; then
    echo "ERROR: Run this script inside Ubuntu." >&2
    exit 1
fi
. /etc/os-release
if [[ "$ID" != ubuntu ]]; then
    echo "ERROR: This setup supports Ubuntu; detected $ID." >&2
    exit 1
fi

sudo apt-get update
sudo apt-get install -y git build-essential cmake python3 python3-pip \
    python3-venv can-utils cppcheck libgtest-dev iproute2 kmod \
    open-vm-tools open-vm-tools-desktop

git --version
python3 --version
g++ --version
cmake --version
cppcheck --version
dpkg-query -W can-utils libgtest-dev
echo "Ubuntu dependencies installed. Next: bash scripts/verify_phase0.sh"
