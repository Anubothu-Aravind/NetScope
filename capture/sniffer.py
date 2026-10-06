#!/usr/bin/env python3
"""
capture/sniffer.py - Background tshark Sniffer for NetScope

Viva Concepts:
- Kernel-Level Packet Filtering (BPF):
    `tshark -f "tcp port 5000"` uses Berkeley Packet Filter (BPF) inside the Linux kernel.
    Only packets matching port 5000 are copied to userspace, reducing CPU overhead and drops.
- Clean Termination via SIGINT:
    Sending SIGINT (equivalent to Ctrl+C) instructs tshark to flush its internal packet buffers
    and write the final pcap headers before closing, avoiding corrupted capture files.
- Non-Root Packet Capture:
    Capturing on Linux typically requires root unless wireshark-common capabilities are enabled:
      sudo dpkg-reconfigure wireshark-common  # Select "Yes"
      sudo usermod -aG wireshark $USER
- Namespace Capture:
    When ns is set, tshark runs inside the namespace via `ip netns exec`. We must send SIGINT
    to the tshark process directly (using `sudo kill -INT <pid>`) because SIGINT sent to the
    outer sudo/nsrun wrapper does not propagate to the grandchild tshark process.
"""

import os
import sys
import re
import time
import signal
import argparse
import subprocess
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Sniffer:
    def __init__(self, iface: str = "veth-c", port: int = 5000,
                 out_path: str = "capture.pcap", ns: Optional[str] = None):
        self.iface = iface
        self.port = port
        self.out_path = os.path.abspath(out_path)
        self.ns = ns
        self.process: Optional[subprocess.Popen] = None
        self._tshark_pid: Optional[int] = None  # PID of tshark inside the namespace

    def _get_nsrun(self) -> str:
        """Return path to nsrun.sh, preferring the installed /opt version."""
        opt = "/opt/netscope/nsrun.sh"
        return opt if os.path.isfile(opt) else os.path.join(PROJECT_ROOT, "network", "nsrun.sh")

    def start(self) -> bool:
        """Launch tshark in background and wait until capture is active."""
        os.makedirs(os.path.dirname(self.out_path), exist_ok=True)

        # Remove existing file if present so tshark creates it freshly as root without
        # tripping Linux kernel fs.protected_regular security checks in world-writable dirs.
        try:
            if os.path.exists(self.out_path):
                os.remove(self.out_path)
        except OSError:
            pass

        tshark_cmd = [
            "tshark",
            "-i", self.iface,
            "-f", f"tcp port {self.port}",
            "-w", self.out_path,
        ]

        if self.ns:
            nsrun = self._get_nsrun()
            cmd = ["sudo", "-n", nsrun, self.ns] + tshark_cmd
            print(f"[SNIFFER] Starting capture inside namespace '[{self.ns}]' on '{self.iface}' "
                  f"for port {self.port}...")
        else:
            cmd = tshark_cmd
            print(f"[SNIFFER] Starting capture on '{self.iface}' for TCP port {self.port}...")

        print(f"[SNIFFER] Output PCAP: {self.out_path}")

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            print("[SNIFFER ERROR] 'tshark' is not installed. Install: sudo apt install -y tshark")
            self.process = None
            return False

        # Wait up to 3 s for tshark to signal "Capturing on …"
        started = False
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if self.process.poll() is not None:
                err = self.process.stderr.read() if self.process.stderr else ""
                print(f"[SNIFFER ERROR] tshark exited immediately: {err.strip()}")
                self.process = None
                return False

            line = self.process.stderr.readline() if self.process.stderr else ""
            if "Capturing on" in line:
                print(f"[SNIFFER] {line.strip()}")
                started = True
                break
            time.sleep(0.1)

        if not started:
            # Give it a little more time even if we didn't see the banner
            time.sleep(0.5)

        print("[SNIFFER] Capture active.\n")
        return True

    def _find_tshark_pid(self) -> Optional[int]:
        """
        Locate the tshark PID (running as root) so we can stop it via tshark_stop.sh.
        Match exact binary name tshark to avoid wrapper processes.
        """
        try:
            result = subprocess.run(
                ["pgrep", "-x", "tshark"],
                capture_output=True, text=True
            )
            pids = [int(p) for p in result.stdout.strip().splitlines() if p.strip().isdigit()]
            if pids:
                return pids[-1]
            return None
        except Exception:
            return None

    def _stop_script(self) -> str:
        """Return path to tshark_stop.sh, preferring the installed /opt version."""
        opt = "/opt/netscope/tshark_stop.sh"
        return opt if os.path.isfile(opt) else os.path.join(PROJECT_ROOT, "network", "tshark_stop.sh")

    def stop(self) -> Optional[str]:
        """
        Sleep 1 s for trailing packets to flush, send SIGINT to tshark, wait, and return pcap path.
        When running in a namespace, SIGINT is sent to the tshark PID directly via `sudo kill`.
        """
        if not self.process:
            return None

        print("[SNIFFER] Flushing trailing packets (1s)...")
        time.sleep(1.0)

        if self.process.poll() is None:
            if self.ns:
                # Use tshark_stop.sh (NOPASSWD in sudoers) to send SIGINT without a password
                pid = self._find_tshark_pid()
                stop_script = self._stop_script()
                if pid and os.path.isfile(stop_script):
                    print(f"[SNIFFER] Stopping tshark (PID {pid}) via {stop_script}...")
                    subprocess.run(["sudo", "-n", stop_script, str(pid)], check=False, timeout=3.0)
                else:
                    print(f"[SNIFFER] tshark PID/script not found; SIGINT to wrapper PID {self.process.pid}...")
                    self.process.send_signal(signal.SIGINT)
            else:
                print("[SNIFFER] Sending SIGINT to tshark...")
                self.process.send_signal(signal.SIGINT)

            try:
                self.process.communicate(timeout=4.0)
            except subprocess.TimeoutExpired:
                print("[SNIFFER WARNING] tshark did not exit in 4s. Terminating...")
                self.process.kill()
                self.process.communicate()

        # Give the OS a moment to flush the file
        time.sleep(0.5)

        if os.path.isfile(self.out_path):
            try:
                os.chmod(self.out_path, 0o666)
            except OSError:
                pass
            if self.ns:
                nsrun = self._get_nsrun()
                subprocess.run(["sudo", "-n", nsrun, self.ns, "chmod", "666", self.out_path], check=False)

        exists = os.path.isfile(self.out_path) and os.path.getsize(self.out_path) > 0
        if exists:
            print(f"[SNIFFER] Capture stopped. Saved to: {self.out_path} "
                  f"({os.path.getsize(self.out_path):,} bytes)")
        else:
            print(f"[SNIFFER] Capture stopped, but PCAP not found or empty: {self.out_path}")

        return self.out_path if exists else None


def main():
    parser = argparse.ArgumentParser(description="NetScope tshark Packet Sniffer")
    parser.add_argument("--iface", default="veth-c", help="Network interface (default: veth-c)")
    parser.add_argument("--port", type=int, default=5000, help="TCP port to filter (default: 5000)")
    parser.add_argument("--out", default="capture.pcap", help="Output PCAP file path")
    parser.add_argument("--ns", default=None, help="Optional network namespace (e.g. ns-client)")
    args = parser.parse_args()

    sniffer = Sniffer(iface=args.iface, port=args.port, out_path=args.out, ns=args.ns)
    if not sniffer.start():
        sys.exit(1)

    print("[*] Sniffer running. Press Ctrl+C to stop capture...")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[*] Stopping sniffer...")
    finally:
        sniffer.stop()


if __name__ == "__main__":
    main()
