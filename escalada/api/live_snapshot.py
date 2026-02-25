"""Snapshot builders extracted from live.py.

This module keeps snapshot projection logic isolated from routing/transport code.
"""

from __future__ import annotations

from typing import Any, Callable

from escalada.api.ranking_time_tiebreak import resolve_rankings_with_time_tiebreak


def public_preparing_climber(state: dict) -> str:
    competitors = state.get("competitors") or []
    if not isinstance(competitors, list):
        return ""

    current = state.get("currentClimber")
    if not isinstance(current, str) or not current:
        return ""

    current_idx = None
    for i, comp in enumerate(competitors):
        if isinstance(comp, dict) and comp.get("nume") == current:
            current_idx = i
            break
    if current_idx is None:
        return ""

    for comp in competitors[current_idx + 1 :]:
        if not isinstance(comp, dict):
            continue
        name = comp.get("nume")
        if not isinstance(name, str) or not name.strip():
            continue
        if comp.get("marked"):
            continue
        return name
    return ""


def merge_persistent_tiebreak_badges(
    state: dict,
    route_index: int,
    ranking_rows: list[dict] | None,
) -> list[dict]:
    def _sanitize_prev_helper(raw: Any) -> dict | None:
        if not isinstance(raw, dict):
            return None
        raw_ranks = raw.get("prev_ranks_by_name")
        if not isinstance(raw_ranks, dict):
            return None
        ranks: dict[str, int] = {}
        for name, rank in raw_ranks.items():
            if not isinstance(name, str) or not name.strip():
                continue
            if isinstance(rank, bool) or not isinstance(rank, int) or rank <= 0:
                continue
            ranks[name.strip()] = int(rank)
        if not ranks:
            return None
        raw_members = raw.get("members")
        members: list[str] = []
        if isinstance(raw_members, list):
            for item in raw_members:
                if not isinstance(item, str):
                    continue
                name = item.strip()
                if not name or name in members:
                    continue
                members.append(name)
        if not members:
            members = sorted(ranks.keys(), key=lambda item: item.lower())
        lineage_key = raw.get("lineage_key")
        if not isinstance(lineage_key, str) or not lineage_key.strip():
            lineage_key = None
        return {
            "prev_ranks_by_name": ranks,
            "members": members,
            "lineage_key": lineage_key,
        }

    rows = ranking_rows if isinstance(ranking_rows, list) else []
    if not rows:
        state["leadTiebreakBadgesByName"] = {}
        state["leadTiebreakBadgesRouteIndex"] = route_index
        return []

    initiated = bool(state.get("initiated"))
    if not initiated:
        state["leadTiebreakBadgesByName"] = {}
        state["leadTiebreakBadgesRouteIndex"] = route_index
        return rows

    prev_route_index = state.get("leadTiebreakBadgesRouteIndex")
    if prev_route_index != route_index:
        state["leadTiebreakBadgesByName"] = {}
        state["leadTiebreakBadgesRouteIndex"] = route_index

    badges = state.get("leadTiebreakBadgesByName")
    if not isinstance(badges, dict):
        badges = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        prev_flags = badges.get(name) if isinstance(badges.get(name), dict) else {}
        next_prev = bool(prev_flags.get("tb_prev")) or bool(row.get("tb_prev"))
        next_time = bool(prev_flags.get("tb_time")) or bool(row.get("tb_time"))
        prev_helper = _sanitize_prev_helper(prev_flags.get("tb_prev_helper"))
        row_helper = _sanitize_prev_helper(row.get("tb_prev_helper"))
        next_helper = row_helper or prev_helper
        if next_prev or next_time:
            next_payload = {"tb_prev": next_prev, "tb_time": next_time}
            if next_prev and next_helper:
                next_payload["tb_prev_helper"] = next_helper
            badges[name] = next_payload

    merged_rows: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        merged = dict(row)
        name = merged.get("name")
        if isinstance(name, str):
            flags = badges.get(name) if isinstance(badges.get(name), dict) else {}
            if bool(flags.get("tb_prev")):
                merged["tb_prev"] = True
            if bool(flags.get("tb_time")):
                merged["tb_time"] = True
            if bool(flags.get("tb_prev")) and _sanitize_prev_helper(merged.get("tb_prev_helper")) is None:
                helper = _sanitize_prev_helper(flags.get("tb_prev_helper"))
                if helper:
                    merged["tb_prev_helper"] = helper
        merged_rows.append(merged)

    state["leadTiebreakBadgesByName"] = badges
    state["leadTiebreakBadgesRouteIndex"] = route_index
    return merged_rows


