"""USB license and admin USB-session endpoints."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from escalada.auth.deps import is_trusted_admin_ip, require_role
from escalada.security import (
    admin_license,
    admin_session,
    license_events,
    recovery_codes,
    usb_license,
)
from escalada.storage.json_store import append_audit_event, build_audit_event

router = APIRouter(tags=["license"])


class RecoveryConsumeRequest(BaseModel):
    code: str


def _to_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _to_iso(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_iso(item) for item in value]
    return value


def _build_status_payload(
    license_status: dict[str, Any],
    admin_unlocked: bool,
    *,
    admin_license_status: dict[str, Any] | None = None,
    recovery_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    admin_license_data = admin_license_status or admin_license.check_admin_license()
    recovery_data = recovery_status or recovery_codes.get_recovery_status()
    return {
        "license_valid": bool(license_status.get("valid")),
        "license_reason": str(license_status.get("reason") or "error"),
        "license_mountpoint": license_status.get("mountpoint"),
        "checked_at": _to_iso(license_status.get("checked_at")),
        "admin_unlocked": bool(admin_unlocked),
        "admin_license_valid": bool(admin_license_data.get("valid")),
        "admin_license_reason": str(admin_license_data.get("reason") or "error"),
        "admin_license_expires_at": _to_iso(admin_license_data.get("expires_at")),
        "admin_license_in_grace": bool(admin_license_data.get("in_grace")),
        "admin_license_grace_until": _to_iso(admin_license_data.get("grace_until")),
        "admin_license_id": admin_license_data.get("license_id"),
        "recovery_override_active": bool(recovery_data.get("recovery_override_active")),
        "recovery_override_until": _to_iso(
            recovery_data.get("recovery_override_until")
        ),
        "recovery_codes_remaining": int(
            recovery_data.get("recovery_codes_remaining") or 0
        ),
    }


def _sse_event(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(_to_iso(data), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


async def _append_recovery_audit(
    *,
    request: Request,
    claims: dict[str, Any],
    outcome: str,
    code_id: str | None = None,
    error_code: str | None = None,
) -> None:
    actor = {
        "username": claims.get("sub"),
        "role": claims.get("role"),
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    payload = {
        "outcome": outcome,
        "error_code": error_code,
        "code_id": code_id,
    }
    try:
        event = build_audit_event(
            action="ADMIN_RECOVERY_CONSUME",
            payload=payload,
            box_id=None,
            state=None,
            actor=actor,
        )
        await append_audit_event(event)
    except Exception:
        # Best-effort audit logging; never block the emergency flow on audit I/O failures.
        return


@router.get("/license/status")
async def license_status():
    license_status_data = usb_license.check_license()
    admin_state = await admin_session.get_status()
    admin_license_status = admin_license.check_admin_license()
    recovery_status_data = recovery_codes.get_recovery_status()
    return _build_status_payload(
        license_status=license_status_data,
        admin_unlocked=bool(admin_state.get("unlocked")),
        admin_license_status=admin_license_status,
        recovery_status=recovery_status_data,
    )


@router.post("/admin/unlock")
async def admin_unlock(claims=Depends(require_role(["admin"]))):
    admin_license_status_data = admin_license.check_admin_license(force_refresh=True)
    if not admin_license_status_data.get("valid"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ADMIN_LICENSE_REQUIRED",
                "reason": admin_license_status_data.get("reason"),
            },
        )

    license_status_data = usb_license.check_license(force_refresh=True)
    recovery_status_data = recovery_codes.get_recovery_status()
    if not license_status_data.get("valid") and not recovery_status_data.get(
        "recovery_override_active"
    ):
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
        **_build_status_payload(
            license_status_data,
            bool(admin_state.get("unlocked")),
            admin_license_status=admin_license_status_data,
            recovery_status=recovery_status_data,
        ),
    }


@router.post("/admin/lock")
async def admin_lock(claims=Depends(require_role(["admin"]))):
    state_changed = await admin_session.lock()
    if state_changed:
        await license_events.publish("admin_locked", {"reason": "manual_lock"})
    license_status_data = usb_license.check_license()
    admin_license_status_data = admin_license.check_admin_license()
    recovery_status_data = recovery_codes.get_recovery_status()
    return {
        "status": "ok",
        **_build_status_payload(
            license_status_data,
            admin_unlocked=False,
            admin_license_status=admin_license_status_data,
            recovery_status=recovery_status_data,
        ),
    }


@router.post("/admin/recovery/consume")
async def consume_recovery_code(
    payload: RecoveryConsumeRequest,
    request: Request,
    claims=Depends(require_role(["admin"])),
):
    request_ip = request.client.host if request.client else None
    if not is_trusted_admin_ip(request_ip):
        await _append_recovery_audit(
            request=request,
            claims=claims if isinstance(claims, dict) else {},
            outcome="rejected_untrusted_ip",
            error_code="ADMIN_TRUSTED_IP_REQUIRED",
        )
        raise HTTPException(
            status_code=403,
            detail={"code": "ADMIN_TRUSTED_IP_REQUIRED"},
        )

    admin_license_status_data = admin_license.check_admin_license(force_refresh=True)
    if not admin_license_status_data.get("valid"):
        await _append_recovery_audit(
            request=request,
            claims=claims if isinstance(claims, dict) else {},
            outcome="rejected_admin_license",
            error_code="ADMIN_LICENSE_REQUIRED",
        )
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ADMIN_LICENSE_REQUIRED",
                "reason": admin_license_status_data.get("reason"),
            },
        )

    try:
        consume_result = await asyncio.to_thread(
            recovery_codes.consume_recovery_code,
            payload.code,
            request_ip or "unknown",
        )
    except recovery_codes.RecoveryRateLimitError:
        await _append_recovery_audit(
            request=request,
            claims=claims if isinstance(claims, dict) else {},
            outcome="rate_limited",
            error_code="RECOVERY_RATE_LIMIT",
        )
        raise HTTPException(
            status_code=429,
            detail={"code": "RECOVERY_RATE_LIMIT"},
        )
    except recovery_codes.RecoveryOverrideActiveError as exc:
        await _append_recovery_audit(
            request=request,
            claims=claims if isinstance(claims, dict) else {},
            outcome="override_already_active",
            error_code="OVERRIDE_ALREADY_ACTIVE",
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "OVERRIDE_ALREADY_ACTIVE",
                "override_until": exc.active_until.isoformat(),
            },
        )
    except recovery_codes.RecoveryInvalidCodeError:
        await _append_recovery_audit(
            request=request,
            claims=claims if isinstance(claims, dict) else {},
            outcome="invalid_code",
            error_code="RECOVERY_CODE_INVALID",
        )
        raise HTTPException(
            status_code=400,
            detail={"code": "RECOVERY_CODE_INVALID"},
        )

    override_until = consume_result.get("override_until")
    remaining = int(consume_result.get("remaining") or 0)
    code_id = consume_result.get("code_id")
    await _append_recovery_audit(
        request=request,
        claims=claims if isinstance(claims, dict) else {},
        outcome="consumed",
        code_id=str(code_id) if code_id else None,
    )

    license_status_data = usb_license.check_license(force_refresh=True)
    admin_state = await admin_session.get_status()
    status_payload = _build_status_payload(
        license_status=license_status_data,
        admin_unlocked=bool(admin_state.get("unlocked")),
        admin_license_status=admin_license_status_data,
        recovery_status={
            "recovery_override_active": True,
            "recovery_override_until": override_until,
            "recovery_codes_remaining": remaining,
        },
    )
    await license_events.publish("license_status_changed", status_payload)

    return {
        "ok": True,
        "override_until": _to_iso(override_until),
        "remaining": remaining,
    }


@router.get("/license/events")
async def license_events_stream(request: Request):
    subscriber = await license_events.subscribe()

    async def stream():
        try:
            license_status_data = usb_license.check_license()
            admin_state = await admin_session.get_status()
            admin_license_status_data = admin_license.check_admin_license()
            recovery_status_data = recovery_codes.get_recovery_status()
            initial_payload = _build_status_payload(
                license_status_data,
                bool(admin_state.get("unlocked")),
                admin_license_status=admin_license_status_data,
                recovery_status=recovery_status_data,
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
