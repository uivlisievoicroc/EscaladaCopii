"""WebSocket helpers extracted from live.py."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from fastapi import HTTPException
from starlette.websockets import WebSocket

from escalada.auth.deps import is_trusted_admin_ip


async def heartbeat(
    ws: WebSocket,
    box_id: int,
    last_pong: dict[str, float],
    *,
    logger: Any,
    interval_sec: int = 30,
    timeout_sec: int = 60,
    include_timestamp: bool = True,
) -> None:
    while True:
        try:
            await asyncio.sleep(interval_sec)
            now = asyncio.get_event_loop().time()
            if now - (last_pong.get("ts") or 0.0) > timeout_sec:
                logger.warning("Heartbeat timeout for box %s, closing", box_id)
                try:
                    await ws.close(code=1000)
                except Exception:
                    pass
                break
            payload: dict[str, Any] = {"type": "PING"}
            if include_timestamp:
                payload["timestamp"] = now
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            logger.debug("Heartbeat error for box %s: %s", box_id, exc)
            break


async def broadcast_to_box(
    box_id: int,
    payload: dict[str, Any],
    *,
    channels: dict[int, set[WebSocket]],
    channels_lock: Any,
    logger: Any,
    timeout_sec: float = 5.0,
) -> None:
    async with channels_lock:
        sockets = list(channels.get(box_id) or set())

    dead: list[WebSocket] = []
    message = json.dumps(payload, ensure_ascii=False)
    for ws in sockets:
        try:
            await asyncio.wait_for(ws.send_text(message), timeout=timeout_sec)
        except asyncio.TimeoutError:
            logger.warning(
                "WebSocket send timeout for box %s, disconnecting slow client",
                box_id,
            )
            dead.append(ws)
            try:
                await ws.close(code=1008, reason="Send timeout")
            except Exception:
                pass
        except Exception as exc:
            logger.debug("Broadcast error to box %s: %s", box_id, exc)
            dead.append(ws)

    if dead:
        async with channels_lock:
            channel = channels.get(box_id, set())
            for ws in dead:
                channel.discard(ws)


async def broadcast_public(
    payload: dict[str, Any],
    *,
    public_channels: set[WebSocket],
    public_channels_lock: Any,
    logger: Any,
) -> None:
    async with public_channels_lock:
        sockets = list(public_channels)

    dead: list[WebSocket] = []
    message = json.dumps(payload, ensure_ascii=False)
    for ws in sockets:
        try:
            await ws.send_text(message)
        except Exception as exc:
            logger.debug("Public broadcast error: %s", exc)
            dead.append(ws)

    if dead:
        async with public_channels_lock:
            for ws in dead:
                public_channels.discard(ws)


def public_update_type(cmd_type: str) -> str | None:
    return {
        "INIT_ROUTE": "BOX_STATUS_UPDATE",
        "RESET_BOX": "BOX_STATUS_UPDATE",
        "RESET_PARTIAL": "BOX_STATUS_UPDATE",
        "START_TIMER": "BOX_FLOW_UPDATE",
        "STOP_TIMER": "BOX_FLOW_UPDATE",
        "RESUME_TIMER": "BOX_FLOW_UPDATE",
        "SET_TIMER_PRESET": "BOX_FLOW_UPDATE",
        "TIMER_SYNC": "BOX_FLOW_UPDATE",
        "REGISTER_TIME": "BOX_FLOW_UPDATE",
        "SUBMIT_SCORE": "BOX_RANKING_UPDATE",
        "MODIFY_SCORE": "BOX_RANKING_UPDATE",
        "SET_TIME_CRITERION": "BOX_RANKING_UPDATE",
        "SET_TIME_TIEBREAK_DECISION": "BOX_RANKING_UPDATE",
        "SET_PREV_ROUNDS_TIEBREAK_DECISION": "BOX_RANKING_UPDATE",
    }.get(cmd_type)


def authorize_ws(box_id: int, claims: dict[str, Any]) -> bool:
    role = claims.get("role")
    if role == "admin":
        return True
    boxes = set(claims.get("boxes") or [])
    if role == "judge":
        return int(box_id) in boxes
    if role == "viewer":
        return not boxes or int(box_id) in boxes
    return False


async def handle_private_websocket(
    ws: WebSocket,
    *,
    box_id: int,
    logger: Any,
    decode_token: Callable[[str], dict[str, Any]],
    authorize_ws_fn: Callable[[int, dict[str, Any]], bool],
    channels: dict[int, set[WebSocket]],
    channels_lock: Any,
    send_state_snapshot: Callable[[int, set[WebSocket] | None], Any],
    heartbeat_fn: Callable[[WebSocket, int, dict[str, float]], Any],
) -> None:
    peer = ws.client.host if ws.client else None

    token = ws.query_params.get("token") or ws.cookies.get("escalada_token")
    if token:
        try:
            claims = decode_token(token)
        except HTTPException as exc:
            logger.warning(
                "WS connect denied: invalid_token box=%s ip=%s detail=%s",
                box_id,
                peer,
                exc.detail,
            )
            await ws.close(code=4401, reason=exc.detail or "invalid_token")
            return
    elif is_trusted_admin_ip(peer):
        claims = {"sub": "trusted-admin", "role": "admin", "boxes": []}
    else:
        logger.warning("WS connect denied: token_required box=%s ip=%s", box_id, peer)
        await ws.close(code=4401, reason="token_required")
        return

    if not authorize_ws_fn(box_id, claims):
        logger.warning(
            "WS connect denied: forbidden box=%s ip=%s role=%s boxes=%s",
            box_id,
            peer,
            claims.get("role"),
            claims.get("boxes"),
        )
        await ws.close(code=4403, reason="forbidden_box_or_role")
        return

    await ws.accept()

    async with channels_lock:
        channels.setdefault(box_id, set()).add(ws)
        subscriber_count = len(channels[box_id])

    logger.info("Client connected to box %s, total: %s", box_id, subscriber_count)
    await send_state_snapshot(box_id, targets={ws})

    last_pong = {"ts": asyncio.get_event_loop().time()}
    heartbeat_task = asyncio.create_task(heartbeat_fn(ws, box_id, last_pong))

    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=180)
            except asyncio.TimeoutError:
                logger.warning("WebSocket receive timeout for box %s", box_id)
                break
            except Exception as exc:
                logger.warning("WebSocket receive error for box %s: %s", box_id, exc)
                break

            try:
                msg = json.loads(data) if isinstance(data, str) else data
            except json.JSONDecodeError:
                logger.debug("Invalid JSON from WS box %s", box_id)
                continue

            if not isinstance(msg, dict):
                continue

            msg_type = msg.get("type")
            if msg_type == "PONG":
                last_pong["ts"] = asyncio.get_event_loop().time()
                continue

            if msg_type == "REQUEST_STATE":
                requested_box_id = msg.get("boxId", box_id)
                try:
                    requested_box_id = int(requested_box_id)
                except Exception:
                    continue
                if requested_box_id != int(box_id) and not authorize_ws_fn(
                    requested_box_id, claims
                ):
                    logger.warning(
                        "Forbidden WS REQUEST_STATE: conn_box=%s requested_box=%s role=%s boxes=%s",
                        box_id,
                        requested_box_id,
                        claims.get("role"),
                        claims.get("boxes"),
                    )
                    continue
                logger.info("WebSocket REQUEST_STATE for box %s", requested_box_id)
                await send_state_snapshot(requested_box_id, targets={ws})
    except Exception as exc:
        logger.error("WebSocket error for box %s: %s", box_id, exc)
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        async with channels_lock:
            channels.get(box_id, set()).discard(ws)
            remaining = len(channels.get(box_id, set()))
        logger.info("Client disconnected from box %s, remaining: %s", box_id, remaining)
        try:
            await ws.close()
        except Exception:
            pass


async def handle_public_websocket(
    ws: WebSocket,
    *,
    logger: Any,
    public_channels: set[WebSocket],
    public_channels_lock: Any,
    send_public_snapshot: Callable[[set[WebSocket] | None], Any],
    heartbeat_fn: Callable[[WebSocket, int, dict[str, float]], Any],
) -> None:
    await ws.accept()

    async with public_channels_lock:
        public_channels.add(ws)

    await send_public_snapshot(targets={ws})

    last_pong = {"ts": asyncio.get_event_loop().time()}
    heartbeat_task = asyncio.create_task(heartbeat_fn(ws, -1, last_pong))

    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=180)
            except asyncio.TimeoutError:
                logger.warning("Public WebSocket receive timeout")
                break
            except Exception as exc:
                logger.warning("Public WebSocket receive error: %s", exc)
                break

            try:
                msg = json.loads(data) if isinstance(data, str) else data
            except json.JSONDecodeError:
                logger.debug("Invalid JSON from public WebSocket")
                continue

            if not isinstance(msg, dict):
                continue

            msg_type = msg.get("type")
            if msg_type == "PONG":
                last_pong["ts"] = asyncio.get_event_loop().time()
                continue
            if msg_type == "PING":
                await ws.send_text(
                    json.dumps(
                        {"type": "PONG", "timestamp": msg.get("timestamp")},
                        ensure_ascii=False,
                    )
                )
                continue
            if msg_type == "REQUEST_STATE":
                await send_public_snapshot(targets={ws})
    except Exception as exc:
        logger.error("Public WebSocket error: %s", exc)
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        async with public_channels_lock:
            public_channels.discard(ws)

        try:
            await ws.close()
        except Exception:
            pass
