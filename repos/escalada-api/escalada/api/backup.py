import asyncio
import csv
import io
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from escalada.api import live
from escalada.api.official_export import build_official_results_zip, safe_zip_component
from escalada.api.save_ranking import _build_overall_df, _format_time
from escalada.auth.deps import require_admin_action
from escalada.storage.json_store import save_box_state

router = APIRouter()


def _snapshot_from_state(box_id: int, state: Dict[str, Any]) -> Dict[str, Any]:
    remaining = state.get("remaining")
    if live._server_side_timer_enabled():
        remaining = live._compute_remaining(state, live._now_ms())

    scores = state.get("scores", {})
    times = state.get("times", {})
    comps_state = state.get("competitors") or []
    clubs: Dict[str, str] = {}
    if isinstance(comps_state, list):
        for comp in comps_state:
            if not isinstance(comp, dict):
                continue
            name = comp.get("nume") or comp.get("name")
            club = comp.get("club")
            if isinstance(name, str) and name.strip() and isinstance(club, str) and club.strip():
                clubs[name] = club.strip()
    snapshot = {
        "boxId": box_id,
        "competitionId": None,
        "initiated": state.get("initiated", False),
        "holdsCount": state.get("holdsCount", 0),
        "holdsCounts": state.get("holdsCounts") or [],
        "routeIndex": state.get("routeIndex", 1),
        "routesCount": state.get("routesCount") or state.get("routes_count"),
        "currentClimber": state.get("currentClimber", ""),
        "started": state.get("started", False),
        "timerState": state.get("timerState", "idle"),
        "holdCount": state.get("holdCount", 0.0),
        "competitors": state.get("competitors", []),
        "categorie": state.get("categorie", ""),
        "clubs": clubs,
        "registeredTime": state.get("lastRegisteredTime"),
        "remaining": remaining,
        "timeCriterionEnabled": state.get("timeCriterionEnabled", False),
        "timeTiebreakPreference": state.get("timeTiebreakPreference"),
        "timeTiebreakDecisions": state.get("timeTiebreakDecisions") or {},
        "timeTiebreakResolvedFingerprint": state.get("timeTiebreakResolvedFingerprint"),
        "timeTiebreakResolvedDecision": state.get("timeTiebreakResolvedDecision"),
        "prevRoundsTiebreakPreference": state.get("prevRoundsTiebreakPreference"),
        "prevRoundsTiebreakDecisions": state.get("prevRoundsTiebreakDecisions") or {},
        "prevRoundsTiebreakOrders": state.get("prevRoundsTiebreakOrders") or {},
        "prevRoundsTiebreakRanks": state.get("prevRoundsTiebreakRanks") or {},
        "prevRoundsTiebreakLineageRanks": state.get("prevRoundsTiebreakLineageRanks")
        or {},
        "prevRoundsTiebreakResolvedFingerprint": state.get("prevRoundsTiebreakResolvedFingerprint"),
        "prevRoundsTiebreakResolvedDecision": state.get("prevRoundsTiebreakResolvedDecision"),
        "timerPreset": state.get("timerPreset"),
        "timerPresetSec": state.get("timerPresetSec"),
        "sessionId": state.get("sessionId"),
        "boxVersion": state.get("boxVersion", 0),
        "competitorsAll": [],
        "scores": scores,
        "times": times,
    }

    if not snapshot.get("routesCount"):
        snapshot["routesCount"] = state.get("routeIndex") or 1

    if not snapshot.get("competitorsAll"):
        for idx, comp in enumerate(comps_state):
            if not isinstance(comp, dict):
                continue
            snapshot["competitorsAll"].append(
                {
                    "id": None,
                    "name": comp.get("nume") or comp.get("name") or f"comp_{idx}",
                    "category": comp.get("categorie") or comp.get("category"),
                    "club": comp.get("club") if isinstance(comp.get("club"), str) else None,
                    "bib": comp.get("bib"),
                    "boxId": box_id,
                }
            )

    try:
        route_count = snapshot.get("routesCount") or 0
        if scores and route_count:
            df_overall = _build_overall_df(
                type(
                    "Payload",
                    (),
                    {
                        "scores": scores,
                        "route_count": route_count,
                        "clubs": clubs,
                        "include_clubs": bool(clubs),
                        "times": times,
                        "use_time_tiebreak": bool(snapshot.get("timeCriterionEnabled")),
                    },
                ),
                times,
            )
            snapshot["ranking"] = df_overall.to_dict(orient="records")
        else:
            snapshot["ranking"] = []
    except Exception:
        snapshot["ranking"] = []

    return snapshot


