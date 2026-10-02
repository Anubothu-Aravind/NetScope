#!/usr/bin/env bash
# setup.sh — NetScope one-time setup.
# Run once after cloning. Requires sudo for namespace scripts.
#
# What it does:
#   1. Creates a Python venv and installs requirements.txt
#   2. Generates tests/data/test_10mb.bin if it doesn't exist
#   3. Installs /etc/sudoers.d/netscope for passwordless namespace commands
#   4. Brings up the ns-client / ns-server namespace testbed
#   5. Runs a quick connectivity test
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

echo "============================================================"
echo " NetScope Setup"
echo "============================================================"

# --- 1. Python venv ---
if [ ! -d ".venv" ]; then
    echo "[1/5] Creating Python virtual environment..."
    python3 -m venv .venv
else
    echo "[1/5] Virtual environment already exists. Skipping."
fi

echo "[1/5] Installing Python dependencies..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "      Dependencies installed."

# --- 2. Test data file ---
echo "[2/5] Checking test data file..."
mkdir -p tests/data
if [ ! -f "tests/data/test_10mb.bin" ]; then
    echo "      Generating 10 MB test file..."
    dd if=/dev/urandom of=tests/data/test_10mb.bin bs=1M count=10 status=none
    echo "      test_10mb.bin created."
else
    echo "      test_10mb.bin already exists. Skipping."
fi

# --- 3. Sudoers (passwordless namespace scripts) ---
echo "[3/5] Installing sudoers rules for namespace scripts..."
if [ -f "network/install_sudoers.sh" ]; then
    sudo bash network/install_sudoers.sh
else
    echo "      WARNING: network/install_sudoers.sh not found. Skipping."
fi

# --- 4. Namespace testbed ---
echo "[4/5] Bringing up network namespace testbed..."
if [ -f "/opt/netscope/netns_setup.sh" ]; then
    sudo -n /opt/netscope/netns_setup.sh up
elif [ -f "network/netns_setup.sh" ]; then
    sudo bash network/netns_setup.sh up
else
    echo "      WARNING: netns_setup.sh not found. Skipping."
fi

# --- 5. Connectivity test ---
echo "[5/5] Running connectivity test..."
if [ -f "/opt/netscope/netns_setup.sh" ]; then
    sudo -n /opt/netscope/netns_setup.sh status
elif [ -f "network/netns_setup.sh" ]; then
    sudo bash network/netns_setup.sh status
fi

echo ""
echo "============================================================"
echo " Setup complete."
echo " Run:  ./run.sh"
echo "============================================================"
