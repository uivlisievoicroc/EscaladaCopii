from __future__ import annotations

from typing import Any, Callable
import uuid


def apply_reset_partial(
    new_state: dict[str, Any],
    cmd: dict[str, Any],
    *,
    parse_timer_preset: Callable[[str | None], int | None],
) -> bool:
    reset_timer = bool(cmd.get("resetTimer"))
    clear_progress = bool(cmd.get("clearProgress"))
    unmark_all = bool(cmd.get("unmarkAll"))

    if unmark_all:
        reset_timer = True
        clear_progress = True

        new_state["initiated"] = False
        new_state["sessionId"] = str(uuid.uuid4())
        new_state["routeIndex"] = 1
        holds_counts = new_state.get("holdsCounts")
        if isinstance(holds_counts, list) and holds_counts:
            first_holds = holds_counts[0]
            if isinstance(first_holds, int):
                new_state["holdsCount"] = first_holds

        new_state["scores"] = {}
        new_state["times"] = {}
        new_state["lastRegisteredTime"] = None
        new_state["timeTiebreakDecisions"] = {}
        new_state["timeTiebreakResolvedFingerprint"] = None
        new_state["timeTiebreakResolvedDecision"] = None
        new_state["prevRoundsTiebreakDecisions"] = {}
        new_state["prevRoundsTiebreakOrders"] = {}
        new_state["prevRoundsTiebreakRanks"] = {}
        new_state["prevRoundsTiebreakLineageRanks"] = {}
        new_state["prevRoundsTiebreakResolvedFingerprint"] = None
        new_state["prevRoundsTiebreakResolvedDecision"] = None

        competitors = new_state.get("competitors")
        if isinstance(competitors, list):
            for comp in competitors:
                if not isinstance(comp, dict):
                    continue
                comp["marked"] = False
            new_state["currentClimber"] = ""
            new_state["preparingClimber"] = ""
        else:
            new_state["currentClimber"] = ""
            new_state["preparingClimber"] = ""

    if reset_timer:
        new_state["started"] = False
        new_state["timerState"] = "idle"
        preset_sec = new_state.get("timerPresetSec")
        if preset_sec is None:
            preset_sec = parse_timer_preset(new_state.get("timerPreset"))
        new_state["remaining"] = (
            float(preset_sec) if isinstance(preset_sec, (int, float)) else None
        )
        new_state["lastRegisteredTime"] = None

    if clear_progress:
        new_state["holdCount"] = 0.0

    return True


def apply_reset_box(new_state: dict[str, Any]) -> bool:
    new_state["initiated"] = False
    new_state["currentClimber"] = ""
    new_state["preparingClimber"] = ""
    new_state["started"] = False
    new_state["timerState"] = "idle"
    new_state["holdCount"] = 0.0
    new_state["lastRegisteredTime"] = None
    new_state["remaining"] = None
    new_state["scores"] = {}
    new_state["times"] = {}
    new_state["routesCount"] = 1
    new_state["holdsCounts"] = []
    new_state["competitors"] = []
    new_state["categorie"] = ""
    new_state["timerPreset"] = None
    new_state["timerPresetSec"] = None
    new_state["timeTiebreakPreference"] = None
    new_state["timeTiebreakResolvedFingerprint"] = None
    new_state["timeTiebreakResolvedDecision"] = None
    new_state["timeTiebreakDecisions"] = {}
    new_state["prevRoundsTiebreakPreference"] = None
    new_state["prevRoundsTiebreakResolvedFingerprint"] = None
    new_state["prevRoundsTiebreakResolvedDecision"] = None
    new_state["prevRoundsTiebreakDecisions"] = {}
    new_state["prevRoundsTiebreakOrders"] = {}
    new_state["prevRoundsTiebreakRanks"] = {}
    new_state["prevRoundsTiebreakLineageRanks"] = {}
    new_state["sessionId"] = str(uuid.uuid4())
    return True

