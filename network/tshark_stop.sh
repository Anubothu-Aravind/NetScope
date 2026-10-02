#!/usr/bin/env bash
# network/tshark_stop.sh — Send SIGINT to a tshark process (by PID).
#
# Usage: tshark_stop.sh <PID>
#
# This script is installed to /opt/netscope/ and added to the sudoers NOPASSWD list
# so that NetScope can cleanly stop a root-owned tshark process (which is running
# inside a network namespace) without needing a password.
#
# Why not just "sudo kill"? The generic kill binary is not in the sudoers list for
# security reasons. This narrow wrapper can only send SIGINT to a single PID.

set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <PID>" >&2
    exit 1
fi

PID="$1"

if ! [[ "$PID" =~ ^[0-9]+$ ]]; then
    echo "[tshark_stop] ERROR: PID must be a positive integer, got: '$PID'" >&2
    exit 1
fi

if [ ! -d "/proc/$PID" ]; then
    echo "[tshark_stop] PID $PID does not exist (already gone)."
    exit 0
fi

echo "[tshark_stop] Sending SIGINT to PID $PID..."
kill -INT "$PID"
echo "[tshark_stop] Done."
