#!/usr/bin/env bash
# run.sh — Start NetScope: Backend, Desktop (5173), Mobile (5174), and TCP Server
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

mkdir -p results/pcaps results/server_storage && chmod 777 results/pcaps results/server_storage 2>/dev/null || true
mkdir -p results/uploads tests/data

# --- Venv check ---
if [ ! -f ".venv/bin/uvicorn" ]; then
    echo "[ERROR] Virtual environment not found. Run './setup.sh' first."
    exit 1
fi

# --- Namespace testbed check ---
NSRUN_STATUS=0
USE_NETNS=0
if [ -f "/opt/netscope/netns_setup.sh" ]; then
    sudo -n /opt/netscope/netns_setup.sh status > /dev/null 2>&1 || NSRUN_STATUS=$?
    if [ "$NSRUN_STATUS" -ne 0 ]; then
        echo "[*] Bringing up network namespaces..."
        sudo -n /opt/netscope/netns_setup.sh up || true
    fi
    USE_NETNS=1
fi

# Track PIDs for clean single-Ctrl+C termination
TCP_PID=""
BACKEND_PID=""
DESKTOP_PID=""
MOBILE_PID=""

cleanup() {
    echo ""
    echo "[*] Stopping NetScope services..."
    [ -n "$MOBILE_PID" ] && kill "$MOBILE_PID" 2>/dev/null || true
    [ -n "$DESKTOP_PID" ] && kill "$DESKTOP_PID" 2>/dev/null || true
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
    [ -n "$TCP_PID" ] && kill "$TCP_PID" 2>/dev/null || true

    if [ "$USE_NETNS" -eq 1 ]; then
        sudo -n /opt/netscope/nsrun.sh ns-server pkill -f "server/tcp_server.py" 2>/dev/null || true
    fi
    pkill -f "server/tcp_server.py" 2>/dev/null || true
    echo "[✔] NetScope shutdown complete."
}
trap cleanup EXIT INT TERM

# 1. Start TCP Server in ns-server (or host fallback)
echo "[*] Starting TCP server on port 5000..."
if [ "$USE_NETNS" -eq 1 ]; then
    sudo -n /opt/netscope/nsrun.sh ns-server \
        "$REPO/.venv/bin/python" "$REPO/server/tcp_server.py" \
        --host 0.0.0.0 --port 5000 --storage-dir "$REPO/results/server_storage" &
    TCP_PID=$!
else
    .venv/bin/python server/tcp_server.py \
        --host 0.0.0.0 --port 5000 --storage-dir results/server_storage &
    TCP_PID=$!
fi

# 2. Start Backend FastAPI server on port 8000
echo "[*] Starting FastAPI Backend on port 8000..."
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level warning &
BACKEND_PID=$!

# 3. Start Desktop React Vite app on port 5173
echo "[*] Starting Desktop Frontend on port 5173..."
npm --prefix frontend/desktop run dev -- --port 5173 --host 0.0.0.0 > /dev/null 2>&1 &
DESKTOP_PID=$!

# 4. Start Mobile React Vite app on port 5174
echo "[*] Starting Mobile Frontend on port 5174..."
npm --prefix frontend/mobile run dev -- --port 5174 --host 0.0.0.0 > /dev/null 2>&1 &
MOBILE_PID=$!

sleep 2

echo "============================================================"
echo " NetScope Orchestration Suite Running"
echo " Backend API:      http://localhost:8000"
echo " Desktop Frontend: http://localhost:5173"
echo " Mobile Peer App:  http://localhost:5174"
echo " TCP Server:       Port 5000 (ns-server)"
echo " Stop All:         Ctrl+C"
echo "============================================================"

# Try to open desktop app in browser
(sleep 1 && xdg-open "http://localhost:5173" 2>/dev/null) &

wait