def build_public_box_state(
    box_id: int,
    state: dict,
    *,
    server_side_timer_enabled: bool,
    compute_remaining: Callable[[dict, int], float | None],
    now_ms: Callable[[], int],
) -> dict:
    routes_count = state.get("routesCount")
    if routes_count is None:
        routes_count = state.get("routeIndex") or 1
    holds_counts = state.get("holdsCounts") or []
    if not isinstance(holds_counts, list):
        holds_counts = []
    remaining = state.get("remaining")
    if server_side_timer_enabled:
        remaining = compute_remaining(state, now_ms())
    route_index = int(state.get("routeIndex") or 1)
    routes_count = int(routes_count or route_index or 1)
    scores_by_name = state.get("scores") or {}
    times_by_name = state.get("times") or {}
    tiebreak_state = resolve_rankings_with_time_tiebreak(
        scores=scores_by_name,
        times=times_by_name,
        route_count=routes_count,
        active_route_index=route_index,
        box_id=box_id,
        time_criterion_enabled=bool(state.get("timeCriterionEnabled", False)),
        active_holds_count=state.get("holdsCount")
        if isinstance(state.get("holdsCount"), int)
        else None,
        prev_resolved_decisions=state.get("prevRoundsTiebreakDecisions"),
        prev_orders_by_fingerprint=state.get("prevRoundsTiebreakOrders"),
        prev_ranks_by_fingerprint=state.get("prevRoundsTiebreakRanks"),
        prev_lineage_ranks_by_key=state.get("prevRoundsTiebreakLineageRanks"),
        prev_resolved_fingerprint=state.get("prevRoundsTiebreakResolvedFingerprint"),
        prev_resolved_decision=state.get("prevRoundsTiebreakResolvedDecision"),
        resolved_decisions=state.get("timeTiebreakDecisions"),
        resolved_fingerprint=state.get("timeTiebreakResolvedFingerprint"),
        resolved_decision=state.get("timeTiebreakResolvedDecision"),
    )
    merged_lead_rows = merge_persistent_tiebreak_badges(
        state,
        route_index,
        tiebreak_state.get("lead_ranking_rows") or [],
    )
    return {
        "boxId": box_id,
        "categorie": state.get("categorie", ""),
        "initiated": state.get("initiated", False),
        "routeIndex": state.get("routeIndex", 1),
        "routesCount": routes_count,
        "holdsCount": state.get("holdsCount", 0),
        "holdsCounts": holds_counts,
        "currentClimber": state.get("currentClimber", ""),
        "preparingClimber": (state.get("preparingClimber") or public_preparing_climber(state)),
        "timerState": state.get("timerState", "idle"),
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
        "prevRoundsTiebreakLineageRanks": state.get("prevRoundsTiebreakLineageRanks") or {},
        "prevRoundsTiebreakResolvedFingerprint": state.get("prevRoundsTiebreakResolvedFingerprint"),
        "prevRoundsTiebreakResolvedDecision": state.get("prevRoundsTiebreakResolvedDecision"),
        "timeTiebreakCurrentFingerprint": tiebreak_state.get("fingerprint"),
        "timeTiebreakHasEligibleTie": tiebreak_state.get("has_eligible_tie"),
        "timeTiebreakIsResolved": tiebreak_state.get("is_resolved"),
        "timeTiebreakEligibleGroups": tiebreak_state.get("eligible_groups") or [],
        "leadRankingRows": merged_lead_rows,
        "leadTieEvents": tiebreak_state.get("lead_tie_events") or [],
        "leadRankingResolved": tiebreak_state.get("lead_ranking_resolved"),
        "leadRankingErrors": tiebreak_state.get("errors") or [],
        "scoresByName": scores_by_name,
        "timesByName": times_by_name,
    }


