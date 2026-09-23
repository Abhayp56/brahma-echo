"""
actions/gods_eye.py — God's Eye View Planetary Intelligence Launcher

Manages the lifecycle of the local God's Eye View (Cesium 3D tactical globe)
application and brings it up on the user's desktop display.
"""

import os
import sys
import time
import socket
import logging
import subprocess
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("GodsEyeLauncher")

# Resolve path to gods-eye-view-main directory
_CURRENT_DIR = Path(__file__).resolve().parent
_BRAHMA_ROOT = _CURRENT_DIR.parent
_CANDIDATE_PATHS = [
    _BRAHMA_ROOT.parent / "gods-eye-view-main",
    _BRAHMA_ROOT / "gods-eye-view-main",
    Path("C:/Users/Asus/Desktop/Brahma-Echo-main/gods-eye-view-main"),
]

def _find_gods_eye_dir() -> Optional[Path]:
    for path in _CANDIDATE_PATHS:
        if path.exists() and (path / "package.json").exists():
            return path
    return None

def _is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if local server port is active and accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex((host, port)) == 0

def _get_active_url() -> Optional[str]:
    """Return URL if God's Eye View is already responding on standard ports."""
    for port in (4173, 5173, 3000):
        if _is_port_in_use(port):
            return f"http://localhost:{port}"
    return None

def _launch_browser(url: str) -> None:
    """Launch browser window, preferring Chrome standalone/app mode if installed."""
    chrome_candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    
    for chrome_path in chrome_candidates:
        if os.path.exists(chrome_path):
            try:
                # Launch Chrome in maximized tactical app mode
                subprocess.Popen(
                    [chrome_path, f"--app={url}", "--start-maximized"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
                logger.info(f"Opened God's Eye View in Chrome app mode: {url}")
                return
            except Exception as e:
                logger.warning(f"Could not launch Chrome app mode: {e}")
                break

    # Fallback to system default browser
    webbrowser.open(url)
    logger.info(f"Opened God's Eye View in default browser: {url}")

_SERVER_PROCESS = None

def launch_gods_eye(parameters: Optional[Dict[str, Any]] = None, player: Optional[Any] = None) -> Dict[str, Any]:
    """
    Launches God's Eye View.
    1. Checks if the server is already active on localhost:4173 or 5173.
    2. If not, spawns 'npm run dev' in the background.
    3. Opens browser display.
    """
    global _SERVER_PROCESS
    params = parameters or {}
    logger.info(f"Initiating God's Eye View launch (params={params})")
    if player and hasattr(player, "write_log"):
        player.write_log("🌐 Initializing God's Eye View Global Intelligence console...")

    project_dir = _find_gods_eye_dir()
    if not project_dir:
        msg = "God's Eye View project folder was not found on this computer."
        logger.error(msg)
        return {"success": False, "error": msg}

    target_url = _get_active_url()

    # If server is not yet running, start it
    if not target_url:
        logger.info(f"Starting God's Eye View dev server in {project_dir}...")
        try:
            # Use detached process flags on Windows so it runs persistently
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = (
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                )

            # Spawn npm run dev
            cmd = "npm.cmd run dev" if sys.platform == "win32" else "npm run dev"
            _SERVER_PROCESS = subprocess.Popen(
                cmd,
                cwd=str(project_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=creation_flags,
                shell=True,
            )

            # Wait up to 8 seconds for Vite to bind port 4173 or 5173
            start_wait = time.time()
            while time.time() - start_wait < 8.0:
                time.sleep(0.8)
                target_url = _get_active_url()
                if target_url:
                    break

            if not target_url:
                target_url = "http://localhost:4173"

        except Exception as exc:
            err = f"Failed to start God's Eye server: {exc}"
            logger.error(err)
            return {"success": False, "error": err}
    else:
        logger.info(f"God's Eye View is already active at {target_url}")

    # Launch browser window to the active interface
    _launch_browser(target_url)

    if player and hasattr(player, "write_log"):
        player.write_log(f"🟢 God's Eye View online at {target_url}")

    return {
        "success": True,
        "url": target_url,
        "message": f"Global Intelligence console is online at {target_url} and displayed on your screen, boss.",
    }

if __name__ == "__main__":
    res = launch_gods_eye()
    print("Result:", res)
