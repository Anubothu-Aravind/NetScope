#!/usr/bin/env python3
"""
client/tcp_client.py - CLI TCP Client for NetScope File Transfers

Viva Concepts:
- TCP 3-Way Handshake Timing:
    The duration of `socket.connect((ip, port))` measures the time taken to complete
    the SYN -> SYN-ACK -> ACK sequence. Under network delay or packet loss,
    this connection establishment latency noticeably increases.
- Throughput Calculation:
    Throughput (Mbps) = (file_size_bytes * 8) / (completion_seconds * 1,000,000)
- End-to-End Integrity:
    SHA-256 checksum is calculated chunk-by-chunk both locally and remotely,
    ensuring bit-exact reliability even under lossy network emulation.
- Metric Logging:
    Every run appends a JSON line to `results/transfers.jsonl`.
"""

import os
import sys
import time
import json
import uuid
import socket
import argparse
from datetime import datetime, timezone
from typing import Optional

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from common.protocol import (
    send_msg,
    recv_msg,
    send_file_stream,
    recv_file_stream,
    compute_sha256,
)


def print_progress(current: int, total: int, prefix: str = "Transferring"):
    """Render a dynamic ASCII progress bar with percentage and megabytes."""
    pct = (current / total) * 100 if total > 0 else 100
    bar_len = 30
    filled = int(bar_len * current / total) if total > 0 else bar_len
    bar = "=" * filled + (">" if filled < bar_len else "") + "." * (bar_len - filled - (1 if filled < bar_len else 0))
    cur_mb = current / (1024 * 1024)
    tot_mb = total / (1024 * 1024)
    sys.stdout.write(f"\r[{prefix}] [{bar}] {pct:5.1f}% ({cur_mb:.2f} / {tot_mb:.2f} MB)")
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")


class JsonProgressTracker:
    """Emits throttled JSON telemetry lines (~250 ms) for frontend/backend streaming."""
    def __init__(self, total_bytes: int):
        self.total_bytes = total_bytes
        self.start_time = time.perf_counter()
        self.last_emit_time = 0.0
        self.interval = 0.25  # 250 ms

    def update(self, current_bytes: int, total_bytes: int):
        now = time.perf_counter()
        is_complete = (current_bytes >= total_bytes)
        if is_complete or (now - self.last_emit_time >= self.interval):
            elapsed = max(now - self.start_time, 1e-6)
            mbps = (current_bytes * 8) / (elapsed * 1_000_000)
            pct = (current_bytes / total_bytes * 100.0) if total_bytes > 0 else 100.0
            data = {
                "pct": round(pct, 1),
                "bytes": current_bytes,
                "mbps": round(mbps, 2)
            }
            sys.stdout.write(json.dumps(data) + "\n")
            sys.stdout.flush()
            self.last_emit_time = now


