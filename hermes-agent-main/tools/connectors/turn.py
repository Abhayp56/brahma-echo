"""
tools/connectors/turn.py — Connector Surface Context
"""

from contextlib import contextmanager
from typing import Any, Generator, Optional


@contextmanager
def agent_connection_surface(*args, **kwargs) -> Generator[None, None, None]:
    yield


@contextmanager
def scoped_connection_surface(*args, **kwargs) -> Generator[None, None, None]:
    yield
