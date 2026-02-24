"""USB license and admin USB-session endpoints."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from escalada.auth.deps import require_role
from escalada.security import admin_session, license_events, usb_license

router = APIRouter(tags=["license"])


def _to_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _to_iso(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_iso(item) for item in value]
    return value


def _build_status_payload(license_status: dict[str, Any], admin_unlocked: bool) -> dict[str, Any]:
    return {
        "license_valid": bool(license_status.get("valid")),
        "license_reason": str(license_status.get("reason") or "error"),
        "license_mountpoint": license_status.get("mountpoint"),
        "checked_at": _to_iso(license_status.get("checked_at")),
        "admin_unlocked": bool(admin_unlocked),
    }


def _sse_event(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(_to_iso(data), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/license/status")
async def license_status():
    license_status_data = usb_license.check_license()
    admin_state = await admin_session.get_status()
    return _build_status_payload(
        license_status=license_status_data,
        admin_unlocked=bool(admin_state.get("unlocked")),
    )


@router.post("/admin/unlock")
async def admin_unlock(claims=Depends(require_role(["admin"]))):
    license_status_data = usb_license.check_license(force_refresh=True)
    if not license_status_data.get("valid"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "LICENSE_REQUIRED",
                "reason": license_status_data.get("reason"),
            },
        )

    token = await admin_session.unlock()
    admin_state = await admin_session.get_status()
    return {
        "status": "ok",
        "token": token,
        **_build_status_payload(license_status_data, bool(admin_state.get("unlocked"))),
    }


@router.post("/admin/lock")
async def admin_lock(claims=Depends(require_role(["admin"]))):
    state_changed = await admin_session.lock()
    if state_changed:
        await license_events.publish("admin_locked", {"reason": "manual_lock"})
    license_status_data = usb_license.check_license()
    return {
        "status": "ok",
        **_build_status_payload(license_status_data, admin_unlocked=False),
    }


@router.get("/license/events")
async def license_events_stream(request: Request):
    subscriber = await license_events.subscribe()

    async def stream():
        try:
            license_status_data = usb_license.check_license()
            admin_state = await admin_session.get_status()
            initial_payload = _build_status_payload(
                license_status_data,
                bool(admin_state.get("unlocked")),
            )
            yield _sse_event("license_status_changed", initial_payload)

            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(subscriber.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                event_name = str(payload.get("event") or "license_status_changed")
                event_data = payload.get("data") or {}
                yield _sse_event(event_name, event_data)
        finally:
            await license_events.unsubscribe(subscriber)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
