import pytest
from fastapi.testclient import TestClient

import escalada.api.live as live
import escalada.api.public as public_api
from escalada.auth.service import create_access_token
from escalada.main import app
from escalada.security import usb_license


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
def reset_live_state():
    live.state_map.clear()
    live.state_locks.clear()
    live.channels.clear()
    live.public_channels.clear()
    live.competition_officials = {
        "federalOfficial": "",
        "judgeChief": "",
        "competitionDirector": "",
        "chiefRoutesetter": "",
    }
    public_api.public_box_channels.clear()
    yield
    live.state_map.clear()
    live.state_locks.clear()
    live.channels.clear()
    live.public_channels.clear()
    public_api.public_box_channels.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _valid_license_status() -> dict:
    return {
        "valid": True,
        "reason": "ok",
        "mountpoint": "/media/test-usb",
    }


def _unlock_admin_headers(client: TestClient, monkeypatch) -> dict[str, str]:
    monkeypatch.setattr(usb_license, "check_license", lambda force_refresh=False: _valid_license_status())
    admin_jwt = create_access_token(
        username="admin",
        role="admin",
        assigned_boxes=[],
        expires_minutes=60,
    )
    client.cookies.set("escalada_token", admin_jwt)
    unlock_res = client.post("/api/admin/unlock")
    assert unlock_res.status_code == 200
    return {"Authorization": f"Bearer {unlock_res.json()['token']}"}


def test_public_boxes_is_unauthenticated_and_filters_initiated(client: TestClient):
    live.state_map[1] = {
        **live._default_state(),
        "initiated": True,
        "categorie": "Youth",
        "timerState": "running",
        "currentClimber": "Ana",
    }
    live.state_map[2] = {
        **live._default_state(),
        "initiated": False,
        "categorie": "Adults",
    }

    response = client.get("/api/public/boxes")

    assert response.status_code == 200
    payload = response.json()
    assert "boxes" in payload
    assert len(payload["boxes"]) == 1
    assert payload["boxes"][0]["boxId"] == 1
    assert payload["boxes"][0]["label"] == "Youth"


def test_public_officials_is_unauthenticated(client: TestClient):
    live.competition_officials = {
        "federalOfficial": "Federal Official",
        "judgeChief": "Chief Judge",
        "competitionDirector": "Director",
        "chiefRoutesetter": "Chief Routesetter",
    }

    response = client.get("/api/public/officials")

    assert response.status_code == 200
    assert response.json() == {
        "federalOfficial": "Federal Official",
        "judgeChief": "Chief Judge",
        "competitionDirector": "Director",
        "chiefRoutesetter": "Chief Routesetter",
    }


def test_public_token_endpoint_removed(client: TestClient):
    response = client.post("/api/public/token")
    assert response.status_code in {404, 405}


def test_public_ws_box_is_unauthenticated_and_read_only(client: TestClient):
    box_id = 3
    live.state_map[box_id] = {
        **live._default_state(),
        "initiated": True,
        "categorie": "Seniors",
        "timerState": "idle",
    }

    with client.websocket_connect(f"/api/public/ws/{box_id}") as ws:
        first = ws.receive_json()
        assert first.get("type") == "STATE_SNAPSHOT"
        assert first.get("boxId") == box_id

        # Public socket must ignore commands.
        ws.send_json({"type": "START_TIMER", "boxId": box_id})
        ws.send_json({"type": "REQUEST_STATE"})

        refreshed = None
        for _ in range(5):
            message = ws.receive_json()
            if message.get("type") == "PING":
                ws.send_json({"type": "PONG"})
                continue
            refreshed = message
            break

        assert refreshed is not None
        assert refreshed.get("type") == "STATE_SNAPSHOT"

    assert live.state_map[box_id]["timerState"] == "idle"


def test_public_ws_box_receives_live_progress_snapshot(client: TestClient, monkeypatch):
    box_id = 4
    live.state_map[box_id] = {
        **live._default_state(),
        "initiated": True,
        "categorie": "Youth",
        "timerState": "running",
        "holdsCount": 12,
        "sessionId": "sess-public-progress",
        "currentClimber": "Ana",
        "competitors": [
            {"nume": "Ana", "marked": False},
            {"nume": "Mara", "marked": False},
        ],
    }
    headers = _unlock_admin_headers(client, monkeypatch)

    with client.websocket_connect(f"/api/public/ws/{box_id}") as ws:
        first = ws.receive_json()
        assert first.get("type") == "STATE_SNAPSHOT"
        assert first.get("holdCount") == 0

        response = client.post(
            "/api/cmd",
            headers=headers,
            json={
                "boxId": box_id,
                "type": "PROGRESS_UPDATE",
                "delta": 1,
                "sessionId": "sess-public-progress",
            },
        )
        assert response.status_code == 200
        assert response.json().get("status") == "ok"

        updated = None
        for _ in range(5):
            message = ws.receive_json()
            if message.get("type") == "PING":
                ws.send_json({"type": "PONG"})
                continue
            updated = message
            break

        assert updated is not None
        assert updated.get("type") == "STATE_SNAPSHOT"
        assert updated.get("boxId") == box_id
        assert updated.get("holdCount") == 1
