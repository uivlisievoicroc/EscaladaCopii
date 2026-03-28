# escalada/api/save_ranking.py
"""
Admin-only "save rankings" endpoint and shared export helpers.

This module renders a category's results to disk under `escalada/clasamente/<categorie>/`:
- `overall.xlsx` / `overall.pdf`
- `route_{n}.xlsx` / `route_{n}.pdf` (one per route)

It also exposes helper functions (`_build_overall_df`, `_df_to_pdf`, `_to_seconds`, etc.) that
are reused by other export features (e.g. official ZIP exports).

Important:
- The `use_time_tiebreak` flag enables the ranking tiebreak workflow used by live/export flows.
- When disabled, ties stay shared; when enabled, previous-rounds/time decisions can affect ranking.
"""

# -------------------- Standard library imports --------------------
import math
import os
from pathlib import Path

# -------------------- Third-party imports --------------------
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from escalada.api.ranking_time_tiebreak import resolve_rankings_with_time_tiebreak
from escalada.api.save_ranking_render import df_to_pdf
from escalada.api.save_ranking_tables import (
    build_by_route_df,
    build_overall_df,
    format_lead_score_display,
    format_time,
    tb_label,
    tb_notes_for_df,
    to_seconds,
)

from escalada.auth.deps import require_admin_action

router = APIRouter()

def _safe_category_dir(category: str) -> Path:
    """
    Build a safe category directory under configured exports root.
    Preserves diacritics/spaces, but blocks path traversal and separators.
    """
    cat = (category or "").strip()
    if not cat or cat in {".", ".."}:
        raise HTTPException(status_code=400, detail="invalid_categorie")
    if "/" in cat or "\\" in cat or ".." in cat:
        raise HTTPException(status_code=400, detail="invalid_categorie")

    base_dir = Path(os.getenv("ESCALADA_EXPORTS_DIR", "escalada/clasamente")).resolve()
    candidate = (base_dir / cat).resolve()
    if base_dir not in candidate.parents:
        raise HTTPException(status_code=400, detail="invalid_categorie")
    return candidate


class RankingIn(BaseModel):
    """Payload used to generate XLSX/PDF exports for a single category."""
    categorie: str
    route_count: int
    # Score matrix indexed by athlete name and route index:
    # { "Name": [scoreR1, scoreR2, ...] }
    scores: dict[str, list[float]]
    clubs: dict[str, str] = {}
    include_clubs: bool = False
    times: dict[str, list[float | None]] | None = None
    # Enables the ranking tiebreak workflow and time column display.
    use_time_tiebreak: bool = False
    # Current active route index (1-based), used for active-route tie-break context.
    route_index: int | None = None
    holds_counts: list[int] | None = None
    active_holds_count: int | None = None
    # Optional box id to make tie fingerprints deterministic across boxes.
    box_id: int | None = None
    # Persisted manual tie decision state.
    time_tiebreak_resolved_decision: str | None = None
    time_tiebreak_resolved_fingerprint: str | None = None
    time_tiebreak_preference: str | None = None
    time_tiebreak_decisions: dict[str, str] | None = None
    prev_rounds_tiebreak_resolved_decision: str | None = None
    prev_rounds_tiebreak_resolved_fingerprint: str | None = None
    prev_rounds_tiebreak_preference: str | None = None
    prev_rounds_tiebreak_decisions: dict[str, str] | None = None
    prev_rounds_tiebreak_orders: dict[str, list[str]] | None = None
    prev_rounds_tiebreak_ranks_by_fingerprint: dict[str, dict[str, int]] | None = None
    prev_rounds_tiebreak_lineage_ranks_by_key: dict[str, dict[str, int]] | None = None
    prev_rounds_tiebreak_resolved_ranks_by_name: dict[str, int] | None = None


def _resolve_route_holds_count(
    *,
    route_idx: int,
    route_count: int,
    holds_counts: list[int] | None,
    active_holds_count: int | None,
) -> int | None:
    if isinstance(holds_counts, list) and route_idx < len(holds_counts):
        candidate = holds_counts[route_idx]
        if isinstance(candidate, int) and candidate > 0:
            return candidate
    if route_count == 1 and isinstance(active_holds_count, int) and active_holds_count > 0:
        return active_holds_count
    return None


def _format_overall_score_columns_for_display(
    df: pd.DataFrame,
    *,
    route_count: int,
    holds_counts: list[int] | None,
    active_holds_count: int | None,
) -> None:
    for route_idx in range(max(0, int(route_count))):
        col = f"Score R{route_idx + 1}"
        if col not in df.columns:
            continue
        holds_count = _resolve_route_holds_count(
            route_idx=route_idx,
            route_count=route_count,
            holds_counts=holds_counts,
            active_holds_count=active_holds_count,
        )
        df[col] = df[col].map(
            lambda score: format_lead_score_display(score, holds_count)
        )


