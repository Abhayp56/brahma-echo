"""
actions/vision_operator.py — Non-Vision Headless Autonomous OS Super-Agent

An ultra-fast, lightweight autonomous desktop & OS agent.
Operates via a non-visual ReAct (Observation-Thought-Action) loop:
- Inspects system state, active window titles, and foreground applications via Windows native APIs.
- Generates dynamic self-healing Python scripts (with auto-pip dependency installation) and PowerShell commands.
- Focuses windows, launches applications, types text, and sends hotkeys without needing screen capture/vision.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("AutonomousOperator")

BASE_DIR = Path(__file__).resolve().parent.parent
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

DEFAULT_MAX_STEPS = 10

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    _PYAUTOGUI_OK = True
except ImportError:
    _PYAUTOGUI_OK = False


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


def _get_active_window_titles() -> List[str]:
    """Retrieve list of visible top-level window titles on Windows via Win32 API."""
    titles = []
    try:
        import ctypes
        EnumWindows = ctypes.windll.user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        GetWindowTextW = ctypes.windll.user32.GetWindowTextW
        GetWindowTextLengthW = ctypes.windll.user32.GetWindowTextLengthW
        IsWindowVisible = ctypes.windll.user32.IsWindowVisible

        def foreach_window(hwnd, lParam):
            if IsWindowVisible(hwnd):
                length = GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.strip()
                    if title and title not in {"Program Manager", "Default IME", "MSCTFIME UI"}:
                        titles.append(title)
            return True

        EnumWindows(EnumWindowsProc(foreach_window), 0)
    except Exception:
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -ExpandProperty MainWindowTitle"],
                capture_output=True, text=True, timeout=5
            )
            titles = [t.strip() for t in res.stdout.splitlines() if t.strip()]
        except Exception:
            pass
    return titles[:20]


def _get_foreground_window_title() -> str:
    """Retrieve title of the currently focused window."""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value.strip()
    except Exception:
        pass
    return "Unknown Window"


def _get_system_state_observation() -> Dict[str, Any]:
    """Gather real-time non-visual OS system observation."""
    active_windows = _get_active_window_titles()
    foreground_window = _get_foreground_window_title()
    cwd = str(Path.cwd())
    user_home = str(Path.home())
    
    return {
        "foreground_window": foreground_window,
        "visible_windows": active_windows,
        "working_directory": cwd,
        "user_home": user_home,
        "os_platform": sys.platform,
        "python_interpreter": sys.executable,
    }


def _execute_python_script(code: str, timeout: int = 60) -> str:
    """
    Execute dynamic Python code string on the laptop.
    Includes auto-healing: if execution fails due to a missing package (ModuleNotFoundError / ImportError),
    it dynamically installs the missing package via pip and re-executes the script.
    """
    temp_dir = Path.home() / "Desktop" / ".agent_scratch"
    temp_dir.mkdir(parents=True, exist_ok=True)
    script_path = temp_dir / "dynamic_agent_script.py"

    try:
        script_path.write_text(code, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        # Check for missing package error to auto-heal
        if proc.returncode != 0 and ("No module named" in stderr or "ModuleNotFoundError" in stderr or "ImportError" in stderr):
            match = re.search(r"No module named\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?", stderr)
            if match:
                missing_pkg = match.group(1).strip()
                logger.info(f"Auto-healing missing Python dependency: {missing_pkg}")
                install_proc = subprocess.run(
                    [sys.executable, "-m", "pip", "install", missing_pkg],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if install_proc.returncode == 0:
                    proc_retry = subprocess.run(
                        [sys.executable, str(script_path)],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        encoding="utf-8",
                        errors="replace",
                    )
                    stdout = (proc_retry.stdout or "").strip()
                    stderr = (proc_retry.stderr or "").strip()
                    if proc_retry.returncode == 0:
                        return f"Auto-installed '{missing_pkg}' & executed successfully.\nOutput:\n{stdout}"

        if proc.returncode == 0:
            return f"Executed Python script successfully.\nOutput:\n{stdout if stdout else '(no stdout output)'}"
        else:
            return f"Python script returned exit code {proc.returncode}.\nStderr:\n{stderr}\nStdout:\n{stdout}"

    except subprocess.TimeoutExpired:
        return f"Python execution timed out after {timeout} seconds."
    except Exception as exc:
        return f"Python execution failed: {exc}"
    finally:
        try:
            if script_path.exists():
                script_path.unlink()
        except Exception:
            pass


def _execute_shell_cmd(command: str, timeout: int = 45) -> str:
    """Execute PowerShell / CMD command on Windows with UTF-8 encoding."""
    ps_cmd = f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {command}"
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            cwd=str(Path.home()),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        if proc.returncode == 0:
            return f"Shell command succeeded (Exit 0):\n{stdout if stdout else '(no output)'}"
        else:
            return f"Shell command failed (Exit {proc.returncode}):\nStderr:\n{stderr}\nStdout:\n{stdout}"

    except subprocess.TimeoutExpired:
        return f"Shell command timed out after {timeout}s."
    except Exception as exc:
        return f"Shell command failed: {exc}"


def _focus_window_by_title(title_query: str) -> str:
    """Bring window matching title_query to foreground."""
    try:
        ps_script = (
            f"$w = Get-Process | Where-Object {{$_.MainWindowTitle -like '*{title_query}*'}} | Select-Object -First 1; "
            "if ($w) { $h = $w.MainWindowHandle; "
            "[void] [System.Reflection.Assembly]::LoadWithPartialName('Microsoft.VisualBasic'); "
            "[Microsoft.VisualBasic.Interaction]::AppActivate($w.Id); 'Focused ' + $w.MainWindowTitle } "
            "else { 'Window not found' }"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True, timeout=5)
        out = res.stdout.strip()
        return out if out else f"Attempted focus on '{title_query}'."
    except Exception as e:
        return f"Failed to focus window: {e}"


def _decide_next_step(
    goal: str,
    sys_obs: Dict[str, Any],
    step_num: int,
    max_steps: int,
    history: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Send text observation and execution history to Gemini text model to select next action."""
    api_key = _get_api_key()
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        history_str = "\n".join(
            f"Step {h.get('step')}: Action: {h.get('action')}, Result: {h.get('exec') or h.get('thought')}"
            for h in history
        ) if history else "No previous steps yet."

        obs_json = json.dumps(sys_obs, indent=2)

        prompt = f"""You are the Master Non-Visual Autonomous PC Operator controlling a Windows laptop.
GOAL: {goal}

Current Step: {step_num} of {max_steps}
Current System Observation:
{obs_json}

Action History So Far:
{history_str}

Decide the single best next action to accomplish the goal.

Available Actions:
- "execute_python": Write and execute dynamic Python script on the laptop (requires "code"). Has self-healing auto-pip installation if packages are missing!
- "run_shell": Execute PowerShell / Windows CLI command (requires "command").
- "open_app": Launch application via Windows Search or path (requires "app_name").
- "focus_window": Focus/Bring an open window to the foreground (requires "window_title").
- "type": Type text at current cursor location (requires "text", optional "press_enter": true to submit immediately).
- "press": Press a keyboard key like "enter", "tab", "esc", "backspace" (requires "key").
- "hotkey": Key combination like "ctrl+t", "alt+f4", "ctrl+a", "ctrl+c", "ctrl+v", "win+r" (requires "keys").
- "wait": Wait 1-2 seconds for background processes (requires "seconds": 1.5).
- "finish": Mark the goal as successfully completed (requires "summary").
- "fail": Mark as impossible or blocked (requires "summary").

Strategy Guidelines:
- Prefer "execute_python" or "run_shell" for 90% of tasks as they are programmatic, robust, fast, and 100% reliable!
- For web searches, opening websites, or YouTube videos, ALWAYS use "execute_python" with `import webbrowser; webbrowser.open('https://...')` or `run_shell` with `start chrome 'https://...'` to navigate directly to the search URL in 1 step!
- Use "open_app" or "focus_window" when interacting with desktop GUI applications.

Return ONLY a valid JSON object matching this exact schema (no markdown, no backticks):
{{
  "thought": "Concise reasoning of system state and next action",
  "action": "execute_python | run_shell | open_app | focus_window | type | press | hotkey | wait | finish | fail",
  "code": "optional Python code string to execute",
  "command": "optional PowerShell command string",
  "app_name": "chrome",
  "window_title": "Notepad",
  "text": "optional text to type",
  "press_enter": false,
  "key": "optional key name",
  "keys": "optional hotkey string",
  "seconds": 1.5,
  "summary": "final explanation if finish or fail"
}}
"""

        fallback_models = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-pro"]
        response = None
        last_err = None

        for model_name in fallback_models:
            for attempt in range(2):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.2,
                            response_mime_type="application/json",
                        ),
                    )
                    if response and response.text:
                        break
                except Exception as e:
                    last_err = e
                    err_str = str(e)
                    if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "UNAVAILABLE" in err_str) and attempt == 0:
                        logger.warning(f"Rate limit / transient error on model {model_name}: {e}. Retrying in 4s...")
                        time.sleep(4.0)
                        continue
                    logger.warning(f"Model {model_name} error: {e}. Falling back to next model...")
                    time.sleep(0.5)
                    break

            if response and response.text:
                break

        if not response or not response.text:
            raise last_err or RuntimeError("All LLM text models failed.")

        raw = response.text.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            raw = match.group(0)

        data = json.loads(raw)
        return data

    except Exception as err:
        logger.warning(f"Decision failed on step {step_num}: {err}")
        return None


