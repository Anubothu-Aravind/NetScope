"""
client/discovery.py - HTTP Client Discovery & Signaling Helper
"""

import time
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional


class DiscoveryClient:
    """Client-side helper for interacting with the NetScope Server Control Plane."""

    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip("/")

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.server_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, path: str) -> Dict[str, Any]:
        url = f"{self.server_url}{path}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def join_session(self, session_id: str, client_name: str, role: str = "unset") -> Dict[str, Any]:
        """Register device with the control plane."""
        return self._post(f"/api/session/{session_id}/clients", {
            "client_name": client_name,
            "role": role
        })

    def select_role(self, session_id: str, client_id: str, role: str) -> Dict[str, Any]:
        """Update role to SEND or RECEIVE."""
        return self._post(f"/api/session/{session_id}/role", {
            "client_id": client_id,
            "role": role
        })

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return self._get(f"/api/session/{session_id}")

    def poll_pairing(self, session_id: str, client_id: str, timeout: float = 30.0, interval: float = 0.5) -> Optional[Dict[str, Any]]:
        """Poll the server until a compatible peer is paired."""
        t_start = time.time()
        while time.time() - t_start < timeout:
            try:
                res = self._get(f"/api/session/{session_id}/pair?client_id={client_id}")
                if res.get("paired") and res.get("pair"):
                    return res["pair"]
            except Exception:
                pass
            time.sleep(interval)
        return None

    def report_progress(self, session_id: str, progress: Dict[str, Any]):
        try:
            self._post(f"/api/session/{session_id}/telemetry/progress", progress)
        except Exception:
            pass

    def report_complete(self, session_id: str, result: Dict[str, Any]):
        try:
            self._post(f"/api/session/{session_id}/telemetry/complete", result)
        except Exception:
            pass
