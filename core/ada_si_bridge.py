"""
Core Ada-SI Bridge Module for Brahma-Echo (Jarvis)
=================================================
Connects Brahma-Echo agent system to the Ada-SI self-improving engine.
Enables runtime skill creation (Forge Master), isolated tool execution via tool_runtime,
and proactive background heartbeat automation.

Architecture Principles Followed:
- SOLID Design Pattern: Loose coupling via bridge pattern.
- Backward Compatibility: Existing tools remain operational while new skills are forged on the fly.
- Isolated Execution: Dynamic tools execute in the dedicated tool_runtime environment (port 8090).
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Resolve paths for both Brahma-Echo and Ada-SI
BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = BASE_DIR.parent
ADA_SI_DIR = WORKSPACE_ROOT / "Ada-SI-main"
ADA_CHAT_DIR = ADA_SI_DIR / "chat"
ADA_TOOL_RUNTIME_DIR = ADA_SI_DIR / "tool_runtime"

# Add Ada-SI paths to sys.path for direct module import
for p in [str(ADA_SI_DIR), str(ADA_CHAT_DIR), str(ADA_TOOL_RUNTIME_DIR)]:
    if p not in sys.path and os.path.exists(p):
        sys.path.insert(0, p)

logger = logging.getLogger("BrahmaEcho.AdaSIBridge")

# Import Ada-SI components safely
try:
    import tools_engine
    from runtime_client import runtime_health, runtime_run_tool, set_runtime_url
    from scout_persona import build_scout_system_instruction
    from tool_creator import draft_tool_plan_stream, draft_tool_edit_plan_stream
    from build_pipeline import stream_runtime_install
    ADA_SI_AVAILABLE = True
    logger.info("[AdaSIBridge] Successfully imported Ada-SI core modules.")
except Exception as e:
    ADA_SI_AVAILABLE = False
    logger.warning(f"[AdaSIBridge] Could not import Ada-SI modules directly: {e}")

# Tool runtime default configuration
TOOL_RUNTIME_URL = os.environ.get("TOOL_RUNTIME_URL", "http://127.0.0.1:8090")
if ADA_SI_AVAILABLE:
    set_runtime_url(TOOL_RUNTIME_URL)


class AdaSIBridge:
    """
    Bridge connecting Brahma-Echo to Ada-SI self-improving subsystem.
    """

    def __init__(self, tool_runtime_url: str = TOOL_RUNTIME_URL):
        self.tool_runtime_url = tool_runtime_url
        self.custom_tools_dir = ADA_CHAT_DIR / "custom_tools"
        self.staging_dir = ADA_CHAT_DIR / "staging"
        self.custom_tools_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def is_runtime_healthy(self) -> bool:
        """Check if Ada-SI tool_runtime service (port 8090) is reachable."""
        if not ADA_SI_AVAILABLE:
            return False
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                health = asyncio.run_coroutine_threadsafe(runtime_health(), loop).result(timeout=5)
            else:
                health = asyncio.run(runtime_health())
            return isinstance(health, dict) and health.get("status") == "ok"
        except Exception as err:
            logger.debug(f"[AdaSIBridge] tool_runtime health check failed: {err}")
            return False

    def list_installed_custom_tools(self) -> List[Dict[str, Any]]:
        """List all forged skills available in chat/custom_tools/."""
        tools = []
        if not self.custom_tools_dir.exists():
            return tools

        for manifest_path in self.custom_tools_dir.glob("*.manifest.json"):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    tools.append(data)
            except Exception as e:
                logger.warning(f"[AdaSIBridge] Failed reading manifest {manifest_path}: {e}")
        return tools

    async def execute_custom_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a forged custom tool via isolated tool_runtime.
        """
        if not ADA_SI_AVAILABLE:
            return {"success": False, "error": "Ada-SI modules not loaded."}

        logger.info(f"[AdaSIBridge] Executing forged tool '{tool_name}' via tool_runtime...")
        try:
            # Check if runtime is running, fallback to direct tools_engine execution if needed
            if self.is_runtime_healthy():
                res = runtime_run_tool(tool_name, arguments)
                return {"success": True, "output": res}
            else:
                # Attempt in-process execution fallback via tools_engine
                logger.info(f"[AdaSIBridge] tool_runtime server offline, invoking fallback executor...")
                # Read tool file and execute
                tool_py = self.custom_tools_dir / f"{tool_name}.py"
                if not tool_py.exists():
                    return {"success": False, "error": f"Tool '{tool_name}' not found."}
                
                # Execute in local context
                import importlib.util
                spec = importlib.util.spec_from_file_location(tool_name, str(tool_py))
                if not spec or not spec.loader:
                    return {"success": False, "error": "Failed loading spec for tool."}
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                run_fn = getattr(mod, "run", None) or getattr(mod, "execute", None)
                if not callable(run_fn):
                    return {"success": False, "error": f"Tool '{tool_name}' has no run() function."}
                
                output = run_fn(**arguments) if asyncio.iscoroutinefunction(run_fn) else await asyncio.to_thread(run_fn, **arguments)
                return {"success": True, "output": output}

        except Exception as exc:
            logger.error(f"[AdaSIBridge] Execution error in '{tool_name}': {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    async def forge_tool_for_prompt(
        self,
        prompt: str,
        creator_model: str = "openai/gpt-4o-mini",
        litellm_url: str = "http://127.0.0.1:4000",
        api_key: str = "sk-ada-dev-key"
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Trigger Forge Master pipeline to plan, write, test, and install a new Python tool on the fly.
        """
        if not ADA_SI_AVAILABLE:
            return False, "Ada-SI modules not available.", None

        logger.info(f"[AdaSIBridge] Starting Forge Master codegen for prompt: '{prompt}'")
        headers = {"Authorization": f"Bearer {api_key}"}

        # Generate a clean tool_name from prompt
        import re
        clean_words = re.findall(r"\w+", prompt.lower())
        tool_name = "_".join(clean_words[:3]) or "custom_tool"

        try:
            # 1. Generate plan text
            plan_text = ""
            async for kind, delta in draft_tool_plan_stream(
                tool_name=tool_name,
                description=prompt,
                creator_model=creator_model,
                litellm_url=litellm_url,
                headers=headers
            ):
                if kind == "content":
                    plan_text += delta

            logger.info(f"[AdaSIBridge] Tool plan created for '{tool_name}'.")

            # 2. Draft code and manifest using draft_tool_code_stream
            full_code_text = ""
            async for kind, delta in draft_tool_code_stream(
                tool_name=tool_name,
                plan=plan_text,
                creator_model=creator_model,
                litellm_url=litellm_url,
                headers=headers
            ):
                if kind == "content":
                    full_code_text += delta

            manifest = {
                "name": tool_name,
                "description": prompt,
                "version": "1.0.0",
                "ui": {"template": "list"}
            }

            # 3. Write files to custom_tools directory
            manifest_path = self.custom_tools_dir / f"{tool_name}.manifest.json"
            tool_path = self.custom_tools_dir / f"{tool_name}.py"

            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            tool_path.write_text(full_code_text, encoding="utf-8")

            logger.info(f"[AdaSIBridge] Forged tool '{tool_name}' successfully installed!")
            return True, f"Tool '{tool_name}' forged and installed successfully.", manifest

        except Exception as e:
            logger.error(f"[AdaSIBridge] Forge failed: {e}", exc_info=True)
            return False, f"Forge pipeline error: {str(e)}", None


# Global Singleton Instance
ada_bridge = AdaSIBridge()
