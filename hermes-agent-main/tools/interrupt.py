"""
tools/interrupt.py — Interruption & Yield Signals for Tool Execution
"""

from typing import Optional

_interrupted = False
_yield_requested = False


def set_interrupt(val: bool = True) -> None:
    global _interrupted
    _interrupted = val


def clear_interrupt() -> None:
    global _interrupted, _yield_requested
    _interrupted = False
    _yield_requested = False


def is_interrupted() -> bool:
    return _interrupted


def request_yield(val: bool = True) -> None:
    global _yield_requested
    _yield_requested = val


def check_yield() -> bool:
    return _yield_requested


def request_interrupt(val: bool = True) -> None:
    set_interrupt(val)
