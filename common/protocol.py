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

import json
import struct
import hashlib
from typing import Optional, Tuple, Dict, Any, Callable

# Standard chunk size for high-throughput streaming (64 Kilobytes)
CHUNK_SIZE = 64 * 1024

# 4-byte big-endian unsigned integer format for struct
HEADER_FORMAT = ">I"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


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
                     progress_cb: Optional[Callable[[int, int], None]] = None) -> str:
    """
    Stream a file as raw bytes over the socket in 64 KB chunks.
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
    while sent_total < actual_size:
        chunk = data[sent_total:sent_total + CHUNK_SIZE]
        if not chunk:
            break
        hasher.update(chunk)
        sock.sendall(chunk)
        sent_total += len(chunk)
        if progress_cb:
            progress_cb(sent_total, actual_size)

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
