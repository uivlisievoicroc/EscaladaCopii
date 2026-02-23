from escalada.api.ranking_time_tiebreak import resolve_rankings_with_time_tiebreak
import math


def _ctx(**kwargs):
    defaults = {
        "scores": {
            "Ana": [10.0],
            "Bob": [10.0],
            "Cris": [9.0],
            "Dan": [8.0],
        },
        "times": {
            "Ana": [120],
            "Bob": [140],
            "Cris": [150],
            "Dan": [160],
        },
        "route_count": 1,
        "active_route_index": 1,
        "box_id": 0,
        "time_criterion_enabled": True,
        "active_holds_count": 10,
        "resolved_fingerprint": None,
        "resolved_decision": None,
    }
    defaults.update(kwargs)
    return resolve_rankings_with_time_tiebreak(**defaults)


def test_unresolved_podium_tie_exposes_pending_previous_rounds_event():
    result = _ctx()
    assert result["has_eligible_tie"] is True
    assert result["fingerprint"]
    rows = result["overall_rows"]
    assert rows[0]["rank"] == 1
    assert rows[1]["rank"] == 1
    events = result["eligible_groups"]
    assert events
    assert events[0]["stage"] == "previous_rounds"
    assert events[0]["affects_podium"] is True
    assert events[0]["status"] in {"pending", "error"}
    assert result["is_resolved"] is False


def test_previous_rounds_yes_splits_top3_tie():
    initial = _ctx()
    fp = initial["eligible_groups"][0]["fingerprint"]
    resolved = _ctx(
        prev_resolved_decisions={fp: "yes"},
        prev_ranks_by_fingerprint={fp: {"Ana": 1, "Bob": 2}},
    )
    by_name = {row["name"]: row for row in resolved["overall_rows"]}
    assert by_name["Ana"]["rank"] == 1
    assert by_name["Bob"]["rank"] == 2
    assert by_name["Ana"]["tb_prev"] is True
    assert by_name["Ana"]["tb_prev_helper"]["prev_ranks_by_name"] == {"Ana": 1, "Bob": 2}
    assert by_name["Ana"]["tb_prev_helper"]["members"] == ["Ana", "Bob"]
    assert resolved["is_resolved"] is True


def test_tb_prev_helper_absent_when_no_historical_data_exists():
    result = _ctx()
    by_name = {row["name"]: row for row in result["overall_rows"]}
    assert "tb_prev_helper" not in by_name["Ana"]
    assert "tb_prev_helper" not in by_name["Bob"]


def test_previous_rounds_no_then_time_yes_splits_tie():
    initial = _ctx()
    fp = initial["eligible_groups"][0]["fingerprint"]
    resolved = _ctx(
        prev_resolved_decisions={fp: "no"},
        resolved_decisions={fp: "yes"},
    )
    by_name = {row["name"]: row for row in resolved["overall_rows"]}
    assert by_name["Ana"]["rank"] == 1
    assert by_name["Bob"]["rank"] == 2
    assert by_name["Ana"]["tb_time"] is True
    assert by_name["Bob"]["tb_time"] is True
    assert resolved["is_resolved"] is True


