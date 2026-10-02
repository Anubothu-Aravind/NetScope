#!/usr/bin/env bash
# network/nsrun.sh - Run command inside a Linux Network Namespace for NetScope
#
# Usage:
#   ./network/nsrun.sh <ns-name> <command...>
# Examples:
#   ./network/nsrun.sh ns-client python3 client/tcp_client.py send ...
#   ./network/nsrun.sh ns-server python3 server/tcp_server.py ...

set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <namespace> <command...>"
  echo "Example: $0 ns-client ping 10.10.0.2"
  exit 1
fi

NS="$1"
shift

RUN_SUDO=""
if [ "$EUID" -ne 0 ]; then
  RUN_SUDO="sudo"
fi

exec $RUN_SUDO ip netns exec "$NS" "$@"