def _format_route_score_column_for_display(
    df: pd.DataFrame,
    *,
    holds_count: int | None,
) -> None:
    if "Score" not in df.columns:
        return
    df["Score"] = df["Score"].map(
        lambda score: format_lead_score_display(score, holds_count)
    )


@router.post("/save_ranking")
def save_ranking(payload: RankingIn, claims=Depends(require_admin_action)):
    """
    Persist category rankings to disk (XLSX + PDF).

    Output path:
      `<ESCALADA_EXPORTS_DIR>/<categorie>/`

    Files:
    - overall.xlsx / overall.pdf: overall ranking across routes (geometric mean of rank-points)
    - route_{n}.xlsx / route_{n}.pdf: per-route ranking with tie-handling and points column
    """
    cat_dir = _safe_category_dir(payload.categorie)
    cat_dir.mkdir(parents=True, exist_ok=True)
    raw_times = payload.times or {}
    # Normalize all times to seconds (int) or None so rendering is consistent.
    times = {name: [_to_seconds(t) for t in arr] for name, arr in raw_times.items()}
    # Drives both time-column display and tie-break activation.
    use_time = payload.use_time_tiebreak
    active_route_index = payload.route_index or payload.route_count
    derived_holds_count = payload.active_holds_count
    if derived_holds_count is None and isinstance(payload.holds_counts, list):
        idx = max(0, int(active_route_index) - 1)
        if idx < len(payload.holds_counts):
            candidate = payload.holds_counts[idx]
            if isinstance(candidate, int):
                derived_holds_count = candidate
    tiebreak_context = resolve_rankings_with_time_tiebreak(
        scores=payload.scores,
        times=times,
        route_count=payload.route_count,
        active_route_index=active_route_index,
        box_id=payload.box_id,
        time_criterion_enabled=bool(use_time),
        active_holds_count=derived_holds_count,
        prev_resolved_decisions=payload.prev_rounds_tiebreak_decisions,
        prev_orders_by_fingerprint=payload.prev_rounds_tiebreak_orders,
        prev_ranks_by_fingerprint=payload.prev_rounds_tiebreak_ranks_by_fingerprint,
        prev_lineage_ranks_by_key=payload.prev_rounds_tiebreak_lineage_ranks_by_key,
        prev_resolved_fingerprint=payload.prev_rounds_tiebreak_resolved_fingerprint,
        prev_resolved_decision=payload.prev_rounds_tiebreak_resolved_decision,
        prev_resolved_ranks_by_name=payload.prev_rounds_tiebreak_resolved_ranks_by_name,
        resolved_decisions=payload.time_tiebreak_decisions,
        resolved_fingerprint=payload.time_tiebreak_resolved_fingerprint,
        resolved_decision=payload.time_tiebreak_resolved_decision,
    )
    overall_rank_override = {
        row["name"]: int(row["rank"]) for row in tiebreak_context["overall_rows"]
    }
    overall_tb_time = {
        row["name"]: bool(row.get("tb_time")) for row in tiebreak_context["overall_rows"]
    }
    overall_tb_prev = {
        row["name"]: bool(row.get("tb_prev")) for row in tiebreak_context["overall_rows"]
    }
    active_route_rank_override = {
        row["name"]: int(row["rank"]) for row in tiebreak_context["route_rows"]
    }
    active_route_tb_time = {
        row["name"]: bool(row.get("tb_time")) for row in tiebreak_context["route_rows"]
    }
    active_route_tb_prev = {
        row["name"]: bool(row.get("tb_prev")) for row in tiebreak_context["route_rows"]
    }

    def time_for(name: str, idx: int):
        arr = times.get(name, [])
        return _to_seconds(arr[idx]) if idx < len(arr) else None

    # ---------- excel + pdf TOTAL ----------
    overall_df = _build_overall_df(
        payload,
        times,
        rank_override=overall_rank_override,
        tb_time_flags=overall_tb_time,
        tb_prev_flags=overall_tb_prev,
    )
    _format_overall_score_columns_for_display(
        overall_df,
        route_count=payload.route_count,
        holds_counts=payload.holds_counts,
        active_holds_count=payload.active_holds_count,
    )
    xlsx_tot = cat_dir / "overall.xlsx"
    pdf_tot = cat_dir / "overall.pdf"
    overall_df.to_excel(xlsx_tot, index=False)
    _df_to_pdf(
        overall_df,
        pdf_tot,
        title=f"{payload.categorie} – Overall",
        notes=tb_notes_for_df(overall_df),
    )
    saved_paths = [xlsx_tot, pdf_tot]

    # ---------- excel + pdf BY‑ROUTE ----------
    scores = payload.scores
    for r in range(payload.route_count):
        # 1) collect (name, raw score, time) for route r
        route_list = [
            (name, arr[r] if r < len(arr) else None, time_for(name, r))
            for name, arr in scores.items()
        ]
        # 2) sort by score desc (None -> last), then name asc for stable output
        route_list_sorted = sorted(
            route_list,
            key=lambda x: (
                -x[1] if x[1] is not None else math.inf,
                x[0].lower(),
            ),
        )

        # 3) compute per-route ranking points with tie-handling:
        # ties share the average of the tied positions (e.g. tie for 2nd/3rd => 2.5 points).
        points = {}
        pos = 1
        i = 0
        while i < len(route_list_sorted):
            same_score = [
                route_list_sorted[j]
                for j in range(i, len(route_list_sorted))
                if route_list_sorted[j][1] == route_list_sorted[i][1]
            ]
            first = pos
            last = pos + len(same_score) - 1
            avg_rank = (first + last) / 2
            for name, _, _ in same_score:
                points[name] = avg_rank
            pos += len(same_score)
            i += len(same_score)

        # 4) build a "Rank" column with ties (same score -> same rank number)
        ranks = []
        prev_score = None
        prev_rank = 0
        for idx, (_, score, tm) in enumerate(route_list_sorted, start=1):
            if score == prev_score:
                rank = prev_rank
            else:
                rank = idx
            ranks.append(rank)
            prev_score = score
            prev_rank = rank

        is_active_route = (r + 1) == int(active_route_index)
        if is_active_route:
            route_list_sorted = sorted(
                route_list_sorted,
                key=lambda item: (
                    active_route_rank_override.get(item[0], 10**9),
                    item[0].lower(),
                ),
            )
            ranks = [
                active_route_rank_override.get(name, ranks[idx])
                for idx, (name, _, _) in enumerate(route_list_sorted)
            ]

        df_route = pd.DataFrame(
            [
                {
                    "Rank": ranks[i],
                    "Name": name,
                    "Club": payload.clubs.get(name, ""),
                    "Score": score,
                    **({"Time": _format_time(tm)} if use_time else {}),
                    "TB": tb_label(
                        bool(is_active_route and active_route_tb_time.get(name)),
                        bool(is_active_route and active_route_tb_prev.get(name)),
                    ),
                    "Points": points.get(name),
                }
                for i, (name, score, tm) in enumerate(route_list_sorted)
            ]
        )
        if "TB" in df_route.columns and not any(
            isinstance(value, str) and value.strip()
            for value in df_route["TB"].tolist()
        ):
            df_route.drop(columns=["TB"], inplace=True)
        route_holds_count = _resolve_route_holds_count(
            route_idx=r,
            route_count=payload.route_count,
            holds_counts=payload.holds_counts,
            active_holds_count=payload.active_holds_count,
        )
        _format_route_score_column_for_display(
            df_route,
            holds_count=route_holds_count,
        )

        # 5) save Excel and PDF for this route
        xlsx_route = cat_dir / f"route_{r+1}.xlsx"
        pdf_route = cat_dir / f"route_{r+1}.pdf"
        df_route.to_excel(xlsx_route, index=False)
        _df_to_pdf(
            df_route,
            pdf_route,
            title=f"{payload.categorie} – Route {r+1}",
            notes=tb_notes_for_df(df_route),
        )
        saved_paths.extend([xlsx_route, pdf_route])

    return {
        "status": "ok",
        "saved": [str(p) for p in saved_paths],
        "time_tiebreak_fingerprint": tiebreak_context.get("fingerprint"),
        "time_tiebreak_has_eligible_tie": tiebreak_context.get("has_eligible_tie"),
        "time_tiebreak_is_resolved": tiebreak_context.get("is_resolved"),
    }


# ------- helpers -------
def _build_overall_df(
    p: RankingIn,
    normalized_times: dict[str, list[int | None]] | None = None,
    rank_override: dict[str, int] | None = None,
    tb_time_flags: dict[str, bool] | None = None,
    tb_prev_flags: dict[str, bool] | None = None,
) -> pd.DataFrame:
    return build_overall_df(
        p,
        normalized_times=normalized_times,
        rank_override=rank_override,
        tb_time_flags=tb_time_flags,
        tb_prev_flags=tb_prev_flags,
    )


def _build_by_route_df(p: RankingIn) -> pd.DataFrame:
    return build_by_route_df(p)


def _format_time(val) -> str | None:
    return format_time(val)


def _to_seconds(val) -> int | None:
    return to_seconds(val)


def _df_to_pdf(
    df: pd.DataFrame,
    pdf_path: Path,
    title: str = "Ranking",
    notes: list[str] | None = None,
):
    return df_to_pdf(df, pdf_path, title=title, notes=notes)
