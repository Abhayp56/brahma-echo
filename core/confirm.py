"""
core/confirm.py — Human Verification Gate for Irreversible Actions

Architecture:
    Prevents autonomous or model-hallucinated execution of high-risk irreversible operations
    (system shutdown, reboot, network disconnect, critical process termination).

    Key Design Principles:
    1. Confirmation tokens are issued and validated by the interface, never by model parameter injection.
    2. Non-blocking design: Parking a pending action returns immediately to the calling thread/tool.
    3. Expiration: Pending actions expire automatically after TIMEOUT_SECONDS (default 90s).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger("ConfirmGate")

TIMEOUT_SECONDS = 90.0


@dataclass
class PendingAction:
    key: str
    title: str
    detail: str
    run_fn: Callable[[], str]
    created_at: float


_pending: Optional[PendingAction] = None
_lock = threading.Lock()

# Callbacks to notify UI/Desktop interface
_show_cb: Optional[Callable[[str, str], None]] = None
_hide_cb: Optional[Callable[[], None]] = None
_log_cb: Optional[Callable[[str], None]] = None


def bind(
    show_cb: Optional[Callable[[str, str], None]] = None,
    hide_cb: Optional[Callable[[], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> None:
    """Wire HUD / Desktop / Headless interfaces to the confirmation manager."""
    global _show_cb, _hide_cb, _log_cb
    _show_cb, _hide_cb, _log_cb = show_cb, hide_cb, log_cb


def _log(msg: str) -> None:
    logger.info(f"[Confirm] {msg}")
    if _log_cb:
        try:
            _log_cb(msg)
        except Exception:
            pass


def request(key: str, title: str, detail: str, run_fn: Callable[[], str]) -> str:
    """Park an irreversible action behind the human confirmation gate.

    Args:
        key: Action key identifier (e.g. 'shutdown', 'toggle_wifi').
        title: Short descriptive title.
        detail: Full description of consequences.
        run_fn: Zero-argument callable to execute if confirmed.

    Returns:
        String message instructing caller that confirmation is pending.
    """
    global _pending

    with _lock:
        _pending = PendingAction(
            key=key,
            title=title,
            detail=detail,
            run_fn=run_fn,
            created_at=time.monotonic(),
        )

    if _show_cb:
        try:
            _show_cb(title, detail)
        except Exception as e:
            logger.error(f"Failed to display confirmation banner: {e}")

    _log(f"Awaiting human confirmation for action: {title}")
    return (
        f"[CONFIRMATION_PENDING] Human confirmation required on desktop for: {title}. "
        f"Do not mark action as completed until confirmed."
    )


def resolve(accepted: bool) -> str:
    """Called by interface/user when confirming or cancelling a pending action."""
    global _pending

    with _lock:
        pending, _pending = _pending, None

    if _hide_cb:
        try:
            _hide_cb()
        except Exception:
            pass

    if pending is None:
        return "No pending action awaiting confirmation."

    if time.monotonic() - pending.created_at > TIMEOUT_SECONDS:
        _log(f"Confirmation expired for: {pending.title}")
        return f"Confirmation request for '{pending.title}' expired."

    if not accepted:
        _log(f"User cancelled action: {pending.title}")
        return f"Cancelled: {pending.title}."

    def _worker():
        try:
            res = pending.run_fn() or "Done."
            _log(f"Executed confirmed action '{pending.title}': {res}")
        except Exception as e:
            logger.error(f"Execution of confirmed action '{pending.title}' failed: {e}")

    threading.Thread(target=_worker, daemon=True, name=f"confirm-{pending.key}").start()
    return f"Confirmed: {pending.title}. Execution started."


def pending_title() -> str:
    """Return the title of currently pending action, or empty string if none/expired."""
    with _lock:
        if _pending is None:
            return ""
        if time.monotonic() - _pending.created_at > TIMEOUT_SECONDS:
            return ""
        return _pending.title