def log_result(record: dict, results_file: str = "results/transfers.jsonl"):
    """Append a structured JSON record to the specified results file."""
    target_path = results_file if os.path.isabs(results_file) else os.path.join(PROJECT_ROOT, results_file)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def run_transfer(mode: str, server_ip: str, port: int, file_arg: str,
                 scenario: str = "standalone", dest_dir: str = "downloads",
                 results_file: str = "results/transfers.jsonl",
                 run_id: Optional[str] = None,
                 progress_json: bool = False) -> dict:
    """
    Connect to server, execute Send or Receive, measure performance, and log results.
    """
    if not run_id:
        run_id = uuid.uuid4().hex[:8]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    print(f"\n=======================================================")
    print(f" NetScope TCP Client - Mode: {mode.upper()} | Run ID: {run_id}")
    print(f" Target Server: {server_ip}:{port} | Scenario: {scenario}")
    print(f"=======================================================")

    # 1. Measure TCP Connection Establishment Time (SYN -> SYN-ACK -> ACK)
    t_conn_start = time.perf_counter()
    sock.connect((server_ip, port))
    t_conn_end = time.perf_counter()
    connect_ms = (t_conn_end - t_conn_start) * 1000.0
    print(f"[✔] Connected to server in {connect_ms:.2f} ms (Handshake complete)")

    sha256_ok = False
    throughput_mbps = 0.0
    completion_s = 0.0
    file_size = 0
    filename = ""

    try:
        if mode == "send":
            if not os.path.isfile(file_arg):
                raise FileNotFoundError(f"Local file '{file_arg}' does not exist.")

            filename = os.path.basename(file_arg)
            file_size = os.path.getsize(file_arg)
            print(f"[*] Hashing local file '{filename}'...")
            local_sha256 = compute_sha256(file_arg)
            print(f"    Local SHA-256: {local_sha256}")

            # Send negotiation request
            send_msg(sock, {
                "type": "SEND_REQUEST",
                "name": filename,
                "size": file_size,
                "sha256": local_sha256
            })

            ready_reply = recv_msg(sock)
            if ready_reply.get("type") != "READY":
                raise RuntimeError(f"Server rejected send request: {ready_reply.get('message')}")

            print(f"[*] Streaming {file_size / (1024*1024):.2f} MB to server in 64 KB chunks...")
            tracker = JsonProgressTracker(file_size) if progress_json else None
            t_tx_start = time.perf_counter()
            actual_sha = send_file_stream(
                sock, file_arg, file_size,
                progress_cb=tracker.update if progress_json else (lambda cur, tot: print_progress(cur, tot, "Uploading"))
            )
            t_tx_end = time.perf_counter()
            completion_s = max(t_tx_end - t_tx_start, 1e-6)

            # Await server's verification acknowledgment
            done_reply = recv_msg(sock)
            sha256_ok = done_reply.get("sha256_ok", False)
            throughput_mbps = (file_size * 8) / (completion_s * 1_000_000)

        elif mode == "receive":
            filename = os.path.basename(file_arg)
            os.makedirs(dest_dir, exist_ok=True)
            local_dest = os.path.join(dest_dir, filename)

            # Request file from server
            send_msg(sock, {
                "type": "RECV_REQUEST",
                "name": filename
            })

            ready_reply = recv_msg(sock)
            if ready_reply.get("type") != "READY":
                raise RuntimeError(f"Server error: {ready_reply.get('message', 'File unavailable')}")

            file_size = ready_reply["size"]
            expected_sha256 = ready_reply["sha256"].lower()

            print(f"[*] Receiving '{filename}' ({file_size / (1024*1024):.2f} MB) from server...")
            tracker = JsonProgressTracker(file_size) if progress_json else None
            t_rx_start = time.perf_counter()
            actual_sha = recv_file_stream(
                sock, local_dest, file_size,
                progress_cb=tracker.update if progress_json else (lambda cur, tot: print_progress(cur, tot, "Downloading"))
            )
            t_rx_end = time.perf_counter()
            completion_s = max(t_rx_end - t_rx_start, 1e-6)

            sha256_ok = (actual_sha.lower() == expected_sha256)
            throughput_mbps = (file_size * 8) / (completion_s * 1_000_000)

            # Send confirmation back to server
            send_msg(sock, {
                "type": "DONE",
                "sha256_ok": sha256_ok,
                "client_sha256": actual_sha
            })

        else:
            raise ValueError(f"Invalid mode '{mode}'. Choose 'send' or 'receive'.")

    finally:
        sock.close()

    # Summary
    if not progress_json:
        print("\n--- Transfer Results ---")
        print(f"Run ID:          {run_id}")
        print(f"Mode:            {mode.upper()}")
        print(f"File:            {filename} ({file_size} bytes)")
        print(f"Connect Time:    {connect_ms:.2f} ms")
        print(f"Transfer Time:   {completion_s:.3f} s")
        print(f"Throughput:      {throughput_mbps:.2f} Mbps")
        print(f"Integrity Check: {'PASSED (SHA-256 Match)' if sha256_ok else 'FAILED'}")
        print("------------------------\n")

    result_record = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario,
        "mode": mode,
        "file": filename,
        "size_bytes": file_size,
        "connect_ms": round(connect_ms, 2),
        "completion_s": round(completion_s, 4),
        "throughput_mbps": round(throughput_mbps, 2),
        "sha256_ok": sha256_ok
    }

    if results_file:
        log_result(result_record, results_file)
    return result_record


def main():
    parser = argparse.ArgumentParser(description="NetScope TCP Transfer Client")
    parser.add_argument("mode", choices=["send", "receive"], help="Transfer mode: send or receive")
    parser.add_argument("--server", default="127.0.0.1", help="Server IP address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="TCP Server port (default: 5000)")
    parser.add_argument("--file", required=True, help="Path to file to send, or filename to receive")
    parser.add_argument("--scenario", default="standalone", help="Scenario label (e.g., Baseline, Delay-1)")
    parser.add_argument("--dest-dir", default="downloads", help="Directory for received files (default: downloads)")
    parser.add_argument("--results-file", default="results/transfers.jsonl", help="Results file path (default: results/transfers.jsonl)")
    parser.add_argument("--run-id", default=None, help="Optional 8-char Run ID (generated if not provided)")
    parser.add_argument("--progress-json", action="store_true", help="Output progress as JSON stream lines (~250ms)")
    args = parser.parse_args()

    try:
        run_transfer(
            mode=args.mode,
            server_ip=args.server,
            port=args.port,
            file_arg=args.file,
            scenario=args.scenario,
            dest_dir=args.dest_dir,
            results_file=args.results_file,
            run_id=args.run_id,
            progress_json=args.progress_json
        )
    except Exception as e:
        print(f"\n[ERROR] Transfer failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
