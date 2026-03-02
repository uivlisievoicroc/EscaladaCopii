from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import escalada.api.auth as auth_api
import escalada.api.live as live
from escalada.auth.service import create_access_token, hash_password
from escalada.main import app
from escalada.security import admin_license, recovery_codes, usb_license


@pytest.fixture(autouse=True)
def patch_run_migrations(monkeypatch):
    async def _noop():
        return None

    monkeypatch.setattr("escalada.main.run_migrations", _noop)
    yield


@pytest.fixture(autouse=True)
def patch_persist_state(monkeypatch):
    async def _noop(box_id, state, action, payload):
        return "ok"

    monkeypatch.setattr(live, "_persist_state", _noop)
    yield


@pytest.fixture(autouse=True)
def patch_ensure_state(monkeypatch):
    async def _fake(box_id: int):
        st = live._default_state()
        live.state_map[box_id] = st
        return st

    monkeypatch.setattr(live, "_ensure_state", _fake)
    yield


@pytest.fixture(autouse=True)
def reset_state_map():
    live.state_map.clear()
    yield
    live.state_map.clear()


@pytest.fixture(autouse=True)
def disable_validation(monkeypatch):
    old = live.VALIDATION_ENABLED
    monkeypatch.setattr(live, "VALIDATION_ENABLED", False)
    yield
    live.VALIDATION_ENABLED = old


@pytest.fixture(autouse=True)
def default_trusted_admin_ips(monkeypatch):
    monkeypatch.setenv("ADMIN_TRUSTED_IPS", "127.0.0.1,::1,localhost")


@pytest.fixture
def client():
    return TestClient(app)


def _token(role: str, boxes=None) -> str:
    return create_access_token(
        username=f"user-{role}", role=role, assigned_boxes=boxes or []
    )


def test_cmd_requires_auth(client: TestClient):
    res = client.post("/api/cmd", json={"boxId": 1, "type": "INIT_ROUTE"})
    assert res.status_code == 401


def test_admin_endpoint_requires_auth_when_ip_untrusted(client: TestClient):
    res = client.get("/api/admin/audit/events")
    assert res.status_code == 401


def test_cmd_trusted_admin_ip_allowed_without_token(client: TestClient, monkeypatch):
    monkeypatch.setenv("ADMIN_TRUSTED_IPS", "testclient")
    res = client.post(
        "/api/cmd", json={"boxId": 1, "type": "INIT_ROUTE", "holdsCount": 5}
    )
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "ADMIN_SESSION_REQUIRED"


def test_admin_endpoint_trusted_admin_ip_allowed_without_token(
    client: TestClient, monkeypatch
):
    monkeypatch.setenv("ADMIN_TRUSTED_IPS", "testclient")
    res = client.get("/api/admin/audit/events")
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "ADMIN_SESSION_REQUIRED"


