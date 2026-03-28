from __future__ import annotations

from typing import Any, Callable


def apply_init_route(
    new_state: dict[str, Any],
    cmd: dict[str, Any],
    payload: dict[str, Any],
    *,
    normalize_competitors: Callable[[list[dict] | None], list[dict]],
    parse_timer_preset: Callable[[str | None], int | None],
) -> bool:
    new_state["boxVersion"] = new_state.get("boxVersion", 0) + 1
    payload["sessionId"] = new_state.get("sessionId")
    new_state["initiated"] = True
    incoming_route_index = cmd.get("routeIndex") or 1
    new_state["holdsCount"] = cmd.get("holdsCount") or 0
    new_state["routeIndex"] = incoming_route_index
    if cmd.get("routesCount") is not None:
        new_state["routesCount"] = cmd.get("routesCount")
    if cmd.get("holdsCounts") is not None:
        new_state["holdsCounts"] = cmd.get("holdsCounts")

    competitors = normalize_competitors(cmd.get("competitors"))
    new_state["competitors"] = competitors
    new_state["currentClimber"] = competitors[0]["nume"] if competitors else ""
    new_state["preparingClimber"] = (
        competitors[1]["nume"] if len(competitors) > 1 else ""
    )

    new_state["started"] = False
    new_state["timerState"] = "idle"
    new_state["holdCount"] = 0.0
    new_state["lastRegisteredTime"] = None
    new_state["remaining"] = None
    new_state["timeTiebreakDecisions"] = {}
    new_state["timeTiebreakResolvedFingerprint"] = None
    new_state["timeTiebreakResolvedDecision"] = None
    new_state["prevRoundsTiebreakDecisions"] = {}
    new_state["prevRoundsTiebreakOrders"] = {}
    new_state["prevRoundsTiebreakRanks"] = {}
    new_state["prevRoundsTiebreakLineageRanks"] = {}
    new_state["prevRoundsTiebreakResolvedFingerprint"] = None
    new_state["prevRoundsTiebreakResolvedDecision"] = None

    if incoming_route_index == 1:
        new_state["scores"] = {}
        new_state["times"] = {}
    else:
        if not isinstance(new_state.get("scores"), dict):
            new_state["scores"] = {}
        if not isinstance(new_state.get("times"), dict):
            new_state["times"] = {}

    if cmd.get("categorie"):
        new_state["categorie"] = cmd["categorie"]
    if cmd.get("timerPreset"):
        new_state["timerPreset"] = cmd["timerPreset"]
        new_state["timerPresetSec"] = parse_timer_preset(cmd.get("timerPreset"))
    return True

