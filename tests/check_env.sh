#!/usr/bin/env bash
# tests/check_env.sh - Diagnostics & Pre-Flight Environment Checker for NetScope
#
# Tests system tools, namespace testbed status, and traffic control capability.
# Prints PASS/FAIL per check with exact resolution commands.

set -u

TOTAL_FAIL=0

check_cmd() {
  local name="$1"
  local cmd="$2"
  local fix="$3"

  if command -v "$cmd" >/dev/null 2>&1; then
    printf "  [ PASS ] %-12s: Found at %s\n" "$name" "$(command -v "$cmd")"
  else
    printf "  [ FAIL ] %-12s: NOT FOUND\n" "$name"
    printf "           Fix: %s\n" "$fix"
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
  fi
}

echo "=========================================================="
echo " NetScope Pre-Flight Diagnostic Check"
echo "=========================================================="
echo ""
echo "--- 1. Required System Binaries ---"
check_cmd "python3" "python3" "sudo apt install -y python3"
check_cmd "ip (iproute2)" "ip" "sudo apt install -y iproute2"
check_cmd "tc (traffic)" "tc" "sudo apt install -y iproute2"
check_cmd "ethtool" "ethtool" "sudo apt install -y ethtool"
check_cmd "tshark" "tshark" "sudo apt install -y tshark && sudo dpkg-reconfigure wireshark-common"

echo ""
echo "--- 2. Virtual Testbed Namespaces ---"

RUN_SUDO=""
if [ "$EUID" -ne 0 ]; then
  RUN_SUDO="sudo -n"
fi

NS_CLIENT_OK=false
NS_SERVER_OK=false

if ip netns list 2>/dev/null | grep -q "\bns-client\b"; then
  printf "  [ PASS ] Namespace ns-client: Active\n"
  NS_CLIENT_OK=true
else
  printf "  [ FAIL ] Namespace ns-client: Missing\n"
  printf "           Fix: sudo ./network/netns_setup.sh up\n"
  TOTAL_FAIL=$((TOTAL_FAIL + 1))
fi

if ip netns list 2>/dev/null | grep -q "\bns-server\b"; then
  printf "  [ PASS ] Namespace ns-server: Active\n"
  NS_SERVER_OK=true
else
  printf "  [ FAIL ] Namespace ns-server: Missing\n"
  printf "           Fix: sudo ./network/netns_setup.sh up\n"
  TOTAL_FAIL=$((TOTAL_FAIL + 1))
fi

echo ""
echo "--- 3. Inter-Namespace Connectivity & Control ---"

if [ "$NS_CLIENT_OK" = true ] && [ "$NS_SERVER_OK" = true ]; then
  NSRUN="/opt/netscope/nsrun.sh"
  if [ ! -f "$NSRUN" ]; then
    NSRUN="$(cd "$(dirname "${BASH_SOURCE[0]}")/../network" && pwd)/nsrun.sh"
  fi

  # Test ping
  if $RUN_SUDO "$NSRUN" ns-client ping -c 1 -W 1 10.10.0.2 </dev/null >/dev/null 2>&1; then
    printf "  [ PASS ] Ping (ns-client -> 10.10.0.2): Reachable\n"
  else
    printf "  [ FAIL ] Ping (ns-client -> 10.10.0.2): Unreachable or sudo auth required\n"
    printf "           Fix: Run 'sudo -v' or setup testbed via 'sudo ./network/netns_setup.sh up'\n"
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
  fi

  # Test tc inside ns-client
  if $RUN_SUDO "$NSRUN" ns-client tc qdisc show dev veth-c </dev/null >/dev/null 2>&1; then
    printf "  [ PASS ] Traffic Control (ns-client:veth-c): Accessible\n"
  else
    printf "  [ FAIL ] Traffic Control (ns-client:veth-c): Failed or sudo auth required\n"
    printf "           Fix: Run 'sudo -v' or install rules via 'sudo ./network/install_sudoers.sh'\n"
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
  fi
else
  printf "  [ SKIP ] Connectivity checks skipped because namespaces are missing.\n"
  printf "           Fix: sudo ./network/netns_setup.sh up\n"
fi

echo ""
echo "=========================================================="
if [ "$TOTAL_FAIL" -eq 0 ]; then
  echo " [✔] ALL DIAGNOSTICS PASSED. NetScope testbed is ready."
  echo "=========================================================="
  exit 0
else
  echo " [!] $TOTAL_FAIL CHECK(S) FAILED. Please apply the fixes above."
  echo "=========================================================="
  exit 1
fi
