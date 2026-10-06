#!/usr/bin/env bash
# setup.sh — NetScope one-time setup: Python venv, Node dependencies, and testbed.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

echo "============================================================"
echo " NetScope Setup"
echo "============================================================"

# --- 1. Python venv & dependencies ---
if [ ! -d ".venv" ]; then
    echo "[1/6] Creating Python virtual environment..."
    python3 -m venv .venv
else
    echo "[1/6] Virtual environment already exists. Skipping creation."
fi

echo "      Installing Python dependencies..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "      Python dependencies installed."

# --- 2. Node & Frontend dependencies ---
echo "[2/6] Installing frontend dependencies..."
if command -v npm > /dev/null 2>&1; then
    echo "      Installing Desktop frontend dependencies (frontend/desktop)..."
    npm --prefix frontend/desktop install --quiet
    echo "      Installing Mobile frontend dependencies (frontend/mobile)..."
    npm --prefix frontend/mobile install --quiet
    echo "      Frontend dependencies installed."
else
    echo "      WARNING: npm command not found. Please install Node.js."
fi

# --- 3. Test data file ---
echo "[3/6] Checking test data file..."
mkdir -p tests/data
if [ ! -f "tests/data/test_10mb.bin" ]; then
    echo "      Generating 10 MB test file..."
    dd if=/dev/urandom of=tests/data/test_10mb.bin bs=1M count=10 status=none
    echo "      test_10mb.bin created."
else
    echo "      test_10mb.bin already exists. Skipping."
fi

# --- 4. Sudoers (passwordless namespace scripts) ---
echo "[4/6] Installing sudoers rules for namespace scripts..."
if [ -f "network/install_sudoers.sh" ]; then
    sudo bash network/install_sudoers.sh
else
    echo "      WARNING: network/install_sudoers.sh not found. Skipping."
fi

# --- 5. Namespace testbed ---
echo "[5/6] Bringing up network namespace testbed..."
if [ -f "/opt/netscope/netns_setup.sh" ]; then
    sudo -n /opt/netscope/netns_setup.sh up || true
elif [ -f "network/netns_setup.sh" ]; then
    sudo bash network/netns_setup.sh up || true
else
    echo "      WARNING: netns_setup.sh not found. Skipping."
fi

# --- 6. Connectivity test ---
echo "[6/6] Running connectivity test..."
if [ -f "/opt/netscope/netns_setup.sh" ]; then
    sudo -n /opt/netscope/netns_setup.sh status || true
elif [ -f "network/netns_setup.sh" ]; then
    sudo bash network/netns_setup.sh status || true
fi

echo ""
echo "============================================================"
echo " Setup complete."
echo " Run:  ./run.sh"
echo "============================================================"
