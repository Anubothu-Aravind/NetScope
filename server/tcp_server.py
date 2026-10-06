#!/usr/bin/env python3
"""
server/tcp_server.py - Multi-Threaded TCP Server for NetScope

Viva Concepts:
- Socket Lifecycle: socket() -> bind() -> listen() -> accept() -> close()
- Multi-threading: Each accepted TCP connection is dispatched to a worker thread,
  preventing one client's file transfer from blocking other connections.
- Port 5000: Chosen so standard Wireshark/tshark capture filters (`tcp.port == 5000`)
  track all data exchange.
- Throughput Calculation:
    Throughput (Mbps) = (Bytes Transferred * 8 bits/byte) / (Elapsed Time in seconds * 10^6)
"""

import os
import sys
import time
import socket
import argparse
import threading
import base64
import hashlib
from typing import Dict, Any

from cryptography.fernet import Fernet

# In-memory dictionary storing encryption keys by run_id
ENCRYPTION_KEYS: Dict[str, bytes] = {}

def get_fernet_key(run_id: str) -> bytes:
    """Derive a deterministic Fernet key (32 URL-safe base64 bytes) from run_id."""
    digest = hashlib.sha256(run_id.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)

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


class TCPServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 5000, storage_dir: str = "server_storage"):
        self.host = host
        self.port = port
        self.storage_dir = os.path.abspath(storage_dir)
        os.makedirs(self.storage_dir, exist_ok=True)
        self.server_sock = None
        self.is_running = False

    def start(self):
        """Bind to host:port and listen for incoming connections."""
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Enable SO_REUSEADDR so server can be restarted immediately without TIME_WAIT errors
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(10)
        self.is_running = True

        print(f"[SERVER] Listening on {self.host}:{self.port}")
        print(f"[SERVER] Storage directory: {self.storage_dir}")
        print("[SERVER] Ready for incoming TCP file transfer sessions...\n")

        try:
            while self.is_running:
                try:
                    conn, addr = self.server_sock.accept()
                except OSError:
                    break  # Socket closed during shutdown
                thread = threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True)
                thread.start()
        except KeyboardInterrupt:
            print("\n[SERVER] Shutting down server...")
        finally:
            self.stop()

    def stop(self):
        """Stop listening and close server socket."""
        self.is_running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
        print("[SERVER] Server stopped.")

    def _handle_client(self, conn: socket.socket, addr):
        """Worker thread executing the NetScope transfer protocol for one client."""
        client_ip, client_port = addr
        print(f"[+] Connection accepted from {client_ip}:{client_port}")

        try:
            while True:
                try:
                    msg = recv_msg(conn)
                except ConnectionError:
                    print(f"[-] Client {client_ip}:{client_port} disconnected.")
                    break
                except Exception as e:
                    print(f"[!] Protocol error reading from {client_ip}:{client_port}: {e}")
                    break

                msg_type = msg.get("type")

                # 1. HELLO handshake
                if msg_type == "HELLO":
                    print(f"[*] HELLO from {client_ip}:{client_port} (Client ID: {msg.get('client_name')})")
                    send_msg(conn, {
                        "type": "HELLO",
                        "server": "NetScope-Server",
                        "status": "OK"
                    })

                # 2. LIST available files in storage directory
                elif msg_type == "LIST":
                    files = [f for f in os.listdir(self.storage_dir) if os.path.isfile(os.path.join(self.storage_dir, f))]
                    send_msg(conn, {
                        "type": "LIST_REPLY",
                        "files": files
                    })

                # 3. Client wants to SEND a file to server (Server receives & stores)
                elif msg_type == "SEND_REQUEST":
                    self._handle_client_send(conn, addr, msg)

                # 4. Client wants to RECEIVE a file from server (Server streams to client)
                elif msg_type == "RECV_REQUEST":
                    self._handle_client_recv(conn, addr, msg)

                else:
                    send_msg(conn, {
                        "type": "ERROR",
                        "message": f"Unknown message type: {msg_type}"
                    })

        finally:
            conn.close()

    def _handle_client_send(self, conn: socket.socket, addr, req: Dict[str, Any]):
        """Handle client uploading a file to this server."""
        filename = os.path.basename(req.get("name", "uploaded.bin"))
        file_size = int(req.get("size", 0))
        expected_sha256 = req.get("sha256", "").lower()
        dest_path = os.path.join(self.storage_dir, filename)

        print(f"[*] Incoming SEND_REQUEST: file='{filename}', size={file_size} bytes ({file_size / (1024*1024):.2f} MB)")
        # Acknowledge that server is ready to receive raw bytes
        send_msg(conn, {"type": "READY"})

        start_time = time.perf_counter()
        try:
            actual_sha256 = recv_file_stream(conn, dest_path, file_size)
            duration_s = max(time.perf_counter() - start_time, 1e-6)
            sha256_ok = (actual_sha256.lower() == expected_sha256)

            throughput_mbps = (file_size * 8) / (duration_s * 1_000_000)

            print(f"[✔] Upload complete: {filename}")
            print(f"    - Duration:   {duration_s:.3f} s")
            print(f"    - Throughput: {throughput_mbps:.2f} Mbps")
            print(f"    - SHA-256 match: {sha256_ok} ({actual_sha256[:12]}...)")

            # Encrypt file in place using Fernet key derived from run_id
            run_id = req.get("run_id")
            if run_id:
                try:
                    fkey = get_fernet_key(run_id)
                    ENCRYPTION_KEYS[run_id] = fkey
                    cipher = Fernet(fkey)
                    with open(dest_path, "rb") as f:
                        plaintext_data = f.read()
                    ciphertext_data = cipher.encrypt(plaintext_data)
                    with open(dest_path, "wb") as f:
                        f.write(ciphertext_data)
                    print(f"    - Encrypted in place with Fernet (run_id: {run_id})")
                except Exception as enc_err:
                    print(f"[!] Warning: failed to encrypt file: {enc_err}")

            send_msg(conn, {
                "type": "DONE",
                "sha256_ok": sha256_ok,
                "server_sha256": actual_sha256,
                "duration_s": round(duration_s, 4),
                "throughput_mbps": round(throughput_mbps, 2)
            })
        except Exception as e:
            print(f"[!] Error receiving file '{filename}': {e}")
            try:
                send_msg(conn, {"type": "ERROR", "message": str(e)})
            except Exception:
                pass

    def _handle_client_recv(self, conn: socket.socket, addr, req: Dict[str, Any]):
        """Handle client requesting to download a file from this server."""
        filename = os.path.basename(req.get("name", ""))
        target_path = os.path.join(self.storage_dir, filename)

        if not os.path.isfile(target_path):
            print(f"[!] File not found: '{filename}'")
            send_msg(conn, {
                "type": "ERROR",
                "message": f"File '{filename}' does not exist on server."
            })
            return

        with open(target_path, "rb") as f:
            raw_data = f.read()

        file_size = len(raw_data)
        try:
            if raw_data.startswith(b"gAAAAA"):
                for k in list(ENCRYPTION_KEYS.values()):
                    try:
                        decrypted = Fernet(k).decrypt(raw_data)
                        file_size = len(decrypted)
                        break
                    except Exception:
                        pass
        except Exception:
            pass

        sha256_hash = compute_sha256(target_path)

        print(f"[*] Preparing RECV_REQUEST: file='{filename}', size={file_size} bytes ({file_size / (1024*1024):.2f} MB)")
        # Inform client about file attributes
        send_msg(conn, {
            "type": "READY",
            "name": filename,
            "size": file_size,
            "sha256": sha256_hash
        })

        start_time = time.perf_counter()
        actual_sha256 = send_file_stream(conn, target_path, file_size)
        duration_s = max(time.perf_counter() - start_time, 1e-6)
        throughput_mbps = (file_size * 8) / (duration_s * 1_000_000)

        # Wait for client confirmation DONE
        try:
            done_msg = recv_msg(conn)
            client_sha256_ok = done_msg.get("sha256_ok", False)
        except Exception:
            client_sha256_ok = False

        print(f"[✔] Stream complete: {filename}")
        print(f"    - Duration:        {duration_s:.3f} s")
        print(f"    - Throughput:      {throughput_mbps:.2f} Mbps")
        print(f"    - Client SHA-256:  {client_sha256_ok}")


def main():
    parser = argparse.ArgumentParser(description="NetScope TCP File Transfer Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="TCP port to listen on (default: 5000)")
    parser.add_argument("--storage-dir", default="server_storage", help="Directory where files are stored")
    args = parser.parse_args()

    server = TCPServer(host=args.host, port=args.port, storage_dir=args.storage_dir)
    server.start()


if __name__ == "__main__":
    main()