async def _fetch_box_snapshot(box_id: int) -> Dict[str, Any] | None:
    state = live.state_map.get(box_id) or live._default_state()
    return _snapshot_from_state(box_id, state)


@router.get("/backup/box/{box_id}")
async def backup_box(box_id: int, claims=Depends(require_admin_action)):
    snap = await _fetch_box_snapshot(box_id)
    if not snap:
        raise HTTPException(status_code=404, detail="box_not_found")
    return {"status": "ok", "snapshot": snap}


@router.get("/backup/full")
async def backup_full(claims=Depends(require_admin_action)):
    snapshots = await collect_snapshots()
    return {"status": "ok", "snapshots": snapshots}


@router.get("/backup/last")
async def backup_last(download: bool = False, claims=Depends(require_admin_action)):
    out_dir = Path(os.getenv("BACKUP_DIR", "backups"))
    last_file = latest_backup_file(out_dir)
    if not last_file:
        raise HTTPException(status_code=404, detail="backup_not_found")

    if download:
        return FileResponse(
            last_file,
            media_type="application/json",
            filename=last_file.name,
        )

    mtime = datetime.fromtimestamp(last_file.stat().st_mtime, tz=timezone.utc)
    return {"status": "ok", "filename": last_file.name, "timestamp": mtime.isoformat()}


@router.get("/export/box/{box_id}")
async def export_box_csv(box_id: int, claims=Depends(require_admin_action)):
    """Export current state to CSV (lightweight per-box export)."""

    snap = await _fetch_box_snapshot(box_id)
    if not snap:
        raise HTTPException(status_code=404, detail="box_not_found")

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["boxId", snap["boxId"]])
    writer.writerow(["competitionId", snap["competitionId"]])
    writer.writerow(["categorie", snap.get("categorie", "")])
    writer.writerow(["boxVersion", snap.get("boxVersion", 0)])
    writer.writerow([])

    writer.writerow(["Current state"])
    writer.writerow(["holdCount", snap.get("holdCount", 0)])
    writer.writerow(["started", snap.get("started", False)])
    writer.writerow(["timerState", snap.get("timerState", "idle")])
    writer.writerow(["currentClimber", snap.get("currentClimber", "")])
    writer.writerow(["remaining", snap.get("remaining")])
    writer.writerow([])

    writer.writerow(["Competitors (all)"])
    writer.writerow(["id", "name", "category", "bib", "boxId"])
    for c in snap.get("competitorsAll", []):
        writer.writerow(
            [
                c.get("id"),
                c.get("name"),
                c.get("category"),
                c.get("bib"),
                c.get("boxId"),
            ]
        )

    scores = snap.get("scores") or {}
    times = snap.get("times") or {}
    if scores:
        writer.writerow([])
        writer.writerow(["Scores (per competitor)"])
        max_routes = max((len(v or []) for v in scores.values()), default=0)
        headers = ["Name"] + [f"Route {i+1}" for i in range(max_routes)]
        use_time = bool(snap.get("timeCriterionEnabled"))
        if use_time:
            for i in range(max_routes):
                headers.append(f"Time {i+1}")
        writer.writerow(headers)
        for name, arr in scores.items():
            row = [name]
            arr = arr or []
            for i in range(max_routes):
                row.append(arr[i] if i < len(arr) else "")
            if use_time:
                t_arr = times.get(name, [])
                for i in range(max_routes):
                    row.append(_format_time(t_arr[i]) if i < len(t_arr) else "")
            writer.writerow(row)

    ranking = snap.get("ranking") or []
    if ranking:
        writer.writerow([])
        writer.writerow(["Ranking (overall)"])
        headers = ranking[0].keys()
        writer.writerow(headers)
        for row in ranking:
            writer.writerow([row.get(h, "") for h in headers])

    csv_bytes = output.getvalue().encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=box_{box_id}_export.csv"},
    )