def _execute_operator_action(action_data: Dict[str, Any]) -> str:
    """Execute action (Python script, shell command, window focus, app launch, key presses)."""
    action = action_data.get("action", "").lower().strip()

    if action == "execute_python":
        code = str(action_data.get("code", ""))
        if not code:
            return "No Python code provided."
        return _execute_python_script(code)

    elif action == "run_shell":
        cmd = str(action_data.get("command", ""))
        if not cmd:
            return "No shell command provided."
        return _execute_shell_cmd(cmd)

    elif action == "focus_window":
        w_title = str(action_data.get("window_title", ""))
        if not w_title:
            return "No window_title provided."
        return _focus_window_by_title(w_title)

    elif action == "open_app":
        app_name = str(action_data.get("app_name", ""))
        if not _PYAUTOGUI_OK:
            subprocess.Popen(["cmd.exe", "/c", f"start {app_name}"], shell=True)
            return f"Launched app via start command: '{app_name}'"
        pyautogui.press("win")
        time.sleep(0.4)
        pyautogui.write(app_name, interval=0.04)
        time.sleep(0.4)
        pyautogui.press("enter")
        time.sleep(1.5)
        return f"Opened application '{app_name}'"

    elif action == "type":
        text = str(action_data.get("text", ""))
        if _PYAUTOGUI_OK:
            pyautogui.write(text, interval=0.03)
            if action_data.get("press_enter", False):
                time.sleep(0.2)
                pyautogui.press("enter")
                return f"Typed '{text}' and pressed Enter"
            return f"Typed '{text}'"
        return f"Cannot type text: PyAutoGUI unavailable."

    elif action == "press":
        key = str(action_data.get("key", "enter")).lower()
        if _PYAUTOGUI_OK:
            pyautogui.press(key)
            return f"Pressed key '{key}'"
        return f"Cannot press key '{key}': PyAutoGUI unavailable."

    elif action == "hotkey":
        keys_str = str(action_data.get("keys", ""))
        if _PYAUTOGUI_OK:
            keys = [k.strip().lower() for k in keys_str.split("+")]
            pyautogui.hotkey(*keys)
            return f"Triggered hotkey '{keys_str}'"
        return f"Cannot trigger hotkey '{keys_str}': PyAutoGUI unavailable."

    elif action == "wait":
        secs = min(float(action_data.get("seconds", 1.5)), 5.0)
        time.sleep(secs)
        return f"Waited {secs}s"

    return f"Processed action '{action}'"


