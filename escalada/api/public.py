"""Public read-only API endpoints and per-box WebSocket feed."""

import asyncio
import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel
from starlette.websockets import WebSocket

from escalada.api.live_ws import (
    broadcast_to_box as broadcast_ws_box,
    heartbeat as run_heartbeat,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["public"])


class PublicBoxInfo(BaseModel):
    boxId: int
    label: str
    initiated: bool
    timerState: str | None = None
    currentClimber: str | None = None
    categorie: str | None = None


class PublicBoxesResponse(BaseModel):
    boxes: List[PublicBoxInfo]


class PublicCompetitionOfficialsResponse(BaseModel):
    federalOfficial: str = ""
    judgeChief: str = ""
    competitionDirector: str = ""
    chiefRoutesetter: str = ""


@router.get("/boxes", response_model=PublicBoxesResponse)
async def get_public_boxes() -> PublicBoxesResponse:
    """Return initiated boxes for public views."""
    from escalada.api.live import init_lock, state_map

    async with init_lock:
        items = list(state_map.items())

    boxes: List[PublicBoxInfo] = []
    for box_id, state in items:
        if not state.get("initiated", False):
            continue
        boxes.append(
            PublicBoxInfo(
                boxId=box_id,
                label=state.get("categorie") or f"Box {box_id}",
                initiated=True,
                timerState=state.get("timerState"),
                currentClimber=state.get("currentClimber"),
                categorie=state.get("categorie"),
            )
        )

    boxes.sort(key=lambda b: b.boxId)
    return PublicBoxesResponse(boxes=boxes)


@router.get("/officials", response_model=PublicCompetitionOfficialsResponse)
async def get_public_officials() -> PublicCompetitionOfficialsResponse:
    """Return global competition officials for public views."""
    from escalada.api import live as live_module

    data = live_module.get_competition_officials()
    return PublicCompetitionOfficialsResponse(
        federalOfficial=data.get("federalOfficial") or "",
        judgeChief=data.get("judgeChief") or "",
        competitionDirector=data.get("competitionDirector") or "",
        chiefRoutesetter=data.get("chiefRoutesetter") or "",
    )


# Per-box public spectators channel registry.
public_box_channels: Dict[int, set[WebSocket]] = {}
public_box_channels_lock = asyncio.Lock()


async def broadcast_to_public_box(box_id: int, payload: dict) -> None:
    """Broadcast a payload to all public subscribers of one box."""
    await broadcast_ws_box(
        box_id,
        payload,
        channels=public_box_channels,
        channels_lock=public_box_channels_lock,
        logger=logger,
        timeout_sec=5.0,
    )


async def _heartbeat(ws: WebSocket, box_id: int, last_pong: dict[str, float]) -> None:
    await run_heartbeat(
        ws,
        box_id,
        last_pong,
        logger=logger,
        interval_sec=30,
        timeout_sec=90,
        include_timestamp=False,
    )


@router.websocket("/ws/{box_id}")
async def public_box_websocket(ws: WebSocket, box_id: int) -> None:
    """Unauthenticated read-only WebSocket for one public box."""
    peer = ws.client.host if ws.client else None

    await ws.accept()

    async with public_box_channels_lock:
        public_box_channels.setdefault(box_id, set()).add(ws)
        subscriber_count = len(public_box_channels[box_id])

    logger.info("Public spectator connected box=%s ip=%s total=%s", box_id, peer, subscriber_count)

    await _send_public_box_snapshot(box_id, targets={ws})

    last_pong = {"ts": asyncio.get_event_loop().time()}
    heartbeat_task = asyncio.create_task(_heartbeat(ws, box_id, last_pong))

    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=180)
            except asyncio.TimeoutError:
                logger.warning("Public WS timeout box=%s", box_id)
                break
            except Exception as exc:
                logger.warning("Public WS receive error box=%s err=%s", box_id, exc)
                break

            try:
                msg = json.loads(data) if isinstance(data, str) else data
            except json.JSONDecodeError:
                logger.debug("Invalid JSON from public WS box=%s", box_id)
                continue

            if not isinstance(msg, dict):
                continue

            msg_type = msg.get("type")
            if msg_type == "PONG":
                last_pong["ts"] = asyncio.get_event_loop().time()
                continue

            if msg_type == "REQUEST_STATE":
                await _send_public_box_snapshot(box_id, targets={ws})
                continue

            # Public stream is read-only: ignore commands or unknown messages.
            logger.debug("Public WS box=%s ignored message type=%s", box_id, msg_type)

    except Exception as exc:
        logger.error("Public WS error box=%s err=%s", box_id, exc)
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        async with public_box_channels_lock:
            public_box_channels.get(box_id, set()).discard(ws)
            remaining = len(public_box_channels.get(box_id, set()))

        logger.info("Public spectator disconnected box=%s remaining=%s", box_id, remaining)

        try:
            await ws.close()
        except Exception:
            pass


async def _send_public_box_snapshot(box_id: int, targets: set[WebSocket] | None = None) -> None:
    """Send one box snapshot to selected sockets or all box subscribers."""
    from escalada.api.live import _build_snapshot, init_lock, state_map

    async with init_lock:
        state = state_map.get(box_id)

    if not state:
        return

    payload: Dict[str, Any] = _build_snapshot(box_id, state)

    if targets:
        for ws in list(targets):
            try:
                await ws.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception as exc:
                logger.debug("Failed to send public snapshot box=%s err=%s", box_id, exc)
    else:
        await broadcast_to_public_box(box_id, payload)
