"""Core contest state transitions (pure, no FastAPI/DB).

This module implements the pure business logic for Escalada climbing competitions.
All functions are deterministic and side-effect free (no I/O, no database, no HTTP).

Architecture:
- State is a plain dict with keys like sessionId, boxVersion, currentClimber, holdCount, etc.
- Commands are plain dicts with a 'type' field (INIT_ROUTE, START_TIMER, SUBMIT_SCORE, etc.)
- apply_command() takes (state, cmd) and returns CommandOutcome with updated state
- Mutations are performed on a deepcopy to preserve functional purity
- Parent (escalada-api) receives CommandOutcome and persists/broadcasts as needed

Key concepts:
- sessionId: UUID generated on INIT_ROUTE; used to detect stale commands from old tabs
- boxVersion: Monotonic counter incremented on state changes; prevents race conditions
- holdCount: Float to support half-holds (e.g., 5.5 for 5 full + 1 bonus hold)
- marked: Boolean per competitor indicating they've been scored (used for queue advancement)
- timerState: 'idle' | 'running' | 'paused' (server-side timer added 2026-01-25)

Validation:
- validate_session_and_version() checks sessionId + boxVersion before applying command
- Returns ValidationError(kind='stale_session'|'stale_version') if rejected
- Input sanitization via InputSanitizer (max lengths, control char stripping)

State transitions:
- INIT_ROUTE: Starts a new route, resets queue, preserves multi-route scores
- PROGRESS_UPDATE: Increments holdCount (supports +1 or +0.1 for half-holds)
- SUBMIT_SCORE: Marks competitor as done, advances queue, stores score + optional time
- MODIFY_SCORE: Updates an existing score/time without changing live contest state
- RESET_PARTIAL: Allows selective reset (timer/progress/unmark) without full restart
- RESET_BOX: Full reset to default_state() with new sessionId
"""
from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .commands.init_route import apply_init_route
from .commands.reset import apply_reset_box, apply_reset_partial
from .commands.submit_score import apply_modify_score, apply_submit_score
from .commands.timer import apply_timer_and_progress
from .validation import InputSanitizer


@dataclass
class CommandOutcome:
    """Result of applying a core command."""

    state: Dict[str, Any]
    cmd_payload: Dict[str, Any]
    snapshot_required: bool


@dataclass
class ValidationError:
    """Represents a non-transport validation failure (pure core)."""

    kind: str
    message: str | None = None
    status_code: int | None = None


def default_state(session_id: str | None = None) -> Dict[str, Any]:
    """Create a fresh contest state with default values.
    
    Args:
        session_id: Optional UUID string; generated if not provided
        
    Returns:
        Dict with keys:
        - initiated: False until INIT_ROUTE called
        - holdsCount: Total holds on current route (int)
        - holdCount: Current progress (float, supports 0.5 increments)
        - currentClimber: Name of active competitor
        - preparingClimber: Next competitor in queue (skips marked)
        - timerState: 'idle' | 'running' | 'paused'
        - routeIndex: 1-based current route number
        - routesCount: Total routes in contest
        - competitors: List of {nume, marked, club?} dicts
        - sessionId: UUID to detect stale commands
        - boxVersion: Monotonic counter (incremented on INIT_ROUTE, SUBMIT_SCORE, etc.)
        - scores/times: Dicts mapping competitor names to arrays (one entry per route)
    """
    import uuid

    return {
        "initiated": False,
        "holdsCount": 0,
        "currentClimber": "",
        "preparingClimber": "",
        "started": False,
        "timerState": "idle",
        "holdCount": 0.0,
        "routeIndex": 1,
        "routesCount": 1,
        "holdsCounts": [],
        "competitors": [],
        "categorie": "",
        "lastRegisteredTime": None,
        "remaining": None,
        "timerPreset": None,
        "timerPresetSec": None,
        "timerRemainingSec": None,
        "timerEndsAtMs": None,
        "timeCriterionEnabled": False,
        "timeTiebreakPreference": None,
        "timeTiebreakResolvedFingerprint": None,
        "timeTiebreakResolvedDecision": None,
        "timeTiebreakDecisions": {},
        "prevRoundsTiebreakPreference": None,
        "prevRoundsTiebreakResolvedFingerprint": None,
        "prevRoundsTiebreakResolvedDecision": None,
        "prevRoundsTiebreakDecisions": {},
        "prevRoundsTiebreakOrders": {},
        "prevRoundsTiebreakRanks": {},
        "prevRoundsTiebreakLineageRanks": {},
        "sessionId": session_id or str(uuid.uuid4()),
        "boxVersion": 0,
    }


