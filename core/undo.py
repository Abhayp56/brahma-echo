"""
core/undo.py — Centralized Undo Stack for Desktop Actions

Architecture:
    Provides a thread-safe, 10-depth Undo Buffer for reversible desktop state mutations
    (file operations, settings changes, desktop organization, layout shifts).
    
    Actions register zero-argument reversal callables at execution time:
        from core.undo import push_undo
        push_undo("volume → 50%", lambda: volume_set(old_val))

    The Cloud Brain or local worker can call undo_last() or the 'undo' tool to rollback
    the last state change safely without manual human repair or risk of data loss.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

logger = logging.getLogger("UndoManager")

# Maximum depth of reversible actions stored in RAM
MAX_DEPTH = 10


@dataclass
class UndoEntry:
    label: str
    undo_fn: Callable[[], str]
    created_at: float = field(default_factory=time.monotonic)


_stack: List[UndoEntry] = []
_lock = threading.Lock()


def push_undo(label: str, undo_fn: Callable[[], str]) -> None:
    """Record a reversible operation.
    
    Args:
        label: Descriptive label of the operation for user feedback.
        undo_fn: Zero-argument callable that performs the reversal and returns a status string.
    """
    if not callable(undo_fn):
        return
    try:
        with _lock:
            _stack.append(UndoEntry(label=str(label)[:120], undo_fn=undo_fn))
            while len(_stack) > MAX_DEPTH:
                _stack.pop(0)
    except Exception as e:
        logger.error(f"Failed to register undo entry '{label}': {e}")


def can_undo() -> bool:
    """Return True if there are operations available to undo."""
    with _lock:
        return bool(_stack)


def peek() -> str:
    """Return the label of the most recent undoable action, or empty string."""
    with _lock:
        return _stack[-1].label if _stack else ""


def history() -> List[str]:
    """Return list of undo labels (most recent first)."""
    with _lock:
        return [entry.label for entry in reversed(_stack)]


def undo_last() -> str:
    """Pop and execute the most recent undo operation.
    
    Returns:
        User-facing result string detailing the outcome.
    """
    with _lock:
        entry = _stack.pop() if _stack else None

    if entry is None:
        return "There is nothing to undo. I only track state changes performed in this session."

    try:
        detail = entry.undo_fn() or ""
        msg = f"Undone: {entry.label}."
        if detail:
            msg += f" {detail}"
        logger.info(f"[Undo] Successfully reversed: {entry.label}")
        return msg
    except Exception as e:
        logger.error(f"[Undo] Error reversing '{entry.label}': {e}")
        return f"Could not undo '{entry.label}': {e}"


def clear() -> None:
    """Clear all pending undo actions."""
    with _lock:
        _stack.clear()
