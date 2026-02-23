"""Shared in-memory state containers for live API modules."""

from __future__ import annotations

import asyncio
from typing import Dict

from escalada_core import default_state

# Authoritative per-box runtime state.
state_map: Dict[int, dict] = {}
state_locks: Dict[int, asyncio.Lock] = {}
init_lock = asyncio.Lock()

# Private/authenticated WS subscribers per box.
channels: dict[int, set] = {}
channels_lock = asyncio.Lock()

# Public aggregated spectators.
public_channels: set = set()
public_channels_lock = asyncio.Lock()


async def ensure_state(box_id: int) -> dict:
    async with init_lock:
        existing = state_map.get(box_id)
        if existing is not None:
            return existing
        if box_id not in state_locks:
            state_locks[box_id] = asyncio.Lock()
        state = default_state()
        state_map[box_id] = state
        return state
