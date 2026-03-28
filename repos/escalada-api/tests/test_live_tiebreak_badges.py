from escalada.api.live import _merge_persistent_tiebreak_badges


def test_tb_time_badge_is_not_preserved_when_athlete_drops_below_podium():
    state = {"initiated": True}

    first_rows = _merge_persistent_tiebreak_badges(
        state,
        1,
        [
            {"name": "Ana", "rank": 1, "tb_prev": True, "tb_time": False},
            {"name": "Bob", "rank": 2, "tb_prev": False, "tb_time": True},
        ],
    )
    assert first_rows[0]["tb_prev"] is True
    assert first_rows[1]["tb_time"] is True

    later_rows = _merge_persistent_tiebreak_badges(
        state,
        1,
        [
            {"name": "Ana", "rank": 4, "tb_prev": False, "tb_time": False},
            {"name": "Bob", "rank": 4, "tb_prev": False, "tb_time": False},
        ],
    )
    assert later_rows[0]["tb_prev"] is True
    assert later_rows[1].get("tb_time") is not True


def test_tiebreak_badges_reset_on_route_change():
    state = {"initiated": True}

    _merge_persistent_tiebreak_badges(
        state,
        1,
        [{"name": "Ana", "rank": 1, "tb_prev": True, "tb_time": False}],
    )

    next_route_rows = _merge_persistent_tiebreak_badges(
        state,
        2,
        [{"name": "Ana", "rank": 1, "tb_prev": False, "tb_time": False}],
    )
    assert next_route_rows[0].get("tb_prev") is not True


def test_tb_prev_helper_is_preserved_with_persistent_badge():
    state = {"initiated": True}

    first_rows = _merge_persistent_tiebreak_badges(
        state,
        1,
        [
            {
                "name": "Ana",
                "rank": 1,
                "tb_prev": True,
                "tb_time": False,
                "tb_prev_helper": {
                    "prev_ranks_by_name": {"Ana": 1, "Bob": 2},
                    "members": ["Ana", "Bob"],
                    "lineage_key": "tb-lineage:abc",
                },
            },
            {"name": "Bob", "rank": 2, "tb_prev": False, "tb_time": False},
        ],
    )
    assert first_rows[0]["tb_prev"] is True
    assert first_rows[0]["tb_prev_helper"]["prev_ranks_by_name"] == {"Ana": 1, "Bob": 2}

    later_rows = _merge_persistent_tiebreak_badges(
        state,
        1,
        [
            {"name": "Ana", "rank": 4, "tb_prev": False, "tb_time": False},
            {"name": "Bob", "rank": 4, "tb_prev": False, "tb_time": False},
        ],
    )
    assert later_rows[0]["tb_prev"] is True
    assert later_rows[0]["tb_prev_helper"]["prev_ranks_by_name"] == {"Ana": 1, "Bob": 2}
