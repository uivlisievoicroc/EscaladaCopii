# pyright: reportMissingImports=false
"""
Pytest configuration and fixtures for Escalada tests
"""
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


def pytest_configure(config):
    """Configure pytest - only stub if modules aren't installed"""

    # Only stub if fastapi isn't actually installed
    try:
        import fastapi
        import fastapi.testclient  # noqa
    except (ImportError, ModuleNotFoundError):
        # Create stubs for optional runtime deps
        fastapi_stub: Any = types.ModuleType("fastapi")

        class _DummyRouter:
            def post(self, *args, **kwargs):
                return lambda f: f

            def websocket(self, *args, **kwargs):
                return lambda f: f

            def get(self, *args, **kwargs):
                return lambda f: f

        class _HTTPException(Exception):
            def __init__(self, status_code=None, detail=None):
                self.status_code = status_code
                self.detail = detail
                super().__init__(f"HTTPException: {status_code} - {detail}")

        fastapi_stub.APIRouter = _DummyRouter
        fastapi_stub.HTTPException = _HTTPException
        sys.modules["fastapi"] = fastapi_stub

    # Only stub starlette/websockets if not installed
    try:
        import starlette
        import starlette.websockets  # noqa
    except (ImportError, ModuleNotFoundError):
        starlette_stub: Any = types.ModuleType("starlette")
        websockets_stub: Any = types.ModuleType("starlette.websockets")

        class _DummyWebSocket:
            pass

        websockets_stub.WebSocket = _DummyWebSocket
        sys.modules["starlette"] = starlette_stub
        sys.modules["starlette.websockets"] = websockets_stub


@pytest.fixture(autouse=True)
def isolate_test_runtime_state(monkeypatch, tmp_path):
    """Run every test with isolated secrets and clean in-memory security state."""
    secrets_dir = Path(tmp_path) / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ESCALADA_SECRETS_DIR", str(secrets_dir))

    try:
        from escalada.security import admin_license
    except Exception:
        admin_license = None

    if admin_license is not None:
        monkeypatch.setattr(admin_license, "_cached_result", None, raising=False)
        monkeypatch.setattr(admin_license, "_cached_at_monotonic", 0.0, raising=False)

    try:
        from escalada.security import recovery_codes
    except Exception:
        recovery_codes = None

    if recovery_codes is not None and hasattr(recovery_codes, "reset_runtime_state"):
        recovery_codes.reset_runtime_state()

    yield

    if recovery_codes is not None and hasattr(recovery_codes, "reset_runtime_state"):
        recovery_codes.reset_runtime_state()


@pytest.fixture(autouse=True)
def default_admin_license_valid(monkeypatch, request):
    module_name = getattr(getattr(request, "module", None), "__name__", "")
    if module_name.endswith("test_admin_license"):
        yield
        return

    try:
        from escalada.security import admin_license
    except Exception:
        yield
        return

    def _fake_admin_license(force_refresh: bool = False, now_utc=None):
        now = (
            now_utc.astimezone(timezone.utc) if now_utc else datetime.now(timezone.utc)
        )
        expires_at = now + timedelta(days=30)
        return {
            "valid": True,
            "reason": "ok",
            "checked_at": now,
            "expires_at": expires_at,
            "in_grace": False,
            "grace_until": expires_at + timedelta(hours=24),
            "license_id": "test-license",
            "kid": "default",
        }

    monkeypatch.setattr(admin_license, "check_admin_license", _fake_admin_license)
    yield
