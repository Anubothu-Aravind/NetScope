"""
app/protocol.py — Re-exports common/protocol.py for backward compatibility.

The canonical implementation lives in common/protocol.py.
This shim exists so any code that does `from app.protocol import ...`
continues to work without changes.
"""
from common.protocol import (  # noqa: F401
    CHUNK_SIZE,
    HEADER_FORMAT,
    HEADER_SIZE,
    recv_exact,
    send_msg,
    recv_msg,
)
