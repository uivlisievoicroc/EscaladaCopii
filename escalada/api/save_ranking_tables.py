"""Table-building helpers for ranking exports."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

TB_TIME_LABEL = "TB Time"
TB_PREV_LABEL = "TB Prev"
TB_NOTES = (
    "Nota: TB Prev = departajare dupa rundele anterioare.",
    "TB Time = departajare dupa timp (mai mic e mai bun).",
)


def tb_label(tb_time: bool, tb_prev: bool) -> str:
    if tb_time:
        return TB_TIME_LABEL
    if tb_prev:
        return TB_PREV_LABEL
    return ""


def tb_notes_for_df(df: pd.DataFrame) -> list[str] | None:
    if "TB" not in df.columns:
        return None
    has_tb = any(
        isinstance(value, str) and value.strip()
        for value in df["TB"].tolist()
    )
    if not has_tb:
        return None
    return list(TB_NOTES)


def to_seconds(val) -> int | None:
    """Normalize various time representations into integer seconds."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if math.isnan(val):
            return None
        return int(val)
    if isinstance(val, str) and ":" in val:
        try:
            parts = val.split(":")
            if len(parts) == 2:
                m, s = parts
                return int(m) * 60 + int(s)
        except Exception:
            return None
    try:
        return int(float(val))
    except Exception:
        return None


def format_time(val) -> str | None:
    sec = to_seconds(val)
    if sec is None:
        return None
    m = sec // 60
    s = sec % 60
    return f"{m:02d}:{s:02d}"


def build_overall_df(
    payload: Any,
    normalized_times: dict[str, list[int | None]] | None = None,
    rank_override: dict[str, int] | None = None,
    tb_time_flags: dict[str, bool] | None = None,
    tb_prev_flags: dict[str, bool] | None = None,
) -> pd.DataFrame:
    """Build the overall ranking DataFrame."""
    from math import prod

    scores = payload.scores
    times = normalized_times if normalized_times is not None else (payload.times or {})
    use_time = payload.use_time_tiebreak
    rows_data = []
    n = payload.route_count
    n_comp = len(scores)

    for name, arr in scores.items():
        rp: list[float | None] = [None] * n
        for r in range(n):
            scored = []
            for nume, sc in scores.items():
                if r < len(sc) and sc[r] is not None:
                    t_val = None
                    t_arr = times.get(nume, [])
                    if r < len(t_arr):
                        t_val = t_arr[r]
                    scored.append((nume, sc[r], t_val))
            scored.sort(key=lambda x: (-x[1], x[0].lower()))

            i = 0
            pos = 1
            while i < len(scored):
                current = scored[i]
                same = [current]
                while (
                    i + len(same) < len(scored)
                    and scored[i][1] == scored[i + len(same)][1]
                ):
                    same.append(scored[i + len(same)])
                avg = (pos + pos + len(same) - 1) / 2
                for nume, _, _ in same:
                    if nume == name:
                        rp[r] = avg
                pos += len(same)
                i += len(same)

        filled = [v if v is not None else n_comp for v in rp]
        while len(filled) < n:
            filled.append(n_comp)

        total = round(prod(filled) ** (1 / n), 3)
        club = payload.clubs.get(name, "")
        row: list[str | float | None] = [name, club]
        time_row = times.get(name, [])
        for idx in range(n):
            row.append(arr[idx] if idx < len(arr) else None)
            if use_time:
                row.append(format_time(time_row[idx] if idx < len(time_row) else None))
        row.append(total)
        rows_data.append((name, row))

    cols = ["Nume", "Club"]
    for i in range(n):
        cols.append(f"Score R{i+1}")
        if use_time:
            cols.append(f"Time R{i+1}")
    cols.append("Total")
    if rank_override:
        rows_data.sort(
            key=lambda item: (
                rank_override.get(item[0], 10**9),
                item[1][-1],
                item[0].lower(),
            )
        )
        data = [row for _, row in rows_data]
        df = pd.DataFrame(data, columns=cols)
        ranks = [rank_override.get(name, idx + 1) for idx, (name, _) in enumerate(rows_data)]
    else:
        data = [row for _, row in rows_data]
        df = pd.DataFrame(data, columns=cols)
        df.sort_values(["Total", "Nume"], inplace=True)
        ranks = []
        prev_total = None
        prev_rank = 0
        for idx, total in enumerate(df["Total"], start=1):
            rank = prev_rank if total == prev_total else idx
            ranks.append(rank)
            prev_total = total
            prev_rank = rank

    tb_time_flags = tb_time_flags or {}
    tb_prev_flags = tb_prev_flags or {}
    if rank_override:
        ordered_names = [name for name, _ in rows_data]
    else:
        ordered_names = [str(row["Nume"]) for _, row in df.iterrows()]
    tb_values = [
        tb_label(
            bool(tb_time_flags.get(name)),
            bool(tb_prev_flags.get(name)),
        )
        for name in ordered_names
    ]
    if any(tb_values):
        insert_at = int(df.columns.get_loc("Nume")) + 1
        df.insert(insert_at, "TB", tb_values)

    df.insert(0, "Rank", ranks)
    return df


def build_by_route_df(payload: Any) -> pd.DataFrame:
    rows = []
    n = payload.route_count
    times = payload.times or {}
    for r in range(n):
        for name, arr in payload.scores.items():
            score = arr[r] if r < len(arr) else None
            t_arr = times.get(name, [])
            tm = t_arr[r] if r < len(t_arr) else None
            rows.append(
                {"Route": r + 1, "Name": name, "Score": score, "Time": format_time(tm)}
            )
    return pd.DataFrame(rows)