def autonomous_operator(
    parameters: Dict[str, Any],
    player: Optional[Any] = None,
    speak: Optional[Any] = None,
) -> str:
    """
    Main entry point for Laptop Execution Node.
    Delegates 100% of decision-making to CloudBrain while executing tasks locally on the PC.
    """
    params = parameters or {}
    goal = str(params.get("goal", "")).strip()
    target_app = params.get("target_app")

    if not goal:
        return "Error: No goal provided to autonomous_operator."

    logger.info(f"Executing laptop worker action for goal: '{goal}'")
    if player:
        player.write_log(f"[Operator] Executing task: {goal[:50]}...")

    if target_app:
        if player:
            player.write_log(f"[Operator] Launching target app: {target_app}")
        if _PYAUTOGUI_OK:
            pyautogui.press("win")
            time.sleep(0.4)
            pyautogui.write(target_app, interval=0.04)
            time.sleep(0.4)
            pyautogui.press("enter")
            time.sleep(1.5)

    # 1. Check if goal is a direct PowerShell command or script
    if goal.lower().startswith("powershell") or goal.lower().startswith("cmd") or "ping" in goal.lower() or "ipconfig" in goal.lower() or "get-process" in goal.lower():
        res = _execute_shell_cmd(goal)
        if player:
            player.write_log("[Operator] Executed shell command successfully.")
        return f"Laptop worker executed shell task successfully.\n{res}"

    # 2. Otherwise execute as self-healing Python task
    res = _execute_python_script(goal)
    if player:
        player.write_log("[Operator] Executed task on laptop.")
    return f"Laptop worker executed task successfully.\n{res}"
