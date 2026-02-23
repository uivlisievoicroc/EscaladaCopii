from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import escalada.api.live as live
from escalada.auth.service import create_access_token
from escalada.main import app


@pytest.fixture(autouse=True)
def patch_preload_states(monkeypatch):
    async def _noop():
        return 0

    monkeypatch.setattr(live, "preload_states", _noop)
    yield


@pytest.fixture(autouse=True)
def patch_persist_state(monkeypatch):
    async def _noop(box_id, state, action, payload):
        return "ok"

    monkeypatch.setattr(live, "_persist_state", _noop)
    yield


@pytest.fixture(autouse=True)
def patch_rate_limit(monkeypatch):
    monkeypatch.setattr(live, "check_rate_limit", lambda box_id, cmd_type: (True, "ok"))
    yield


@pytest.fixture(autouse=True)
def reset_live_state():
    live.state_map.clear()
    live.state_locks.clear()
    live.channels.clear()
    live.public_channels.clear()
    yield
    live.state_map.clear()
    live.state_locks.clear()
    live.channels.clear()
    live.public_channels.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _admin_headers() -> dict[str, str]:
    token = create_access_token(
        username="admin",
        role="admin",
        assigned_boxes=[],
        expires_minutes=60,
    )
    return {"Authorization": f"Bearer {token}"}


def _init_and_submit(client: TestClient, *, box_id: int = 0) -> None:
    headers = _admin_headers()
    init_payload = {
        "boxId": box_id,
        "type": "INIT_ROUTE",
        "categorie": "Seniors",
        "routeIndex": 1,
        "routesCount": 1,
        "holdsCount": 20,
        "competitors": [{"nume": "Ana", "club": "CSC", "marked": False}],
    }
    init_res = client.post("/api/cmd", headers=headers, json=init_payload)
    assert init_res.status_code == 200
    assert init_res.json().get("status") == "ok"

    session_id = live.state_map[box_id]["sessionId"]
    submit_payload = {
        "boxId": box_id,
        "type": "SUBMIT_SCORE",
        "competitor": "Ana",
        "score": 12.0,
        "registeredTime": 95.0,
        "sessionId": session_id,
    }
    submit_res = client.post("/api/cmd", headers=headers, json=submit_payload)
    assert submit_res.status_code == 200
    assert submit_res.json().get("status") == "ok"


def test_public_rankings_contains_lead_ranking_rows_after_submit_score(client: TestClient):
    _init_and_submit(client, box_id=0)

    res = client.get("/api/public/rankings")
    assert res.status_code == 200
    payload = res.json()
    assert payload.get("type") == "PUBLIC_STATE_SNAPSHOT"

    box = next(item for item in payload["boxes"] if item["boxId"] == 0)
    assert isinstance(box.get("leadRankingRows"), list)
    assert box["leadRankingRows"], "leadRankingRows should not be empty after SUBMIT_SCORE"
    assert box["leadRankingRows"][0]["name"] == "Ana"
    assert "leadTieEvents" in box
    assert "leadRankingResolved" in box
    assert "leadRankingErrors" in box


def test_public_ws_box_ranking_update_includes_lead_ranking_rows(client: TestClient):
    headers = _admin_headers()
    box_id = 1

    init_payload = {
        "boxId": box_id,
        "type": "INIT_ROUTE",
        "categorie": "Youth",
        "routeIndex": 1,
        "routesCount": 1,
        "holdsCount": 18,
        "competitors": [{"nume": "Mara", "marked": False}],
    }
    init_res = client.post("/api/cmd", headers=headers, json=init_payload)
    assert init_res.status_code == 200
    assert init_res.json().get("status") == "ok"
    session_id = live.state_map[box_id]["sessionId"]

    with client.websocket_connect("/api/public/ws") as ws:
        first = ws.receive_json()
        assert first.get("type") == "PUBLIC_STATE_SNAPSHOT"

        submit_payload = {
            "boxId": box_id,
            "type": "SUBMIT_SCORE",
            "competitor": "Mara",
            "score": 11.0,
            "registeredTime": 88.0,
            "sessionId": session_id,
        }
        submit_res = client.post("/api/cmd", headers=headers, json=submit_payload)
        assert submit_res.status_code == 200
        assert submit_res.json().get("status") == "ok"

        update = None
        for _ in range(5):
            message = ws.receive_json()
            if message.get("type") == "PING":
                ws.send_json({"type": "PONG", "timestamp": message.get("timestamp")})
                continue
            update = message
            break

        assert update is not None
        assert update.get("type") == "BOX_RANKING_UPDATE"
        assert update.get("box", {}).get("boxId") == box_id
        assert isinstance(update["box"].get("leadRankingRows"), list)
        assert update["box"]["leadRankingRows"], "BOX_RANKING_UPDATE should include ranking rows"
        assert update["box"]["leadRankingRows"][0]["name"] == "Mara"
