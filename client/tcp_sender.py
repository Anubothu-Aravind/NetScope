"""
client/tcp_sender.py - Standalone TCP Sender for Client-to-Client File Transfers
"""

import os
import sys
import time
import json
import struct
import socket
from typing import Optional, Callable, Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from client.integrity import compute_file_sha256
from common.protocol import send_msg, recv_msg


class TCPSender:
    """Connects to a paired receiver client and directly streams a binary file."""

    def __init__(self, target_ip: str, target_port: int = 5000, chunk_size: int = 65536):
        self.target_ip = target_ip
        self.target_port = target_port
        self.chunk_size = chunk_size

    def send_file(
        self,
        filepath: str,
        transfer_id: str = "T-001",
        pair_id: str = "P-001",
        sender_name: str = "Sender",
        receiver_name: str = "Receiver",
        progress_cb: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Transmit the file over TCP with metadata and live progress tracking."""
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Source file not found: {filepath}")

        file_size = os.path.getsize(filepath)
        filename = os.path.basename(filepath)
        sha256_hash = compute_file_sha256(filepath)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        t_start_connect = time.time()
        print(f"[SENDER] Connecting to receiver at {self.target_ip}:{self.target_port}...")
        sock.connect((self.target_ip, self.target_port))
        connect_time_ms = round((time.time() - t_start_connect) * 1000, 2)
        print(f"[SENDER] Connected in {connect_time_ms} ms. Sending metadata...")

        # 1. Send metadata header
        metadata = {
            "transfer_id": transfer_id,
            "pair_id": pair_id,
            "filename": filename,
            "size_bytes": file_size,
            "sha256": sha256_hash,
            "sender": sender_name,
            "receiver": receiver_name
        }
        send_msg(sock, metadata)

        # 2. Stream file chunks
        bytes_sent = 0
        t_start_transfer = time.time()
        last_report_time = time.time()

        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(self.chunk_size)
                if not chunk:
                    break

                # Frame with 4-byte length prefix
                sock.sendall(struct.pack("!I", len(chunk)) + chunk)
                bytes_sent += len(chunk)

                now = time.time()
                if progress_cb and (now - last_report_time >= 0.25 or bytes_sent >= file_size):
                    elapsed = max(now - t_start_transfer, 0.001)
                    mbps = (bytes_sent * 8) / (elapsed * 1_000_000)
                    pct = round((bytes_sent / file_size) * 100, 1) if file_size > 0 else 100.0
                    progress_cb({
                        "transfer_id": transfer_id,
                        "pair_id": pair_id,
                        "pct": pct,
                        "bytes": bytes_sent,
                        "total_bytes": file_size,
                        "mbps": round(mbps, 2)
                    })
                    last_report_time = now

        transfer_duration = max(time.time() - t_start_transfer, 0.001)
        throughput_mbps = (bytes_sent * 8) / (transfer_duration * 1_000_000)

        # 3. Read Acknowledgment from receiver
        ack = recv_msg(sock)
        sock.close()

        if not ack:
            raise ConnectionError("Receiver closed connection without sending acknowledgment.")

        sha256_match = ack.get("sha256_match", False)

        result = {
            "transfer_id": transfer_id,
            "pair_id": pair_id,
            "filename": filename,
            "size_bytes": file_size,
            "bytes_sent": bytes_sent,
            "connect_time_ms": connect_time_ms,
            "transfer_time_s": round(transfer_duration, 4),
            "throughput_mbps": round(throughput_mbps, 2),
            "sha256_match": sha256_match,
            "receiver_ack": ack
        }
        print(f"[SENDER] Transfer complete: {bytes_sent} bytes in {transfer_duration:.3f}s ({throughput_mbps:.2f} Mbps) | SHA-256 match: {sha256_match}")
        return result
