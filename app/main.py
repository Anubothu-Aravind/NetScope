"""
app/main.py - NetScope FastAPI Backend (Control & Monitoring Plane)

Provides:
- Web Session & Device Discovery API (QR generation via segno)
- Deterministic Client Pairing Engine (Sender <-> Receiver)
- Real-time Transfer Orchestration (Control Plane monitoring Data Plane)
- Traffic Control API (calling network/impair.sh inside ns-client)
- Server-Sent Events (SSE) for live telemetry, progress, sparklines & packet events
- Benchmark Suite execution & Results API
- Pre-flight diagnostic health check API
"""

import os
import sys
import json
import time
import uuid
import socket
import asyncio
import re
import subprocess
import base64
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from cryptography.fernet import Fernet
from fastapi import (
    FastAPI, Request, BackgroundTasks, HTTPException,
    UploadFile, File, WebSocket, WebSocketDisconnect
)
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import segno

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from common.protocol import compute_sha256
from capture.sniffer import Sniffer
from analysis.pcap_analyzer import analyze
from experiments.summarize import summarize

from app.models import (
    ClientRole,
    ClientStatus,
    PairStatus,
    ClientInfo,
    PairInfo,
    SessionInfo,
    ClientJoinRequest,
    RoleSelectRequest,
    ImpairRequest,
    TransferRequest,
    TransferProgressReport
)
from app.events import broadcaster
from app.session_manager import session_manager
from app.pairing_manager import pairing_manager

OPT_NETSCOPE = "/opt/netscope"

def get_script_path(script_name: str) -> str:
    """Return path to script in /opt/netscope if present, else fallback to network/."""
    opt_path = os.path.join(OPT_NETSCOPE, script_name)
    if os.path.isfile(opt_path):
        return opt_path
    return os.path.join(PROJECT_ROOT, "network", script_name)

