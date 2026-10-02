"""
app/tcp_client.py — Re-exports client/tcp_client.py for backward compatibility.

The canonical implementation lives in client/tcp_client.py.
This shim exists so the spec-required path app/tcp_client.py resolves.
"""
from client.tcp_client import run_transfer, log_result  # noqa: F401
