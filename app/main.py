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
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
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

app = FastAPI(title="NetScope Control Center")

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
        elif method == "GET" and path.startswith("/api/qr/"):
            is_allowed = True
        elif method == "GET" and path in ("/manifest.json", "/icon.svg", "/sw.js", "/favicon.ico"):
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

# Experiment background task handle
ACTIVE_EXPERIMENT: Optional[subprocess.Popen] = None

# Background TCP Server handle
SERVER_PROCESS: Optional[subprocess.Popen] = None


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
    file: Optional[str] = "tests/data/test_10mb.bin"
    scenario: Optional[str] = "Manual"

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


@app.post("/api/session/{session_id}/clients")
async def register_session_client(session_id: str, req: ClientJoinRequest, request: Request):
    """Register device with the control plane in this session."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    # Check X-Forwarded-For if present
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    try:
        client = session_manager.register_client(session_id, req.client_name, client_ip, req.role or "unset")
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

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Failed to apply impairment: {proc.stderr}")

    CURRENT_IMPAIRMENT = {
        "delay": req.delay or "0ms",
        "loss": req.loss or "0%",
        "rate": req.rate or "Unlimited"
    }

    await broadcaster.broadcast("impairment_update", CURRENT_IMPAIRMENT)
    return {"status": "ok", "impairment": CURRENT_IMPAIRMENT}


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

    return {
        "status": "ok",
        "filename": filename,
        "path": dest_path,
        "size_bytes": total_bytes,
        "size_mb": round(total_bytes / (1024 * 1024), 2)
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
    if CURRENT_TRANSFER["running"]:
        raise HTTPException(status_code=400, detail="A transfer is already in progress.")

    ensure_server_running()

    file_path = os.path.abspath(req.file if os.path.isabs(req.file) else os.path.join(PROJECT_ROOT, req.file))
    if not os.path.isfile(file_path):
        # Fall back to sample testfile or create one
        os.makedirs(os.path.join(PROJECT_ROOT, "tests", "data"), exist_ok=True)
        file_path = os.path.join(PROJECT_ROOT, "tests", "data", "test_10mb.bin")
        if not os.path.isfile(file_path):
            with open(file_path, "wb") as f:
                f.write(os.urandom(10485760))

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

    background_tasks.add_task(
        execute_transfer_worker,
        mode=req.mode,
        file_path=file_path,
        scenario=req.scenario or "Manual",
        run_id=run_id
    )
    return {"status": "started", "run_id": run_id}


async def execute_transfer_worker(mode: str, file_path: str, scenario: str, run_id: str):
    """Background worker executing the transfer with live sniffer and progress stream."""
    global CURRENT_TRANSFER
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

    # Simulate SYN packet event
    await broadcaster.broadcast("packet_event", {"flag": "SYN", "info": "Connection SYN initiated", "time": time.time()})

    client_py = os.path.join(PROJECT_ROOT, "client", "tcp_client.py")
    base_client_cmd = [
        sys.executable, client_py, mode,
        "--server", server_ip,
        "--port", "5000",
        "--file", file_path,
        "--scenario", scenario,
        "--run-id", run_id,
        "--progress-json",
        "--results-file", os.path.join(PROJECT_ROOT, "results", "transfers.jsonl")
    ]

    if ns_name:
        nsrun_script = get_script_path("nsrun.sh")
        cmd = ["sudo", nsrun_script, ns_name] + base_client_cmd
    else:
        cmd = base_client_cmd

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
                CURRENT_TRANSFER["pct"] = prog.get("pct", 0.0)
                CURRENT_TRANSFER["bytes"] = prog.get("bytes", 0)
                CURRENT_TRANSFER["mbps"] = prog.get("mbps", 0.0)

                await broadcaster.broadcast("transfer_progress", {
                    "run_id": run_id,
                    "pct": prog.get("pct", 0.0),
                    "bytes": prog.get("bytes", 0),
                    "mbps": prog.get("mbps", 0.0)
                })
            except json.JSONDecodeError:
                pass

        proc.wait()
    except Exception as e:
        print(f"[ERROR] Transfer execution error: {e}")

    # 2. Stop Sniffer and dissect PCAP
    sniffer.stop()
    await broadcaster.broadcast("packet_event", {"flag": "FIN", "info": "TCP teardown FIN complete", "time": time.time()})

    tcp_metrics = analyze(pcap_file, port=5000)

    # 3. Read latest record from transfers.jsonl and augment with tcp metrics
    results_file = os.path.join(PROJECT_ROOT, "results", "transfers.jsonl")
    latest_record = {}
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

    # Re-write the augmented record
    if os.path.isfile(results_file):
        with open(results_file, "r", encoding="utf-8") as rf:
            all_lines = [ln.strip() for ln in rf if ln.strip()]
        if all_lines:
            all_lines[-1] = json.dumps(latest_record)
            with open(results_file, "w", encoding="utf-8") as wf:
                wf.write("\n".join(all_lines) + "\n")

    CURRENT_TRANSFER["running"] = False
    CURRENT_TRANSFER["sha256_ok"] = latest_record.get("sha256_ok", True)

    await broadcaster.broadcast("transfer_complete", {
        "run_id": run_id,
        "record": latest_record,
        "tcp": tcp_metrics
    })


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

@app.get("/", response_class=HTMLResponse)
def index_view():
    gui_index = os.path.join(PROJECT_ROOT, "gui", "index.html")
    if os.path.isfile(gui_index):
        with open(gui_index, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>NetScope GUI Loading...</h1>"


@app.get("/join/{session_id}", response_class=HTMLResponse)
def join_view(session_id: str):
    join_html = os.path.join(PROJECT_ROOT, "gui", "join.html")
    if os.path.isfile(join_html):
        with open(join_html, "r", encoding="utf-8") as f:
            content = f.read()
            return content.replace("{{SESSION_ID}}", session_id.upper())
    return f"<h1>NetScope Join Session {session_id}</h1>"


@app.get("/manifest.json")
def get_manifest():
    manifest_path = os.path.join(PROJECT_ROOT, "gui", "manifest.json")
    if os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            return JSONResponse(content=json.load(f))
    return JSONResponse(content={"name": "NetScope", "short_name": "NetScope"})


@app.get("/sw.js")
def get_service_worker():
    sw_path = os.path.join(PROJECT_ROOT, "gui", "sw.js")
    if os.path.isfile(sw_path):
        with open(sw_path, "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="application/javascript")
    return Response(content="// sw", media_type="application/javascript")


@app.get("/icon.svg")
def get_app_icon():
    icon_path = os.path.join(PROJECT_ROOT, "gui", "icon.svg")
    if os.path.isfile(icon_path):
        with open(icon_path, "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="image/svg+xml")
    return Response(content="<svg></svg>", media_type="image/svg+xml")
