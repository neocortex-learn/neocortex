"""Shared asyncio.run bridge for sync CLI commands calling async code."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine from a sync context (CLI command entry points)."""
    return asyncio.run(coro)