def test_three_way_partial_previous_rounds_then_time_for_subgroup():
    initial = _ctx(
        scores={"Ana": [10.0], "Bob": [10.0], "Cris": [10.0], "Dan": [8.0]},
        times={"Ana": [100], "Bob": [130], "Cris": [150], "Dan": [200]},
    )
    fp_prev = initial["eligible_groups"][0]["fingerprint"]
    after_prev = _ctx(
        scores={"Ana": [10.0], "Bob": [10.0], "Cris": [10.0], "Dan": [8.0]},
        times={"Ana": [100], "Bob": [130], "Cris": [150], "Dan": [200]},
        prev_resolved_decisions={fp_prev: "yes"},
        prev_ranks_by_fingerprint={fp_prev: {"Cris": 1, "Ana": 2, "Bob": 2}},
    )
    time_events = [ev for ev in after_prev["eligible_groups"] if ev["stage"] == "time"]
    assert time_events
    fp_time = time_events[0]["fingerprint"]
    resolved = _ctx(
        scores={"Ana": [10.0], "Bob": [10.0], "Cris": [10.0], "Dan": [8.0]},
        times={"Ana": [100], "Bob": [130], "Cris": [150], "Dan": [200]},
        prev_resolved_decisions={fp_prev: "yes"},
        prev_ranks_by_fingerprint={fp_prev: {"Cris": 1, "Ana": 2, "Bob": 2}},
        resolved_decisions={fp_time: "yes"},
    )
    assert [row["name"] for row in resolved["overall_rows"][:3]] == ["Cris", "Ana", "Bob"]
    assert [row["rank"] for row in resolved["overall_rows"][:3]] == [1, 2, 3]


def test_non_podium_tie_stays_shared_and_is_not_exposed_for_resolution():
    result = _ctx(
        scores={
            "Ana": [10.0],
            "Bob": [9.0],
            "Cris": [8.0],
            "Dan": [7.0],
            "Ema": [7.0],
        },
        times={
            "Ana": [100],
            "Bob": [110],
            "Cris": [120],
            "Dan": [130],
            "Ema": [140],
        },
    )
    assert result["has_eligible_tie"] is True
    assert result["is_resolved"] is True
    assert result["eligible_groups"] == []


def test_invalid_previous_rounds_input_reports_error():
    initial = _ctx()
    fp = initial["eligible_groups"][0]["fingerprint"]
    result = _ctx(
        prev_resolved_decisions={fp: "yes"},
        prev_ranks_by_fingerprint={fp: {"Ana": 1}},
    )
    assert result["is_resolved"] is False
    assert result["errors"] == []
    rows = {row["name"]: row for row in result["overall_rows"]}
    assert rows["Ana"]["rank"] == 1
    assert rows["Bob"]["rank"] == 2


def test_old_podium_decision_does_not_split_when_tie_moves_below_podium():
    initial = _ctx(
        scores={"Top": [40.0], "Ana": [30.0], "Bob": [30.0]},
        times={"Top": [80], "Ana": [100], "Bob": [120]},
        active_holds_count=100,
    )
    fp = initial["eligible_groups"][0]["fingerprint"]
    resolved = _ctx(
        scores={"Top": [40.0], "Ana": [30.0], "Bob": [30.0]},
        times={"Top": [80], "Ana": [100], "Bob": [120]},
        active_holds_count=100,
        prev_resolved_decisions={fp: "yes"},
        prev_ranks_by_fingerprint={fp: {"Ana": 1, "Bob": 2}},
    )
    resolved_by_name = {row["name"]: row for row in resolved["overall_rows"]}
    assert resolved_by_name["Ana"]["rank"] == 2
    assert resolved_by_name["Bob"]["rank"] == 3

    moved = _ctx(
        scores={
            "Top": [40.0],
            "Cara": [35.0],
            "Dan": [34.0],
            "Ana": [30.0],
            "Bob": [30.0],
        },
        times={
            "Top": [80],
            "Cara": [90],
            "Dan": [95],
            "Ana": [100],
            "Bob": [120],
        },
        active_holds_count=100,
        prev_resolved_decisions={fp: "yes"},
        prev_ranks_by_fingerprint={fp: {"Ana": 1, "Bob": 2}},
        prev_resolved_fingerprint=fp,
        prev_resolved_decision="yes",
    )
    moved_by_name = {row["name"]: row for row in moved["overall_rows"]}
    assert moved_by_name["Ana"]["rank"] == 4
    assert moved_by_name["Bob"]["rank"] == 4


