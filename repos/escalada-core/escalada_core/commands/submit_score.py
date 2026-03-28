from __future__ import annotations

from typing import Any, Callable


def _resolve_competitor_name(
    cmd: dict[str, Any],
    payload: dict[str, Any],
    competitors: list[dict],
    *,
    coerce_idx: Callable[[Any], int | None],
    command_name: str,
) -> str | None:
    idx = None
    if "idx" in cmd:
        raw_idx = cmd.get("idx")
        if raw_idx not in (None, ""):
            idx = coerce_idx(raw_idx)
            if idx is None:
                raise ValueError(f"{command_name} idx must be an int or numeric string")
    elif "competitorIdx" in cmd:
        raw_idx = cmd.get("competitorIdx")
        if raw_idx not in (None, ""):
            idx = coerce_idx(raw_idx)
            if idx is None:
                raise ValueError(
                    f"{command_name} competitorIdx must be an int or numeric string"
                )

    competitor_name = cmd.get("competitor")
    if idx is not None:
        if idx < 0 or idx >= len(competitors):
            raise ValueError(f"{command_name} idx out of range")
        comp = competitors[idx]
        if not isinstance(comp, dict):
            raise ValueError(f"{command_name} idx refers to invalid competitor")
        resolved_name = comp.get("nume")
        if not isinstance(resolved_name, str) or not resolved_name.strip():
            raise ValueError(f"{command_name} idx refers to invalid competitor")
        competitor_name = resolved_name
        payload["competitor"] = competitor_name

    return competitor_name


def _upsert_score_and_time(
    new_state: dict[str, Any],
    cmd: dict[str, Any],
    competitor_name: str | None,
    *,
    route_idx: int,
    effective_time: float | None,
    write_time: bool,
) -> float | None:
    if not competitor_name:
        return None

    scores = new_state.get("scores") or {}
    times = new_state.get("times") or {}

    if cmd.get("score") is not None:
        arr = scores.get(competitor_name) or []
        while len(arr) <= route_idx:
            arr.append(None)
        arr[route_idx] = cmd.get("score")
        scores[competitor_name] = arr

    final_time = None
    existing_times = times.get(competitor_name) or []
    if len(existing_times) > route_idx:
        final_time = existing_times[route_idx]

    if write_time and effective_time is not None:
        tarr = times.get(competitor_name) or []
        while len(tarr) <= route_idx:
            tarr.append(None)
        tarr[route_idx] = effective_time
        times[competitor_name] = tarr
        final_time = effective_time

    new_state["scores"] = scores
    new_state["times"] = times
    return final_time


def apply_submit_score(
    new_state: dict[str, Any],
    cmd: dict[str, Any],
    payload: dict[str, Any],
    *,
    coerce_optional_time: Callable[[Any], float | None],
    coerce_idx: Callable[[Any], int | None],
    compute_preparing_climber: Callable[[list[dict], str], str],
) -> bool:
    competitors = new_state.get("competitors") or []
    competitor_name = _resolve_competitor_name(
        cmd,
        payload,
        competitors,
        coerce_idx=coerce_idx,
        command_name="SUBMIT_SCORE",
    )

    active_name = new_state.get("currentClimber") or ""
    target_comp = next(
        (
            comp
            for comp in competitors
            if isinstance(comp, dict) and comp.get("nume") == competitor_name
        ),
        None,
    )
    already_marked = bool(target_comp.get("marked")) if isinstance(target_comp, dict) else False
    route_idx = max((new_state.get("routeIndex") or 1) - 1, 0)

    # Defensive fallback for legacy edit flows:
    # if a competitor is already marked and is no longer the active climber,
    # treat repeated SUBMIT_SCORE as a score correction only.
    if competitor_name and already_marked and competitor_name != active_name:
        payload["preserveLiveFlow"] = True
        has_registered_time = "registeredTime" in cmd
        correction_time = (
            coerce_optional_time(cmd.get("registeredTime")) if has_registered_time else None
        )
        payload["registeredTime"] = _upsert_score_and_time(
            new_state,
            cmd,
            competitor_name,
            route_idx=route_idx,
            effective_time=correction_time,
            write_time=has_registered_time and correction_time is not None,
        )
        return True

    payload["preserveLiveFlow"] = False
    raw_time = cmd.get("registeredTime")
    if raw_time is None:
        raw_time = new_state.get("lastRegisteredTime")
    effective_time = coerce_optional_time(raw_time)
    payload["registeredTime"] = _upsert_score_and_time(
        new_state,
        cmd,
        competitor_name,
        route_idx=route_idx,
        effective_time=effective_time,
        write_time=True,
    )

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


def apply_modify_score(
    new_state: dict[str, Any],
    cmd: dict[str, Any],
    payload: dict[str, Any],
    *,
    coerce_optional_time: Callable[[Any], float | None],
    coerce_idx: Callable[[Any], int | None],
) -> bool:
    competitors = new_state.get("competitors") or []
    competitor_name = _resolve_competitor_name(
        cmd,
        payload,
        competitors,
        coerce_idx=coerce_idx,
        command_name="MODIFY_SCORE",
    )

    route_idx = max((new_state.get("routeIndex") or 1) - 1, 0)
    has_registered_time = "registeredTime" in cmd
    effective_time = (
        coerce_optional_time(cmd.get("registeredTime")) if has_registered_time else None
    )
    payload["registeredTime"] = _upsert_score_and_time(
        new_state,
        cmd,
        competitor_name,
        route_idx=route_idx,
        effective_time=effective_time,
        write_time=has_registered_time and effective_time is not None,
    )
    return True