def cleanup_old_server_storage(max_age_seconds: int = 300):
    """Delete files in results/server_storage older than 5 minutes."""
    storage_dir = os.path.join(PROJECT_ROOT, "results", "server_storage")
    if not os.path.isdir(storage_dir):
        return
    now = time.time()
    for fn in os.listdir(storage_dir):
        fp = os.path.join(storage_dir, fn)
        if os.path.isfile(fp):
            try:
                if now - os.path.getmtime(fp) > max_age_seconds:
                    os.remove(fp)
            except Exception:
                pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Background task that runs periodically to delete files older than 5 minutes."""
    task = None
    async def _loop():
        while True:
            await asyncio.sleep(60)
            cleanup_old_server_storage(300)

    task = asyncio.create_task(_loop())
    yield
    if task:
        task.cancel()


app = FastAPI(title="NetScope Control Center", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

@app.middleware("http")
async def restrict_remote_access(request: Request, call_next):
    """
    Security Middleware:
    External clients (such as mobile phones joining via Wi-Fi) are permitted ONLY to:
      - GET /join/*
      - All /api/session/* endpoints (client registration, role picking, pairing, QR, telemetry)
      - GET static assets (/manifest.json, /icon.svg, /sw.js)
    All core admin endpoints (impair, transfer, upload, experiments, events, etc.)
    are strictly restricted to loopback (localhost).
    """
    client_host = request.client.host if request.client else "127.0.0.1"

    # Support testing or proxies via X-Forwarded-For
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_host = forwarded.split(",")[0].strip()

    is_loopback = (client_host in LOOPBACK_HOSTS)

    if not is_loopback:
        path = request.url.path
        method = request.method.upper()

        is_allowed = False
        if method == "GET" and (path.startswith("/join/") or path == "/join"):
            is_allowed = True
        elif path.startswith("/api/session/"):
            is_allowed = True
        elif path.startswith("/api/ws"):
            is_allowed = True
        elif method == "GET" and path.startswith("/api/download/"):
            is_allowed = True
        elif method == "GET" and path.startswith("/api/qr/"):
            is_allowed = True
        elif method == "GET" and (path in ("/manifest.json", "/icon.svg", "/sw.js", "/favicon.ico") or path.startswith("/assets/")):
            is_allowed = True

        if not is_allowed:
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: Non-loopback clients may only access session join, registration, and QR endpoints."}
            )

    return await call_next(request)

# ---------------------------------------------------------------------------
# Global State & Telemetry
# ---------------------------------------------------------------------------

# In-memory sessions reference for compatibility
SESSIONS = session_manager.sessions

# Active transfer state
CURRENT_TRANSFER = {
    "running": False,
    "run_id": None,
    "mode": None,
    "file": None,
    "pct": 0.0,
    "mbps": 0.0,
    "bytes": 0,
    "total_bytes": 0,
    "sha256_ok": None
}

# Active impairment configuration
CURRENT_IMPAIRMENT = {
    "delay": "0ms",
    "loss": "0%",
    "rate": "Unlimited"
}

# Live packet stream and cursor state
CURRENT_PACKETS: List[Dict[str, Any]] = []
_PACKET_CURSORS: Dict[str, int] = {}

# Experiment background task handle
ACTIVE_EXPERIMENT: Optional[subprocess.Popen] = None

# Background TCP Server handle
SERVER_PROCESS: Optional[subprocess.Popen] = None


def get_kernel_tcp_stats(port: int = 5000, ns: Optional[str] = None) -> Dict[str, Any]:
    cmd = ["ss", "-tin", f"( sport = :{port} or dport = :{port} )"]
    if ns:
        nsrun = "/opt/netscope/nsrun.sh"
        if not os.path.isfile(nsrun):
            nsrun = os.path.join(PROJECT_ROOT, "network", "nsrun.sh")
        if os.path.isfile(nsrun):
            cmd = ["sudo", "-n", nsrun, ns] + cmd
        else:
            cmd = ["sudo", "-n", "ip", "netns", "exec", ns] + cmd

    stats = {"rtt": 0.0, "cwnd": 0, "retrans": 0}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1.0)
        if proc.returncode == 0 and proc.stdout:
            out = proc.stdout
            rtt_m = re.search(r"\brtt:([0-9.]+)", out)
            if rtt_m:
                stats["rtt"] = float(rtt_m.group(1))
            cwnd_m = re.search(r"\bcwnd:(\d+)", out)
            if cwnd_m:
                stats["cwnd"] = int(cwnd_m.group(1))
            ret_m = re.search(r"\bretrans:(\d+)/(\d+)", out)
            if ret_m:
                stats["retrans"] = int(ret_m.group(2))
    except Exception:
        pass
    return stats


def extract_pcap_packets(pcap_path: str, port: int = 5000, limit: int = 200) -> List[Dict[str, Any]]:
    if not os.path.isfile(pcap_path) or os.path.getsize(pcap_path) == 0:
        return []
    fields = [
        "-e", "frame.number",
        "-e", "frame.time_relative",
        "-e", "ip.src",
        "-e", "ip.dst",
        "-e", "tcp.srcport",
        "-e", "tcp.dstport",
        "-e", "tcp.flags.str",
        "-e", "tcp.seq",
        "-e", "tcp.ack",
        "-e", "frame.len",
        "-e", "tcp.analysis.retransmission",
        "-e", "tcp.analysis.duplicate_ack",
        "-e", "_ws.col.Info",
    ]
    cmd = [
        "tshark", "-r", "-", "-Y", f"tcp.port == {port}",
        "-T", "fields", "-E", "separator=\t", "-E", "occurrence=f"
    ] + fields
    try:
        with open(pcap_path, "rb") as f:
            proc = subprocess.run(cmd, stdin=f, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=3.0)
        lines = [ln for ln in proc.stdout.strip().split("\n") if ln.strip()]
        if not lines:
            return []
        if len(lines) > limit:
            lines = lines[-limit:]
        pkts = []
        for line in lines:
            parts = line.split("\t")
            if len(parts) < 13:
                parts.extend([""] * (13 - len(parts)))
            raw_flags = parts[6]
            if "S" in raw_flags and "A" in raw_flags:
                flag_str = "SYN-ACK"
            elif "S" in raw_flags:
                flag_str = "SYN"
            elif "F" in raw_flags:
                flag_str = "FIN"
            elif "R" in raw_flags:
                flag_str = "RST"
            elif "A" in raw_flags:
                flag_str = "ACK"
            else:
                flag_str = "DATA"

            is_ret = bool(parts[10])
            is_dup = bool(parts[11])
            src_p = int(parts[4]) if parts[4].isdigit() else 0
            dst_p = int(parts[5]) if parts[5].isdigit() else 0
            pkts.append({
                "num": int(parts[0]) if parts[0].isdigit() else len(pkts) + 1,
                "time": round(float(parts[1]), 4) if parts[1] else 0.0,
                "src": parts[2] or "Client",
                "dst": parts[3] or "Server",
                "src_port": src_p,
                "dst_port": dst_p,
                "direction": "c2s" if dst_p == port else "s2c",
                "flags": flag_str,
                "seq": int(parts[7]) if parts[7].isdigit() else 0,
                "ack": int(parts[8]) if parts[8].isdigit() else 0,
                "len": int(parts[9]) if parts[9].isdigit() else 0,
                "is_retrans": is_ret,
                "is_dup_ack": is_dup,
                "info": parts[12] or f"TCP {flag_str}"
            })
        return pkts
    except Exception:
        return []


def get_lan_ip() -> str:
    """Retrieve the primary local area network IP for device discovery."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def check_netns_active() -> bool:
    """Check if ns-client and ns-server namespaces exist."""
    try:
        out = subprocess.check_output(["ip", "netns", "list"], text=True)
        return ("ns-client" in out) and ("ns-server" in out)
    except Exception:
        return False


def ensure_server_running():
    """Ensure tcp_server.py is running inside ns-server (or host)."""
    global SERVER_PROCESS
    if SERVER_PROCESS and SERVER_PROCESS.poll() is None:
        return  # already running

    server_script = os.path.join(PROJECT_ROOT, "server", "tcp_server.py")
    storage_dir = os.path.join(PROJECT_ROOT, "server_storage")
    os.makedirs(storage_dir, exist_ok=True)

    use_netns = check_netns_active()
    if use_netns:
        nsrun_script = get_script_path("nsrun.sh")
        cmd = [
            "sudo", nsrun_script, "ns-server",
            sys.executable, server_script,
            "--host", "0.0.0.0",
            "--port", "5000",
            "--storage-dir", storage_dir
        ]
    else:
        cmd = [
            sys.executable, server_script,
            "--host", "0.0.0.0",
            "--port", "5000",
            "--storage-dir", storage_dir
        ]

    try:
        SERVER_PROCESS = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.3)
    except Exception as e:
        print(f"[ERROR] Failed to start tcp_server: {e}")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ImpairRequest(BaseModel):
    delay: Optional[str] = "0ms"
    loss: Optional[str] = "0%"
    rate: Optional[str] = "Unlimited"

class TransferRequest(BaseModel):
    mode: str = "send"
    file: Optional[str] = None
    scenario: Optional[str] = "Manual"
    pair_id: Optional[str] = None
    session_id: Optional[str] = None

class JoinRequest(BaseModel):
    role: str = "send"  # send or receive


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def api_health():
    """Run diagnostic checks on system requirements and testbed state."""
    netns_ok = check_netns_active()
    tshark_ok = (subprocess.run(["which", "tshark"], stdout=subprocess.DEVNULL).returncode == 0)
    tc_ok = (subprocess.run(["which", "tc"], stdout=subprocess.DEVNULL).returncode == 0)
    ethtool_ok = (subprocess.run(["which", "ethtool"], stdout=subprocess.DEVNULL).returncode == 0)

    ping_ok = False
    if netns_ok:
        nsrun_script = get_script_path("nsrun.sh")
        res = subprocess.run(
            ["sudo", "-n", nsrun_script, "ns-client", "ping", "-c", "1", "-W", "1", "10.10.0.2"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        ping_ok = (res.returncode == 0)

    return {
        "status": "ready" if (netns_ok and ping_ok) else "degraded",
        "netns_active": netns_ok,
        "ping_reachable": ping_ok,
        "tshark_installed": tshark_ok,
        "tc_installed": tc_ok,
        "ethtool_installed": ethtool_ok,
        "lan_ip": get_lan_ip(),
        "fix_command": "sudo ./network/netns_setup.sh up"
    }


@app.post("/api/session")
async def create_session():
    """Create a new discovery session with an 'NS-' prefix and return join metadata."""
    lan_ip = get_lan_ip()
    sess = session_manager.create_session(lan_ip=lan_ip, port=8000)

    data = sess.model_dump()
    data["id"] = sess.session_id  # compatibility

    await broadcaster.broadcast("SESSION_CREATED", data)
    return data


@app.get("/api/session/{session_id}")
def get_session(session_id: str):
    sess = session_manager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    data = sess.model_dump()
    data["id"] = sess.session_id
    data["peer_joined"] = len(sess.clients) > 0
    return data


@app.get("/api/session/{session_id}/available-role")
def get_session_available_roles(session_id: str):
    """Return which roles ('sender', 'receiver') are still available in that session."""
    sess = session_manager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    has_sender = any(c.role == ClientRole.SEND for c in sess.clients.values() if c.online)
    has_receiver = any(c.role == ClientRole.RECEIVE for c in sess.clients.values() if c.online)

    available = []
    if not has_sender:
        available.append("sender")
    if not has_receiver:
        available.append("receiver")

    return {"available": available}


@app.post("/api/session/{session_id}/clients")
async def register_session_client(session_id: str, req: ClientJoinRequest, request: Request):
    """Register device with the control plane in this session."""
    sess = session_manager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    client_ip = request.client.host if request.client else "127.0.0.1"
    # Check X-Forwarded-For if present
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    req_role = (req.role or "unset").lower()
    has_sender = any(c.role == ClientRole.SEND for c in sess.clients.values() if c.online)
    has_receiver = any(c.role == ClientRole.RECEIVE for c in sess.clients.values() if c.online)

    # Enforce that only one sender and one receiver can exist. Reject with 400 if requested role is already taken.
    if req_role in ("send", "sender"):
        if has_sender:
            raise HTTPException(status_code=400, detail="Sender role is already taken in this session")
        resolved_role = "send"
    elif req_role in ("receive", "receiver"):
        if has_receiver:
            raise HTTPException(status_code=400, detail="Receiver role is already taken in this session")
        resolved_role = "receive"
    elif req_role == "auto":
        if not has_sender:
            resolved_role = "send"
        elif not has_receiver:
            resolved_role = "receive"
        else:
            raise HTTPException(status_code=400, detail="Session is full. Both sender and receiver roles are taken.")
    else:
        # unset or other role
        if has_sender and has_receiver:
            raise HTTPException(status_code=400, detail="Session is full. Both sender and receiver roles are taken.")
        resolved_role = req_role

    try:
        client = session_manager.register_client(session_id, req.client_name, client_ip, resolved_role)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    await broadcaster.broadcast("CLIENT_JOINED", {
        "session_id": session_id,
        "client": client.model_dump()
    })

    # Evaluate pairing
    pair = pairing_manager.attempt_pairing(session_id)
    if pair:
        await broadcaster.broadcast("PAIR_CREATED", {
            "session_id": session_id,
            "pair": pair.model_dump()
        })

    res_data = client.model_dump()
    res_data.update({
        "status": "ok",
        "client": client.model_dump(),
        "client_id": client.client_id,
        "role": client.role.value if hasattr(client.role, "value") else str(client.role),
        "paired": pair is not None,
        "pair": pair.model_dump() if pair else None
    })
    return res_data


@app.get("/api/session/{session_id}/clients")
def list_session_clients(session_id: str):
    """List all connected devices in the session."""
    sess = session_manager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    clients = session_manager.list_clients(session_id)
    return [c.model_dump() for c in clients]


@app.post("/api/session/{session_id}/role")
async def set_client_role(session_id: str, req: RoleSelectRequest):
    """Set role for registered client (SEND or RECEIVE) and attempt pairing."""
    try:
        client = session_manager.set_client_role(session_id, req.client_id, req.role)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    await broadcaster.broadcast("ROLE_SELECTED", {
        "session_id": session_id,
        "client": client.model_dump()
    })

    pair = pairing_manager.attempt_pairing(session_id)
    if pair:
        await broadcaster.broadcast("PAIR_CREATED", {
            "session_id": session_id,
            "pair": pair.model_dump()
        })

    return {
        "status": "ok",
        "client": client.model_dump(),
        "paired": pair is not None,
        "pair": pair.model_dump() if pair else None
    }


@app.get("/api/session/{session_id}/pair")
def check_client_pairing(session_id: str, client_id: Optional[str] = None):
    """Check pairing state for a specific client or the session's active pair."""
    if client_id:
        pair = pairing_manager.get_client_pair(session_id, client_id)
    else:
        pairs = pairing_manager.get_session_pairs(session_id)
        pair = pairs[0] if pairs else None

    if pair:
        data = pair.model_dump()
        data["paired"] = True
        data["pair"] = pair.model_dump()
        return data
    return {"paired": False, "pair": None, "pair_id": None}


@app.delete("/api/session/{session_id}/clients/{client_id}")
async def remove_session_client(session_id: str, client_id: str):
    """Handle client departure."""
    pairing_manager.handle_client_disconnect(session_id, client_id)
    client = session_manager.remove_client(session_id, client_id)
    if client:
        await broadcaster.broadcast("CLIENT_LEFT", {
            "session_id": session_id,
            "client_id": client_id
        })
    return {"status": "ok"}


@app.post("/api/session/{session_id}/join")
async def legacy_join_session(session_id: str, req: Dict[str, Any], request: Request):
    """Backward compatibility for existing peer join from UI/tests."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    name = req.get("client_name") or req.get("device") or "MobilePeer"
    role = req.get("role", "receive")

    try:
        client = session_manager.register_client(session_id, name, client_ip, role)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    pair = pairing_manager.attempt_pairing(session_id)

    await broadcaster.broadcast("CLIENT_JOINED", {
        "session_id": session_id,
        "client": client.model_dump()
    })
    if pair:
        await broadcaster.broadcast("PAIR_CREATED", {
            "session_id": session_id,
            "pair": pair.model_dump()
        })

    sess = session_manager.get_session(session_id)
    data = sess.model_dump()
    data["id"] = sess.session_id
    data["peer_joined"] = True
    data["peer_role"] = role
    return {"status": "ok", "session": data, "client": client.model_dump()}


@app.post("/api/session/{session_id}/telemetry/progress")
async def report_telemetry_progress(session_id: str, prog: TransferProgressReport):
    """Client reports live transfer progress to control plane."""
    global CURRENT_TRANSFER
    CURRENT_TRANSFER["running"] = True
    CURRENT_TRANSFER["pct"] = prog.pct
    CURRENT_TRANSFER["bytes"] = prog.bytes_sent
    CURRENT_TRANSFER["total_bytes"] = prog.total_bytes
    CURRENT_TRANSFER["mbps"] = prog.mbps

    pairing_manager.update_pair_status(prog.pair_id, PairStatus.TRANSFERRING)

    await broadcaster.broadcast("TRANSFER_PROGRESS", prog.model_dump())
    return {"status": "ok"}


@app.post("/api/session/{session_id}/telemetry/complete")
async def report_telemetry_complete(session_id: str, result: Dict[str, Any]):
    """Client reports transfer completion to control plane."""
    global CURRENT_TRANSFER
    CURRENT_TRANSFER["running"] = False
    CURRENT_TRANSFER["sha256_ok"] = result.get("sha256_match", True)

    pair_id = result.get("pair_id")
    if pair_id:
        status = PairStatus.COMPLETED if result.get("sha256_match") else PairStatus.FAILED
        pairing_manager.update_pair_status(pair_id, status)

    await broadcaster.broadcast("TRANSFER_COMPLETED", {
        "session_id": session_id,
        "result": result
    })
    return {"status": "ok"}


@app.get("/api/qr/{session_id}")
def get_qr_svg(session_id: str):
    """Render a pure vector SVG QR code for the session join URL using segno."""
    sid = session_id.upper()
    sess = session_manager.get_session(sid)
    lan_ip = get_lan_ip()
    join_url = sess.join_url if sess else f"http://{lan_ip}:8000/join/{sid}"

    qr = segno.make(join_url, error='m')
    svg_str = qr.svg_data_uri(scale=6, light="#FFFFFF", dark="#0F1B31")
    header, data = svg_str.split(",", 1)
    import urllib.parse
    svg_content = urllib.parse.unquote(data)
    return Response(content=svg_content, media_type="image/svg+xml")


@app.post("/api/impair")
async def apply_impairment(req: ImpairRequest):
    """Apply traffic control impairment to ns-client veth-c interface."""
    global CURRENT_IMPAIRMENT
    use_netns = check_netns_active()
    script = get_script_path("impair.sh")

    cmd = ["sudo", script]
    if use_netns:
        cmd.extend(["--ns", "ns-client", "veth-c", "apply"])
    else:
        cmd.extend(["eth0", "apply"])

    if req.delay and req.delay != "0ms":
        cmd.extend(["--delay", req.delay])
    if req.loss and req.loss != "0%":
        cmd.extend(["--loss", req.loss])
    if req.rate and req.rate != "Unlimited":
        cmd.extend(["--rate", req.rate])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            err_msg = f"Failed to apply impairment: {proc.stderr.strip() or proc.stdout.strip()}"
            await broadcaster.broadcast("error", {"message": err_msg})
            raise HTTPException(status_code=500, detail=err_msg)

        CURRENT_IMPAIRMENT = {
            "delay": req.delay or "0ms",
            "loss": req.loss or "0%",
            "rate": req.rate or "Unlimited"
        }

        await broadcaster.broadcast("impairment_update", CURRENT_IMPAIRMENT)
        await broadcaster.broadcast("impairments_applied", CURRENT_IMPAIRMENT)
        return {"status": "ok", "impairment": CURRENT_IMPAIRMENT}
    except HTTPException:
        raise
    except Exception as e:
        err_msg = f"Impairment execution error: {str(e)}"
        await broadcaster.broadcast("error", {"message": err_msg})
        raise HTTPException(status_code=500, detail=err_msg)


@app.delete("/api/impair")
async def clear_impairment():
    """Clear traffic control impairments."""
    global CURRENT_IMPAIRMENT
    use_netns = check_netns_active()
    script = get_script_path("impair.sh")

    cmd = ["sudo", script]
    if use_netns:
        cmd.extend(["--ns", "ns-client", "veth-c", "clear"])
    else:
        cmd.extend(["eth0", "clear"])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    CURRENT_IMPAIRMENT = {"delay": "0ms", "loss": "0%", "rate": "Unlimited"}
    await broadcaster.broadcast("impairment_update", CURRENT_IMPAIRMENT)
    return {"status": "ok", "cleared": True}


@app.get("/api/impair")
def get_impairment():
    return CURRENT_IMPAIRMENT


MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200 MB limit


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload custom test file for transfer (max 200 MB). Saved to results/uploads/."""
    uploads_dir = os.path.join(PROJECT_ROOT, "results", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    filename = os.path.basename(file.filename or "upload.bin")
    dest_path = os.path.join(uploads_dir, filename)

    total_bytes = 0
    chunk_size = 1024 * 1024  # 1MB chunk

    try:
        with open(dest_path, "wb") as out_f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_SIZE:
                    out_f.close()
                    if os.path.isfile(dest_path):
                        os.remove(dest_path)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed size of 200 MB ({total_bytes} bytes uploaded)."
                    )
                out_f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.isfile(dest_path):
            os.remove(dest_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    if session_manager.sessions:
        for s in session_manager.sessions.values():
            s.uploaded_file = dest_path
            s.sender_file_path = dest_path

    return {
        "status": "ok",
        "filename": filename,
        "path": dest_path,
        "size_bytes": total_bytes,
        "size_mb": round(total_bytes / (1024 * 1024), 2)
    }


@app.post("/api/session/{session_id}/upload")
async def upload_session_file(session_id: str, file: UploadFile = File(...)):
    """Upload payload file directly registered to a specific session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    uploads_dir = os.path.join(PROJECT_ROOT, "results", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    filename = os.path.basename(file.filename or "upload.bin")
    dest_path = os.path.join(uploads_dir, f"{session_id}_{filename}")

    total_bytes = 0
    chunk_size = 1024 * 1024

    try:
        with open(dest_path, "wb") as out_f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_SIZE:
                    out_f.close()
                    if os.path.isfile(dest_path):
                        os.remove(dest_path)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed size of 200 MB ({total_bytes} bytes uploaded)."
                    )
                out_f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.isfile(dest_path):
            os.remove(dest_path)
        raise HTTPException(status_code=500, detail=f"Session upload failed: {str(e)}")

    session.uploaded_file = dest_path
    session.sender_file_path = dest_path

    await broadcaster.broadcast("file_uploaded", {
        "session_id": session_id,
        "filename": filename,
        "path": dest_path,
        "size": total_bytes
    })

    return {
        "status": "ok",
        "session_id": session_id,
        "filename": filename,
        "path": dest_path,
        "size_bytes": total_bytes
    }


@app.get("/api/scenarios")
def get_scenarios():
    """Load and return the 11 specification scenarios from network/scenarios.json."""
    scenarios_file = os.path.join(PROJECT_ROOT, "network", "scenarios.json")
    if not os.path.isfile(scenarios_file):
        raise HTTPException(status_code=404, detail="scenarios.json not found")
    with open(scenarios_file, "r", encoding="utf-8") as f:
        return json.load(f)
    return CURRENT_IMPAIRMENT


@app.post("/api/transfer")
async def trigger_transfer(req: TransferRequest, background_tasks: BackgroundTasks):
    """Execute a file transfer between ns-client and ns-server, streaming telemetry."""
    global CURRENT_PACKETS, _PACKET_CURSORS
    if CURRENT_TRANSFER["running"]:
        raise HTTPException(status_code=400, detail="A transfer is already in progress.")

    CURRENT_PACKETS = []
    _PACKET_CURSORS.clear()

    ensure_server_running()

    # Strictly resolve target file path from session upload or explicit request parameter
    target_file = None
    target_session = None

    if req.session_id:
        target_session = session_manager.get_session(req.session_id)
    if not target_session and req.pair_id:
        for s in session_manager.sessions.values():
            if s.active_pair and s.active_pair.pair_id == req.pair_id:
                target_session = s
                break
    if not target_session and session_manager.sessions:
        target_session = list(session_manager.sessions.values())[-1]

    if target_session and target_session.uploaded_file and os.path.isfile(target_session.uploaded_file):
        target_file = target_session.uploaded_file
    elif target_session and getattr(target_session, "sender_file_path", None) and os.path.isfile(target_session.sender_file_path):
        target_file = target_session.sender_file_path
    elif req.file:
        cand = os.path.abspath(req.file if os.path.isabs(req.file) else os.path.join(PROJECT_ROOT, req.file))
        if os.path.isfile(cand):
            target_file = cand

    if not target_file:
        raise HTTPException(
            status_code=400,
            detail="No source file uploaded or specified for transfer. Please have sender upload a file."
        )

    file_path = target_file

    run_id = uuid.uuid4().hex[:8]
    CURRENT_TRANSFER["running"] = True
    CURRENT_TRANSFER["run_id"] = run_id
    CURRENT_TRANSFER["mode"] = req.mode
    CURRENT_TRANSFER["file"] = os.path.basename(file_path)
    CURRENT_TRANSFER["pct"] = 0.0
    CURRENT_TRANSFER["mbps"] = 0.0
    CURRENT_TRANSFER["bytes"] = 0
    CURRENT_TRANSFER["total_bytes"] = os.path.getsize(file_path)
    CURRENT_TRANSFER["sha256_ok"] = None

    await broadcaster.broadcast("transfer_started", {
        "run_id": run_id,
        "mode": req.mode,
        "file": os.path.basename(file_path),
        "total_bytes": os.path.getsize(file_path)
    })

    background_tasks.add_task(
        execute_transfer_worker,
        mode=req.mode,
        file_path=file_path,
        scenario=req.scenario or "Manual",
        run_id=run_id
    )
    return {"status": "started", "run_id": run_id, "file": os.path.basename(file_path)}


async def execute_transfer_worker(mode: str, file_path: str, scenario: str, run_id: str):
    """Background worker executing the transfer with live sniffer and progress stream."""
    global CURRENT_TRANSFER, CURRENT_PACKETS
    use_netns = check_netns_active()
    server_ip = "10.10.0.2" if use_netns else "127.0.0.1"
    iface_name = "veth-c" if use_netns else "eth0"
    ns_name = "ns-client" if use_netns else None

    pcap_dir = os.path.join(PROJECT_ROOT, "results", "pcaps")
    os.makedirs(pcap_dir, exist_ok=True)
    pcap_file = os.path.join(pcap_dir, f"{scenario}_{run_id}.pcap")
    rel_pcap = os.path.relpath(pcap_file, PROJECT_ROOT)

    # 1. Start packet sniffer
    sniffer = Sniffer(iface=iface_name, port=5000, out_path=pcap_file, ns=ns_name)
    sniffer.start()

    # Initial SYN packet event
    await broadcaster.broadcast("packet_event", {"flag": "SYN", "info": "Connection SYN initiated", "time": time.time()})

    client_py = os.path.join(PROJECT_ROOT, "client", "tcp_client.py")
    results_file = os.path.join(PROJECT_ROOT, "results", "transfers.jsonl")
    base_client_cmd = [
        sys.executable, client_py, mode,
        "--server", server_ip,
        "--port", "5000",
        "--file", file_path,
        "--scenario", scenario,
        "--run-id", run_id,
        "--progress-json",
        "--results-file", results_file
    ]

    if ns_name:
        nsrun_script = get_script_path("nsrun.sh")
        cmd = ["sudo", nsrun_script, ns_name] + base_client_cmd
    else:
        cmd = base_client_cmd

    last_bytes = 0
    last_time = time.perf_counter()
    last_telemetry_time = time.perf_counter()
    last_pcap_time = time.perf_counter()
    latest_record = {}
    tcp_metrics = {}

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        # Handshake simulated events
        await asyncio.sleep(0.05)
        await broadcaster.broadcast("packet_event", {"flag": "SYN-ACK", "info": "Server SYN-ACK returned", "time": time.time()})
        await broadcaster.broadcast("packet_event", {"flag": "ACK", "info": "Handshake ACK complete", "time": time.time()})

        # Read JSON progress stream from client stdout
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            line = line.strip()
            if not line:
                continue

            try:
                prog = json.loads(line)
                cur_bytes = prog.get("bytes", 0)
                now = time.perf_counter()
                dt = max(now - last_time, 0.05)
                instant_mbps = round(((cur_bytes - last_bytes) * 8) / (dt * 1_000_000), 2)
                last_bytes = cur_bytes
                last_time = now

                pct = prog.get("pct", 0.0)
                CURRENT_TRANSFER["pct"] = pct
                CURRENT_TRANSFER["bytes"] = cur_bytes
                CURRENT_TRANSFER["mbps"] = instant_mbps

                await broadcaster.broadcast("transfer_progress", {
                    "run_id": run_id,
                    "pct": pct,
                    "bytes": cur_bytes,
                    "mbps": instant_mbps
                })

                # Broadcast telemetry_update every second (Requirement 3)
                if now - last_telemetry_time >= 1.0:
                    last_telemetry_time = now
                    kernel_stats = get_kernel_tcp_stats(port=5000, ns=ns_name)
                    telemetry_data = {
                        "throughput": instant_mbps,
                        "rtt": kernel_stats.get("rtt", 0.0),
                        "cwnd": kernel_stats.get("cwnd", 0),
                        "retransmissions": kernel_stats.get("retrans", 0),
                        "pct": pct
                    }
                    await broadcaster.broadcast("telemetry_update", telemetry_data)

                # Periodic pcap packet streaming
                if now - last_pcap_time >= 1.0:
                    last_pcap_time = now
                    pkts = extract_pcap_packets(pcap_file, port=5000, limit=200)
                    if pkts:
                        CURRENT_PACKETS = pkts
                        await broadcaster.broadcast("packets_batch", {"packets": pkts[-50:], "count": len(pkts)})

            except json.JSONDecodeError:
                pass

        proc.wait()
        sniffer.stop()
        await broadcaster.broadcast("packet_event", {"flag": "FIN", "info": "TCP teardown FIN complete", "time": time.time()})

        tcp_metrics = analyze(pcap_file, port=5000)
        CURRENT_PACKETS = extract_pcap_packets(pcap_file, port=5000, limit=2000)

        # 3. Read latest record from transfers.jsonl and augment with tcp metrics
        if os.path.isfile(results_file):
            with open(results_file, "r", encoding="utf-8") as rf:
                lines = [ln.strip() for ln in rf if ln.strip()]
                if lines:
                    try:
                        latest_record = json.loads(lines[-1])
                    except Exception:
                        pass

        latest_record["pcap"] = rel_pcap
        latest_record["tcp"] = tcp_metrics
        latest_record["packets"] = CURRENT_PACKETS

        # Re-write the augmented record
        if os.path.isfile(results_file):
            with open(results_file, "r", encoding="utf-8") as rf:
                all_lines = [ln.strip() for ln in rf if ln.strip()]
            if all_lines:
                all_lines[-1] = json.dumps(latest_record)
                with open(results_file, "w", encoding="utf-8") as wf:
                    wf.write("\n".join(all_lines) + "\n")

        CURRENT_TRANSFER["pct"] = 100.0
        CURRENT_TRANSFER["sha256_ok"] = latest_record.get("sha256_ok", True)
        if latest_record.get("throughput_mbps"):
            CURRENT_TRANSFER["mbps"] = float(latest_record["throughput_mbps"])

        # Final packets and completion broadcast
        await broadcaster.broadcast("packets_batch", {"packets": CURRENT_PACKETS, "count": len(CURRENT_PACKETS)})
        await broadcaster.broadcast("transfer_complete", {
            "run_id": run_id,
            "record": latest_record,
            "tcp": tcp_metrics,
            "packets": CURRENT_PACKETS
        })

    except Exception as e:
        print(f"[ERROR] Transfer execution error: {e}")
        try:
            sniffer.stop()
        except Exception:
            pass
    finally:
        CURRENT_TRANSFER["running"] = False


@app.get("/api/packets")
def get_packets():
    return {"packets": CURRENT_PACKETS, "count": len(CURRENT_PACKETS)}


@app.get("/api/telemetry")
def get_telemetry():
    return CURRENT_TRANSFER


@app.post("/api/session/{session_id}/signal/ready")
async def signal_sender_ready(session_id: str, payload: Optional[Dict[str, Any]] = None):
    """Signal that sender is ready to transfer."""
    filename = (payload or {}).get("filename", "")
    await broadcaster.broadcast("sender_ready", {
        "session_id": session_id,
        "ready": True,
        "filename": filename
    })
    return {"status": "ok", "ready": True, "filename": filename}


@app.websocket("/api/ws")
@app.websocket("/api/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: Optional[str] = None):
    await websocket.accept()
    await broadcaster.register_ws(websocket)
    try:
        while True:
            text = await websocket.receive_text()
            if not text:
                continue
            try:
                msg = json.loads(text)
                if msg.get("type") == "PING":
                    await websocket.send_text(json.dumps({"type": "PONG", "time": time.time()}))
            except Exception:
                pass
    except WebSocketDisconnect:
        broadcaster.unregister_ws(websocket)
    except Exception:
        broadcaster.unregister_ws(websocket)


@app.get("/api/events")
async def sse_stream(request: Request):
    """Server-Sent Events endpoint broadcasting live telemetry and packet events."""
    q = await broadcaster.subscribe()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=5.0)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat
                    yield f"data: {json.dumps({'type': 'heartbeat', 'time': time.time()})}\n\n"
        finally:
            broadcaster.unsubscribe(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/results")
def get_results():
    """Return all transfer records from results/transfers.jsonl."""
    res_path = os.path.join(PROJECT_ROOT, "results", "transfers.jsonl")
    if not os.path.isfile(res_path):
        return []

    records = []
    with open(res_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


@app.get("/api/summary")
def get_summary():
    """Return summarized mean and standard deviation per scenario."""
    return summarize("results/transfers.jsonl", "results/summary.csv")


@app.post("/api/experiments/start")
def start_experiments(repeats: int = 3):
    """Trigger background execution of all 11 benchmark scenarios."""
    global ACTIVE_EXPERIMENT
    if ACTIVE_EXPERIMENT and ACTIVE_EXPERIMENT.poll() is None:
        raise HTTPException(status_code=400, detail="Experiment already running.")

    ensure_server_running()
    runner = os.path.join(PROJECT_ROOT, "experiments", "run_all.py")
    cmd = [sys.executable, runner, "--repeats", str(repeats), "--capture"]
    ACTIVE_EXPERIMENT = subprocess.Popen(cmd)
    return {"status": "started", "repeats": repeats}


@app.post("/api/experiments/stop")
def stop_experiments():
    """Cancel currently running benchmark."""
    global ACTIVE_EXPERIMENT
    if ACTIVE_EXPERIMENT and ACTIVE_EXPERIMENT.poll() is None:
        ACTIVE_EXPERIMENT.terminate()
        ACTIVE_EXPERIMENT = None
        # Clear impairment
        script = get_script_path("impair.sh")
        subprocess.run(["sudo", script, "--ns", "ns-client", "veth-c", "clear"], check=False)
        return {"status": "stopped"}
    return {"status": "not_running"}


# ---------------------------------------------------------------------------
# Frontend Views & Static Delivery
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Fernet Key Derivation & Server Storage Cleanup (Task 10)
# ---------------------------------------------------------------------------

def get_fernet_key(run_id: str) -> bytes:
    """Derive a deterministic Fernet key (32 URL-safe base64 bytes) from run_id."""
    digest = hashlib.sha256(run_id.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)




@app.get("/api/download/{run_id}")
async def download_file_by_run_id(run_id: str, background_tasks: BackgroundTasks):
    """
    Find file in results/server_storage by run_id from transfers.jsonl,
    decrypt using Fernet key derived from run_id, stream as download, and delete after.
    """
    cleanup_old_server_storage()
    results_file = os.path.join(PROJECT_ROOT, "results", "transfers.jsonl")
    matched_file = None
    if os.path.isfile(results_file):
        with open(results_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("run_id") == run_id:
                        matched_file = rec.get("file")
                        break
                except Exception:
                    pass

    storage_dir = os.path.join(PROJECT_ROOT, "results", "server_storage")
    file_path = None
    if matched_file:
        candidate = os.path.join(storage_dir, matched_file)
        if os.path.isfile(candidate):
            file_path = candidate

    # Fallback: check if run_id directly names or matches a file in server_storage
    if not file_path and os.path.isdir(storage_dir):
        for fn in os.listdir(storage_dir):
            if fn == run_id or run_id in fn:
                file_path = os.path.join(storage_dir, fn)
                matched_file = fn
                break

    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"File for run_id '{run_id}' not found in storage.")

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # Attempt Fernet decryption using key derived from run_id
    try:
        cipher = Fernet(get_fernet_key(run_id))
        decrypted_bytes = cipher.decrypt(file_bytes)
    except Exception:
        # Fallback to raw bytes if not encrypted
        decrypted_bytes = file_bytes

    # Schedule deletion after response finishes
    background_tasks.add_task(os.remove, file_path)

    out_name = matched_file or f"download_{run_id}.bin"
    return Response(
        content=decrypted_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'}
    )


# ---------------------------------------------------------------------------
# API Root & Redirects (Old GUI routes removed per Task 1)
# ---------------------------------------------------------------------------

@app.get("/")
def api_root():
    """FastAPI only serves API endpoints and WebSocket (Task 1)."""
    return {
        "service": "NetScope API",
        "status": "running",
        "version": "2.0.0",
        "docs": "/docs",
        "desktop_frontend": "http://localhost:5173",
        "mobile_frontend": "http://localhost:5174",
    }


@app.get("/join/{session_id}", response_class=HTMLResponse)
def api_join_redirect(session_id: str, request: Request):
    """Redirect mobile join requests to the mobile React Vite app on port 5174."""
    host = request.url.hostname or "localhost"
    redirect_target = f"http://{host}:5174/join/{session_id}"
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>NetScope Join {session_id}</title>
    <meta http-equiv="refresh" content="0; url={redirect_target}">
</head>
<body>
    <p>Joining NetScope session {session_id}... <a href="{redirect_target}">Click here to continue</a></p>
    <script>window.location.href = "{redirect_target}";</script>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)