def test_tail_below_podium_collapses_when_tie_group_spans_3_4_5():
    initial = _ctx(
        scores={"Top": [40.0], "Second": [39.0], "Ana": [30.0], "Bob": [30.0], "Cara": [30.0]},
        times={"Top": [80], "Second": [85], "Ana": [100], "Bob": [110], "Cara": [120]},
        active_holds_count=100,
    )
    fp = initial["eligible_groups"][0]["fingerprint"]
    resolved = _ctx(
        scores={"Top": [40.0], "Second": [39.0], "Ana": [30.0], "Bob": [30.0], "Cara": [30.0]},
        times={"Top": [80], "Second": [85], "Ana": [100], "Bob": [110], "Cara": [120]},
        active_holds_count=100,
        prev_resolved_decisions={fp: "yes"},
        prev_ranks_by_fingerprint={fp: {"Ana": 1, "Bob": 2, "Cara": 3}},
        prev_resolved_fingerprint=fp,
        prev_resolved_decision="yes",
    )
    rows = {row["name"]: row for row in resolved["overall_rows"]}
    assert rows["Ana"]["rank"] == 3
    assert rows["Bob"]["rank"] == 4
    assert rows["Cara"]["rank"] == 4


def test_incremental_prev_rounds_memory_keeps_existing_split_when_tie_expands():
    initial = _ctx(
        scores={"Ana": [10.0], "Bob": [10.0], "Dan": [8.0]},
        times={"Ana": [100], "Bob": [120], "Dan": [200]},
    )
    fp_prev = initial["eligible_groups"][0]["fingerprint"]
    lineage_key = initial["eligible_groups"][0]["lineage_key"]
    resolved_two = _ctx(
        scores={"Ana": [10.0], "Bob": [10.0], "Dan": [8.0]},
        times={"Ana": [100], "Bob": [120], "Dan": [200]},
        prev_resolved_decisions={fp_prev: "yes"},
        prev_ranks_by_fingerprint={fp_prev: {"Ana": 1, "Bob": 2}},
        prev_lineage_ranks_by_key={lineage_key: {"Ana": 1, "Bob": 2}},
    )
    rows_two = {row["name"]: row for row in resolved_two["overall_rows"]}
    assert rows_two["Ana"]["rank"] == 1
    assert rows_two["Bob"]["rank"] == 2

    expanded = _ctx(
        scores={"Ana": [10.0], "Bob": [10.0], "Cris": [10.0], "Dan": [8.0]},
        times={"Ana": [100], "Bob": [120], "Cris": [140], "Dan": [200]},
        prev_lineage_ranks_by_key={lineage_key: {"Ana": 1, "Bob": 2}},
    )
    rows_expanded = {row["name"]: row for row in expanded["overall_rows"]}
    assert rows_expanded["Ana"]["rank"] == 1
    assert rows_expanded["Bob"]["rank"] == 2
    assert rows_expanded["Cris"]["rank"] == 3
    assert rows_expanded["Ana"]["tb_prev_helper"]["prev_ranks_by_name"] == {"Ana": 1, "Bob": 2}
    assert rows_expanded["Ana"]["tb_prev_helper"]["members"] == ["Ana", "Bob"]
    pending_prev = [ev for ev in expanded["eligible_groups"] if ev["stage"] == "previous_rounds"]
    assert pending_prev
    assert pending_prev[0]["lineage_key"] == lineage_key
    assert pending_prev[0]["known_prev_ranks_by_name"] == {"Ana": 1, "Bob": 2}
    assert pending_prev[0]["missing_prev_rounds_members"] == ["Cris"]
    assert pending_prev[0]["requires_prev_rounds_input"] is True


