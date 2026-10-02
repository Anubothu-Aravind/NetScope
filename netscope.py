#!/usr/bin/env python3
"""
netscope.py - Desktop Launcher for NetScope

Starts the FastAPI control backend on 127.0.0.1:8000 and launches
a dedicated desktop application window (1280x960) via Chrome/Chromium app mode,
falling back to xdg-open if Chrome is not installed.
"""

import os
import sys
import time
import shutil
import subprocess
import threading
import webbrowser

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

PORT = 8000
HOST = "0.0.0.0"
APP_URL = f"http://127.0.0.1:{PORT}"


def launch_browser():
    """Wait for server to bind, then launch dedicated 1280x960 app window."""
    time.sleep(1.0)
    print(f"\n[LAUNCHER] Opening NetScope desktop window ({APP_URL})...")

    # Check for Chrome/Chromium application mode
    chrome_bins = ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"]
    for b in chrome_bins:
        path = shutil.which(b)
        if path:
            try:
                subprocess.Popen([
                    path,
                    f"--app={APP_URL}",
                    "--window-size=1280,960",
                    "--user-data-dir=" + os.path.join(PROJECT_ROOT, ".chrome_app_profile")
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"[LAUNCHER] Started via {b} in native app mode.")
                return
            except Exception:
                pass

    # Fallback to xdg-open / default browser
    if shutil.which("xdg-open"):
        try:
            subprocess.Popen(["xdg-open", APP_URL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass

    webbrowser.open(APP_URL)


def main():
    print("==========================================================")
    print(" NetScope Control Center - Starting Desktop Application")
    print("==========================================================")

    # Spawn browser in separate background thread
    t = threading.Thread(target=launch_browser, daemon=True)
    t.start()

    # Start Uvicorn / FastAPI server
    try:
        import uvicorn
        uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="warning")
    except ImportError:
        print("[ERROR] uvicorn / fastapi not found in current environment.")
        print("        Ensure .venv is activated: source .venv/bin/activate")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[LAUNCHER] NetScope closed. Goodbye!")


if __name__ == "__main__":
    main()