def parse_timer_preset(preset: str | None) -> int | None:
    """Parse timer preset string (MM:SS format) to total seconds.
    
    Args:
        preset: String like "05:00" or "3:30"
        
    Returns:
        Total seconds as int, or None if parsing fails
        
    Examples:
        - "05:00" → 300
        - "3:30" → 210
        - "" → None
        - "invalid" → None
    """
    if not preset:
        return None
    try:
        minutes, seconds = (preset or "").split(":")
        return int(minutes or 0) * 60 + int(seconds or 0)
    except Exception:
        return None


def _coerce_optional_time(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = float(stripped)
            if not math.isfinite(parsed):
                return None
            return parsed
        except ValueError:
            return None
    return None


def _coerce_idx(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped, 10)
        except ValueError:
            return None
    return None


def _normalize_competitors(competitors: List[dict] | None) -> List[dict]:
    """Sanitize and normalize competitor list from client input.
    
    Args:
        competitors: List of dicts with 'nume' (name), optional 'club', 'marked' fields
        
    Returns:
        List of normalized dicts with:
        - nume: Sanitized name (max 255 chars, no control chars)
        - marked: Boolean (default False)
        - club: Optional sanitized club name
        
    Behavior:
        - Skips entries with missing/invalid 'nume'
        - Sanitizes names via InputSanitizer (prevents XSS, length limits)
        - Coerces 'marked' to bool (handles string/int/bool inputs)
        - Preserves 'club' field if present and non-empty
        - Skips malformed entries (returns only valid competitors)
    """
    normalized: List[dict] = []
    if not competitors:
        return normalized

    for comp in competitors:
        try:
            if not isinstance(comp, dict):
                continue
            name = comp.get("nume")
            if not isinstance(name, str):
                continue
            safe_name = InputSanitizer.sanitize_competitor_name(name)
            if not safe_name:
                continue
            club = None
            if comp.get("club") not in (None, ""):
                club_candidate = InputSanitizer.sanitize_string(
                    comp.get("club") if isinstance(comp.get("club"), str) else str(comp.get("club")),
                    255,
                )
                if club_candidate:
                    club = club_candidate
            marked_val = comp.get("marked", False)
            if isinstance(marked_val, bool):
                marked_bool = marked_val
            elif isinstance(marked_val, (int, float)):
                marked_bool = bool(int(marked_val))
            elif isinstance(marked_val, str):
                lowered = marked_val.strip().lower()
                if lowered in {"1", "true", "yes", "y", "on"}:
                    marked_bool = True
                elif lowered in {"0", "false", "no", "n", "off", ""}:
                    marked_bool = False
                else:
                    marked_bool = False
            else:
                marked_bool = False
            entry: dict[str, Any] = {"nume": safe_name, "marked": marked_bool}
            if club is not None:
                entry["club"] = club
            normalized.append(entry)
        except Exception:
            continue
    return normalized


def _compute_preparing_climber(competitors: List[dict], current_climber: str) -> str:
    """Find the next competitor in queue after the current climber.
    
    Match ContestPage behavior: "preparing" is the next competitor after the active climber,
    based on the competitors order. Skips already-marked (scored) competitors.
    
    Args:
        competitors: List of competitor dicts with 'nume' and 'marked' fields
        current_climber: Name of the currently active competitor
        
    Returns:
        Name of next unmarked competitor, or empty string if none found
        
    Logic:
        1. Find index of current_climber in competitors list
        2. Iterate through remaining competitors after current index
        3. Return first competitor where marked=False
        4. Return "" if no unmarked competitors remain (contest finished)
    """
    if not competitors or not current_climber:
        return ""
    current_idx = None
    for i, comp in enumerate(competitors):
        if isinstance(comp, dict) and comp.get("nume") == current_climber:
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


def _apply_transition(state: Dict[str, Any], cmd: Dict[str, Any]) -> CommandOutcome:
    """Apply pure state transition without side effects.
    
    Pure transition: works on a deepcopy of the provided state and returns new state + payload.
    Parent (escalada-api) is responsible for persistence and broadcasting.
    
    Args:
        state: Current contest state dict (not mutated)
        cmd: Command dict with 'type' field and command-specific params
        
    Returns:
        CommandOutcome with:
        - state: Updated state dict (deepcopy with changes applied)
        - cmd_payload: Enriched command (adds resolved fields like competitor names)
        - snapshot_required: True if this change should trigger persistence/broadcast
        
    Command types:
        - INIT_ROUTE: Start new route, reset queue, normalize competitors
        - START_TIMER/STOP_TIMER/RESUME_TIMER: Control timer state
        - PROGRESS_UPDATE: Increment holdCount (supports +1 or +0.1)
        - SUBMIT_SCORE: Mark competitor done, advance queue, store score + time
        - MODIFY_SCORE: Correct a stored score/time without changing timer or queue
        - REGISTER_TIME: Store lastRegisteredTime for tiebreaking
        - TIMER_SYNC: Update remaining time (server-side ticker)
        - SET_TIMER_PRESET: Change timer duration
        - SET_TIME_CRITERION: Toggle time tiebreak mode
        - SET_TIME_TIEBREAK_DECISION: Persist manual tie decision for current tie fingerprint
        - RESET_PARTIAL: Selective reset (timer/progress/unmark)
        - RESET_BOX: Full reset to default state
    """
    # Work on a copy to keep transitions pure and deterministic for the same input.
    new_state: Dict[str, Any] = deepcopy(state)
    ctype = cmd.get("type")
    snapshot_required = False
    payload = dict(cmd)

    if ctype == "INIT_ROUTE":
        apply_init_route(
            new_state,
            cmd,
            payload,
            normalize_competitors=_normalize_competitors,
            parse_timer_preset=parse_timer_preset,
        )
        snapshot_required = True

    else:
        handled_timer, timer_snapshot = apply_timer_and_progress(
            new_state,
            cmd,
            ctype,
            coerce_optional_time=_coerce_optional_time,
            parse_timer_preset=parse_timer_preset,
        )
        if handled_timer:
            snapshot_required = timer_snapshot

    if ctype == "SUBMIT_SCORE":
        apply_submit_score(
            new_state,
            cmd,
            payload,
            coerce_optional_time=_coerce_optional_time,
            coerce_idx=_coerce_idx,
            compute_preparing_climber=_compute_preparing_climber,
        )
        snapshot_required = True

    elif ctype == "MODIFY_SCORE":
        apply_modify_score(
            new_state,
            cmd,
            payload,
            coerce_optional_time=_coerce_optional_time,
            coerce_idx=_coerce_idx,
        )
        snapshot_required = True

    elif ctype == "SET_TIME_CRITERION":
        if cmd.get("timeCriterionEnabled") is not None:
            new_state["timeCriterionEnabled"] = bool(cmd.get("timeCriterionEnabled"))
        snapshot_required = True

    elif ctype == "SET_TIME_TIEBREAK_DECISION":
        decision = cmd.get("timeTiebreakDecision")
        fingerprint = cmd.get("timeTiebreakFingerprint")
        if decision not in {"yes", "no"}:
            raise ValueError(
                "SET_TIME_TIEBREAK_DECISION requires timeTiebreakDecision in {'yes','no'}"
            )
        if not isinstance(fingerprint, str) or not fingerprint.strip():
            raise ValueError(
                "SET_TIME_TIEBREAK_DECISION requires non-empty timeTiebreakFingerprint"
            )
        normalized_fingerprint = fingerprint.strip()
        decisions = new_state.get("timeTiebreakDecisions")
        if not isinstance(decisions, dict):
            decisions = {}
        decisions[normalized_fingerprint] = decision
        new_state["timeTiebreakDecisions"] = decisions
        new_state["timeTiebreakPreference"] = decision
        new_state["timeTiebreakResolvedFingerprint"] = normalized_fingerprint
        new_state["timeTiebreakResolvedDecision"] = decision
        payload["timeTiebreakDecision"] = decision
        payload["timeTiebreakFingerprint"] = normalized_fingerprint
        snapshot_required = True

    elif ctype == "SET_PREV_ROUNDS_TIEBREAK_DECISION":
        decision = cmd.get("prevRoundsTiebreakDecision")
        fingerprint = cmd.get("prevRoundsTiebreakFingerprint")
        raw_order = cmd.get("prevRoundsTiebreakOrder")
        raw_ranks_map = cmd.get("prevRoundsTiebreakRanksByName")
        raw_lineage_key = cmd.get("prevRoundsTiebreakLineageKey")
        if decision not in {"yes", "no"}:
            raise ValueError(
                "SET_PREV_ROUNDS_TIEBREAK_DECISION requires prevRoundsTiebreakDecision in {'yes','no'}"
            )
        if not isinstance(fingerprint, str) or not fingerprint.strip():
            raise ValueError(
                "SET_PREV_ROUNDS_TIEBREAK_DECISION requires non-empty prevRoundsTiebreakFingerprint"
            )
        normalized_fingerprint = fingerprint.strip()
        normalized_lineage_key: str | None = None
        if raw_lineage_key is not None:
            if not isinstance(raw_lineage_key, str) or not raw_lineage_key.strip():
                raise ValueError(
                    "SET_PREV_ROUNDS_TIEBREAK_DECISION prevRoundsTiebreakLineageKey must be a non-empty string"
                )
            normalized_lineage_key = raw_lineage_key.strip()
        normalized_order: list[str] = []
        if raw_order is not None:
            if not isinstance(raw_order, list):
                raise ValueError(
                    "SET_PREV_ROUNDS_TIEBREAK_DECISION prevRoundsTiebreakOrder must be a list"
                )
            for item in raw_order:
                if not isinstance(item, str):
                    continue
                name = item.strip()
                if not name:
                    continue
                if name in normalized_order:
                    continue
                normalized_order.append(name)
        normalized_ranks_map: dict[str, int] = {}
        if raw_ranks_map is not None:
            if not isinstance(raw_ranks_map, dict):
                raise ValueError(
                    "SET_PREV_ROUNDS_TIEBREAK_DECISION prevRoundsTiebreakRanksByName must be an object"
                )
            for raw_name, raw_rank in raw_ranks_map.items():
                if not isinstance(raw_name, str):
                    continue
                name = raw_name.strip()
                if not name:
                    continue
                if isinstance(raw_rank, bool) or not isinstance(raw_rank, int) or raw_rank <= 0:
                    raise ValueError(
                        "SET_PREV_ROUNDS_TIEBREAK_DECISION prevRoundsTiebreakRanksByName values must be positive integers"
                    )
                normalized_ranks_map[name] = int(raw_rank)

        decisions = new_state.get("prevRoundsTiebreakDecisions")
        if not isinstance(decisions, dict):
            decisions = {}
        decisions[normalized_fingerprint] = decision
        new_state["prevRoundsTiebreakDecisions"] = decisions

        orders = new_state.get("prevRoundsTiebreakOrders")
        if not isinstance(orders, dict):
            orders = {}
        if decision == "yes" and normalized_order:
            orders[normalized_fingerprint] = normalized_order
        else:
            orders.pop(normalized_fingerprint, None)
        new_state["prevRoundsTiebreakOrders"] = orders

        ranks_map = new_state.get("prevRoundsTiebreakRanks")
        if not isinstance(ranks_map, dict):
            ranks_map = {}
        if decision == "yes" and normalized_ranks_map:
            ranks_map[normalized_fingerprint] = normalized_ranks_map
        else:
            ranks_map.pop(normalized_fingerprint, None)
        new_state["prevRoundsTiebreakRanks"] = ranks_map
        lineage_ranks = new_state.get("prevRoundsTiebreakLineageRanks")
        if not isinstance(lineage_ranks, dict):
            lineage_ranks = {}
        if decision == "yes" and normalized_lineage_key and normalized_ranks_map:
            existing_lineage = lineage_ranks.get(normalized_lineage_key)
            if not isinstance(existing_lineage, dict):
                existing_lineage = {}
            merged_lineage = dict(existing_lineage)
            merged_lineage.update(normalized_ranks_map)
            lineage_ranks[normalized_lineage_key] = merged_lineage
        new_state["prevRoundsTiebreakLineageRanks"] = lineage_ranks

        new_state["prevRoundsTiebreakPreference"] = decision
        new_state["prevRoundsTiebreakResolvedFingerprint"] = normalized_fingerprint
        new_state["prevRoundsTiebreakResolvedDecision"] = decision
        payload["prevRoundsTiebreakDecision"] = decision
        payload["prevRoundsTiebreakFingerprint"] = normalized_fingerprint
        if normalized_lineage_key:
            payload["prevRoundsTiebreakLineageKey"] = normalized_lineage_key
        payload["prevRoundsTiebreakOrder"] = normalized_order
        payload["prevRoundsTiebreakRanksByName"] = normalized_ranks_map
        snapshot_required = True

    elif ctype == "RESET_PARTIAL":
        apply_reset_partial(new_state, cmd, parse_timer_preset=parse_timer_preset)
        snapshot_required = True

    elif ctype == "RESET_BOX":
        apply_reset_box(new_state)
        snapshot_required = True

    return CommandOutcome(
        state=new_state, cmd_payload=payload, snapshot_required=snapshot_required
    )


def apply_command(state: Dict[str, Any], cmd: Dict[str, Any]) -> CommandOutcome:
    """Apply a contest command to in-memory state.
    
    Args:
        state: Current contest state dict (will be mutated for backward compatibility)
        cmd: Command dict with 'type' field and command-specific params
        
    Returns:
        CommandOutcome with updated state, enriched command payload, and snapshot flag
        
    Backward compatibility note:
        - Internally uses _apply_transition which works on a deepcopy (pure)
        - Mutates input state dict by clearing and updating with new values
        - New callers should prefer consuming CommandOutcome.state instead of relying on mutation
    """
    outcome = _apply_transition(state, cmd)

    # Preserve backward compatibility for callers that expect in-place mutation.
    state.clear()
    state.update(outcome.state)

    return outcome


def validate_session_and_version(
    state: Dict[str, Any],
    cmd: Dict[str, Any],
    *,
    require_session: bool = True,
) -> ValidationError | None:
    """Validate command against current state to prevent stale/conflicting updates.
    
    Pure validation for sessionId and boxVersion against current state.
    Returns ValidationError if rejected, otherwise None.
    
    Args:
        state: Current contest state dict
        cmd: Incoming command dict
        require_session: If True, reject commands without sessionId (except INIT_ROUTE)
        
    Returns:
        ValidationError if command is stale/invalid, None if valid
        
    Validation rules:
        1. sessionId mismatch → stale_session (command from old/different contest)
        2. boxVersion < current → stale_version (command based on outdated state)
        3. Missing sessionId when required → missing_session (malformed command)
        
    Use case:
        Prevents race conditions when multiple tabs/judges send commands simultaneously.
        Example: Tab A submits score (boxVersion=5), Tab B (still on boxVersion=3) tries
        to submit → rejected as stale_version, forcing Tab B to refresh state first.
    """
    current_session = state.get("sessionId")
    incoming_session = cmd.get("sessionId")

    if require_session and not incoming_session:
        return ValidationError(
            kind="missing_session",
            message="sessionId required for all commands except INIT_ROUTE",
            status_code=400,
        )

    if incoming_session and current_session and incoming_session != current_session:
        return ValidationError(kind="stale_session")

    incoming_version = cmd.get("boxVersion")
    if cmd.get("type") == "TIMER_SYNC":
        incoming_version = None
    current_version = state.get("boxVersion", 0)
    if incoming_version is not None and incoming_version < current_version:
        return ValidationError(kind="stale_version")

    return None


def toggle_time_criterion(
    current_value: bool, enabled: bool | None, box_id: int | None = None
) -> Tuple[bool, Dict[str, Any]]:
    """Pure helper to compute new time criterion flag and payload."""
    new_value = bool(enabled)
    payload = {
        "type": "SET_TIME_CRITERION",
        "timeCriterionEnabled": new_value,
    }
    if box_id is not None:
        payload["boxId"] = box_id
    return new_value, payload