def test_overall_uses_geometric_mean_for_multi_route_no_tie():
    result = resolve_rankings_with_time_tiebreak(
        scores={"Ana": [10.0, 10.0], "Bob": [9.0, 9.0], "Cris": [8.0, 8.0]},
        times={"Ana": [100, 100], "Bob": [110, 110], "Cris": [120, 120]},
        route_count=2,
        active_route_index=2,
        box_id=1,
        time_criterion_enabled=True,
    )
    by_name = {row["name"]: row for row in result["overall_rows"]}
    assert by_name["Ana"]["rank"] == 1
    assert by_name["Bob"]["rank"] == 2
    assert by_name["Cris"]["rank"] == 3
    assert math.isclose(by_name["Ana"]["total"], 1.0, rel_tol=1e-9)
    assert math.isclose(by_name["Bob"]["total"], 2.0, rel_tol=1e-9)
    assert math.isclose(by_name["Cris"]["total"], 3.0, rel_tol=1e-9)


def test_route_tie_uses_average_rank_in_geometric_mean():
    result = resolve_rankings_with_time_tiebreak(
        scores={"Ana": [10.0, 9.0], "Bob": [10.0, 7.0], "Cris": [8.0, 10.0]},
        times={"Ana": [100, 110], "Bob": [120, 130], "Cris": [140, 90]},
        route_count=2,
        active_route_index=2,
        box_id=2,
        time_criterion_enabled=False,
    )
    by_name = {row["name"]: row for row in result["overall_rows"]}
    expected = math.sqrt(3.0)  # Ana/Cris => route ranks 1.5 and 2 (or 3 and 1)
    assert math.isclose(by_name["Ana"]["total"], expected, rel_tol=1e-9)
    assert math.isclose(by_name["Cris"]["total"], expected, rel_tol=1e-9)
    assert by_name["Ana"]["rank"] == 1
    assert by_name["Cris"]["rank"] == 1


def test_missing_route_uses_last_place_rank_for_geometric_mean():
    result = resolve_rankings_with_time_tiebreak(
        scores={"Ana": [10.0, 9.0], "Bob": [9.0], "Cris": [8.0, 8.0]},
        times={"Ana": [100, 100], "Bob": [110], "Cris": [120, 130]},
        route_count=2,
        active_route_index=2,
        box_id=3,
        time_criterion_enabled=False,
    )
    by_name = {row["name"]: row for row in result["overall_rows"]}
    # Bob missing route 2 => rank 3 on route 2 (last place), not 4.
    assert math.isclose(by_name["Bob"]["total"], math.sqrt(6.0), rel_tol=1e-9)
    assert math.isclose(by_name["Cris"]["total"], math.sqrt(6.0), rel_tol=1e-9)
    assert by_name["Bob"]["rank"] == 2
    assert by_name["Cris"]["rank"] == 2


def test_gm_top3_tie_requires_prev_then_time_resolution():
    initial = resolve_rankings_with_time_tiebreak(
        scores={"Ana": [100.0, 80.0], "Bob": [80.0, 100.0], "Cris": [90.0, 90.0], "Dan": [70.0, 70.0]},
        times={"Ana": [100, 120], "Bob": [110, 90], "Cris": [130, 130], "Dan": [150, 150]},
        route_count=2,
        active_route_index=2,
        box_id=4,
        time_criterion_enabled=True,
    )
    prev_event = initial["eligible_groups"][0]
    assert prev_event["stage"] == "previous_rounds"
    assert prev_event["affects_podium"] is True

    after_prev_no = resolve_rankings_with_time_tiebreak(
        scores={"Ana": [100.0, 80.0], "Bob": [80.0, 100.0], "Cris": [90.0, 90.0], "Dan": [70.0, 70.0]},
        times={"Ana": [100, 120], "Bob": [110, 90], "Cris": [130, 130], "Dan": [150, 150]},
        route_count=2,
        active_route_index=2,
        box_id=4,
        time_criterion_enabled=True,
        prev_resolved_decisions={prev_event["fingerprint"]: "no"},
    )
    time_events = [ev for ev in after_prev_no["eligible_groups"] if ev["stage"] == "time"]
    assert time_events
    time_fp = time_events[0]["fingerprint"]

    resolved = resolve_rankings_with_time_tiebreak(
        scores={"Ana": [100.0, 80.0], "Bob": [80.0, 100.0], "Cris": [90.0, 90.0], "Dan": [70.0, 70.0]},
        times={"Ana": [100, 120], "Bob": [110, 90], "Cris": [130, 130], "Dan": [150, 150]},
        route_count=2,
        active_route_index=2,
        box_id=4,
        time_criterion_enabled=True,
        prev_resolved_decisions={prev_event["fingerprint"]: "no"},
        resolved_decisions={time_fp: "yes"},
    )
    rows = {row["name"]: row for row in resolved["overall_rows"]}
    assert rows["Bob"]["rank"] == 1
    assert rows["Ana"]["rank"] == 2
    assert rows["Bob"]["tb_time"] is True
    assert rows["Ana"]["tb_time"] is True


