#!/usr/bin/env bash
set -euo pipefail

for tool in ip modprobe; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'Missing dependency: %s. Install iproute2 and kmod.\n' "$tool" >&2
        exit 1
    fi
done

run_privileged() {
    if [[ "${EUID}" -eq 0 ]]; then
        "$@"
    else
        if ! command -v sudo >/dev/null 2>&1; then
            printf 'Root privileges are required; install sudo or run this script as root.\n' >&2
            return 1
        fi
        sudo "$@"
    fi
}

run_privileged modprobe vcan || {
    printf 'Could not load the vcan kernel module. Check kernel support and privileges.\n' >&2
    exit 1
}

if ip link show dev vcan0 >/dev/null 2>&1; then
    link_details="$(ip -j -details link show dev vcan0)" || {
        printf 'Could not inspect existing interface vcan0.\n' >&2
        exit 1
    }
    if ! grep -Eq '"info_kind"[[:space:]]*:[[:space:]]*"vcan"' <<<"$link_details"; then
        printf 'Interface vcan0 already exists but is not a vcan interface; leaving it unchanged.\n' >&2
        exit 1
    fi
else
    run_privileged ip link add dev vcan0 type vcan || {
        printf 'Could not create vcan0. Check kernel support and network privileges.\n' >&2
        exit 1
    }
fi

run_privileged ip link set dev vcan0 up || {
    printf 'Could not bring vcan0 up. Check network privileges.\n' >&2
    exit 1
}

ip -details link show dev vcan0
