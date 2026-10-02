"""
app/server.py — Re-exports the FastAPI application from app/main.py.

The canonical server implementation is in app/main.py.
This shim exists so the spec-required path app/server.py resolves,
and so uvicorn can be launched as:
    uvicorn app.server:app
in addition to:
    uvicorn app.main:app
"""
from app.main import app  # noqa: F401
