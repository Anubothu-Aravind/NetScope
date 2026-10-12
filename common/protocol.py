"""
common/protocol.py - Shared TCP Framing and Control Protocol for NetScope.

Concept for Viva:
TCP is a byte-stream protocol without built-in message boundaries. If two messages
are sent close together, the receiver might get them in one chunk (concatenation),
or a single message might arrive split across multiple packets (fragmentation).
To solve this, NetScope uses Length-Prefixed Framing:
  [ 4-byte Header: Message Length (Big-Endian UInt32) ] + [ JSON Control Payload ]

For file data:
  Raw binary bytes are streamed immediately after control handshakes in 64 KB chunks.
"""

import os
import sys
import time
import json
import socket
import struct
import random
import hashlib
from typing import Optional, Tuple, Dict, Any, Callable

# Standard chunk size for high-throughput streaming (64 Kilobytes)
CHUNK_SIZE = 64 * 1024

# 4-byte big-endian unsigned integer format for struct
HEADER_FORMAT = ">I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


def get_default_port() -> int:
    """Return default NetScope TCP port (5000 on Linux, or 5001 if 5000 is occupied e.g. macOS AirPlay)."""
    env_port = os.environ.get("NETSCOPE_PORT")
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            pass
    preferred = 5001 if sys.platform == "darwin" else 5000
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", preferred))
            return preferred
        except OSError:
            return 5001 if preferred == 5000 else 5002


DEFAULT_PORT = get_default_port()


def parse_rate_bps(rate_str: Optional[str]) -> float:
    """Parse bandwidth rate string like '5mbit', '5Mbps', '1000kbit' into bits per second."""
    if not rate_str or str(rate_str).lower() in ("0", "none", "unlimited"):
        return 0.0
    r = str(rate_str).strip().lower()
    mult = 1.0
    if "gbit" in r or "gbps" in r:
        mult = 1_000_000_000.0
        r = r.replace("gbit", "").replace("gbps", "")
    elif "mbit" in r or "mbps" in r:
        mult = 1_000_000.0
        r = r.replace("mbit", "").replace("mbps", "")
    elif "kbit" in r or "kbps" in r:
        mult = 1_000.0
        r = r.replace("kbit", "").replace("kbps", "")
    try:
        return float(r.strip()) * mult
    except ValueError:
        return 0.0


def parse_delay_ms(delay_str: Optional[str]) -> float:
    """Parse latency string like '100ms', '0.1s', '50' into milliseconds."""
    if not delay_str or str(delay_str).lower() in ("0", "0ms", "none"):
        return 0.0
    d = str(delay_str).strip().lower()
    if d.endswith("ms"):
        try:
            return float(d[:-2])
        except ValueError:
            return 0.0
    elif d.endswith("s"):
        try:
            return float(d[:-1]) * 1000.0
        except ValueError:
            return 0.0
    try:
        return float(d)
    except ValueError:
        return 0.0


def parse_loss_pct(loss_str: Optional[str]) -> float:
    """Parse packet loss string like '2%', '0.02', '5' into percentage (0-100)."""
    if not loss_str or str(loss_str).lower() in ("0", "0%", "none"):
        return 0.0
    l = str(loss_str).strip().lower().replace("%", "")
    try:
        return float(l)
    except ValueError:
        return 0.0


def recv_exact(sock, n: int) -> bytes:
    """
    Read exactly n bytes from a TCP socket.
    Raises ConnectionError if the socket closes before n bytes are read.
    """
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError(f"Connection closed unexpectedly while expecting {n - len(buf)} more bytes.")
        buf.extend(chunk)
    return bytes(buf)


def send_msg(sock, msg: Dict[str, Any]) -> None:
    """
    Serialize a dictionary as JSON and send it with a 4-byte length prefix.
    """
    payload = json.dumps(msg).encode("utf-8")
    header = struct.pack(HEADER_FORMAT, len(payload))
    sock.sendall(header + payload)


def recv_msg(sock) -> Dict[str, Any]:
    """
    Read a 4-byte length prefix, then read the JSON payload and deserialize it.
    """
    header_bytes = recv_exact(sock, HEADER_SIZE)
    (msg_length,) = struct.unpack(HEADER_FORMAT, header_bytes)
    payload_bytes = recv_exact(sock, msg_length)
    return json.loads(payload_bytes.decode("utf-8"))


