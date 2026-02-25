"""In-process runtime metadata shared between launcher and API handlers."""

from __future__ import annotations

import threading
from typing import Any

_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "host": None,
    "port": None,
    "base_url": None,
}


def set_runtime(host: str, port: int, base_url: str | None = None) -> None:
    with _state_lock:
        _state["host"] = host
        _state["port"] = int(port)
        if base_url:
            _state["base_url"] = base_url


def get_runtime() -> dict[str, Any]:
    with _state_lock:
        return dict(_state)

