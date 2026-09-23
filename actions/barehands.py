"""
actions/barehands.py — Barehands Touchless Holographic Workspace Launcher

Manages the lifecycle of the local Barehands webcam hand-tracking interface,
allows JARVIS to stage holographic cards/models, and syncs JARVIS AI states
with the on-screen glowing pulse ring.
"""

import os
import sys
import json
import time
import socket
import logging
import subprocess
import webbrowser
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("BarehandsLauncher")

_CURRENT_DIR = Path(__file__).resolve().parent
_BRAHMA_ROOT = _CURRENT_DIR.parent
_CANDIDATE_PATHS = [
    _BRAHMA_ROOT.parent / "barehands-main",
    _BRAHMA_ROOT / "barehands-main",
    Path("C:/Users/Asus/Desktop/Brahma-Echo-main/barehands-main"),
]

_SERVER_PROCESS = None
BAREHANDS_PORT = 8794
BAREHANDS_URL = f"http://127.0.0.1:{BAREHANDS_PORT}/stage.html"
CMD_ENDPOINT = f"http://127.0.0.1:{BAREHANDS_PORT}/cmd"


def _find_barehands_dir() -> Optional[Path]:
    for path in _CANDIDATE_PATHS:
        if path.exists() and (path / "stage.html").exists():
            return path
    return None


def _is_server_running(port: int = BAREHANDS_PORT, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def set_ring_state(state: str) -> bool:
    """Update on-screen reactive ring state (idle, listening, thinking, speaking)."""
    barehands_dir = _find_barehands_dir()
    if not barehands_dir:
        return False
    state_file = barehands_dir / "state" / "state"
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(state.strip().lower() + "\n", encoding="utf-8")
        return True
    except Exception as exc:
        logger.debug(f"Failed to write barehands state: {exc}")
        return False


def stage_item(action: str = "present", title: str = "", body: str = "", src: Optional[str] = None) -> Dict[str, Any]:
    """
    Sends a staging command to the active Barehands glass board.
    Supported actions: 'present', 'add_card', 'clear', 'reset', 'explode', 'assemble'
    """
    if not _is_server_running():
        return {"success": False, "error": "Barehands server is not currently running"}

    payload: Dict[str, Any] = {"a": action}
    if title:
        payload["title"] = str(title)
    if body:
        payload["body"] = str(body)
    if src:
        payload["src"] = str(src)

    try:
        req = urllib.request.Request(
            CMD_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return {"success": resp.status in (200, 204), "action": action}
    except Exception as exc:
        logger.warning(f"Could not stage item to Barehands board: {exc}")
        return {"success": False, "error": str(exc)}


def _launch_browser(url: str) -> None:
    """Launch browser, preferring Chrome standalone app mode for clean holographic HUD."""
    chrome_candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for chrome_path in chrome_candidates:
        if os.path.exists(chrome_path):
            try:
                subprocess.Popen(
                    [chrome_path, f"--app={url}", "--start-maximized"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
                logger.info(f"Opened Barehands in Chrome app mode: {url}")
                return
            except Exception as e:
                logger.warning(f"Could not launch Chrome app mode: {e}")
                break

    webbrowser.open(url)
    logger.info(f"Opened Barehands in default browser: {url}")


def launch_barehands(parameters: Optional[Dict[str, Any]] = None, player: Optional[Any] = None) -> Dict[str, Any]:
    """
    Launches Barehands holographic glass board.
    1. Checks if server.py is running on port 8794.
    2. If offline, spawns python server.py in the background.
    3. Opens Chrome to stage.html.
    4. Optionally presents an initial card if specified.
    """
    global _SERVER_PROCESS
    params = parameters or {}
    logger.info(f"Initiating Barehands launch (params={params})")

    if player and hasattr(player, "write_log"):
        player.write_log("🖐️ Initializing Barehands Holographic Workspace...")

    project_dir = _find_barehands_dir()
    if not project_dir:
        msg = "Barehands project folder was not found on this computer."
        logger.error(msg)
        return {"success": False, "error": msg}

    # Start server if not running
    if not _is_server_running():
        logger.info(f"Starting Barehands server in {project_dir}...")
        try:
            python_exe = sys.executable or "python"
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)

            _SERVER_PROCESS = subprocess.Popen(
                [python_exe, "server.py"],
                cwd=str(project_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=creation_flags,
            )

            # Wait up to 5 seconds for port to open
            start_wait = time.time()
            while time.time() - start_wait < 5.0:
                time.sleep(0.4)
                if _is_server_running():
                    break

        except Exception as exc:
            err = f"Failed to start Barehands server: {exc}"
            logger.error(err)
            return {"success": False, "error": err}
    else:
        logger.info("Barehands server is already active.")

    # Set initial ring state
    set_ring_state("listening")

    # Launch browser window
    _launch_browser(BAREHANDS_URL)

    # If the user asked to present a specific card/topic, push it to the board
    card_title = params.get("card_title") or params.get("title") or ""
    card_body = params.get("card_body") or params.get("body") or ""
    if card_title or card_body or params.get("present_card"):
        time.sleep(1.5)  # allow browser page to load tracker
        stage_item(
            action="present",
            title=card_title or "TACTICAL INTEL",
            body=card_body or "Holographic workspace online.",
        )

    if player and hasattr(player, "write_log"):
        player.write_log(f"🟢 Barehands online at {BAREHANDS_URL}")

    return {
        "success": True,
        "url": BAREHANDS_URL,
        "message": f"Holographic glass board is now online at {BAREHANDS_URL} and displayed on your screen, boss.",
    }


if __name__ == "__main__":
    res = launch_barehands()
    print("Result:", res)