@router.get("/export/official/box/{box_id}")
async def export_official_results_zip(box_id: int, claims=Depends(require_admin_action)):
    """Export "official" results bundle (ZIP with XLSX+PDF) for a box."""

    snap = await _fetch_box_snapshot(box_id)
    if not snap:
        raise HTTPException(status_code=404, detail="box_not_found")

    try:
        zip_bytes = build_official_results_zip(snap)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    folder = safe_zip_component(str(snap.get("categorie") or f"box_{box_id}"))
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"official_{folder}_box{box_id}_{ts}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


MAX_RESTORE_SNAPSHOTS = 50
RESTORE_PUBLIC_UPDATE_TYPE = "BOX_STATUS_UPDATE"


class RestoreSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    boxId: int = Field(ge=0, le=9999)
    initiated: bool | None = None
    holdsCount: int | float | None = None
    holdsCounts: list[int] | None = None
    routeIndex: int | None = None
    routesCount: int | None = None
    currentClimber: str | None = None
    started: bool | None = None
    timerState: str | None = None
    holdCount: int | float | None = None
    competitors: list[dict[str, Any]] | None = None
    categorie: str | None = None
    registeredTime: int | float | None = None
    remaining: int | float | None = None
    timerPreset: str | None = None
    timerPresetSec: int | float | None = None
    scores: dict[str, Any] | None = None
    times: dict[str, Any] | None = None
    timeCriterionEnabled: bool | None = None
    sessionId: str | None = None
    boxVersion: int | None = None


class RestoreRequest(BaseModel):
    snapshots: List[RestoreSnapshot]
    box_ids: List[int] | None = None

    @field_validator("snapshots")
    @classmethod
    def _validate_snapshots_count(cls, value: List[RestoreSnapshot]) -> List[RestoreSnapshot]:
        if len(value) > MAX_RESTORE_SNAPSHOTS:
            raise ValueError("too_many_snapshots")
        return value

    @field_validator("box_ids")
    @classmethod
    def _validate_box_ids(cls, value: List[int] | None) -> List[int] | None:
        if value is None:
            return value
        if len(value) > MAX_RESTORE_SNAPSHOTS:
            raise ValueError("too_many_box_ids")
        if any(box_id < 0 or box_id > 9999 for box_id in value):
            raise ValueError("invalid_box_id")
        return value


