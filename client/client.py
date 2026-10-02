"""
client/client.py - Unified NetScope Client CLI for Peer-to-Peer TCP Transfers
"""

import os
import sys
import time
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from client.discovery import DiscoveryClient
from client.tcp_receiver import TCPReceiver
from client.tcp_sender import TCPSender


def main():
    parser = argparse.ArgumentParser(description="NetScope Client - Peer-to-Peer TCP File Transfer")
    parser.add_argument("--server", required=True, help="NetScope control plane server URL (e.g. http://192.168.1.20:8000)")
    parser.add_argument("--session", required=True, help="Session ID (e.g. NS-AB12CD)")
    parser.add_argument("--name", default=None, help="Client identifier name (e.g. Phone-A, Laptop-B)")
    parser.add_argument("--role", choices=["send", "receive"], required=True, help="Transfer role: 'send' or 'receive'")
    parser.add_argument("--file", default="tests/data/test_10mb.bin", help="File to send (only required if role is send)")
    parser.add_argument("--port", type=int, default=5000, help="TCP port for direct peer transfer (default: 5000)")
    parser.add_argument("--dest-dir", default="downloads", help="Destination directory for received file")
    args = parser.parse_args()

    client_name = args.name or f"Client-{os.getpid()}"
    discovery = DiscoveryClient(args.server)

    print("==========================================================")
    print(" NetScope Client - Direct Peer-to-Peer Transfer")
    print(f" Server:   {args.server}")
    print(f" Session:  {args.session}")
    print(f" Client:   {client_name}")
    print(f" Role:     {args.role.upper()}")
    print("==========================================================")

    # 1. Join Session
    print("[*] Registering with control plane...")
    join_res = discovery.join_session(args.session, client_name, args.role)
    client_id = join_res["client"]["client_id"]
    print(f"[✔] Registered as Client ID: {client_id}")

    # 2. Await pairing
    print("[*] Waiting for compatible peer to pair...")
    pair = discovery.poll_pairing(args.session, client_id, timeout=60.0)
    if not pair:
        print("[!] Timed out waiting for peer to pair.")
        sys.exit(1)

    pair_id = pair["pair_id"]
    print(f"\n[✔] PAIRED! Pair ID: {pair_id}")
    print(f"    Sender:   {pair['sender_name']} ({pair['sender_ip']})")
    print(f"    Receiver: {pair['receiver_name']} ({pair['receiver_ip']}:{pair['receiver_port']})")

    def on_progress(p):
        print(f"\r[PROGRESS] {p['pct']}% | {p['bytes']}/{p['total_bytes']} bytes | {p['mbps']} Mbps", end="", flush=True)
        discovery.report_progress(args.session, p)

    # 3. Execute Transfer
    if args.role == "receive":
        print(f"\n[*] Starting receiver on port {args.port}...")
        receiver = TCPReceiver(host="0.0.0.0", port=args.port, save_dir=args.dest_dir)
        try:
            res = receiver.listen_once(timeout=45.0, progress_cb=on_progress)
            print()
            discovery.report_complete(args.session, res)
            print(f"[✔] Received '{res['filename']}' ({res['bytes_received']} bytes) with SHA-256 match: {res['sha256_match']}")
        except Exception as e:
            print(f"\n[ERROR] Receive failed: {e}")
            sys.exit(1)
    else:
        # Sender
        target_ip = pair["receiver_ip"]
        target_port = pair.get("receiver_port", 5000)
        # In namespace or local testing, if target_ip is 0.0.0.0, use localhost
        if target_ip in ("0.0.0.0", ""):
            target_ip = "127.0.0.1"

        print(f"\n[*] Preparing to send '{args.file}' to {target_ip}:{target_port}...")
        time.sleep(0.5)  # brief pause for receiver socket bind
        sender = TCPSender(target_ip=target_ip, target_port=target_port)
        try:
            res = sender.send_file(
                filepath=args.file,
                transfer_id=f"T-{pair_id}",
                pair_id=pair_id,
                sender_name=client_name,
                receiver_name=pair["receiver_name"],
                progress_cb=on_progress
            )
            print()
            discovery.report_complete(args.session, res)
            print(f"[✔] Transfer complete: {res['throughput_mbps']} Mbps | SHA-256 match: {res['sha256_match']}")
        except Exception as e:
            print(f"\n[ERROR] Send failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
