"""Command handling extracted from live.py.

This module keeps /api/cmd processing logic isolated from transport route setup.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from fastapi import HTTPException, Request


async def handle_command(
    *,
    cmd: Any,
    request: Request | None,
    validation_enabled: bool,
    logger: Any,
    validated_cmd_cls: type,
    check_rate_limit: Callable[[int, str], tuple[bool, str]],
    init_lock: Any,
    state_locks: dict[int, Any],
    ensure_state: Callable[[int], Any],
    validate_session_and_version: Callable[..., Any],
    apply_command: Callable[[dict[str, Any], dict[str, Any]], Any],
    server_side_timer_enabled: Callable[[], bool],
    apply_server_side_timer: Callable[[dict[str, Any], dict[str, Any], int], None],
    now_ms: Callable[[], int],
    persist_state: Callable[[int, dict[str, Any], str, dict[str, Any]], Any],
    broadcast_to_box: Callable[[int, dict[str, Any]], Any],
    send_state_snapshot: Callable[[int], Any],
    public_update_type: Callable[[str], str | None],
    broadcast_public_box_update: Callable[[int, str], Any],
) -> dict[str, Any]:
    # Map legacy "time" field to registeredTime when provided.
    if cmd.registeredTime is None and cmd.time is not None:
        cmd.registeredTime = cmd.time

    try:
        if validation_enabled:
            cmd_data = {k: v for k, v in cmd.model_dump().items() if v is not None}
            if "time" in cmd_data and "registeredTime" not in cmd_data:
                cmd_data["registeredTime"] = cmd_data.pop("time")
            validated_cmd = validated_cmd_cls(**cmd_data)
        else:
            validated_cmd = cmd
    except Exception as exc:
        logger.warning("Command validation failed for box %s: %s", cmd.boxId, exc)
        raise HTTPException(status_code=400, detail=f"Invalid command: {str(exc)}")

    cmd = validated_cmd

    if validation_enabled:
        is_allowed, reason = check_rate_limit(cmd.boxId, cmd.type)
        if not is_allowed:
            logger.warning("Rate limit exceeded for box %s: %s", cmd.boxId, reason)
            raise HTTPException(status_code=429, detail=reason)

    async with init_lock:
        if cmd.boxId not in state_locks:
            state_locks[cmd.boxId] = asyncio.Lock()
        lock = state_locks[cmd.boxId]

    async with lock:
        sm = await ensure_state(cmd.boxId)

        if validation_enabled:
            validation_error = validate_session_and_version(
                sm,
                cmd.model_dump(),
                require_session=cmd.type != "INIT_ROUTE",
            )
            if validation_error:
                if validation_error.status_code:
                    logger.warning(
                        "Command %s for box %s missing sessionId",
                        cmd.type,
                        cmd.boxId,
                    )
                    raise HTTPException(
                        status_code=validation_error.status_code,
                        detail=validation_error.message,
                    )
                if validation_error.kind:
                    logger.warning(
                        "Command %s for box %s rejected: %s",
                        cmd.type,
                        cmd.boxId,
                        validation_error.kind,
                    )
                    return {"status": "ignored", "reason": validation_error.kind}

        if cmd.type == "REQUEST_STATE":
            await send_state_snapshot(cmd.boxId)
            return {"status": "ok"}

        cmd_dict = cmd.model_dump()
        if cmd.type == "RESET_PARTIAL" and request is not None:
            try:
                raw = await request.json()
                if isinstance(raw, dict):
                    for key in ("resetTimer", "clearProgress", "unmarkAll"):
                        if key in raw and isinstance(raw.get(key), bool):
                            cmd_dict[key] = raw.get(key)
            except Exception:
                pass

        outcome = apply_command(sm, cmd_dict)
        cmd_payload = outcome.cmd_payload
        if server_side_timer_enabled():
            apply_server_side_timer(sm, cmd_payload, now_ms())

        if validation_enabled:
            persist_result = await persist_state(cmd.boxId, sm, cmd.type, cmd_payload)
            if persist_result == "stale":
                return {"status": "ignored", "reason": "stale_version"}

        await broadcast_to_box(cmd.boxId, cmd_payload)

        if outcome.snapshot_required:
            await send_state_snapshot(cmd.boxId)

        update_type = public_update_type(cmd.type)
        if update_type:
            await broadcast_public_box_update(cmd.boxId, update_type)

    return {"status": "ok"}