def build_snapshot(
    box_id: int,
    state: dict,
    *,
    server_side_timer_enabled: bool,
    compute_remaining: Callable[[dict, int], float | None],
    now_ms: Callable[[], int],
    get_competition_officials: Callable[[], dict[str, str]],
) -> dict:
    remaining = state.get("remaining")
    if server_side_timer_enabled:
        remaining = compute_remaining(state, now_ms())
    route_index = int(state.get("routeIndex") or 1)
    routes_count = int(state.get("routesCount") or route_index or 1)
    scores_by_name = state.get("scores") or {}
    times_by_name = state.get("times") or {}
    tiebreak_state = resolve_rankings_with_time_tiebreak(
        scores=scores_by_name,
        times=times_by_name,
        route_count=routes_count,
        active_route_index=route_index,
        box_id=box_id,
        time_criterion_enabled=bool(state.get("timeCriterionEnabled", False)),
        active_holds_count=state.get("holdsCount")
        if isinstance(state.get("holdsCount"), int)
        else None,
        prev_resolved_decisions=state.get("prevRoundsTiebreakDecisions"),
        prev_orders_by_fingerprint=state.get("prevRoundsTiebreakOrders"),
        prev_ranks_by_fingerprint=state.get("prevRoundsTiebreakRanks"),
        prev_lineage_ranks_by_key=state.get("prevRoundsTiebreakLineageRanks"),
        prev_resolved_fingerprint=state.get("prevRoundsTiebreakResolvedFingerprint"),
        prev_resolved_decision=state.get("prevRoundsTiebreakResolvedDecision"),
        resolved_decisions=state.get("timeTiebreakDecisions"),
        resolved_fingerprint=state.get("timeTiebreakResolvedFingerprint"),
        resolved_decision=state.get("timeTiebreakResolvedDecision"),
    )
    merged_lead_rows = merge_persistent_tiebreak_badges(
        state,
        route_index,
        tiebreak_state.get("lead_ranking_rows") or [],
    )
    officials = get_competition_officials()
    return {
        "type": "STATE_SNAPSHOT",
        "boxId": box_id,
        "initiated": state.get("initiated", False),
        "holdsCount": state.get("holdsCount", 0),
        "routeIndex": state.get("routeIndex", 1),
        "routesCount": state.get("routesCount"),
        "holdsCounts": state.get("holdsCounts"),
        "currentClimber": state.get("currentClimber", ""),
        "preparingClimber": state.get("preparingClimber", ""),
        "started": state.get("started", False),
        "timerState": state.get("timerState", "idle"),
        "holdCount": state.get("holdCount", 0.0),
        "competitors": state.get("competitors", []),
        "categorie": state.get("categorie", ""),
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
        "prevRoundsTiebreakLineageRanks": state.get("prevRoundsTiebreakLineageRanks") or {},
        "prevRoundsTiebreakResolvedFingerprint": state.get("prevRoundsTiebreakResolvedFingerprint"),
        "prevRoundsTiebreakResolvedDecision": state.get("prevRoundsTiebreakResolvedDecision"),
        "timeTiebreakCurrentFingerprint": tiebreak_state.get("fingerprint"),
        "timeTiebreakHasEligibleTie": tiebreak_state.get("has_eligible_tie"),
        "timeTiebreakIsResolved": tiebreak_state.get("is_resolved"),
        "timeTiebreakEligibleGroups": tiebreak_state.get("eligible_groups") or [],
        "leadRankingRows": merged_lead_rows,
        "leadTieEvents": tiebreak_state.get("lead_tie_events") or [],
        "leadRankingResolved": tiebreak_state.get("lead_ranking_resolved"),
        "leadRankingErrors": tiebreak_state.get("errors") or [],
        "scoresByName": scores_by_name,
        "timesByName": times_by_name,
        "timerPreset": state.get("timerPreset"),
        "timerPresetSec": state.get("timerPresetSec"),
        "federalOfficial": officials.get("federalOfficial", ""),
        "judgeChief": officials.get("judgeChief", ""),
        "competitionDirector": officials.get("competitionDirector", ""),
        "chiefRoutesetter": officials.get("chiefRoutesetter", ""),
        "sessionId": state.get("sessionId"),
        "boxVersion": state.get("boxVersion", 0),
    }