def test_gm_tie_outside_podium_remains_shared_without_prompt():
    result = resolve_rankings_with_time_tiebreak(
        scores={
            "A": [50.0, 50.0],
            "B": [40.0, 40.0],
            "C": [30.0, 30.0],
            "D": [20.0, 10.0],
            "E": [10.0, 20.0],
        },
        times={name: [100, 100] for name in ["A", "B", "C", "D", "E"]},
        route_count=2,
        active_route_index=2,
        box_id=5,
        time_criterion_enabled=True,
    )
    assert result["has_eligible_tie"] is True
    assert result["eligible_groups"] == []
    by_name = {row["name"]: row for row in result["overall_rows"]}
    assert by_name["D"]["rank"] == 4
    assert by_name["E"]["rank"] == 4


def test_resolved_gm_podium_tie_collapses_to_shared_when_dropped_below_top3():
    initial = resolve_rankings_with_time_tiebreak(
        scores={"Ana": [100.0, 90.0], "Bob": [90.0, 100.0], "Cris": [80.0, 80.0]},
        times={"Ana": [100, 100], "Bob": [120, 120], "Cris": [140, 140]},
        route_count=2,
        active_route_index=2,
        box_id=6,
        time_criterion_enabled=True,
    )
    fp = initial["eligible_groups"][0]["fingerprint"]
    resolved = resolve_rankings_with_time_tiebreak(
        scores={"Ana": [100.0, 90.0], "Bob": [90.0, 100.0], "Cris": [80.0, 80.0]},
        times={"Ana": [100, 100], "Bob": [120, 120], "Cris": [140, 140]},
        route_count=2,
        active_route_index=2,
        box_id=6,
        time_criterion_enabled=True,
        prev_resolved_decisions={fp: "yes"},
        prev_ranks_by_fingerprint={fp: {"Ana": 1, "Bob": 2}},
        prev_resolved_fingerprint=fp,
        prev_resolved_decision="yes",
    )
    assert {row["name"]: row["rank"] for row in resolved["overall_rows"]}["Ana"] == 1

    moved = resolve_rankings_with_time_tiebreak(
        scores={
            "X": [120.0, 120.0],
            "Y": [115.0, 115.0],
            "Z": [110.0, 110.0],
            "Ana": [100.0, 90.0],
            "Bob": [90.0, 100.0],
            "Cris": [80.0, 80.0],
        },
        times={name: [100, 100] for name in ["X", "Y", "Z", "Ana", "Bob", "Cris"]},
        route_count=2,
        active_route_index=2,
        box_id=6,
        time_criterion_enabled=True,
        prev_resolved_decisions={fp: "yes"},
        prev_ranks_by_fingerprint={fp: {"Ana": 1, "Bob": 2}},
        prev_resolved_fingerprint=fp,
        prev_resolved_decision="yes",
    )
    moved_by_name = {row["name"]: row for row in moved["overall_rows"]}
    assert moved_by_name["Ana"]["rank"] == 4
    assert moved_by_name["Bob"]["rank"] == 4