def send_file_stream(sock, file_path: str, file_size: int,
                     progress_cb: Optional[Callable[[int, int], None]] = None,
                     delay_ms: float = 0.0,
                     loss_pct: float = 0.0,
                     rate_bps: float = 0.0,
                     stats_cb: Optional[Callable[[Dict[str, Any]], None]] = None) -> str:
    """
    Stream a file as raw bytes over the socket in 64 KB chunks.
    Accurately emulates bandwidth limiting, delay, packet loss, RTO timers,
    and retransmissions with fine-grained pacing to keep UI responsive.
    Computes and returns the SHA-256 checksum of the transmitted data.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        data = f.read()

    try:
        if data.startswith(b"gAAAAA"):
            from server.tcp_server import ENCRYPTION_KEYS
            from cryptography.fernet import Fernet
            for k in list(ENCRYPTION_KEYS.values()):
                try:
                    data = Fernet(k).decrypt(data)
                    break
                except Exception:
                    pass
    except Exception:
        pass

    sent_total = 0
    actual_size = len(data)
    retransmissions = 0
    total_chunks = max((actual_size + CHUNK_SIZE - 1) // CHUNK_SIZE, 1)

    # Base RTT and CWND models
    base_rtt = max(delay_ms * 2.0, 1.0) if delay_ms > 0 else 2.5
    current_cwnd = 32
    ssthresh = 64
    MAX_RETRIES = 5

    # Initial connection propagation delay simulation (sliced to keep heartbeat responsive)
    if delay_ms > 0:
        rem_init_delay = (delay_ms / 1000.0)
        while rem_init_delay > 0:
            step = min(rem_init_delay, 0.05)
            time.sleep(step)
            rem_init_delay -= step
            if stats_cb:
                stats_cb({
                    "state": "Establishing connection (propagation delay)",
                    "pct": 0.0,
                    "bytes": 0,
                    "total_bytes": actual_size,
                    "rtt": round(base_rtt, 2),
                    "cwnd": current_cwnd,
                    "retransmissions": retransmissions,
                })

    t_start = time.perf_counter()
    chunk_idx = 0

    while sent_total < actual_size:
        chunk = data[sent_total:sent_total + CHUNK_SIZE]
        if not chunk:
            break

        chunk_idx += 1
        chunk_len = len(chunk)
        seq_num = sent_total + 1
        t_chunk_start = time.perf_counter()

        # 1. Packet Loss & Retransmission emulation with RTO timers and retry counts
        retry_count = 0
        while loss_pct > 0 and random.random() < (loss_pct / 100.0):
            retry_count += 1
            retransmissions += 1

            # Congestion window shrinks on loss / timeout event
            ssthresh = max(current_cwnd // 2, 4)
            current_cwnd = max(current_cwnd // 2, 4)

            # Calculate RTO timer (with exponential backoff for repeated timeouts)
            rto_delay = max(0.12, (base_rtt * 1.5 + 40.0) / 1000.0) * (2 ** min(retry_count - 1, 3))

            # A. Emit Packet Loss event (packet dropped in transit)
            if stats_cb:
                stats_cb({
                    "event": "packet_loss",
                    "seq": seq_num,
                    "len": chunk_len,
                    "chunk": chunk_idx,
                    "retry": retry_count,
                    "retransmissions": retransmissions,
                    "rto_ms": round(rto_delay * 1000.0, 1),
                    "state": f"Packet dropped in transit (Seq={seq_num}). RTO timer active.",
                    "bytes": sent_total,
                    "total_bytes": actual_size,
                    "cwnd": current_cwnd,
                    "rtt": round(base_rtt + random.uniform(1.0, 4.0), 2),
                })

            # B. Wait for RTO timer to expire in responsive non-blocking slices
            rem_rto = rto_delay
            while rem_rto > 0:
                step = min(rem_rto, 0.05)
                time.sleep(step)
                rem_rto -= step
                if stats_cb:
                    stats_cb({
                        "event": "timer_tick",
                        "seq": seq_num,
                        "retry": retry_count,
                        "retransmissions": retransmissions,
                        "state": f"RTO timer running ({round(rem_rto * 1000.0)}ms remaining)",
                        "bytes": sent_total,
                        "total_bytes": actual_size,
                    })

            # C. Timeout expired -> Trigger retransmission event
            if stats_cb:
                stats_cb({
                    "event": "timeout",
                    "seq": seq_num,
                    "len": chunk_len,
                    "chunk": chunk_idx,
                    "retry": retry_count,
                    "retransmissions": retransmissions,
                    "rto_ms": round(rto_delay * 1000.0, 1),
                    "state": f"RTO Timeout ({round(rto_delay * 1000.0, 1)}ms) expired. Retrying #{retry_count}.",
                    "bytes": sent_total,
                    "total_bytes": actual_size,
                    "cwnd": current_cwnd,
                })
                # Immediately emit retransmission segment event
                stats_cb({
                    "event": "retransmission",
                    "seq": seq_num,
                    "len": chunk_len,
                    "chunk": chunk_idx,
                    "retry": retry_count,
                    "retransmissions": retransmissions,
                    "state": f"Retrying transmission #{retry_count} for Seq={seq_num}",
                    "bytes": sent_total,
                    "total_bytes": actual_size,
                    "cwnd": current_cwnd,
                })

            if retry_count >= MAX_RETRIES:
                # Limit retries to prevent infinite loops under extreme drop rates
                break

        # Transmit the data bytes over TCP socket
        hasher.update(chunk)
        sock.sendall(chunk)
        sent_total += chunk_len

        # Window recovery / growth on successful transmission
        if current_cwnd < ssthresh:
            current_cwnd = min(current_cwnd + 2, 128)
        else:
            current_cwnd = min(current_cwnd + 1, 128)

        # 2. Bandwidth rate-limiting (pacing) with responsive sliced heartbeat ticks
        if rate_bps > 0:
            target_chunk_time = (chunk_len * 8.0) / rate_bps
            chunk_elapsed = time.perf_counter() - t_chunk_start
            sleep_needed = target_chunk_time - chunk_elapsed
            while sleep_needed > 0:
                step = min(sleep_needed, 0.05)
                time.sleep(step)
                sleep_needed -= step
                # Keep UI active with smooth partial movement even during high rate limiting
                partial_pct = round(((sent_total - chunk_len * max(sleep_needed / target_chunk_time, 0.0)) / actual_size) * 100.0, 1)
                if stats_cb:
                    stats_cb({
                        "event": "pacing",
                        "pct": min(max(partial_pct, 0.1), 99.9),
                        "bytes": sent_total,
                        "total_bytes": actual_size,
                        "mbps": round(rate_bps / 1_000_000.0, 2),
                        "state": f"Pacing bandwidth at {round(rate_bps / 1_000_000.0, 2)} Mbps",
                        "rtt": round(base_rtt, 2),
                        "cwnd": current_cwnd,
                        "retransmissions": retransmissions,
                    })

        # 3. Propagation micro-delay per chunk if configured
        if delay_ms > 0 and total_chunks > 1:
            per_chunk_delay = (delay_ms / 1000.0) / total_chunks
            time.sleep(per_chunk_delay)

        elapsed_total = max(time.perf_counter() - t_start, 0.001)
        instant_mbps = round((sent_total * 8.0) / (elapsed_total * 1_000_000.0), 2)
        if rate_bps > 0:
            instant_mbps = min(instant_mbps, round(rate_bps / 1_000_000.0, 2))

        # Measured/simulated RTT
        current_rtt = round(base_rtt + (random.uniform(-1.0, 2.0) if delay_ms > 0 else random.uniform(0.2, 1.5)), 2)

        if progress_cb:
            progress_cb(sent_total, actual_size)

        if stats_cb:
            sample_step = max(total_chunks // 100, 1)
            is_sample_chunk = (chunk_idx % sample_step == 0) or (chunk_idx == total_chunks) or (retry_count > 0)

            chunk_stats = {
                "pct": round((sent_total / actual_size) * 100.0, 1),
                "bytes": sent_total,
                "total_bytes": actual_size,
                "mbps": instant_mbps,
                "rtt": max(current_rtt, 1.0),
                "cwnd": max(current_cwnd, 4),
                "retransmissions": retransmissions,
                "retry": retry_count,
                "state": "Sending packets",
            }
            if is_sample_chunk:
                chunk_stats["event"] = "data_chunk"
                chunk_stats["seq"] = seq_num
                chunk_stats["len"] = chunk_len
                chunk_stats["chunk"] = chunk_idx

            stats_cb(chunk_stats)

    return hasher.hexdigest()


def recv_file_stream(sock, dest_path: str, file_size: int,
                     progress_cb: Optional[Callable[[int, int], None]] = None) -> str:
    """
    Receive exactly file_size raw bytes from the socket in 64 KB chunks,
    writing them directly to dest_path. Computes and returns the SHA-256 checksum.
    """
    hasher = hashlib.sha256()
    received_total = 0

    with open(dest_path, "wb") as f:
        while received_total < file_size:
            chunk_to_recv = min(CHUNK_SIZE, file_size - received_total)
            chunk = sock.recv(chunk_to_recv)
            if not chunk:
                raise ConnectionError(f"Socket closed prematurely after {received_total}/{file_size} bytes.")
            f.write(chunk)
            hasher.update(chunk)
            received_total += len(chunk)
            if progress_cb:
                progress_cb(received_total, file_size)

    return hasher.hexdigest()


def compute_sha256(file_path: str) -> str:
    """Compute the SHA-256 hash of a file on disk."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        data = f.read()

    try:
        if data.startswith(b"gAAAAA"):
            from server.tcp_server import ENCRYPTION_KEYS
            from cryptography.fernet import Fernet
            for k in list(ENCRYPTION_KEYS.values()):
                try:
                    decrypted = Fernet(k).decrypt(data)
                    return hashlib.sha256(decrypted).hexdigest()
                except Exception:
                    pass
    except Exception:
        pass

    hasher.update(data)
    return hasher.hexdigest()
