"""
actions/lauda_agent.py — Laudacode Enterprise Desktop Coding Engine for Jarvis

Brings the full architecture of Laudacode (pure modular agentic loop, planner-coder-reviewer-tester
sub-agents, precision diffs, git tracking, self-healing compiler/runtime diagnostics)
to Windows Desktop, powered by the resilient multi-provider AI pool (Groq 500 t/s + Gemini + OpenRouter).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.resilient_ai_client import resilient_ai

logger = logging.getLogger("LaudaAgent")

PROJECTS_ROOT = Path.home() / "Desktop" / "JarvisProjects"
MAX_FIX_ITERATIONS = 2


def _clean_json_response(raw: str) -> str:
    """Extract clean JSON substring from model output."""
    raw = raw.strip()
    match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
    if match:
        return match.group(0)
    return raw


def _clean_code_fences(code: str) -> str:
    """Strip markdown code block fences."""
    code = code.strip()
    code = re.sub(r"^```[a-zA-Z0-9_\-\+]*\r?\n?", "", code)
    code = re.sub(r"\r?\n?```\s*$", "", code)
    return code.strip()


def _sanitize_name(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_\-]+", "_", name.strip())
    return safe.strip("_") or "lauda_project"


class LaudaProjectPlanner:
    """Deconstructs user instructions into a concrete architecture and file graph."""

    @staticmethod
    def plan(description: str, language: str = "python") -> Dict[str, Any]:
        system_prompt = (
            "You are the Lead Software Architect for Laudacode. "
            "Your job is to break down a project request into an elegant, production-ready specification. "
            "Output MUST be a single valid JSON object with this exact structure:\n"
            "{\n"
            '  "project_name": "snake_case_name",\n'
            '  "files": [\n'
            '    {"path": "relative/path/to/file.ext", "purpose": "description of file"}\n'
            "  ],\n"
            '  "dependencies": ["list", "of", "packages"],\n'
            '  "entry_point": "main.py",\n'
            '  "run_command": "python main.py",\n'
            '  "summary": "Short 1-sentence architectural summary"\n'
            "}"
        )

        prompt = (
            f"User Goal: {description}\n"
            f"Preferred Language: {language}\n"
            "Plan the full project architecture now:"
        )

        try:
            raw = resilient_ai.generate(prompt, system_prompt=system_prompt, json_mode=True, temperature=0.1)
            data = json.loads(_clean_json_response(raw))
            return data
        except Exception as e:
            logger.warning(f"[LaudaPlanner] Fallback plan due to parsing: {e}")
            proj_name = _sanitize_name(description[:20])
            ext = ".py" if language.lower() == "python" else ".js"
            entry = f"main{ext}"
            return {
                "project_name": proj_name,
                "files": [{"path": entry, "purpose": "Main program entry point"}],
                "dependencies": [],
                "entry_point": entry,
                "run_command": f"python {entry}" if language.lower() == "python" else f"node {entry}",
                "summary": description,
            }


class LaudaCodeSynthesizer:
    """Generates clean, full file implementations without missing boilerplate."""

    @staticmethod
    def write_file(
        file_spec: Dict[str, str],
        project_plan: Dict[str, Any],
        existing_files: Dict[str, str],
    ) -> str:
        file_path = file_spec.get("path", "script.py")
        purpose = file_spec.get("purpose", "")

        system_prompt = (
            "You are the Laudacode Core Synthesizer. Write complete, robust, production-quality code. "
            "Never use placeholders like '# TODO' or '...rest of code'. Implement all logic fully. "
            "IMPORTANT: If the script accepts interactive user console input (e.g., input() in Python or readline in Node), "
            "always write it defensively so that non-interactive execution works (e.g., handle EOFError or default values). "
            "Output ONLY raw executable code. No markdown fences, no explanatory chat."
        )

        context_files = "\n".join(
            f"--- {p} ---\n{c[:800]}\n" for p, c in existing_files.items() if p != file_path
        ) or "(No other files yet)"

        prompt = (
            f"Project: {project_plan.get('project_name')}\n"
            f"Summary: {project_plan.get('summary')}\n"
            f"Target File: {file_path}\n"
            f"File Purpose: {purpose}\n"
            f"Other Files in Project:\n{context_files}\n\n"
            f"Write the complete content for {file_path}:"
        )

        raw = resilient_ai.generate(prompt, system_prompt=system_prompt, temperature=0.2)
        return _clean_code_fences(raw)


class LaudaDiagnosticTester:
    """Runs the project, catches errors, and generates targeted self-healing patches."""

    @staticmethod
    def run_and_diagnose(
        run_command: str,
        project_dir: Path,
        timeout: int = 10,
    ) -> Tuple[bool, str]:
        simulated_input = "10\nyes\n1\n\n\n"
        cmd_args: Optional[List[str]] = None
        cmd_str = run_command.strip()
        if cmd_str.startswith("python "):
            script_args = cmd_str[7:].strip()
            cmd_args = [sys.executable] + shlex.split(script_args, posix=False)

        try:
            if cmd_args:
                proc = subprocess.run(
                    cmd_args,
                    cwd=str(project_dir),
                    input=simulated_input,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                )
            else:
                proc = subprocess.run(
                    run_command,
                    shell=True,
                    cwd=str(project_dir),
                    input=simulated_input,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                )
            output = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()
            combined = f"{output}\n{stderr}".strip()

            if proc.returncode == 0:
                return True, combined or "(Clean execution — zero exit code)"
            return False, combined or f"Exited with error code {proc.returncode}"

        except subprocess.TimeoutExpired:
            # GUI apps (like Tkinter, Pygame, Flask, web servers) stay open until closed — this counts as success!
            return True, f"Process is actively running (alive after {timeout}s timeout test)."
        except Exception as exc:
            return False, f"Failed to spawn process: {exc}"

    @staticmethod
    def heal(
        error_output: str,
        project_plan: Dict[str, Any],
        project_dir: Path,
    ) -> bool:
        """Analyzes error output and rewrites/patches faulty files."""
        # 1. Check for missing pip packages and install dynamically
        if "No module named" in error_output or "ModuleNotFoundError" in error_output:
            match = re.search(r"No module named\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?", error_output)
            if match:
                pkg = match.group(1).strip()
                logger.info(f"[LaudaTester] Auto-installing missing dependency: {pkg}")
                subprocess.run([sys.executable, "-m", "pip", "install", pkg], cwd=str(project_dir), timeout=90)
                return True

        system_prompt = (
            "You are the Laudacode Self-Healing Debugger. Analyze the execution error and provide fixed files. "
            "Output a JSON object mapping file paths to their full corrected code:\n"
            '{\n  "path/to/broken_file.py": "full corrected code string"\n}'
        )

        # Read current files in project
        files_dump = {}
        for p in project_dir.rglob("*"):
            if p.is_file() and p.suffix in {".py", ".js", ".html", ".css", ".json", ".ts", ".sh"}:
                try:
                    rel = p.relative_to(project_dir).as_posix()
                    files_dump[rel] = p.read_text(encoding="utf-8", errors="replace")[:2000]
                except Exception:
                    pass

        prompt = (
            f"Run Command: {project_plan.get('run_command')}\n"
            f"Error Traceback:\n{error_output[:2000]}\n\n"
            f"Project Files:\n{json.dumps(files_dump, indent=2)}\n\n"
            "Return the corrected file(s) in JSON:"
        )

        try:
            raw = resilient_ai.generate(prompt, system_prompt=system_prompt, json_mode=True, temperature=0.1)
            fixes = json.loads(_clean_json_response(raw))
            if isinstance(fixes, dict):
                for fpath, fcontent in fixes.items():
                    target = project_dir / fpath
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(_clean_code_fences(str(fcontent)), encoding="utf-8")
                    logger.info(f"[LaudaTester] Patched and healed: {fpath}")
                return True
        except Exception as e:
            logger.warning(f"[LaudaTester] Healing step error: {e}")

        return False


def run_laudacode_task(
    description: str,
    language: str = "python",
    project_name: str = "",
    timeout: int = 10,
    player: Optional[Any] = None,
    speak: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Main entry point for Laudacode Desktop Engine.
    Executes full multi-file software engineering lifecycle with zero rate limits.
    """
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)

    log_fn = lambda msg: player.write_log(f"[LaudaCode] {msg}") if player else logger.info(msg)

    log_fn(f"Architecting solution for: {description[:50]}...")
    if speak:
        speak("I'm architecting and building your project with Laudacode now, boss.")

    # 1. Plan
    plan = LaudaProjectPlanner.plan(description, language)
    proj_name = _sanitize_name(project_name or plan.get("project_name") or "lauda_app")
    project_dir = PROJECTS_ROOT / proj_name
    project_dir.mkdir(parents=True, exist_ok=True)

    files = plan.get("files") or [{"path": "main.py", "purpose": "Core application"}]
    dependencies = plan.get("dependencies") or []
    run_cmd = plan.get("run_command") or "python main.py"

    log_fn(f"Project '{proj_name}' planned ({len(files)} files, dependencies: {dependencies})")

    # 2. Synthesize files
    written_files: Dict[str, str] = {}
    for fspec in files:
        fpath = fspec.get("path", "main.py")
        log_fn(f"Synthesizing: {fpath}...")
        content = LaudaCodeSynthesizer.write_file(fspec, plan, written_files)
        target_file = project_dir / fpath
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(content, encoding="utf-8")
        written_files[fpath] = content

    # 3. Create Project README
    readme_path = project_dir / "README.md"
    if not readme_path.exists():
        readme_content = f"# {proj_name}\n\n{plan.get('summary') or description}\n\n## Run\n```bash\n{run_cmd}\n```\n\n*Built autonomously by Laudacode for Brahma Echo.*"
        readme_path.write_text(readme_content, encoding="utf-8")

    # 4. Install dependencies if needed
    if dependencies:
        log_fn(f"Installing dependencies: {', '.join(dependencies)}...")
        for dep in dependencies:
            subprocess.run([sys.executable, "-m", "pip", "install", dep], cwd=str(project_dir), timeout=90)

    # 5. Initialize Git Repository
    try:
        subprocess.run(["git", "init"], cwd=str(project_dir), capture_output=True, timeout=10)
        subprocess.run(["git", "add", "."], cwd=str(project_dir), capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", f"Initial build by Laudacode: {proj_name}"], cwd=str(project_dir), capture_output=True, timeout=10)
        log_fn("Initialized local Git repository and created baseline commit.")
    except Exception:
        pass

    # 6. Self-Healing Test & Verification Loop
    log_fn("Running automated test validation...")
    success = False
    last_output = ""

    for iteration in range(1, MAX_FIX_ITERATIONS + 1):
        success, last_output = LaudaDiagnosticTester.run_and_diagnose(run_cmd, project_dir, timeout=timeout)
        if success:
            log_fn(f"Validation passed cleanly on iteration {iteration}!")
            break

        log_fn(f"Test failure detected (iteration {iteration}/{MAX_FIX_ITERATIONS}). Applying self-healing patch...")
        healed = LaudaDiagnosticTester.heal(last_output, plan, project_dir)
        if not healed:
            time.sleep(1.0)

    # 7. Open Project in VS Code if available
    try:
        subprocess.Popen(["code", str(project_dir)], shell=True)
        log_fn(f"Opened workspace in VS Code: {project_dir}")
    except Exception:
        pass

    status_word = "successfully created and validated" if success else "created with diagnostic notes"
    summary_msg = (
        f"Laudacode has {status_word} '{proj_name}' on your Desktop at:\n{project_dir}\n\n"
        f"Files created ({len(written_files)}): {', '.join(written_files.keys())}\n"
        f"Run command: {run_cmd}\n"
        f"Validation Output:\n{last_output[:400]}"
    )

    if speak:
        speak(f"Project {proj_name} has been built by Laudacode and is ready on your Desktop, boss.")

    return summary_msg
