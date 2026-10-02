#!/usr/bin/env bash
# run.sh — Start the NetScope dashboard.
#
# What it does:
#   1. Verifies the venv exists (tells user to run ./setup.sh if not).
#   2. Verifies the namespace testbed is up; brings it up if not.
#   3. Starts the FastAPI server on 0.0.0.0:8000 using uvicorn.
#   4. Opens http://localhost:8000 in the default browser (best-effort).
#
# Stop with Ctrl+C. The namespace testbed remains up between runs.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

# --- Venv check ---
if [ ! -f ".venv/bin/uvicorn" ]; then
    echo "[ERROR] Virtual environment not found."
    echo "        Run './setup.sh' first."
    exit 1
fi

# --- Namespace testbed ---
NSRUN_STATUS=0
if [ -f "/opt/netscope/netns_setup.sh" ]; then
    sudo -n /opt/netscope/netns_setup.sh status > /dev/null 2>&1 || NSRUN_STATUS=$?
    if [ "$NSRUN_STATUS" -ne 0 ]; then
        echo "[*] Namespace testbed is down. Bringing it up..."
        sudo -n /opt/netscope/netns_setup.sh up
    fi
elif [ -f "network/netns_setup.sh" ]; then
    echo "[WARNING] /opt/netscope/netns_setup.sh not found. Run './setup.sh' for sudoers rules."
fi

echo "============================================================"
echo " NetScope Dashboard"
echo " URL:  http://localhost:8000"
echo " Stop: Ctrl+C"
echo "============================================================"
echo ""

# Try to open browser in background (best-effort, don't fail if no display)
(sleep 1.5 && xdg-open "http://localhost:8000" 2>/dev/null) &

# Start uvicorn
exec .venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info
