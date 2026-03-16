"""
API adapter over the core Lead ranking engine.

This module keeps backwards-compatible response keys used by API/UI/export layers,
while delegating ranking/tie-break semantics to `escalada-core`.
"""

from __future__ import annotations

import hashlib
import json
import math
from fractions import Fraction
from typing import Any

from escalada_core import Athlete, LeadResult, TieBreakDecision, TieContext, compute_lead_ranking


def _coerce_time_seconds(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        if not math.isfinite(val):
            return None
        return float(val)
    if isinstance(val, str):
        raw = val.strip()
        if not raw:
            return None
        if ":" in raw:
            parts = raw.split(":")
            if len(parts) == 2:
                try:
                    return float(int(parts[0]) * 60 + int(parts[1]))
                except Exception:
                    return None
        try:
            parsed = float(raw)
            if not math.isfinite(parsed):
                return None
            return parsed
        except Exception:
            return None
    return None


def _sanitize_scores(
    scores: dict[str, list[float | None | int]] | None,
) -> dict[str, list[float | None]]:
    out: dict[str, list[float | None]] = {}
    for name, arr in (scores or {}).items():
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(arr, list):
            continue
        clean: list[float | None] = []
        for value in arr:
            if isinstance(value, bool):
                clean.append(None)
                continue
            if isinstance(value, (int, float)) and math.isfinite(value):
                clean.append(float(value))
            else:
                clean.append(None)
        out[name] = clean
    return out


def _sanitize_times(
    times: dict[str, list[int | float | str | None]] | None,
) -> dict[str, list[float | None]]:
    out: dict[str, list[float | None]] = {}
    for name, arr in (times or {}).items():
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(arr, list):
            continue
        out[name] = [_coerce_time_seconds(v) for v in arr]
    return out


def _normalize_resolved_decisions(
    *,
    resolved_decisions: dict[str, str] | None,
    resolved_fingerprint: str | None,
    resolved_decision: str | None,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if isinstance(resolved_decisions, dict):
        for fp, decision in resolved_decisions.items():
            if not isinstance(fp, str) or not fp.strip():
                continue
            if decision not in {"yes", "no"}:
                continue
            normalized[fp.strip()] = decision
    if (
        isinstance(resolved_fingerprint, str)
        and resolved_fingerprint.strip()
        and resolved_decision in {"yes", "no"}
    ):
        normalized[resolved_fingerprint.strip()] = resolved_decision
    return normalized


def _normalize_order_map(orders: dict[str, Any] | None) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    if not isinstance(orders, dict):
        return normalized
    for fp, value in orders.items():
        if not isinstance(fp, str) or not fp.strip():
            continue
        if not isinstance(value, list):
            continue
        seen: set[str] = set()
        out: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            name = item.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            out.append(name)
        if out:
            normalized[fp.strip()] = out
    return normalized


def _normalize_ranks_map(
    ranks: dict[str, Any] | None,
) -> dict[str, dict[str, int]]:
    normalized: dict[str, dict[str, int]] = {}
    if not isinstance(ranks, dict):
        return normalized
    for fp, value in ranks.items():
        if not isinstance(fp, str) or not fp.strip() or not isinstance(value, dict):
            continue
        out: dict[str, int] = {}
        for raw_name, raw_rank in value.items():
            if not isinstance(raw_name, str):
                continue
            name = raw_name.strip()
            if not name:
                continue
            if isinstance(raw_rank, bool) or not isinstance(raw_rank, int) or raw_rank <= 0:
                continue
            out[name] = int(raw_rank)
        if out:
            normalized[fp.strip()] = out
    return normalized


def _order_to_ranks(
    order: list[str] | None,
    member_ids: list[str],
) -> dict[str, int] | None:
    if not isinstance(order, list) or not order:
        return None
    available = list(member_ids)
    available_set = set(available)
    clean_order: list[str] = []
    seen: set[str] = set()
    for raw in order:
        if not isinstance(raw, str):
            continue
        name = raw.strip()
        if not name or name in seen or name not in available_set:
            continue
        seen.add(name)
        clean_order.append(name)
    if not clean_order:
        return None
    if len(available) >= 3 and len(clean_order) != len(available):
        return None
    if len(available) == 2 and len(clean_order) == 1:
        winner = clean_order[0]
        other = [nm for nm in available if nm != winner]
        clean_order = [winner, *other]
    else:
        leftovers = [nm for nm in sorted(available, key=str.lower) if nm not in set(clean_order)]
        clean_order = [*clean_order, *leftovers]
    return {name: idx + 1 for idx, name in enumerate(clean_order)}


def _result_key(result: LeadResult) -> tuple[int, int, int]:
    return (
        1 if result.topped else 0,
        int(result.hold),
        1 if (result.plus and not result.topped) else 0,
    )


def _score_to_lead_result(
    *,
    score: float | None,
    time_seconds: float | None,
    active_holds_count: int | None,
) -> LeadResult:
    if score is None:
        return LeadResult(topped=False, hold=-1, plus=False, time_seconds=time_seconds)
    safe_score = float(score)
    hold_cap = int(active_holds_count) if isinstance(active_holds_count, int) and active_holds_count > 0 else None
    if hold_cap is not None and safe_score >= float(hold_cap):
        return LeadResult(topped=True, hold=hold_cap, plus=False, time_seconds=time_seconds)
    hold = int(math.floor(max(safe_score, 0.0)))
    frac = safe_score - float(hold)
    plus = frac > 1e-9
    return LeadResult(topped=False, hold=hold, plus=plus, time_seconds=time_seconds)


def _event_global_fingerprint(
    *,
    box_id: int | None,
    route_index: int,
    tie_groups: list[dict[str, Any]],
) -> str | None:
    if not tie_groups:
        return None
    payload = {
        "boxId": box_id,
        "routeIndex": route_index,
        "ties": tie_groups,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"tb3:{hashlib.sha1(raw.encode('utf-8')).hexdigest()}"


def _compute_route_rank_maps(
    *,
    athlete_ids: list[str],
    scores: dict[str, list[float | None]],
    route_count: int,
) -> list[dict[str, Fraction]]:
    total_athletes = max(1, len(athlete_ids))
    rank_maps: list[dict[str, Fraction]] = []
    for route_offset in range(route_count):
        present: list[tuple[str, float]] = []
        missing: list[str] = []
        for athlete_id in athlete_ids:
            arr = scores.get(athlete_id, [])
            score = arr[route_offset] if route_offset < len(arr) else None
            if score is None:
                missing.append(athlete_id)
                continue
            present.append((athlete_id, float(score)))
        present.sort(key=lambda item: (-item[1], item[0].lower(), item[0]))

        route_ranks: dict[str, Fraction] = {}
        i = 0
        pos = 1
        while i < len(present):
            score = present[i][1]
            j = i + 1
            while j < len(present) and present[j][1] == score:
                j += 1
            size = j - i
            avg_rank = Fraction((2 * pos) + size - 1, 2)
            for k in range(i, j):
                route_ranks[present[k][0]] = avg_rank
            pos += size
            i = j

        missing_rank = Fraction(total_athletes, 1)
        for athlete_id in missing:
            route_ranks[athlete_id] = missing_rank
        for athlete_id in athlete_ids:
            route_ranks.setdefault(athlete_id, missing_rank)
        rank_maps.append(route_ranks)
    return rank_maps


def _compute_gm_products_and_totals(
    *,
    athlete_ids: list[str],
    route_rank_maps: list[dict[str, Fraction]],
    route_count: int,
) -> tuple[dict[str, Fraction], dict[str, float]]:
    gm_products: dict[str, Fraction] = {}
    gm_totals: dict[str, float] = {}
    exponent = 1.0 / max(1, route_count)
    for athlete_id in athlete_ids:
        product = Fraction(1, 1)
        for route_ranks in route_rank_maps:
            product *= route_ranks[athlete_id]
        gm_products[athlete_id] = product
        gm_totals[athlete_id] = float(product) ** exponent
    return gm_products, gm_totals


def _build_gm_tie_groups(
    *,
    ordered_athlete_ids: list[str],
    gm_products: dict[str, Fraction],
    gm_totals: dict[str, float],
    active_results: dict[str, LeadResult],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    i = 0
    rank = 1
    while i < len(ordered_athlete_ids):
        athlete_id = ordered_athlete_ids[i]
        current_product = gm_products[athlete_id]
        j = i + 1
        while j < len(ordered_athlete_ids) and gm_products[ordered_athlete_ids[j]] == current_product:
            j += 1
        size = j - i
        if size > 1:
            members_payload: list[dict[str, Any]] = []
            for member_id in ordered_athlete_ids[i:j]:
                res = active_results[member_id]
                members_payload.append(
                    {
                        "name": member_id,
                        "value": gm_totals[member_id],
                        "time": res.time_seconds,
                    }
                )
            groups.append(
                {
                    "rank_start": rank,
                    "rank_end": rank + size - 1,
                    "affects_podium": rank <= 3,
                    "gm_product": f"{current_product.numerator}/{current_product.denominator}",
                    "members": members_payload,
                }
            )
        rank += size
        i = j
    return groups


def _build_route_rows(
    *,
    athlete_ids: list[str],
    active_results: dict[str, LeadResult],
    tb_flags_by_name: dict[str, dict[str, bool]],
) -> list[dict[str, Any]]:
    sorted_ids = sorted(
        athlete_ids,
        key=lambda athlete_id: (
            -_result_key(active_results[athlete_id])[0],
            -_result_key(active_results[athlete_id])[1],
            -_result_key(active_results[athlete_id])[2],
            athlete_id.lower(),
            athlete_id,
        ),
    )
    rows: list[dict[str, Any]] = []
    i = 0
    rank = 1
    while i < len(sorted_ids):
        athlete_id = sorted_ids[i]
        current_key = _result_key(active_results[athlete_id])
        j = i + 1
        while j < len(sorted_ids) and _result_key(active_results[sorted_ids[j]]) == current_key:
            j += 1
        for k in range(i, j):
            member_id = sorted_ids[k]
            result = active_results[member_id]
            raw_score = float(result.hold) + (
                0.0 if result.topped else (0.1 if result.plus else 0.0)
            )
            rows.append(
                {
                    "name": member_id,
                    "rank": rank,
                    "score": raw_score if result.hold >= 0 else None,
                    "time": result.time_seconds,
                    "tb_time": bool(tb_flags_by_name.get(member_id, {}).get("tb_time")),
                    "tb_prev": bool(tb_flags_by_name.get(member_id, {}).get("tb_prev")),
                }
            )
        rank += j - i
        i = j
    return rows


def _select_best_rank_map_for_members(
    *,
    member_ids: list[str],
    ranks_by_key: dict[str, dict[str, int]],
    required_member: str | None = None,
) -> tuple[str | None, dict[str, int] | None]:
    member_set = set(member_ids)
    required = required_member.strip() if isinstance(required_member, str) and required_member.strip() else None
    best_key: str | None = None
    best_map: dict[str, int] | None = None
    best_overlap = -1
    best_size = -1
    for map_key, raw_map in ranks_by_key.items():
        if not isinstance(map_key, str) or not map_key.strip() or not isinstance(raw_map, dict):
            continue
        candidate = {
            name: int(rank)
            for name, rank in raw_map.items()
            if isinstance(name, str) and isinstance(rank, int) and rank > 0
        }
        if not candidate:
            continue
        if required and required not in candidate:
            continue
        overlap = len(member_set.intersection(candidate.keys()))
        if overlap <= 0:
            continue
        candidate_size = len(candidate)
        if (
            overlap > best_overlap
            or (overlap == best_overlap and candidate_size > best_size)
            or (
                overlap == best_overlap
                and candidate_size == best_size
                and isinstance(best_key, str)
                and map_key < best_key
            )
            or best_key is None
        ):
            best_key = map_key
            best_map = candidate
            best_overlap = overlap
            best_size = candidate_size
    return best_key, best_map


def _select_best_lineage_map_for_members(
    *,
    member_ids: list[str],
    lineage_ranks_by_key: dict[str, dict[str, int]],
    required_member: str | None = None,
) -> tuple[str | None, dict[str, int] | None]:
    return _select_best_rank_map_for_members(
        member_ids=member_ids,
        ranks_by_key=lineage_ranks_by_key,
        required_member=required_member,
    )


def _build_prev_helper_for_event(
    *,
    event: Any,
    prev_ranks_by_fingerprint: dict[str, dict[str, int]],
    prev_lineage_ranks_by_key: dict[str, dict[str, int]],
) -> dict[str, Any] | None:
    member_ids = [member.athlete_id for member in event.members]
    if not member_ids:
        return None
    member_set = set(member_ids)
    fp = event.fingerprint if isinstance(event.fingerprint, str) else None
    lineage_key = event.lineage_key if isinstance(event.lineage_key, str) and event.lineage_key else None
    event_known = {
        name: int(rank)
        for name, rank in (event.known_prev_ranks_by_athlete or {}).items()
        if isinstance(name, str) and isinstance(rank, int) and rank > 0 and name in member_set
    }
    fp_ranks = {
        name: int(rank)
        for name, rank in (prev_ranks_by_fingerprint.get(fp or "") or {}).items()
        if isinstance(name, str) and isinstance(rank, int) and rank > 0 and name in member_set
    }

    selected_lineage_key: str | None = None
    selected_lineage_map: dict[str, int] | None = None
    if lineage_key and isinstance(prev_lineage_ranks_by_key.get(lineage_key), dict):
        selected_lineage_key = lineage_key
        selected_lineage_map = {
            name: int(rank)
            for name, rank in (prev_lineage_ranks_by_key.get(lineage_key) or {}).items()
            if isinstance(name, str) and isinstance(rank, int) and rank > 0 and name in member_set
        }
    if not selected_lineage_map:
        selected_lineage_key, selected_lineage_map = _select_best_lineage_map_for_members(
            member_ids=member_ids,
            lineage_ranks_by_key=prev_lineage_ranks_by_key,
        )
        if selected_lineage_map:
            selected_lineage_map = {
                name: rank for name, rank in selected_lineage_map.items() if name in member_set
            }

    merged: dict[str, int] = {}
    if selected_lineage_map:
        merged.update(selected_lineage_map)
    merged.update(fp_ranks)
    merged.update(event_known)
    if not merged:
        return None

    ordered_members = [member_id for member_id in member_ids if member_id in merged]
    if not ordered_members:
        ordered_members = sorted(merged.keys(), key=lambda item: item.lower())

    return {
        "prev_ranks_by_name": merged,
        "members": ordered_members,
        "lineage_key": selected_lineage_key,
    }


def _build_prev_helper_for_athlete(
    *,
    athlete_id: str,
    tie_members: list[str] | None,
    prev_ranks_by_fingerprint: dict[str, dict[str, int]],
    prev_lineage_ranks_by_key: dict[str, dict[str, int]],
) -> dict[str, Any] | None:
    member_ids: list[str] = []
    if isinstance(tie_members, list):
        for name in tie_members:
            if isinstance(name, str) and name and name not in member_ids:
                member_ids.append(name)
    if athlete_id not in member_ids:
        member_ids.append(athlete_id)
    member_set = set(member_ids)

    lineage_key, lineage_map = _select_best_lineage_map_for_members(
        member_ids=member_ids,
        lineage_ranks_by_key=prev_lineage_ranks_by_key,
        required_member=athlete_id,
    )
    fp_key, fp_map = _select_best_rank_map_for_members(
        member_ids=member_ids,
        ranks_by_key=prev_ranks_by_fingerprint,
        required_member=athlete_id,
    )

    merged: dict[str, int] = {}
    if isinstance(lineage_map, dict):
        merged.update(
            {
                name: int(rank)
                for name, rank in lineage_map.items()
                if isinstance(name, str)
                and isinstance(rank, int)
                and rank > 0
                and (not tie_members or name in member_set)
            }
        )
    if isinstance(fp_map, dict):
        merged.update(
            {
                name: int(rank)
                for name, rank in fp_map.items()
                if isinstance(name, str)
                and isinstance(rank, int)
                and rank > 0
                and (not tie_members or name in member_set)
            }
        )
    if athlete_id not in merged:
        return None

    if tie_members:
        members = [name for name in tie_members if name in merged]
    else:
        members = sorted(
            merged.keys(),
            key=lambda name: (merged[name], name.lower(), name),
        )
    if athlete_id not in members:
        members.append(athlete_id)

    return {
        "prev_ranks_by_name": merged,
        "members": members,
        "lineage_key": lineage_key if isinstance(lineage_key, str) else fp_key,
    }


class _StateBackedResolver:
    def __init__(
        self,
        *,
        prev_decisions: dict[str, str],
        prev_orders: dict[str, list[str]],
        prev_ranks: dict[str, dict[str, int]],
        prev_lineage_ranks: dict[str, dict[str, int]],
        time_decisions: dict[str, str],
        global_fingerprint: str | None,
        event_prev_fingerprint: str | None,
        event_prev_decision: str | None,
        event_prev_order: list[str] | None,
        event_prev_ranks: dict[str, int] | None,
        event_prev_lineage_key: str | None,
        event_time_fingerprint: str | None,
        event_time_decision: str | None,
    ):
        self.prev_decisions = prev_decisions
        self.prev_orders = prev_orders
        self.prev_ranks = prev_ranks
        self.prev_lineage_ranks = prev_lineage_ranks
        self.time_decisions = time_decisions
        self.global_fingerprint = global_fingerprint
        self.event_prev_fingerprint = event_prev_fingerprint
        self.event_prev_decision = event_prev_decision
        self.event_prev_order = event_prev_order
        self.event_prev_ranks = event_prev_ranks
        self.event_prev_lineage_key = event_prev_lineage_key
        self.event_time_fingerprint = event_time_fingerprint
        self.event_time_decision = event_time_decision
        self._prev_fp_by_signature: dict[tuple[tuple[str, ...], int, int], str] = {}

    def _matches_event_scope(self, event_fp: str | None, ctx_fp: str) -> bool:
        if not isinstance(event_fp, str) or not event_fp:
            return False
        if event_fp == ctx_fp:
            return True
        if self.global_fingerprint and event_fp == self.global_fingerprint:
            return True
        return False

    def resolve(self, group: list[Athlete], context: TieContext) -> TieBreakDecision:
        signature = (
            tuple(sorted(a.id for a in group)),
            int(context.rank_start),
            int(context.rank_end),
        )
        if context.stage == "previous_rounds":
            self._prev_fp_by_signature[signature] = context.fingerprint
            member_ids = {a.id for a in group}
            lineage_key = (
                context.lineage_key.strip()
                if isinstance(context.lineage_key, str) and context.lineage_key.strip()
                else None
            )
            lineage_ranks: dict[str, int] = {}
            if lineage_key:
                lineage_ranks = {
                    athlete_id: int(rank)
                    for athlete_id, rank in (self.prev_lineage_ranks.get(lineage_key) or {}).items()
                    if athlete_id in member_ids
                }
            if (
                not lineage_ranks
                and lineage_key
                and isinstance(self.event_prev_lineage_key, str)
                and self.event_prev_lineage_key == lineage_key
            ):
                lineage_ranks = {
                    athlete_id: int(rank)
                    for athlete_id, rank in (self.event_prev_ranks or {}).items()
                    if athlete_id in member_ids
                }
            decision = self.prev_decisions.get(context.fingerprint)
            if decision not in {"yes", "no"} and self._matches_event_scope(
                self.event_prev_fingerprint, context.fingerprint
            ):
                decision = self.event_prev_decision
            if decision not in {"yes", "no"} and lineage_ranks:
                decision = "yes"
            if decision not in {"yes", "no"}:
                return TieBreakDecision(choice="pending")
            if decision == "no":
                return TieBreakDecision(choice="no")
            merged_ranks: dict[str, int] = dict(lineage_ranks)
            fp_ranks = self.prev_ranks.get(context.fingerprint)
            if isinstance(fp_ranks, dict):
                merged_ranks.update(
                    {
                        athlete_id: int(rank)
                        for athlete_id, rank in fp_ranks.items()
                        if athlete_id in member_ids
                    }
                )
            if not merged_ranks:
                order_ranks = _order_to_ranks(
                    self.prev_orders.get(context.fingerprint), [a.id for a in group]
                )
                if isinstance(order_ranks, dict):
                    merged_ranks.update(order_ranks)
            if not merged_ranks and self._matches_event_scope(
                self.event_prev_fingerprint, context.fingerprint
            ):
                order_ranks = _order_to_ranks(self.event_prev_order, [a.id for a in group])
                if isinstance(order_ranks, dict):
                    merged_ranks.update(order_ranks)
            if (
                isinstance(self.event_prev_ranks, dict)
                and self._matches_event_scope(self.event_prev_fingerprint, context.fingerprint)
            ):
                merged_ranks.update(
                    {
                        athlete_id: int(rank)
                        for athlete_id, rank in self.event_prev_ranks.items()
                        if athlete_id in member_ids
                    }
                )
            return TieBreakDecision(choice="yes", previous_ranks_by_athlete=merged_ranks or {})

        decision = self.time_decisions.get(context.fingerprint)
        if decision not in {"yes", "no"}:
            legacy_prev_fp = self._prev_fp_by_signature.get(signature)
            if legacy_prev_fp:
                decision = self.time_decisions.get(legacy_prev_fp)
        if decision not in {"yes", "no"} and self._matches_event_scope(
            self.event_time_fingerprint, context.fingerprint
        ):
            decision = self.event_time_decision
        if decision not in {"yes", "no"}:
            legacy_prev_fp = self._prev_fp_by_signature.get(signature)
            if self._matches_event_scope(self.event_time_fingerprint, legacy_prev_fp or ""):
                decision = self.event_time_decision
        if decision not in {"yes", "no"}:
            return TieBreakDecision(choice="pending")
        return TieBreakDecision(choice=decision)


def resolve_rankings_with_time_tiebreak(
    *,
    scores: dict[str, list[float | None | int]] | None,
    times: dict[str, list[int | float | str | None]] | None,
    route_count: int,
    active_route_index: int,
    box_id: int | None,
    time_criterion_enabled: bool,
    active_holds_count: int | None = None,
    prev_resolved_decisions: dict[str, str] | None = None,
    prev_orders_by_fingerprint: dict[str, list[str]] | None = None,
    prev_ranks_by_fingerprint: dict[str, dict[str, int]] | None = None,
    prev_lineage_ranks_by_key: dict[str, dict[str, int]] | None = None,
    prev_resolved_fingerprint: str | None = None,
    prev_resolved_decision: str | None = None,
    prev_resolved_order: list[str] | None = None,
    prev_resolved_ranks_by_name: dict[str, int] | None = None,
    prev_resolved_lineage_key: str | None = None,
    resolved_decisions: dict[str, str] | None = None,
    resolved_fingerprint: str | None = None,
    resolved_decision: str | None = None,
) -> dict[str, Any]:
    normalized_scores = _sanitize_scores(scores)
    normalized_times = _sanitize_times(times)
    active_route_norm = max(1, int(active_route_index or 1))
    route_count_norm = max(1, int(route_count or active_route_norm))
    route_offset = active_route_norm - 1

    athlete_ids = sorted(
        set(normalized_scores.keys()) | set(normalized_times.keys()),
        key=lambda name: name.lower(),
    )
    athletes = [Athlete(id=name, name=name) for name in athlete_ids]

    active_results: dict[str, LeadResult] = {}
    active_raw_scores: dict[str, float | None] = {}
    for athlete_id in athlete_ids:
        score_arr = normalized_scores.get(athlete_id, [])
        time_arr = normalized_times.get(athlete_id, [])
        active_score = score_arr[route_offset] if route_offset < len(score_arr) else None
        active_time = time_arr[route_offset] if route_offset < len(time_arr) else None
        active_raw_scores[athlete_id] = active_score
        active_results[athlete_id] = _score_to_lead_result(
            score=active_score,
            time_seconds=active_time,
            active_holds_count=active_holds_count,
        )

    route_rank_maps = _compute_route_rank_maps(
        athlete_ids=athlete_ids,
        scores=normalized_scores,
        route_count=route_count_norm,
    )
    gm_products, gm_totals = _compute_gm_products_and_totals(
        athlete_ids=athlete_ids,
        route_rank_maps=route_rank_maps,
        route_count=route_count_norm,
    )
    ordered_by_gm = sorted(
        athlete_ids,
        key=lambda athlete_id: (
            gm_products.get(athlete_id, Fraction(10**9, 1)),
            athlete_id.lower(),
            athlete_id,
        ),
    )
    gm_tie_groups = _build_gm_tie_groups(
        ordered_athlete_ids=ordered_by_gm,
        gm_products=gm_products,
        gm_totals=gm_totals,
        active_results=active_results,
    )
    tiebreak_enabled = bool(time_criterion_enabled)
    has_eligible_tie = bool(gm_tie_groups) if tiebreak_enabled else False
    event_fp = _event_global_fingerprint(
        box_id=box_id,
        route_index=active_route_norm,
        tie_groups=gm_tie_groups,
    )

    normalized_prev_decisions = _normalize_resolved_decisions(
        resolved_decisions=prev_resolved_decisions,
        resolved_fingerprint=prev_resolved_fingerprint,
        resolved_decision=prev_resolved_decision,
    )
    normalized_prev_orders = _normalize_order_map(prev_orders_by_fingerprint)
    if (
        isinstance(prev_resolved_fingerprint, str)
        and prev_resolved_fingerprint.strip()
        and isinstance(prev_resolved_order, list)
    ):
        normalized_prev_orders[prev_resolved_fingerprint.strip()] = [
            item.strip()
            for item in prev_resolved_order
            if isinstance(item, str) and item.strip()
        ]
    normalized_prev_ranks = _normalize_ranks_map(prev_ranks_by_fingerprint)
    normalized_prev_lineage_ranks = _normalize_ranks_map(prev_lineage_ranks_by_key)
    event_prev_ranks = None
    if isinstance(prev_resolved_ranks_by_name, dict):
        event_prev_ranks = {
            str(name).strip(): int(rank)
            for name, rank in prev_resolved_ranks_by_name.items()
            if isinstance(name, str)
            and name.strip()
            and isinstance(rank, int)
            and not isinstance(rank, bool)
            and rank > 0
        }
    normalized_time_decisions = _normalize_resolved_decisions(
        resolved_decisions=resolved_decisions,
        resolved_fingerprint=resolved_fingerprint,
        resolved_decision=resolved_decision,
    )

    if not athlete_ids:
        return {
            "overall_rows": [],
            "route_rows": [],
            "lead_ranking_rows": [],
            "lead_tie_events": [],
            "lead_ranking_resolved": True,
            "eligible_groups": [],
            "prev_resolved_decisions": normalized_prev_decisions,
            "prev_orders_by_fingerprint": normalized_prev_orders,
            "prev_ranks_by_fingerprint": normalized_prev_ranks,
            "prev_lineage_ranks_by_key": normalized_prev_lineage_ranks,
            "resolved_decisions": normalized_time_decisions,
            "fingerprint": None,
            "has_eligible_tie": False,
            "is_resolved": True,
            "errors": [],
        }

    if not tiebreak_enabled:
        overall_rows: list[dict[str, Any]] = []
        i = 0
        rank = 1
        while i < len(ordered_by_gm):
            athlete_id = ordered_by_gm[i]
            product = gm_products[athlete_id]
            j = i + 1
            while j < len(ordered_by_gm) and gm_products[ordered_by_gm[j]] == product:
                j += 1
            for k in range(i, j):
                member_id = ordered_by_gm[k]
                overall_rows.append(
                    {
                        "name": member_id,
                        "rank": rank,
                        "total": gm_totals[member_id],
                        "score": active_raw_scores.get(member_id),
                        "time": active_results[member_id].time_seconds,
                        "tb_time": False,
                        "tb_prev": False,
                        "raw_scores": normalized_scores.get(member_id, []),
                        "raw_times": normalized_times.get(member_id, []),
                    }
                )
            rank += j - i
            i = j

        route_rows = _build_route_rows(
            athlete_ids=athlete_ids,
            active_results=active_results,
            tb_flags_by_name={},
        )
        return {
            "overall_rows": overall_rows,
            "route_rows": route_rows,
            "lead_ranking_rows": overall_rows,
            "lead_tie_events": [],
            "lead_ranking_resolved": True,
            "eligible_groups": [],
            "prev_resolved_decisions": normalized_prev_decisions,
            "prev_orders_by_fingerprint": normalized_prev_orders,
            "prev_ranks_by_fingerprint": normalized_prev_ranks,
            "prev_lineage_ranks_by_key": normalized_prev_lineage_ranks,
            "resolved_decisions": normalized_time_decisions,
            "fingerprint": None,
            "has_eligible_tie": False,
            "is_resolved": True,
            "errors": [],
        }

    unique_products = sorted(set(gm_products.values()))
    product_to_hold = {
        product: (len(unique_products) - idx)
        for idx, product in enumerate(unique_products)
    }
    gm_results: dict[str, LeadResult] = {}
    for athlete_id in athlete_ids:
        gm_results[athlete_id] = LeadResult(
            topped=True,
            hold=int(product_to_hold[gm_products[athlete_id]]),
            plus=False,
            time_seconds=active_results[athlete_id].time_seconds,
        )

    resolver = _StateBackedResolver(
        prev_decisions=normalized_prev_decisions,
        prev_orders=normalized_prev_orders,
        prev_ranks=normalized_prev_ranks,
        prev_lineage_ranks=normalized_prev_lineage_ranks,
        time_decisions=normalized_time_decisions,
        global_fingerprint=event_fp,
        event_prev_fingerprint=prev_resolved_fingerprint.strip()
        if isinstance(prev_resolved_fingerprint, str)
        else None,
        event_prev_decision=prev_resolved_decision
        if prev_resolved_decision in {"yes", "no"}
        else None,
        event_prev_order=prev_resolved_order if isinstance(prev_resolved_order, list) else None,
        event_prev_ranks=event_prev_ranks,
        event_prev_lineage_key=prev_resolved_lineage_key.strip()
        if isinstance(prev_resolved_lineage_key, str) and prev_resolved_lineage_key.strip()
        else None,
        event_time_fingerprint=resolved_fingerprint.strip()
        if isinstance(resolved_fingerprint, str)
        else None,
        event_time_decision=resolved_decision if resolved_decision in {"yes", "no"} else None,
    )

    core_result = compute_lead_ranking(
        athletes=athletes,
        results=gm_results,
        tie_break_resolver=resolver,
        podium_places=3,
        round_name=f"Final|overall_gm|routes:{route_count_norm}|active:{active_route_norm}",
        tiebreak_enabled=tiebreak_enabled,
    )

    tb_prev_helpers_by_name: dict[str, dict[str, Any]] = {}
    for event in core_result.tie_events:
        if event.stage != "previous_rounds":
            continue
        helper = _build_prev_helper_for_event(
            event=event,
            prev_ranks_by_fingerprint=normalized_prev_ranks,
            prev_lineage_ranks_by_key=normalized_prev_lineage_ranks,
        )
        if not helper:
            continue
        for member_name in helper.get("members") or []:
            if not isinstance(member_name, str) or not member_name:
                continue
            tb_prev_helpers_by_name[member_name] = helper

    gm_members_by_product: dict[Fraction, list[str]] = {}
    for athlete_id in athlete_ids:
        gm_members_by_product.setdefault(gm_products[athlete_id], []).append(athlete_id)
    gm_tie_members_by_name: dict[str, list[str]] = {}
    for members in gm_members_by_product.values():
        if len(members) < 2:
            continue
        ordered_members = sorted(members, key=lambda name: (name.lower(), name))
        for member_name in ordered_members:
            gm_tie_members_by_name[member_name] = ordered_members

    overall_rows: list[dict[str, Any]] = []
    tb_flags_by_name: dict[str, dict[str, bool]] = {}
    for row in core_result.rows:
        athlete_id = row.athlete_id
        tb_flags_by_name[athlete_id] = {
            "tb_time": bool(row.tb_time),
            "tb_prev": bool(row.tb_prev),
        }
        row_helper = (
            tb_prev_helpers_by_name.get(athlete_id)
            if bool(row.tb_prev)
            else None
        )
        if bool(row.tb_prev) and row_helper is None:
            row_helper = _build_prev_helper_for_athlete(
                athlete_id=athlete_id,
                tie_members=gm_tie_members_by_name.get(athlete_id),
                prev_ranks_by_fingerprint=normalized_prev_ranks,
                prev_lineage_ranks_by_key=normalized_prev_lineage_ranks,
            )
        overall_rows.append(
            {
                "name": row.athlete_name,
                "rank": int(row.rank),
                "total": gm_totals.get(athlete_id, float("inf")),
                "score": active_raw_scores.get(athlete_id),
                "time": active_results[athlete_id].time_seconds,
                "tb_time": bool(row.tb_time),
                "tb_prev": bool(row.tb_prev),
                "raw_scores": normalized_scores.get(athlete_id, []),
                "raw_times": normalized_times.get(athlete_id, []),
                **({"tb_prev_helper": row_helper} if row_helper else {}),
            }
        )

    route_rows = _build_route_rows(
        athlete_ids=athlete_ids,
        active_results=active_results,
        tb_flags_by_name=tb_flags_by_name,
    )

    eligible_groups: list[dict[str, Any]] = []
    for event in core_result.tie_events:
        members = [
            {
                "name": member.athlete_name,
                "time": active_results[member.athlete_id].time_seconds,
                "value": gm_totals.get(member.athlete_id),
            }
            for member in event.members
        ]
        prev_decision = (
            normalized_prev_decisions.get(event.fingerprint)
            if event.stage == "previous_rounds"
            else None
        )
        time_decision = (
            normalized_time_decisions.get(event.fingerprint)
            if event.stage == "time"
            else None
        )
        known_prev = {
            name: int(rank)
            for name, rank in (event.known_prev_ranks_by_athlete or {}).items()
            if isinstance(name, str) and isinstance(rank, int) and rank > 0
        }
        if not known_prev:
            known_prev = {
                name: int(rank)
                for name, rank in (normalized_prev_ranks.get(event.fingerprint) or {}).items()
                if isinstance(name, str) and isinstance(rank, int) and rank > 0
            }
        eligible_groups.append(
            {
                "context": "overall",
                "rank": int(event.rank_start),
                "value": gm_totals.get(event.members[0].athlete_id) if event.members else None,
                "members": members,
                "fingerprint": event.fingerprint,
                "stage": event.stage,
                "affects_podium": bool(event.affects_podium),
                "status": event.status,
                "detail": event.detail,
                "prev_rounds_decision": prev_decision if prev_decision in {"yes", "no"} else None,
                "prev_rounds_order": normalized_prev_orders.get(event.fingerprint),
                "prev_rounds_ranks_by_name": known_prev or None,
                "lineage_key": event.lineage_key,
                "known_prev_ranks_by_name": known_prev or {},
                "missing_prev_rounds_members": list(event.missing_prev_rounds_athlete_ids or []),
                "requires_prev_rounds_input": bool(event.requires_prev_rounds_input),
                "time_decision": time_decision if time_decision in {"yes", "no"} else None,
                "resolved_decision": time_decision if time_decision in {"yes", "no"} else None,
                "resolution_kind": "time" if event.stage == "time" else "previous_rounds",
                "is_resolved": bool(event.status == "resolved"),
            }
        )

    return {
        "overall_rows": overall_rows,
        "route_rows": route_rows,
        "lead_ranking_rows": overall_rows,
        "lead_tie_events": eligible_groups,
        "lead_ranking_resolved": bool(core_result.is_resolved),
        "eligible_groups": eligible_groups,
        "prev_resolved_decisions": normalized_prev_decisions,
        "prev_orders_by_fingerprint": normalized_prev_orders,
        "prev_ranks_by_fingerprint": normalized_prev_ranks,
        "prev_lineage_ranks_by_key": normalized_prev_lineage_ranks,
        "resolved_decisions": normalized_time_decisions,
        "fingerprint": event_fp,
        "has_eligible_tie": has_eligible_tie,
        "is_resolved": bool(core_result.is_resolved),
        "errors": list(core_result.errors),
    }
