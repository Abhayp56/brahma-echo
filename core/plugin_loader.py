"""
core/plugin_loader.py — Self-Describing Modular Tool & Plugin Loader

Architecture:
    Enables zero-touch tool additions for local worker nodes.
    Discovers plugins in the `plugins/` folder using fast `importlib.util.find_spec`
    inspection to avoid heavy imports during initial discovery.

    Plugin Interface:
        Plugins placed in `plugins/<plugin_name>.py` declare:
        - `TOOL`: Dictionary describing tool name, description, and parameter schemas.
        - `execute(parameters, player=None)` or `run(parameters, player=None)`: Handler function.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("PluginLoader")

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

PLUGINS_DIR = BASE_DIR / "plugins"


class PluginRegistration:
    def __init__(self, name: str, tool_def: Dict[str, Any], handler: Callable[[Dict[str, Any]], Any], module_path: Path):
        self.name = name
        self.tool_def = tool_def
        self.handler = handler
        self.module_path = module_path


class PluginRegistry:
    """Registry holding all dynamically loaded tool plugins."""

    def __init__(self, plugins_dir: Path = PLUGINS_DIR):
        self.plugins_dir = plugins_dir
        self.registered_plugins: Dict[str, PluginRegistration] = {}

    def discover_and_load() -> Dict[str, PluginRegistration]:
        """Scan plugins directory and load valid tool plugins."""
        if not self.plugins_dir.exists():
            try:
                self.plugins_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"Could not create plugins directory {self.plugins_dir}: {e}")
                return self.registered_plugins

        if str(self.plugins_dir.parent) not in sys.path:
            sys.path.insert(0, str(self.plugins_dir.parent))

        for py_file in self.plugins_dir.glob("*.py"):
            if py_file.name.startswith("_") or py_file.name == "__init__.py":
                continue

            plugin_name = py_file.stem
            mod_spec = f"plugins.{plugin_name}"

            # Check spec availability first without executing module top-level code
            try:
                spec = importlib.util.find_spec(mod_spec)
                if spec is None:
                    continue
            except Exception as e:
                logger.debug(f"Spec check skipped for {py_file.name}: {e}")

            # Import module safely
            try:
                mod = importlib.import_module(mod_spec)
                tool_def = getattr(mod, "TOOL", None) or getattr(mod, "TOOL_DEF", None)
                handler = getattr(mod, "execute", None) or getattr(mod, "run", None) or getattr(mod, "handler", None)

                if not handler:
                    logger.debug(f"Plugin '{plugin_name}' has no execute/run handler. Skipping.")
                    continue

                tool_name = (tool_def.get("name") if isinstance(tool_def, dict) else None) or plugin_name
                reg = PluginRegistration(
                    name=tool_name,
                    tool_def=tool_def or {"name": tool_name, "description": f"Custom plugin {plugin_name}"},
                    handler=handler,
                    module_path=py_file,
                )
                self.registered_plugins[tool_name] = reg
                logger.info(f"🧩 Plugin discovered and registered: '{tool_name}' from {py_file.name}")
            except Exception as e:
                logger.error(f"Failed to load plugin from {py_file.name}: {e}")

        return self.registered_plugins

    def get_handler(self, tool_name: str) -> Optional[Callable[[Dict[str, Any]], Any]]:
        """Retrieve handler callable for registered plugin tool name."""
        reg = self.registered_plugins.get(tool_name)
        if reg:
            return reg.handler
        return None


# Global singleton instance
_registry = PluginRegistry()


def get_plugin_registry() -> PluginRegistry:
    return _registry
