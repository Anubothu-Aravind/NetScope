#!/usr/bin/env bash
# network/install_sudoers.sh - Configure secure passwordless sudo for NetScope scripts
#
# SECURITY & VIVA EXPLANATION:
#   Granting NOPASSWD sudo access to scripts located in a user's home directory
#   is a known privilege escalation vector (the user could edit the script to execute
#   arbitrary root commands).
#   
#   To prevent this vulnerability:
#     1. The scripts are copied to /opt/netscope/
#     2. Ownership is set to root:root with permission 755 (read & execute only)
#     3. The sudoers rule (/etc/sudoers.d/netscope) strictly allows executing:
#          - /opt/netscope/netns_setup.sh
#          - /opt/netscope/nsrun.sh
#          - /opt/netscope/impair.sh
#   This allows the NetScope application and benchmarks to run cleanly without
#   exposing arbitrary root execution.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPT_DIR="/opt/netscope"
TARGET_USER="${SUDO_USER:-$USER}"

echo "=========================================================="
echo " NetScope Sudoers & /opt Provisioner"
echo " Target User: $TARGET_USER"
echo " Destination: $OPT_DIR"
echo "=========================================================="

SUDO_CMD=""
if [ "$EUID" -ne 0 ]; then
  SUDO_CMD="sudo"
fi

echo "[*] Creating $OPT_DIR and copying testbed scripts..."
$SUDO_CMD mkdir -p "$OPT_DIR"
$SUDO_CMD cp "$SCRIPT_DIR/netns_setup.sh" "$OPT_DIR/netns_setup.sh"
$SUDO_CMD cp "$SCRIPT_DIR/nsrun.sh" "$OPT_DIR/nsrun.sh"
$SUDO_CMD cp "$SCRIPT_DIR/impair.sh" "$OPT_DIR/impair.sh"
$SUDO_CMD cp "$SCRIPT_DIR/tshark_stop.sh" "$OPT_DIR/tshark_stop.sh"

echo "[*] Securing permissions: owner root:root, mode 755..."
$SUDO_CMD chown -R root:root "$OPT_DIR"
$SUDO_CMD chmod 755 "$OPT_DIR/netns_setup.sh" "$OPT_DIR/nsrun.sh" "$OPT_DIR/impair.sh" "$OPT_DIR/tshark_stop.sh"

echo "[*] Generating sudoers configuration..."
SUDOERS_CONTENT="# NetScope automated network namespace and impairment rules
$TARGET_USER ALL=(ALL) NOPASSWD: $OPT_DIR/netns_setup.sh, $OPT_DIR/nsrun.sh, $OPT_DIR/impair.sh, $OPT_DIR/tshark_stop.sh
"

TMP_FILE=$(mktemp)
echo "$SUDOERS_CONTENT" > "$TMP_FILE"

echo "[*] Validating sudoers syntax with visudo..."
if command -v visudo >/dev/null 2>&1; then
  visudo -cf "$TMP_FILE"
fi

echo "[*] Installing to /etc/sudoers.d/netscope..."
$SUDO_CMD cp "$TMP_FILE" /etc/sudoers.d/netscope
$SUDO_CMD chmod 0440 /etc/sudoers.d/netscope
rm -f "$TMP_FILE"

echo ""
echo "[✔] Installation complete!"
echo "    - Scripts installed in $OPT_DIR (owned by root:root)"
echo "    - /etc/sudoers.d/netscope created and validated"
echo "    - User '$TARGET_USER' can now run NetScope without password prompts."
echo "    - tshark_stop.sh added for passwordless tshark SIGINT."
