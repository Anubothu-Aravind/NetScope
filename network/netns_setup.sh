#!/usr/bin/env bash
# network/netns_setup.sh - Linux Network Namespace Testbed for NetScope
#
# Concept for Viva:
# 1. Network Namespaces (netns):
#    Provide complete isolation of network system resources (interfaces, routing tables,
#    firewalls, socket tables) on a single Linux kernel.
# 2. Virtual Ethernet (veth) Pair:
#    Acts like a bidirectional virtual Ethernet patch cord. Packets transmitted into veth-c
#    in ns-client instantly emerge from veth-s in ns-server.
# 3. Offload Disabling (ethtool):
#    TSO (TCP Segmentation Offload), GSO (Generic Segmentation Offload), and GRO
#    (Generic Receive Offload) aggregate packets into 64 KB buffers inside the NIC/kernel.
#    To accurately emulate packet loss, latency, and standard MTU (1500 byte) frames,
#    these offloads MUST be turned OFF.
#
# Usage:
#   sudo ./network/netns_setup.sh up
#   sudo ./network/netns_setup.sh down
#   ./network/netns_setup.sh status

set -euo pipefail

ACTION="${1:-status}"

# Helper for sudo execution if not already root
RUN_SUDO=""
if [ "$EUID" -ne 0 ]; then
  RUN_SUDO="sudo"
fi

case "$ACTION" in
  up)
    echo "=========================================================="
    echo " Setting up NetScope Virtual Two-Node Testbed"
    echo "=========================================================="

    # 1. Clean existing namespaces and interfaces
    $RUN_SUDO ip netns del ns-client 2>/dev/null || true
    $RUN_SUDO ip netns del ns-server 2>/dev/null || true
    $RUN_SUDO ip link del veth-c 2>/dev/null || true
    $RUN_SUDO ip link del veth-s 2>/dev/null || true

    # 2. Create namespaces
    echo "[*] Creating namespaces: ns-client and ns-server..."
    $RUN_SUDO ip netns add ns-client
    $RUN_SUDO ip netns add ns-server

    # 3. Create veth peer pair
    echo "[*] Creating virtual Ethernet pair: veth-c <-> veth-s..."
    $RUN_SUDO ip link add veth-c type veth peer name veth-s

    # 4. Move interfaces into respective namespaces
    $RUN_SUDO ip link set veth-c netns ns-client
    $RUN_SUDO ip link set veth-s netns ns-server

    # 5. Configure IP addresses (10.10.0.0/24 subnet)
    echo "[*] Assigning IP addresses (ns-client: 10.10.0.1, ns-server: 10.10.0.2)..."
    $RUN_SUDO ip netns exec ns-client ip addr add 10.10.0.1/24 dev veth-c
    $RUN_SUDO ip netns exec ns-server ip addr add 10.10.0.2/24 dev veth-s

    # 6. Bring up loopback and veth interfaces
    $RUN_SUDO ip netns exec ns-client ip link set lo up
    $RUN_SUDO ip netns exec ns-server ip link set lo up
    $RUN_SUDO ip netns exec ns-client ip link set veth-c up
    $RUN_SUDO ip netns exec ns-server ip link set veth-s up

    # 7. Disable hardware segmentation and receive offloads
    echo "[*] Disabling TSO, GSO, GRO offloads on veth interfaces for true packet emulation..."
    if command -v ethtool >/dev/null 2>&1; then
      $RUN_SUDO ip netns exec ns-client ethtool -K veth-c tso off gso off gro off 2>/dev/null || true
      $RUN_SUDO ip netns exec ns-server ethtool -K veth-s tso off gso off gro off 2>/dev/null || true
    else
      echo "    [NOTE] ethtool not found. Install via: sudo apt install -y ethtool"
    fi

    echo "[✔] Testbed is UP and ready."
    echo ""
    $0 status
    ;;

  down)
    echo "[*] Tearing down NetScope testbed..."
    $RUN_SUDO ip netns del ns-client 2>/dev/null || true
    $RUN_SUDO ip netns del ns-server 2>/dev/null || true
    $RUN_SUDO ip link del veth-c 2>/dev/null || true
    $RUN_SUDO ip link del veth-s 2>/dev/null || true
    echo "[✔] Testbed teardown complete."
    ;;

  status)
    echo "=== NetScope Testbed Status ==="
    CLIENT_EXISTS=false
    SERVER_EXISTS=false

    if ip netns list | grep -q "\bns-client\b"; then
      CLIENT_EXISTS=true
    fi
    if ip netns list | grep -q "\bns-server\b"; then
      SERVER_EXISTS=true
    fi

    echo "ns-client: $([ "$CLIENT_EXISTS" = true ] && echo "PRESENT" || echo "MISSING")"
    echo "ns-server: $([ "$SERVER_EXISTS" = true ] && echo "PRESENT" || echo "MISSING")"

    if [ "$CLIENT_EXISTS" = true ] && [ "$SERVER_EXISTS" = true ]; then
      echo ""
      echo "--- Interface Addresses ---"
      $RUN_SUDO ip netns exec ns-client ip -4 -br addr show veth-c || true
      $RUN_SUDO ip netns exec ns-server ip -4 -br addr show veth-s || true
      echo ""
      echo "--- Connectivity Test (ns-client -> 10.10.0.2) ---"
      if $RUN_SUDO ip netns exec ns-client ping -c 2 -W 1 10.10.0.2 >/dev/null 2>&1; then
        echo "[✔] PING SUCCESSFUL: ns-client <---> ns-server connected."
      else
        echo "[!] PING FAILED: Packets cannot reach ns-server."
      fi
    else
      echo "[!] Testbed is not running. Start with: sudo ./network/netns_setup.sh up"
    fi
    ;;

  *)
    echo "Usage: $0 {up|down|status}"
    exit 1
    ;;
esac
