from io import BytesIO
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from openpyxl import Workbook

from escalada.auth.service import create_access_token
from escalada.main import app
from escalada.security import usb_license


def _admin_token() -> str:
    return create_access_token(username="admin-test", role="admin", assigned_boxes=[])


def _valid_license_status() -> dict:
    return {
        "valid": True,
        "reason": "ok",
        "mountpoint": "/media/test-usb",
        "checked_at": datetime.now(timezone.utc),
    }


def _unlock_headers(client: TestClient, monkeypatch) -> dict[str, str]:
    monkeypatch.setattr(usb_license, "check_license", lambda force_refresh=False: _valid_license_status())
    client.cookies.set("escalada_token", _admin_token())
    unlock_response = client.post("/api/admin/unlock")
    assert unlock_response.status_code == 200
    usb_token = unlock_response.json()["token"]
    return {"Authorization": f"Bearer {usb_token}"}


def _xlsx_bytes(rows: list[tuple[str | None, str | None]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Name", "Club"])
    for name, club in rows:
        ws.append([name, club])
    buffer = BytesIO()
    wb.save(buffer)
    wb.close()
    return buffer.getvalue()


def test_upload_invalid_routes_count_returns_422(monkeypatch):
    client = TestClient(app)
    headers = _unlock_headers(client, monkeypatch)
    payload = _xlsx_bytes([("Alex", "Club A")])

    res = client.post(
        "/api/admin/upload",
        data={
            "category": "Cat",
            "routesCount": "abc",
            "holdsCounts": "[10]",
            "include_clubs": "true",
        },
        files={
            "file": (
                "list.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=headers,
    )

    assert res.status_code == 422
    assert res.json()["detail"] == "invalid_routes_count"


def test_upload_invalid_holds_counts_returns_422(monkeypatch):
    client = TestClient(app)
    headers = _unlock_headers(client, monkeypatch)
    payload = _xlsx_bytes([("Alex", "Club A")])

    res = client.post(
        "/api/admin/upload",
        data={
            "category": "Cat",
            "routesCount": "1",
            "holdsCounts": "{\"bad\": true}",
            "include_clubs": "true",
        },
        files={
            "file": (
                "list.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=headers,
    )

    assert res.status_code == 422
    assert res.json()["detail"] == "invalid_holds_counts"


def test_upload_keeps_competitor_without_club_when_include_clubs_false(monkeypatch):
    client = TestClient(app)
    headers = _unlock_headers(client, monkeypatch)
    payload = _xlsx_bytes([("Alex", None), ("Bob", "Club B")])

    res = client.post(
        "/api/admin/upload",
        data={
            "category": "Cat",
            "routesCount": "1",
            "holdsCounts": "[10]",
            "include_clubs": "false",
        },
        files={
            "file": (
                "list.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=headers,
    )

    assert res.status_code == 200
    competitors = res.json()["listbox"]["concurenti"]
    assert competitors == [{"nume": "Alex"}, {"nume": "Bob"}]


def test_upload_accepts_holds_counts_numeric_strings(monkeypatch):
    client = TestClient(app)
    headers = _unlock_headers(client, monkeypatch)
    payload = _xlsx_bytes([("Alex", "Club A")])

    res = client.post(
        "/api/admin/upload",
        data={
            "category": "Cat",
            "routesCount": "1",
            "holdsCounts": "[\"10\"]",
            "include_clubs": "true",
        },
        files={
            "file": (
                "list.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=headers,
    )

    assert res.status_code == 200
    assert res.json()["listbox"]["holdsCounts"] == [10]
