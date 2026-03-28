"""In-memory admin USB unlock session manager."""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timezone

_session_lock = asyncio.Lock()
_admin_token: str | None = None
_unlocked = False
_last_unlocked_at: datetime | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def unlock() -> str:
    """Create a new admin USB session token."""
    global _admin_token, _unlocked, _last_unlocked_at
    async with _session_lock:
        _admin_token = secrets.token_urlsafe(32)
        _unlocked = True
        _last_unlocked_at = _utcnow()
        return _admin_token


async def lock() -> bool:
    """Revoke the current admin USB session token.

    Returns True when state changed (was previously unlocked), False otherwise.
    """
    global _admin_token, _unlocked
    async with _session_lock:
        changed = _unlocked or _admin_token is not None
        _admin_token = None
        _unlocked = False
        return changed


async def is_token_valid(token: str | None) -> bool:
    """Validate the provided token against the active admin USB token."""
    if not token:
        return False
    async with _session_lock:
        return bool(_unlocked and _admin_token and secrets.compare_digest(_admin_token, token))


async def is_unlocked() -> bool:
    """Return True when an admin USB session is active."""
    async with _session_lock:
        return bool(_unlocked and _admin_token)


async def get_status() -> dict[str, datetime | bool | None]:
    """Return current in-memory admin USB session state."""
    async with _session_lock:
        return {
            "unlocked": bool(_unlocked and _admin_token),
            "last_unlocked_at": _last_unlocked_at,
        }