def _snapshot_data(snapshot: RestoreSnapshot | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(snapshot, RestoreSnapshot):
        return snapshot.model_dump()
    return dict(snapshot)


def _state_from_backup_snapshot(snapshot: RestoreSnapshot | Dict[str, Any]) -> Dict[str, Any]:
    """Convert backup snapshot back into internal live state shape."""
    snapshot_data = _snapshot_data(snapshot)

    session_id = snapshot_data.get("sessionId")
    box_version = snapshot_data.get("boxVersion", 0) or 0

    state = live._default_state(session_id)
    state.update(
        {
            "initiated": bool(snapshot_data.get("initiated", False)),
            "holdsCount": snapshot_data.get("holdsCount", 0) or 0,
            "routeIndex": snapshot_data.get("routeIndex", 1) or 1,
            "routesCount": snapshot_data.get("routesCount")
            or snapshot_data.get("routes_count")
            or 1,
            "holdsCounts": snapshot_data.get("holdsCounts") or [],
            "currentClimber": snapshot_data.get("currentClimber", "") or "",
            "started": bool(snapshot_data.get("started", False)),
            "timerState": snapshot_data.get("timerState", "idle") or "idle",
            "holdCount": snapshot_data.get("holdCount", 0.0) or 0.0,
            "competitors": snapshot_data.get("competitors", []) or [],
            "categorie": snapshot_data.get("categorie", "") or "",
            "lastRegisteredTime": snapshot_data.get("registeredTime"),
            "remaining": snapshot_data.get("remaining"),
            "timerPreset": snapshot_data.get("timerPreset"),
            "timerPresetSec": snapshot_data.get("timerPresetSec"),
            "scores": snapshot_data.get("scores") or {},
            "times": snapshot_data.get("times") or {},
            "timeCriterionEnabled": snapshot_data.get("timeCriterionEnabled"),
            "sessionId": session_id or state.get("sessionId"),
            "boxVersion": box_version,
        }
    )
    return state


def _normalize_restore_snapshots(
    snapshots: List[RestoreSnapshot | Dict[str, Any]],
) -> list[RestoreSnapshot]:
    if len(snapshots) > MAX_RESTORE_SNAPSHOTS:
        raise ValueError("too_many_snapshots")
    normalized: list[RestoreSnapshot] = []
    for snapshot in snapshots:
        if isinstance(snapshot, RestoreSnapshot):
            normalized.append(snapshot)
        else:
            normalized.append(RestoreSnapshot.model_validate(snapshot))
    return normalized


async def _get_live_box_lock(box_id: int) -> asyncio.Lock:
    async with live.init_lock:
        lock = live.state_locks.get(box_id)
        if lock is None:
            lock = asyncio.Lock()
            live.state_locks[box_id] = lock
        return lock


async def restore_snapshots_json(
    snapshots: List[RestoreSnapshot | Dict[str, Any]],
    *,
    box_ids: List[int] | None = None,
) -> list[int]:
    normalized_snapshots = _normalize_restore_snapshots(snapshots)
    if box_ids is not None:
        if len(box_ids) > MAX_RESTORE_SNAPSHOTS or any(
            box_id < 0 or box_id > 9999 for box_id in box_ids
        ):
            raise ValueError("invalid_box_ids")
    allowed_box_ids = set(box_ids or [])
    restored: list[int] = []
    for snap in normalized_snapshots:
        box_id = snap.boxId
        if allowed_box_ids and box_id not in allowed_box_ids:
            continue

        state = _state_from_backup_snapshot(snap)
        lock = await _get_live_box_lock(box_id)
        async with lock:
            live.state_map[box_id] = state
            await save_box_state(box_id, state)
        await live._send_state_snapshot(box_id)
        await live._broadcast_public_box_update(box_id, RESTORE_PUBLIC_UPDATE_TYPE)
        restored.append(box_id)
    return restored


@router.post("/restore")
async def restore_backup(payload: RestoreRequest, claims=Depends(require_admin_action)):
    try:
        restored = await restore_snapshots_json(
            payload.snapshots,
            box_ids=payload.box_ids,
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"status": "ok", "restored": restored}


async def collect_snapshots() -> List[Dict[str, Any]]:
    """Collect snapshots for all boxes from in-memory state_map (thread-safe)."""
    states = await live.get_all_states_snapshot()
    snapshots: List[Dict[str, Any]] = []
    for box_id, state in states.items():
        snapshots.append(_snapshot_from_state(int(box_id), state))
    return snapshots


async def write_backup_file(output_dir: Path, snapshots: List[Dict[str, Any]]) -> Path:
    """Persist snapshots to a JSON file on disk."""

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    suffix = uuid.uuid4().hex[:8]
    path = output_dir / f"backup_{ts}_{suffix}.json"
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps({"snapshots": snapshots}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)
    return path


def latest_backup_file(output_dir: Path) -> Path | None:
    files = sorted(
        output_dir.glob("backup_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None
