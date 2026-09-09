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


def _resolve_task_id(task_id_or_name: str) -> Optional[Dict[str, Any]]:
    """
    Given an ID or task name/keyword, find the matching active task in Todoist.
    Returns the task dictionary if found, or None.
    """
    clean_target = str(task_id_or_name).strip()
    if not clean_target:
        return None

    all_res = list_tasks_sync()
    if not all_res.get("success"):
        return None

    tasks = all_res.get("tasks", [])

    # 1. Exact ID match
    for t in tasks:
        if str(t.get("id")) == clean_target:
            return t

    # 2. Exact content match (case-insensitive)
    target_lower = clean_target.lower()
    for t in tasks:
        if t.get("content", "").lower() == target_lower:
            return t

    # 3. Substring match (either target is in content, or content is in target)
    for t in tasks:
        c_lower = t.get("content", "").lower()
        if target_lower in c_lower or c_lower in target_lower:
            return t

    # 4. Partial word match (e.g. "air project" matches "finish air project")
    words = [w for w in target_lower.split() if len(w) > 2]
    if words:
        for t in tasks:
            c_lower = t.get("content", "").lower()
            if any(w in c_lower for w in words):
                return t

    return None


def update_task_sync(
    task_id_or_name: str,
    new_content: Optional[str] = None,
    due_string: Optional[str] = None,
    priority: Optional[int] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Update an existing task in Todoist (content, due date, priority, or description)."""
    clean_target = str(task_id_or_name).strip()
    if not clean_target:
        return {"success": False, "error": "Task identifier or name cannot be empty."}

    task = _resolve_task_id(clean_target)
    if not task:
        return {"success": False, "error": f"Could not find an active task matching '{clean_target}'."}

    task_id = task["id"]
    payload: Dict[str, Any] = {}

    if new_content and new_content.strip():
        payload["content"] = new_content.strip()
    if due_string and due_string.strip():
        payload["due_string"] = due_string.strip()
    if priority is not None and 1 <= int(priority) <= 4:
        payload["priority"] = int(priority)
    if description is not None:
        payload["description"] = description

    if not payload:
        return {"success": False, "error": "No updates specified. Please provide a new name, due_date, or priority."}

    res = _todoist_request(f"/tasks/{task_id}", method="POST", payload=payload)
    if isinstance(res, dict) and res.get("id"):
        return {
            "success": True,
            "configured": True,
            "message": f"Updated task '{task.get('content')}' successfully.",
            "task_id": res.get("id"),
            "content": res.get("content"),
            "due": res.get("due", {}).get("string") if res.get("due") else None,
            "priority": res.get("priority"),
        }
    return res if isinstance(res, dict) else {"success": False, "error": "Failed to update task."}


def complete_task_sync(task_id_or_name: str) -> Dict[str, Any]:
    """Mark a task completed by task ID or by searching task name."""
    clean_target = str(task_id_or_name).strip()
    if not clean_target:
        return {"success": False, "error": "Task identifier or name cannot be empty."}

    task = _resolve_task_id(clean_target)
    if not task:
        if len(clean_target) >= 10 and clean_target.isalnum():
            task_id = clean_target
            display_name = clean_target
        else:
            return {"success": False, "error": f"Could not find an active task matching '{clean_target}'."}
    else:
        task_id = task["id"]
        display_name = task.get("content", clean_target)

    res = _todoist_request(f"/tasks/{task_id}/close", method="POST")
    if isinstance(res, dict) and res.get("success"):
        return {"success": True, "message": f"Completed task '{display_name}'."}
    return res


def delete_task_sync(task_id_or_name: str) -> Dict[str, Any]:
    """Delete a task by ID or name."""
    clean_target = str(task_id_or_name).strip()
    if not clean_target:
        return {"success": False, "error": "Task identifier or name cannot be empty."}

    task = _resolve_task_id(clean_target)
    if not task:
        if len(clean_target) >= 10 and clean_target.isalnum():
            task_id = clean_target
            display_name = clean_target
        else:
            return {"success": False, "error": f"Could not find an active task matching '{clean_target}'."}
    else:
        task_id = task["id"]
        display_name = task.get("content", clean_target)

    res = _todoist_request(f"/tasks/{task_id}", method="DELETE")
    if isinstance(res, dict) and res.get("success"):
        return {"success": True, "message": f"Deleted task '{display_name}'."}
    return res


async def execute_todoist_tool(action: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronous entry point for ARYA Cloud Brain."""
    act = (action or args.get("action", "list_tasks")).lower().strip()
    task_name = args.get("task_name") or args.get("content") or args.get("name") or ""
    task_id = args.get("task_id") or ""
    target_identifier = task_id or task_name

    due_date = args.get("due_date") or args.get("due_string") or args.get("due") or ""
    priority_val = args.get("priority")
    priority = int(priority_val) if priority_val is not None else None

    # New title / content when updating
    new_content = args.get("new_content") or args.get("new_task_name") or args.get("new_name") or args.get("title")

    if act in {"list_tasks", "list", "get_tasks"}:
        return await asyncio.to_thread(list_tasks_sync, filter_str=args.get("filter"))

    elif act in {"add_task", "create_task", "create", "add"}:
        content_to_add = task_name or new_content or "New Task"
        return await asyncio.to_thread(
            create_task_sync,
            content=content_to_add,
            due_string=due_date or None,
            priority=priority or 1,
            description=args.get("description"),
        )

    elif act in {"update_task", "modify_task", "update", "modify", "edit_task", "edit", "reschedule", "change_task"}:
        # If new_content was not provided, but content was passed as what to change to, or target was specified by task_id:
        update_text = new_content
        if not update_text and args.get("new_title"):
            update_text = args.get("new_title")

        return await asyncio.to_thread(
            update_task_sync,
            task_id_or_name=target_identifier,
            new_content=update_text,
            due_string=due_date or None,
            priority=priority,
            description=args.get("description"),
        )

    elif act in {"complete_task", "complete", "done", "close", "finish"}:
        return await asyncio.to_thread(complete_task_sync, task_id_or_name=target_identifier)

    elif act in {"delete_task", "delete", "remove", "cancel"}:
        return await asyncio.to_thread(delete_task_sync, task_id_or_name=target_identifier)

    return {"success": False, "error": f"Unknown Todoist action: '{action}'."}
