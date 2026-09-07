"""
actions/terminal_agent.py — Self-Healing PowerShell & Terminal Engineer

Executes PowerShell, Command Prompt, and system CLI commands on the local Windows laptop.
Equipped with an autonomous diagnostic engine: if a command fails, it analyzes the error
stack trace using Gemini, generates remediation commands (package install, service restart,
syntax repair), executes the fix, and re-runs the original command automatically.
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

logger = logging.getLogger("TerminalAgent")

BASE_DIR = Path(__file__).resolve().parent.parent
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

MODEL_DIAGNOSTIC = "gemini-2.5-flash"
MAX_HEAL_ATTEMPTS = 2
DEFAULT_TIMEOUT = 45

# Safety guardrails: commands that could wipe data or break the operating system
DANGEROUS_PATTERNS = [
    r"\bformat\s+[a-z]:",
    r"\bdiskpart\b",
    r"rmdir\s+/[sq]\s+[a-z]:\\",
    r"del\s+/[sqfa]\s+[a-z]:\\",
    r"remove-item\s+.*-recurse.*[a-z]:\\(windows|system32)",
    r"\bformat-volume\b",
    r"\bcd\s+[a-z]:\\windows\\system32\b",
]


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


def _is_dangerous(command: str) -> bool:
    cmd_lower = command.lower().strip()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_lower):
            return True
    return False


def _run_shell(
    command: str,
    working_dir: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    shell_type: str = "powershell",
) -> tuple[int, str, str]:
    """Execute command via PowerShell or CMD and return (exit_code, stdout, stderr)."""
    cwd = working_dir if (working_dir and Path(working_dir).exists()) else str(Path.home())

    if shell_type.lower() == "cmd":
        args = ["cmd.exe", "/c", command]
    else:
        # PowerShell with UTF-8 encoding output
        ps_cmd = f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {command}"
        args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]

    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout} seconds."
    except Exception as exc:
        return -1, "", f"Execution error: {exc}"


def _diagnose_and_heal(
    command: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    working_dir: str,
) -> Optional[Dict[str, Any]]:
    """Use Gemini to diagnose root cause and recommend self-healing commands."""
    api_key = _get_api_key()
    if not api_key:
        return None

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        prompt = f"""You are an expert Windows Systems and PowerShell Engineer.
A terminal command failed on a Windows 10/11 system.

WORKING DIRECTORY: {working_dir}
COMMAND: {command}
EXIT CODE: {exit_code}
STDOUT:
{stdout[:1500]}
STDERR:
{stderr[:1500]}

Your task is to diagnose the root cause and propose an automated self-healing fix.
Examples of common fixes:
- Missing Python package -> ["pip install <package>"]
- Missing CLI tool -> ["winget install <tool> --accept-source-agreements --accept-package-agreements"]
- Wrong PowerShell syntax or parameter -> fix the command syntax
- Port conflict -> find and kill process or use alternate port
- Missing directory -> ["mkdir <path>"]

