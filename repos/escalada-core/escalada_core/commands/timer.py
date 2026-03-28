from __future__ import annotations

from typing import Any, Callable


def apply_timer_and_progress(
    new_state: dict[str, Any],
    cmd: dict[str, Any],
    ctype: str | None,
    *,
    coerce_optional_time: Callable[[Any], float | None],
    parse_timer_preset: Callable[[str | None], int | None],
) -> tuple[bool, bool]:
    if ctype == "START_TIMER":
        new_state["started"] = True
        new_state["timerState"] = "running"
        new_state["lastRegisteredTime"] = None
        new_state["remaining"] = None
        return True, True

    if ctype == "STOP_TIMER":
        new_state["started"] = False
        new_state["timerState"] = "paused"
        return True, True

    if ctype == "RESUME_TIMER":
        new_state["started"] = True
        new_state["timerState"] = "running"
        new_state["lastRegisteredTime"] = None
        return True, True

    if ctype == "PROGRESS_UPDATE":
        delta = cmd.get("delta") or 1
        new_count = (
            (int(new_state.get("holdCount", 0)) + 1)
            if delta == 1
            else round(new_state.get("holdCount", 0) + delta, 1)
        )
        if new_count < 0:
            new_count = 0.0
        max_holds = new_state.get("holdsCount") or 0
        if isinstance(max_holds, int) and max_holds > 0 and new_count > max_holds:
            new_count = float(max_holds)
        new_state["holdCount"] = new_count
        return True, True

    if ctype == "REGISTER_TIME":
        if "registeredTime" in cmd:
            candidate = coerce_optional_time(cmd.get("registeredTime"))
            if candidate is not None:
                new_state["lastRegisteredTime"] = candidate
        return True, True

    if ctype == "TIMER_SYNC":
        new_state["remaining"] = cmd.get("remaining")
        return True, False

    if ctype == "SET_TIMER_PRESET":
        preset = cmd.get("timerPreset")
        if preset is not None:
            new_state["timerPreset"] = preset
            new_state["timerPresetSec"] = parse_timer_preset(preset)
            timer_state = new_state.get("timerState") or "idle"
            if timer_state not in {"running", "paused"}:
                preset_sec = new_state.get("timerPresetSec")
                new_state["remaining"] = (
                    float(preset_sec) if isinstance(preset_sec, int) else None
                )
        return True, True

    return False, False

