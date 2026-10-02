#!/usr/bin/env bash
# network/impair.sh - Linux tc/netem Network Impairment Tool for NetScope
#
# Concept for Viva:
# Linux Traffic Control (tc) uses the Network Emulation (netem) queuing discipline (qdisc)
# at the kernel level to manipulate packets on network interfaces:
#  - Delay: Packets are placed in a delay buffer before transmission.
#  - Loss: Random packet dropping according to a designated probability.
#  - Rate: Limits egress bandwidth throughput.
#  - Network Namespaces (--ns): Targets interfaces isolated inside an emulated node (e.g. ns-client).
#
# Usage:
#   sudo ./network/impair.sh [--ns <ns>] <iface> apply [--delay 100ms] [--loss 2%] [--rate 5mbit]
#   sudo ./network/impair.sh [--ns <ns>] <iface> clear
#   ./network/impair.sh [--ns <ns>] <iface> show

set -euo pipefail

RUN_SUDO=""
if [ "$EUID" -ne 0 ]; then
  RUN_SUDO="sudo"
fi

NS=""
ARGS=()

# Extract --ns if present anywhere in arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ns)
      NS="$2"
      shift 2
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

if [ ${#ARGS[@]} -lt 2 ]; then
  echo "Usage: $0 [--ns <namespace>] <iface> {apply|clear|show} [options]"
  echo "Examples:"
  echo "  sudo $0 --ns ns-client veth-c apply --delay 100ms --loss 2% --rate 5mbit"
  echo "  sudo $0 --ns ns-client veth-c clear"
  echo "  $0 --ns ns-client veth-c show"
  exit 1
fi

IFACE="${ARGS[0]}"
ACTION="${ARGS[1]}"
REM_ARGS=("${ARGS[@]:2}")

# Wrapper for running tc, optionally inside a namespace
run_tc() {
  if [ -n "$NS" ]; then
    $RUN_SUDO ip netns exec "$NS" tc "$@"
  else
    $RUN_SUDO tc "$@"
  fi
}

case "$ACTION" in
  apply)
    DELAY=""
    LOSS=""
    RATE=""

    idx=0
    while [ $idx -lt ${#REM_ARGS[@]} ]; do
      arg="${REM_ARGS[$idx]}"
      case "$arg" in
        --delay)
          DELAY="${REM_ARGS[$((idx+1))]}"
          idx=$((idx+2))
          ;;
        --loss)
          LOSS="${REM_ARGS[$((idx+1))]}"
          idx=$((idx+2))
          ;;
        --rate)
          RATE="${REM_ARGS[$((idx+1))]}"
          idx=$((idx+2))
          ;;
        *)
          echo "Unknown option: $arg" >&2
          exit 1
          ;;
      esac
    done

    # Normalize rate parameter if user supplies Mbps/mbps
    if [[ -n "$RATE" ]]; then
      RATE="${RATE//Mbps/mbit}"
      RATE="${RATE//mbps/mbit}"
      RATE="${RATE//Kbps/kbit}"
      RATE="${RATE//kbps/kbit}"
    fi

    # Build netem parameters
    NETEM_PARAMS=()
    if [[ -n "$DELAY" && "$DELAY" != "0ms" && "$DELAY" != "0" ]]; then
      NETEM_PARAMS+=(delay "$DELAY")
    fi
    if [[ -n "$LOSS" && "$LOSS" != "0%" && "$LOSS" != "0" ]]; then
      NETEM_PARAMS+=(loss "$LOSS")
    fi
    if [[ -n "$RATE" && "$RATE" != "Unlimited" && "$RATE" != "unlimited" ]]; then
      NETEM_PARAMS+=(rate "$RATE")
    fi

    TARGET_DESC="$IFACE"
    if [ -n "$NS" ]; then
      TARGET_DESC="$IFACE in [$NS]"
    fi

    # Reset existing qdisc first to ensure clean state
    run_tc qdisc del dev "$IFACE" root 2>/dev/null || true

    if [ ${#NETEM_PARAMS[@]} -eq 0 ]; then
      echo "[*] Baseline (no impairments applied) on $TARGET_DESC."
    else
      echo "[*] Applying netem on $TARGET_DESC: ${NETEM_PARAMS[*]}"
      run_tc qdisc add dev "$IFACE" root netem "${NETEM_PARAMS[@]}"
    fi

    echo "[✔] Current qdisc on $TARGET_DESC:"
    run_tc -s qdisc show dev "$IFACE"
    ;;

  clear)
    TARGET_DESC="$IFACE"
    if [ -n "$NS" ]; then
      TARGET_DESC="$IFACE in [$NS]"
    fi
    echo "[*] Clearing all traffic control qdisc on $TARGET_DESC..."
    run_tc qdisc del dev "$IFACE" root 2>/dev/null || true
    echo "[✔] Impairments removed from $TARGET_DESC."
    run_tc qdisc show dev "$IFACE"
    ;;

  show)
    TARGET_DESC="$IFACE"
    if [ -n "$NS" ]; then
      TARGET_DESC="$IFACE in [$NS]"
    fi
    echo "=== Active qdisc for $TARGET_DESC ==="
    run_tc -s qdisc show dev "$IFACE"
    ;;

  *)
    echo "Unknown action '$ACTION'. Use apply, clear, or show." >&2
    exit 1
    ;;
esac