Return ONLY a valid JSON object in this exact schema (no markdown, no backticks):
{{
  "diagnosis": "Short explanation of why it failed",
  "can_fix": true,
  "fix_commands": ["list of exact commands to run sequentially to fix the problem"],
  "retry_command": "the command to run after the fix (either corrected command or original command)"
}}
If it cannot be fixed automatically or requires manual user login/credentials, set "can_fix": false and "fix_commands": [].
"""

        response = client.models.generate_content(
            model=MODEL_DIAGNOSTIC,
            contents=prompt,
        )

        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?", "", raw).strip().rstrip("`").strip()
        data = json.loads(raw)
        return data

    except Exception as err:
        logger.warning(f"Diagnosis failed: {err}")
        return None


def terminal_agent(
    parameters: Dict[str, Any],
    player: Optional[Any] = None,
    speak: Optional[Any] = None,
) -> str:
    """
    Main entry point for the Self-Healing PowerShell & Terminal Engineer tool.

    parameters:
      command (str, required): Shell command or instruction to execute
      working_dir (str, optional): Target folder path
      auto_heal (bool, optional): Enable AI diagnostic self-healing loop (default: True)
      shell (str, optional): 'powershell' (default) or 'cmd'
      timeout (int, optional): Max execution time in seconds (default: 45)
    """
    params = parameters or {}
    command = str(params.get("command", "")).strip()
    working_dir = params.get("working_dir") or str(Path.home())
    auto_heal = bool(params.get("auto_heal", True))
    shell = params.get("shell", "powershell").lower()
    timeout = int(params.get("timeout", DEFAULT_TIMEOUT))

    if not command:
        return "Error: No command provided to terminal_agent."

    if _is_dangerous(command):
        return f"Blocked: Command '{command}' was rejected by safety guardrails."

    if player:
        player.write_log(f"[Terminal] Running: {command[:60]}...")

    logger.info(f"Running terminal command: '{command}' in {working_dir}")
    exit_code, stdout, stderr = _run_shell(command, working_dir, timeout, shell)

    if exit_code == 0:
        output = stdout if stdout else "(Command executed successfully with no output)"
        if player:
            player.write_log("[Terminal] Success")
        return output

    # Command failed
    error_summary = stderr if stderr else stdout
    logger.warning(f"Command failed (exit {exit_code}): {error_summary[:200]}")

    if not auto_heal:
        return f"Command failed with exit code {exit_code}:\n{error_summary}"

    # Self-Healing Execution Loop
    history_fixes = []
    current_cmd = command

    for attempt in range(1, MAX_HEAL_ATTEMPTS + 1):
        if player:
            player.write_log(f"[Terminal] Self-Healing attempt {attempt}/{MAX_HEAL_ATTEMPTS}...")

        logger.info(f"Self-healing attempt {attempt} for: '{current_cmd}'")
        diagnosis_data = _diagnose_and_heal(current_cmd, exit_code, stdout, stderr, working_dir)

        if not diagnosis_data or not diagnosis_data.get("can_fix"):
            diag_text = diagnosis_data.get("diagnosis") if diagnosis_data else "Unknown error"
            return f"Command failed (exit {exit_code}):\n{error_summary}\n\nDiagnosis: {diag_text}"

        diagnosis = diagnosis_data.get("diagnosis", "")
        fix_commands = diagnosis_data.get("fix_commands", [])
        retry_command = diagnosis_data.get("retry_command", current_cmd)

        logger.info(f"Diagnosis: {diagnosis} | Fixes: {fix_commands}")

        # Execute remediation commands
        for fix_cmd in fix_commands:
            if _is_dangerous(fix_cmd):
                continue
            if player:
                player.write_log(f"[Fix] {fix_cmd[:50]}")
            f_code, f_out, f_err = _run_shell(fix_cmd, working_dir, timeout=60, shell_type=shell)
            history_fixes.append(f"{fix_cmd} (exit {f_code})")
            time.sleep(0.5)

        # Retry original or corrected command
        current_cmd = retry_command
        exit_code, stdout, stderr = _run_shell(current_cmd, working_dir, timeout, shell)

        if exit_code == 0:
            success_output = stdout if stdout else "(Command succeeded after fix)"
            fixes_str = " -> ".join(history_fixes)
            result_msg = (
                f"[Self-Healed Successfully]\n"
                f"Root Cause: {diagnosis}\n"
                f"Remediation Applied: {fixes_str}\n"
                f"Final Command: {current_cmd}\n\n"
                f"Output:\n{success_output}"
            )
            if player:
                player.write_log("[Terminal] Healed and completed!")
            return result_msg

        error_summary = stderr if stderr else stdout

    # If all heal attempts failed
    return (
        f"Command failed after {MAX_HEAL_ATTEMPTS} self-healing attempts.\n"
        f"Last Command: {current_cmd}\n"
        f"Exit Code: {exit_code}\n"
        f"Error Output:\n{error_summary}\n"
        f"Attempted Fixes: {history_fixes}"
    )
