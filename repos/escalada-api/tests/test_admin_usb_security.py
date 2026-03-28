from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import escalada.main as main_module
from escalada.api import license as license_api
from escalada.auth.service import create_access_token
from escalada.main import app
from escalada.security import admin_session, license_events, usb_license


def _license_status(valid: bool, reason: str | None = None) -> dict:
    resolved_reason = reason or ("ok" if valid else "not_found")
    return {
        "valid": valid,
        "reason": resolved_reason,
        "mountpoint": "/media/test-usb" if valid else None,
        "checked_at": datetime.now(timezone.utc),
    }


def _set_admin_auth_cookie(client: TestClient) -> None:
    jwt_token = create_access_token(
        username="usb-admin-test",
        role="admin",
        assigned_boxes=[],
    )
    client.cookies.set("escalada_token", jwt_token)


@pytest.fixture(autouse=True)
def trusted_testclient_ip(monkeypatch):
    monkeypatch.setenv("ADMIN_TRUSTED_IPS", "testclient")


@pytest.fixture(autouse=True)
def reset_admin_session_state():
    asyncio.run(admin_session.lock())
    yield
    asyncio.run(admin_session.lock())


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_admin_unlock_without_license_returns_403(client, monkeypatch):
    monkeypatch.setattr(usb_license, "check_license", lambda force_refresh=False: _license_status(False))

    response = client.post("/api/admin/unlock")

    assert response.status_code == 403
    payload = response.json()
    assert payload["detail"]["code"] == "LICENSE_REQUIRED"


def test_admin_unlock_with_license_returns_token(client, monkeypatch):
    monkeypatch.setattr(usb_license, "check_license", lambda force_refresh=False: _license_status(True))

    response = client.post("/api/admin/unlock")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("token"), str)
    assert payload["token"]
    assert payload["admin_unlocked"] is True
    assert payload["license_valid"] is True


def test_admin_action_without_usb_token_returns_401(client, monkeypatch):
    monkeypatch.setattr(usb_license, "check_license", lambda force_refresh=False: _license_status(True))

    response = client.get("/api/admin/backup/full")

    assert response.status_code == 401
    payload = response.json()
    assert payload["detail"]["code"] == "ADMIN_SESSION_REQUIRED"


def test_admin_action_with_token_but_missing_license_returns_403(client, monkeypatch):
    current = {"valid": True}

    def fake_license(force_refresh: bool = False) -> dict:
        return _license_status(current["valid"])

    monkeypatch.setattr(usb_license, "check_license", fake_license)
    _set_admin_auth_cookie(client)

    unlock_response = client.post("/api/admin/unlock")
    assert unlock_response.status_code == 200
    token = unlock_response.json()["token"]

    current["valid"] = False
    response = client.get(
        "/api/admin/backup/full",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["detail"]["code"] == "LICENSE_REQUIRED"


def test_trusted_admin_without_cookie_can_call_admin_action_with_usb_token(client, monkeypatch):
    monkeypatch.setattr(usb_license, "check_license", lambda force_refresh=False: _license_status(True))

    unlock_response = client.post("/api/admin/unlock")
    assert unlock_response.status_code == 200
    token = unlock_response.json()["token"]

    response = client.get(
        "/api/admin/backup/full",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "ok"


def test_watchdog_revokes_session_when_license_turns_invalid(monkeypatch):
    current = {"valid": True}

    def fake_license(force_refresh: bool = False) -> dict:
        return _license_status(current["valid"])

    monkeypatch.setattr(usb_license, "check_license", fake_license)
    monkeypatch.setattr(main_module, "USB_WATCHDOG_INTERVAL_SEC", 1)

    with TestClient(app) as local_client:
        _set_admin_auth_cookie(local_client)
        unlock_response = local_client.post("/api/admin/unlock")
        assert unlock_response.status_code == 200
        token = unlock_response.json()["token"]
        assert asyncio.run(admin_session.is_unlocked()) is True

        current["valid"] = False

        deadline = time.time() + 4.0
        while time.time() < deadline and asyncio.run(admin_session.is_unlocked()):
            time.sleep(0.2)

        assert asyncio.run(admin_session.is_unlocked()) is False

        action_response = local_client.get(
            "/api/admin/backup/full",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert action_response.status_code == 401


@pytest.mark.asyncio
async def test_license_sse_stream_emits_initial_status_event(monkeypatch):
    monkeypatch.setattr(usb_license, "check_license", lambda force_refresh=False: _license_status(True))
    await admin_session.lock()

    class _FakeRequest:
        async def is_disconnected(self) -> bool:
            return False

    response = await license_api.license_events_stream(
        request=_FakeRequest(),
    )
    assert response.media_type == "text/event-stream"

    first_chunk = await anext(response.body_iterator)
    if isinstance(first_chunk, bytes):
        first_chunk = first_chunk.decode("utf-8")
    assert "event: license_status_changed" in first_chunk

    await response.body_iterator.aclose()


def test_license_event_bus_emits_admin_locked():
    async def run_assertion():
        subscriber = await license_events.subscribe()
        try:
            await license_events.publish("admin_locked", {"reason": "test"})
            payload = await asyncio.wait_for(subscriber.get(), timeout=1.0)
            assert payload["event"] == "admin_locked"
        finally:
            await license_events.unsubscribe(subscriber)

    asyncio.run(run_assertion())
