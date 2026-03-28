from __future__ import annotations

from typing import Any, Callable


def apply_submit_score(
    new_state: dict[str, Any],
    cmd: dict[str, Any],
    payload: dict[str, Any],
    *,
    coerce_optional_time: Callable[[Any], float | None],
    coerce_idx: Callable[[Any], int | None],
    compute_preparing_climber: Callable[[list[dict], str], str],
) -> bool:
    raw_time = cmd.get("registeredTime")
    if raw_time is None:
        raw_time = new_state.get("lastRegisteredTime")
    effective_time = coerce_optional_time(raw_time)
    payload["registeredTime"] = effective_time

    competitors = new_state.get("competitors") or []
    idx = None
    if "idx" in cmd:
        raw_idx = cmd.get("idx")
        if raw_idx not in (None, ""):
            idx = coerce_idx(raw_idx)
            if idx is None:
                raise ValueError("SUBMIT_SCORE idx must be an int or numeric string")
    elif "competitorIdx" in cmd:
        raw_idx = cmd.get("competitorIdx")
        if raw_idx not in (None, ""):
            idx = coerce_idx(raw_idx)
            if idx is None:
                raise ValueError(
                    "SUBMIT_SCORE competitorIdx must be an int or numeric string"
                )

    competitor_name = cmd.get("competitor")
    if idx is not None:
        if idx < 0 or idx >= len(competitors):
            raise ValueError("SUBMIT_SCORE idx out of range")
        comp = competitors[idx]
        if not isinstance(comp, dict):
            raise ValueError("SUBMIT_SCORE idx refers to invalid competitor")
        resolved_name = comp.get("nume")
        if not isinstance(resolved_name, str) or not resolved_name.strip():
            raise ValueError("SUBMIT_SCORE idx refers to invalid competitor")
        competitor_name = resolved_name
        payload["competitor"] = competitor_name

    active_name = new_state.get("currentClimber") or ""
    route_idx = max((new_state.get("routeIndex") or 1) - 1, 0)
    if competitor_name:
        scores = new_state.get("scores") or {}
        times = new_state.get("times") or {}
        if cmd.get("score") is not None:
            arr = scores.get(competitor_name) or []
            while len(arr) <= route_idx:
                arr.append(None)
            arr[route_idx] = cmd.get("score")
            scores[competitor_name] = arr
        if effective_time is not None:
            tarr = times.get(competitor_name) or []
            while len(tarr) <= route_idx:
                tarr.append(None)
            tarr[route_idx] = effective_time
            times[competitor_name] = tarr
        new_state["scores"] = scores
        new_state["times"] = times

    new_state["started"] = False
    new_state["timerState"] = "idle"
    new_state["holdCount"] = 0.0
    new_state["lastRegisteredTime"] = effective_time
    new_state["remaining"] = None

    if competitors:
        for comp in competitors:
            if not isinstance(comp, dict):
                continue
            if comp.get("nume") == competitor_name:
                comp["marked"] = True
                break
        if competitor_name and competitor_name == active_name:
            next_active = compute_preparing_climber(competitors, active_name)
            new_state["currentClimber"] = next_active
        new_state["preparingClimber"] = compute_preparing_climber(
            competitors, new_state.get("currentClimber") or ""
        )
    return True