def test_cmd_forbidden_box(client: TestClient):
    token = _token("judge", boxes=[2])
    res = client.post(
        "/api/cmd",
        headers={"Authorization": f"Bearer {token}"},
        json={"boxId": 1, "type": "INIT_ROUTE"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "forbidden_box"


def test_cmd_judge_allowed(client: TestClient):
    token = _token("judge", boxes=[1])
    payload = {"boxId": 1, "type": "INIT_ROUTE", "holdsCount": 5}
    res = client.post(
        "/api/cmd",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert 1 in live.state_map


def test_ws_judge_allowed(client: TestClient):
    token = _token("judge", boxes=[1])
    with client.websocket_connect(f"/api/ws/1?token={token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "STATE_SNAPSHOT"
        assert msg["boxId"] == 1


def test_ws_judge_forbidden_box(client: TestClient):
    token = _token("judge", boxes=[2])
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/ws/1?token={token}") as ws:
            ws.receive_text()
    assert exc.value.code == 4403


def test_admin_password_login_is_disabled(client: TestClient, monkeypatch):
    monkeypatch.setattr(auth_api, "load_users", lambda: {})
    res = client.post(
        "/api/auth/login", json={"username": "admin", "password": "ignored"}
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "admin_password_login_disabled"


def test_admin_role_password_login_is_disabled(client: TestClient, monkeypatch):
    users = {
        "ops-admin": {
            "username": "ops-admin",
            "password_hash": hash_password("secret"),
            "role": "admin",
            "assigned_boxes": [],
            "is_active": True,
        }
    }
    monkeypatch.setattr(auth_api, "load_users", lambda: users)
    res = client.post(
        "/api/auth/login", json={"username": "ops-admin", "password": "secret"}
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "admin_password_login_disabled"


def test_judge_login_still_works(client: TestClient, monkeypatch):
    users = {
        "Box 1": {
            "username": "Box 1",
            "password_hash": hash_password("judge-pass"),
            "role": "judge",
            "assigned_boxes": [1],
            "is_active": True,
        }
    }
    monkeypatch.setattr(auth_api, "load_users", lambda: users)
    res = client.post(
        "/api/auth/login", json={"username": "Box 1", "password": "judge-pass"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["role"] == "judge"
    assert body["boxes"] == [1]
    assert "escalada_token" in res.cookies


def test_recovery_consume_blocked_when_admin_license_invalid(
    client: TestClient, monkeypatch
):
    monkeypatch.setenv("ADMIN_TRUSTED_IPS", "testclient")
    monkeypatch.setattr(
        admin_license,
        "check_admin_license",
        lambda force_refresh=False, now_utc=None: {
            "valid": False,
            "reason": "expired",
            "checked_at": None,
            "expires_at": None,
            "in_grace": False,
            "grace_until": None,
            "license_id": None,
            "kid": "default",
        },
    )
    response = client.post(
        "/api/admin/recovery/consume",
        json={"code": "ABCD-EFGH-JKLM-NPQR"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ADMIN_LICENSE_REQUIRED"


def test_recovery_consume_requires_trusted_ip(client: TestClient, monkeypatch):
    monkeypatch.setenv("ADMIN_TRUSTED_IPS", "127.0.0.1,::1,localhost")
    admin_jwt = _token("admin", boxes=[])
    response = client.post(
        "/api/admin/recovery/consume",
        headers={"Authorization": f"Bearer {admin_jwt}"},
        json={"code": "ABCD-EFGH-JKLM-NPQR"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ADMIN_TRUSTED_IP_REQUIRED"


def test_admin_unlock_and_action_pass_with_override_when_usb_missing(
    client: TestClient, monkeypatch
):
    monkeypatch.setenv("ADMIN_TRUSTED_IPS", "testclient")
    monkeypatch.setattr(
        usb_license,
        "check_license",
        lambda force_refresh=False: {
            "valid": False,
            "reason": "not_found",
            "mountpoint": None,
            "checked_at": None,
        },
    )
    monkeypatch.setattr(recovery_codes, "is_override_active", lambda now_utc=None: True)
    monkeypatch.setattr(
        recovery_codes,
        "get_recovery_status",
        lambda now_utc=None: {
            "recovery_override_active": True,
            "recovery_override_until": datetime.now(timezone.utc) + timedelta(hours=23),
            "recovery_codes_remaining": 19,
        },
    )

    unlock_response = client.post("/api/admin/unlock")
    assert unlock_response.status_code == 200
    token = unlock_response.json()["token"]

    admin_action_response = client.get(
        "/api/admin/backup/full",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert admin_action_response.status_code == 200


def test_judge_cmd_unaffected_by_admin_security_overrides(
    client: TestClient, monkeypatch
):
    monkeypatch.setattr(
        admin_license,
        "check_admin_license",
        lambda force_refresh=False, now_utc=None: {
            "valid": False,
            "reason": "expired",
            "checked_at": None,
            "expires_at": None,
            "in_grace": False,
            "grace_until": None,
            "license_id": None,
            "kid": "default",
        },
    )
    monkeypatch.setattr(
        usb_license,
        "check_license",
        lambda force_refresh=False: {
            "valid": False,
            "reason": "not_found",
            "mountpoint": None,
            "checked_at": None,
        },
    )
    judge_token = _token("judge", boxes=[1])
    payload = {"boxId": 1, "type": "INIT_ROUTE", "holdsCount": 5}
    response = client.post(
        "/api/cmd",
        headers={"Authorization": f"Bearer {judge_token}"},
        json=payload,
    )
    assert response.status_code == 200
