"""
client/tcp_receiver.py - Standalone TCP Receiver for Client-to-Client File Transfers
"""

import os
import sys
import time
import json
import struct
import socket
import threading
from typing import Optional, Callable, Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from client.integrity import StreamHashValidator
from common.protocol import send_msg, recv_msg, recv_exact


class TCPReceiver:
    """
    Listens on a TCP port to directly receive a file from a paired sender client.
    Verifies SHA-256 integrity on-the-fly and sends back an acknowledgment.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 5000, save_dir: str = "downloads"):
        self.host = host
        self.port = port
        self.save_dir = save_dir
        os.makedirs(self.save_dir, exist_ok=True)
        self.server_sock: Optional[socket.socket] = None
        self._running = False

    def listen_once(self, timeout: Optional[float] = None, progress_cb: Optional[Callable] = None) -> Dict[str, Any]:
        """Listen for ONE incoming peer transfer, accept it, receive file, and return summary."""
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(1)
        if timeout:
            self.server_sock.settimeout(timeout)

        print(f"[RECEIVER] Listening on {self.host}:{self.port} for paired sender...")
        try:
            conn, addr = self.server_sock.accept()
        except socket.timeout:
            self.close()
            raise TimeoutError("Timed out waiting for sender connection.")

        print(f"[RECEIVER] Connection established from sender {addr[0]}:{addr[1]}")
        start_time = time.time()

        try:
            # 1. Read metadata header
            metadata = recv_msg(conn)
            if not metadata:
                raise ConnectionError("Connection closed before metadata header was received.")

            filename = os.path.basename(metadata.get("filename", "received.bin"))
            expected_size = metadata.get("size_bytes", 0)
            expected_sha256 = metadata.get("sha256", "")
            transfer_id = metadata.get("transfer_id", "T-001")
            pair_id = metadata.get("pair_id", "P-001")

            out_path = os.path.join(self.save_dir, filename)
            validator = StreamHashValidator(expected_hash=expected_sha256)

            bytes_received = 0
            last_report_time = time.time()

            with open(out_path, "wb") as out_f:
                while bytes_received < expected_size:
                    # Read 4-byte chunk length
                    raw_len = recv_exact(conn, 4)
                    if not raw_len:
                        break
                    chunk_len = struct.unpack("!I", raw_len)[0]
                    chunk = recv_exact(conn, chunk_len)
                    if not chunk:
                        break

                    out_f.write(chunk)
                    validator.update(chunk)
                    bytes_received += len(chunk)

                    now = time.time()
                    if progress_cb and (now - last_report_time >= 0.25 or bytes_received >= expected_size):
                        elapsed = max(now - start_time, 0.001)
                        mbps = (bytes_received * 8) / (elapsed * 1_000_000)
                        pct = round((bytes_received / expected_size) * 100, 1) if expected_size > 0 else 100.0
                        progress_cb({
                            "transfer_id": transfer_id,
                            "pair_id": pair_id,
                            "pct": pct,
                            "bytes": bytes_received,
                            "total_bytes": expected_size,
                            "mbps": round(mbps, 2)
                        })
                        last_report_time = now

            duration = max(time.time() - start_time, 0.001)
            sha256_match = validator.verify()
            actual_sha256 = validator.digest()
            throughput_mbps = (bytes_received * 8) / (duration * 1_000_000)

            # Send Acknowledgment back to sender
            ack = {
                "status": "COMPLETED" if sha256_match else "INTEGRITY_MISMATCH",
                "sha256_match": sha256_match,
                "bytes_received": bytes_received,
                "sha256": actual_sha256
            }
            send_msg(conn, ack)

            result = {
                "transfer_id": transfer_id,
                "pair_id": pair_id,
                "filename": filename,
                "path": out_path,
                "bytes_received": bytes_received,
                "expected_size": expected_size,
                "duration_s": round(duration, 4),
                "throughput_mbps": round(throughput_mbps, 2),
                "sha256_match": sha256_match,
                "sha256": actual_sha256,
                "peer_addr": f"{addr[0]}:{addr[1]}"
            }
            print(f"[RECEIVER] Transfer finished: {bytes_received} bytes in {duration:.3f}s ({throughput_mbps:.2f} Mbps) | SHA-256 OK: {sha256_match}")
            return result

        finally:
            conn.close()
            self.close()

    def close(self):
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None
