from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from escalada.api import backup, live
from escalada.auth.service import create_access_token
from escalada.main import app
from escalada.security import usb_license


def _valid_license_status() -> dict:
    return {
        "valid": True,
        "reason": "ok",
        "mountpoint": "/media/test-usb",
        "checked_at": datetime.now(timezone.utc),
    }


def _unlock_headers(client: TestClient, monkeypatch) -> dict[str, str]:
    monkeypatch.setattr(usb_license, "check_license", lambda force_refresh=False: _valid_license_status())
    token = create_access_token(username="admin-test", role="admin", assigned_boxes=[])
    client.cookies.set("escalada_token", token)
    unlock_response = client.post("/api/admin/unlock")
    assert unlock_response.status_code == 200
    return {"Authorization": f"Bearer {unlock_response.json()['token']}"}


def _snapshot(box_id: int, category: str = "Cat") -> dict:
    return {
        "boxId": box_id,
        "initiated": True,
        "holdsCount": 10,
        "holdsCounts": [10],
        "routeIndex": 1,
        "routesCount": 1,
        "currentClimber": "Alex",
        "timerState": "idle",
        "holdCount": 0,
        "competitors": [{"nume": "Alex", "marked": False}],
        "categorie": category,
        "scores": {},
        "times": {},
        "sessionId": f"session-{box_id}",
        "boxVersion": 3,
    }


def test_restore_invalid_payload_is_all_or_nothing(monkeypatch):
    live.state_map.clear()
    live.state_locks.clear()
    live.state_map[1] = {**live._default_state("original"), "categorie": "Original"}
    live.state_locks[1] = asyncio.Lock()

    client = TestClient(app, raise_server_exceptions=False)
    headers = _unlock_headers(client, monkeypatch)

    response = client.post(
        "/api/admin/restore",
        headers=headers,
        json={"snapshots": [_snapshot(2, "Valid"), {"boxId": "bad", "categorie": "Bad"}]},
    )

    assert response.status_code == 422
    assert 2 not in live.state_map
    assert live.state_map[1]["categorie"] == "Original"


def test_restore_valid_payload_persists_and_broadcasts(monkeypatch):
    live.state_map.clear()
    live.state_locks.clear()
    saved: list[tuple[int, dict]] = []
    private_broadcasts: list[int] = []
    public_broadcasts: list[tuple[int, str]] = []

    async def fake_save_box_state(box_id: int, state: dict) -> None:
        saved.append((box_id, dict(state)))

    async def fake_send_state_snapshot(box_id: int) -> None:
        private_broadcasts.append(box_id)

    async def fake_broadcast_public_box_update(box_id: int, update_type: str) -> None:
        public_broadcasts.append((box_id, update_type))

    monkeypatch.setattr(backup, "save_box_state", fake_save_box_state)
    monkeypatch.setattr(live, "_send_state_snapshot", fake_send_state_snapshot)
    monkeypatch.setattr(live, "_broadcast_public_box_update", fake_broadcast_public_box_update)

    restored = asyncio.run(backup.restore_snapshots_json([_snapshot(7, "Restore")]))

    assert restored == [7]
    assert live.state_map[7]["categorie"] == "Restore"
    assert saved == [(7, live.state_map[7])]
    assert private_broadcasts == [7]
    assert public_broadcasts == [(7, "BOX_STATUS_UPDATE")]


def test_write_backup_file_uses_unique_atomic_filenames(tmp_path):
    snapshots = [_snapshot(1)]

    first = asyncio.run(backup.write_backup_file(tmp_path, snapshots))
    second = asyncio.run(backup.write_backup_file(tmp_path, snapshots))

    assert first != second
    assert first.exists()
    assert second.exists()
    assert not list(tmp_path.glob("*.tmp"))
