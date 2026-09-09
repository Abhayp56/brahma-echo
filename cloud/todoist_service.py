"""
cloud/todoist_service.py — ARYA Todoist Task & Project Management Integration

Uses Todoist REST API v2 to list, add, complete, and delete tasks.
API Token is loaded from TODOIST_API_TOKEN env var or config/api_keys.json.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TodoistService")

BASE_DIR = Path(__file__).resolve().parent.parent
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
TODOIST_API_BASE = "https://api.todoist.com/api/v1"


def get_todoist_token() -> str:
    """Retrieve Todoist Personal API Token."""
    if token := os.environ.get("TODOIST_API_TOKEN"):
        return token.strip()
    if API_CONFIG_PATH.exists():
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("todoist_api_token", "").strip()
        except Exception:
            pass
    return ""


def _todoist_request(
    endpoint: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    """Helper executing HTTP requests to the Todoist REST API."""
    token = get_todoist_token()
    if not token:
        return {
            "success": False,
            "configured": False,
            "error": "Todoist API token is not configured. Please add 'todoist_api_token' to config/api_keys.json or set TODOIST_API_TOKEN.",
        }

    url = f"{TODOIST_API_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Brahma-Echo-Assistant/2.0",
    }

    data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            # 204 No Content for close/delete
            if resp.status == 204:
                return {"success": True, "status": 204}
            content = resp.read().decode("utf-8")
            if not content:
                return {"success": True}
            return json.loads(content)
    except urllib.error.HTTPError as he:
        err_msg = he.read().decode("utf-8") if he.fp else str(he)
        logger.error(f"Todoist API HTTP error {he.code}: {err_msg}")
        return {"success": False, "error": f"Todoist HTTP {he.code}: {err_msg}"}
    except Exception as e:
        logger.error(f"Todoist API request error: {e}")
        return {"success": False, "error": str(e)}


def list_tasks_sync(filter_str: Optional[str] = None) -> Dict[str, Any]:
    """List active tasks from Todoist."""
    endpoint = "/tasks"
    if filter_str:
        endpoint += f"?filter={urllib.parse.quote(filter_str)}"

    res = _todoist_request(endpoint, method="GET")
    if isinstance(res, dict) and not res.get("success", True):
        return res

    raw_items = []
    if isinstance(res, dict) and "results" in res:
        raw_items = res["results"]
    elif isinstance(res, list):
        raw_items = res

    tasks = []
    for t in raw_items:
        tasks.append({
            "id": t.get("id"),
            "content": t.get("content"),
            "description": t.get("description", ""),
            "due": t.get("due", {}).get("string") if t.get("due") else None,
            "priority": t.get("priority", 1),
            "url": t.get("url"),
        })

    return {
        "success": True,
        "configured": True,
        "total": len(tasks),
        "tasks": tasks,
    }


def create_task_sync(
    content: str,
    due_string: Optional[str] = None,
    priority: int = 1,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new task in Todoist."""
    if not content or not content.strip():
        return {"success": False, "error": "Task content cannot be empty."}

    payload: Dict[str, Any] = {"content": content.strip(), "priority": priority}
    if due_string:
        payload["due_string"] = due_string
    if description:
        payload["description"] = description

    res = _todoist_request("/tasks", method="POST", payload=payload)
    if isinstance(res, dict) and res.get("id"):
        return {
            "success": True,
            "configured": True,
            "task_id": res.get("id"),
            "content": res.get("content"),
            "due": res.get("due", {}).get("string") if res.get("due") else None,
            "url": res.get("url"),
        }
    return res if isinstance(res, dict) else {"success": False, "error": "Failed to create task."}


def complete_task_sync(task_id_or_name: str) -> Dict[str, Any]:
    """Mark a task completed by task ID or by searching task name."""
    clean_target = str(task_id_or_name).strip()
    if not clean_target:
        return {"success": False, "error": "Task identifier or name cannot be empty."}

    task_id = clean_target
    # If not numeric ID, look up task by name
    if not clean_target.isdigit():
        all_tasks = list_tasks_sync()
        if not all_tasks.get("success"):
            return all_tasks
        match = None
        for t in all_tasks.get("tasks", []):
            if clean_target.lower() in t.get("content", "").lower():
                match = t
                break
        if not match:
            return {"success": False, "error": f"Could not find an active task matching '{clean_target}'."}
        task_id = match["id"]

    res = _todoist_request(f"/tasks/{task_id}/close", method="POST")
    if isinstance(res, dict) and res.get("success"):
        return {"success": True, "message": f"Completed task '{clean_target}'."}
    return res


def delete_task_sync(task_id_or_name: str) -> Dict[str, Any]:
    """Delete a task by ID or name."""
    clean_target = str(task_id_or_name).strip()
    task_id = clean_target

    if not clean_target.isdigit():
        all_tasks = list_tasks_sync()
        if not all_tasks.get("success"):
            return all_tasks
        match = None
        for t in all_tasks.get("tasks", []):
            if clean_target.lower() in t.get("content", "").lower():
                match = t
                break
        if not match:
            return {"success": False, "error": f"Could not find an active task matching '{clean_target}'."}
        task_id = match["id"]

    res = _todoist_request(f"/tasks/{task_id}", method="DELETE")
    if isinstance(res, dict) and res.get("success"):
        return {"success": True, "message": f"Deleted task '{clean_target}'."}
    return res


async def execute_todoist_tool(action: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronous entry point for ARYA Cloud Brain."""
    act = (action or args.get("action", "list_tasks")).lower().strip()
    task_name = args.get("task_name") or args.get("content") or args.get("name", "")
    due_date = args.get("due_date") or args.get("due_string", "")
    priority = int(args.get("priority", 1))

    if act in {"list_tasks", "list", "get_tasks"}:
        return await asyncio.to_thread(list_tasks_sync, filter_str=args.get("filter"))
    elif act in {"add_task", "create_task", "create", "add"}:
        return await asyncio.to_thread(create_task_sync, content=task_name, due_string=due_date, priority=priority)
    elif act in {"complete_task", "complete", "done", "close"}:
        return await asyncio.to_thread(complete_task_sync, task_id_or_name=task_name or args.get("task_id", ""))
    elif act in {"delete_task", "delete", "remove"}:
        return await asyncio.to_thread(delete_task_sync, task_id_or_name=task_name or args.get("task_id", ""))

    return {"success": False, "error": f"Unknown Todoist action: '{action}'."}
