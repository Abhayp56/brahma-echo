"""
actions/vision_operator.py — Autonomous Vision-Action Loop ("Computer Operator")

An Anthropic-style autonomous desktop agent that takes a high-level goal, looks at the screen
using Gemini Vision, determines UI coordinates, clicks, types, navigates, and verifies screen
updates in a multi-step loop until the objective is accomplished.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("VisionOperator")

BASE_DIR = Path(__file__).resolve().parent.parent
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

MODEL_OPERATOR = "gemini-2.5-flash"
DEFAULT_MAX_STEPS = 10
TARGET_IMG_WIDTH = 1280

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
    _PYAUTOGUI_OK = True
except ImportError:
    _PYAUTOGUI_OK = False

try:
    import mss
    _MSS_OK = True
except ImportError:
    _MSS_OK = False

try:
    import PIL.Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


def _get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key and API_CONFIG_PATH.exists():
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                key = cfg.get("gemini_api_key", "").strip()
        except Exception:
            pass
    return key


def _capture_screen() -> Tuple[Optional[bytes], int, int, float]:
    """
    Capture current screen and return (jpeg_bytes, img_width, img_height, scale_factor).
    Scale factor transforms image pixel coordinates to actual monitor screen coordinates.
    """
    if not _MSS_OK or not _PIL_OK or not _PYAUTOGUI_OK:
        logger.error("Missing required libraries: mss, pillow, or pyautogui.")
        return None, 0, 0, 1.0

    screen_w, screen_h = pyautogui.size()

    with mss.mss() as sct:
        # Capture primary monitor (monitors[1])
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        sct_img = sct.grab(monitor)
        img = PIL.Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

    orig_w, orig_h = img.size
    scale = 1.0

    if orig_w > TARGET_IMG_WIDTH:
        scale = orig_w / float(TARGET_IMG_WIDTH)
        new_h = int(orig_h / scale)
        img = img.resize((TARGET_IMG_WIDTH, new_h), PIL.Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return buf.getvalue(), img.width, img.height, (screen_w / float(img.width))


def _decide_next_step(
    goal: str,
    jpeg_bytes: bytes,
    img_w: int,
    img_h: int,
    step_num: int,
    max_steps: int,
    history: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Send screenshot and execution history to Gemini Vision to select next action."""
    api_key = _get_api_key()
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        history_str = "\n".join(
            f"Step {h.get('step')}: Action: {h.get('action')}, Result: {h.get('thought')}"
            for h in history
        ) if history else "No previous steps yet."

        prompt = f"""You are an autonomous GUI Computer Operator controlling a Windows laptop.
GOAL: {goal}

Current Step: {step_num} of {max_steps}
Action History So Far:
{history_str}

Attached is the current screenshot of the user's screen ({img_w}x{img_h} pixels).
Inspect the screenshot carefully, locate any relevant buttons, inputs, icons, or text, and decide the single best next action.

Available Actions:
- "click": Left click at pixel coordinates (requires "x", "y")
- "double_click": Double click at pixel coordinates (requires "x", "y")
- "right_click": Right click at pixel coordinates (requires "x", "y")
- "type": Type text at current cursor location (requires "text")
- "press": Press a keyboard key like "enter", "tab", "esc", "backspace" (requires "key")
- "hotkey": Key combination like "ctrl+t", "alt+f4", "ctrl+a", "ctrl+c", "ctrl+v" (requires "keys")
- "scroll": Scroll page (requires "direction": "up"|"down", "amount": 3)
- "wait": Wait 1-2 seconds for page or app to load (requires "seconds": 1.5)
- "open_app": Launch application via Windows Search (requires "app_name")
- "finish": Mark the goal as successfully completed (requires "summary")
- "fail": Mark as impossible or blocked (requires "summary")

Return ONLY a valid JSON object matching this exact schema (no markdown, no backticks):
{{
  "thought": "Concise reasoning of what you see on screen and what action to perform next",
  "action": "click | double_click | right_click | type | press | hotkey | scroll | wait | open_app | finish | fail",
  "x": 640,
  "y": 360,
  "text": "optional text to type",
  "key": "optional key name",
  "keys": "optional hotkey string",
  "direction": "down",
  "amount": 3,
  "seconds": 1.5,
  "app_name": "chrome",
  "summary": "final explanation if finish or fail"
}}
Coordinates (x, y) must strictly be within [0, {img_w}] and [0, {img_h}].
"""

        image_part = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")

        response = client.models.generate_content(
            model=MODEL_OPERATOR,
            contents=[prompt, image_part],
        )

        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?", "", raw).strip().rstrip("`").strip()
        data = json.loads(raw)
        return data

    except Exception as err:
        logger.warning(f"Vision decision failed on step {step_num}: {err}")
        return None


def _execute_gui_action(action_data: Dict[str, Any], coord_scale: float) -> str:
    """Execute the physical GUI action on Windows using PyAutoGUI."""
    if not _PYAUTOGUI_OK:
        return "PyAutoGUI is not installed."

    action = action_data.get("action", "").lower().strip()

    if action == "click":
        raw_x = action_data.get("x", 0)
        raw_y = action_data.get("y", 0)
        x = int(raw_x * coord_scale)
        y = int(raw_y * coord_scale)
        pyautogui.moveTo(x, y, duration=0.25)
        pyautogui.click()
        return f"Clicked at ({x}, {y})"

    elif action == "double_click":
        raw_x = action_data.get("x", 0)
        raw_y = action_data.get("y", 0)
        x = int(raw_x * coord_scale)
        y = int(raw_y * coord_scale)
        pyautogui.moveTo(x, y, duration=0.25)
        pyautogui.doubleClick()
        return f"Double-clicked at ({x}, {y})"

    elif action == "right_click":
        raw_x = action_data.get("x", 0)
        raw_y = action_data.get("y", 0)
        x = int(raw_x * coord_scale)
        y = int(raw_y * coord_scale)
        pyautogui.moveTo(x, y, duration=0.25)
        pyautogui.rightClick()
        return f"Right-clicked at ({x}, {y})"

    elif action == "type":
        text = str(action_data.get("text", ""))
        pyautogui.write(text, interval=0.03)
        return f"Typed '{text}'"

    elif action == "press":
        key = str(action_data.get("key", "enter")).lower()
        pyautogui.press(key)
        return f"Pressed key '{key}'"

    elif action == "hotkey":
        keys_str = str(action_data.get("keys", ""))
        keys = [k.strip().lower() for k in keys_str.split("+")]
        pyautogui.hotkey(*keys)
        return f"Triggered hotkey '{keys_str}'"

    elif action == "scroll":
        direction = action_data.get("direction", "down")
        amt = int(action_data.get("amount", 3))
        scroll_clicks = -amt * 120 if direction == "down" else amt * 120
        pyautogui.scroll(scroll_clicks)
        return f"Scrolled {direction} by {amt}"

    elif action == "wait":
        secs = min(float(action_data.get("seconds", 1.5)), 5.0)
        time.sleep(secs)
        return f"Waited {secs}s"

    elif action == "open_app":
        app_name = str(action_data.get("app_name", ""))
        pyautogui.press("win")
        time.sleep(0.4)
        pyautogui.write(app_name, interval=0.04)
        time.sleep(0.4)
        pyautogui.press("enter")
        time.sleep(2.0)
        return f"Opened application '{app_name}'"

    return f"Processed action '{action}'"


def autonomous_operator(
    parameters: Dict[str, Any],
    player: Optional[Any] = None,
    speak: Optional[Any] = None,
) -> str:
    """
    Main entry point for Autonomous Vision-Action Loop ("Computer Operator").

    parameters:
      goal (str, required): Natural language instruction to complete
      max_steps (int, optional): Max vision-action iterations (default: 10, max: 15)
      target_app (str, optional): App to focus or open first
    """
    params = parameters or {}
    goal = str(params.get("goal", "")).strip()
    max_steps = min(int(params.get("max_steps", DEFAULT_MAX_STEPS)), 15)
    target_app = params.get("target_app")

    if not goal:
        return "Error: No goal provided to autonomous_operator."

    if not _PYAUTOGUI_OK:
        return "Error: PyAutoGUI is not available on this laptop."

    logger.info(f"Starting Autonomous Vision-Action Loop for goal: '{goal}' (max {max_steps} steps)")
    if player:
        player.write_log(f"[Operator] Starting goal: {goal[:50]}...")

    # Optional pre-step: open target app if specified
    if target_app:
        if player:
            player.write_log(f"[Operator] Launching target app: {target_app}")
        pyautogui.press("win")
        time.sleep(0.4)
        pyautogui.write(target_app, interval=0.04)
        time.sleep(0.4)
        pyautogui.press("enter")
        time.sleep(2.0)

    history: List[Dict[str, Any]] = []

    for step in range(1, max_steps + 1):
        if player:
            player.write_log(f"[Operator] Step {step}/{max_steps}: Observing screen...")

        # 1. Capture screen
        jpeg_bytes, img_w, img_h, coord_scale = _capture_screen()
        if not jpeg_bytes:
            return "Error capturing screenshot for vision operator."

        # 2. Decide next action using Gemini Vision
        decision = _decide_next_step(goal, jpeg_bytes, img_w, img_h, step, max_steps, history)
        if not decision:
            logger.warning(f"Step {step}: No valid decision from Gemini.")
            time.sleep(1.0)
            continue

        thought = decision.get("thought", "")
        action = decision.get("action", "").lower().strip()
        summary = decision.get("summary", "")

        logger.info(f"Step {step}/{max_steps} -> Action: {action} | Thought: {thought}")

        # Check for completion or failure
        if action == "finish":
            final_msg = summary or thought or "Goal successfully completed."
            if player:
                player.write_log(f"[Operator] Completed: {final_msg[:50]}")
            return f"Autonomous Operator completed goal in {step} steps: {final_msg}"

        if action == "fail":
            fail_msg = summary or thought or "Could not accomplish goal."
            if player:
                player.write_log(f"[Operator] Failed: {fail_msg[:50]}")
            return f"Autonomous Operator stopped on step {step}: {fail_msg}"

        # 3. Execute action
        exec_desc = _execute_gui_action(decision, coord_scale)
        if player:
            player.write_log(f"[Operator] {exec_desc[:50]}")

        # Record to history
        history.append({
            "step": step,
            "action": action,
            "thought": thought,
            "exec": exec_desc,
        })

        # Settling pause for UI rendering
        time.sleep(0.8)

    # Reached step limit
    return (
        f"Autonomous Operator completed maximum {max_steps} steps for goal: '{goal}'.\n"
        f"Last action: {history[-1] if history else 'None'}.\n"
        f"Check your screen to verify current status."
    )
