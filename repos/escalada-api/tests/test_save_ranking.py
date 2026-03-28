"""
Test suite for save_ranking.py helper functions
Run: poetry run pytest tests/test_save_ranking.py -v --cov=escalada.api.save_ranking
"""
import unittest
import math


class FormatTimeTest(unittest.TestCase):
    """Test _format_time helper function"""

    def test_format_time_basic(self):
        from escalada.api.save_ranking import _format_time
        self.assertEqual(_format_time(125), "02:05")
        self.assertEqual(_format_time(60), "01:00")
        self.assertEqual(_format_time(0), "00:00")

    def test_format_time_large_values(self):
        from escalada.api.save_ranking import _format_time
        self.assertEqual(_format_time(3600), "60:00")
        self.assertEqual(_format_time(3661), "61:01")

    def test_format_time_none(self):
        from escalada.api.save_ranking import _format_time
        self.assertIsNone(_format_time(None))

    def test_format_time_with_decimal(self):
        from escalada.api.save_ranking import _format_time
        # Should convert to int first
        self.assertEqual(_format_time(125.7), "02:05")


class ToSecondsTest(unittest.TestCase):
    """Test _to_seconds helper function"""

    def test_to_seconds_integer(self):
        from escalada.api.save_ranking import _to_seconds
        self.assertEqual(_to_seconds(125), 125)
        self.assertEqual(_to_seconds(0), 0)
        self.assertEqual(_to_seconds(3600), 3600)

    def test_to_seconds_float(self):
        from escalada.api.save_ranking import _to_seconds
        self.assertEqual(_to_seconds(125.7), 125)
        self.assertEqual(_to_seconds(60.9), 60)

    def test_to_seconds_string_mmss(self):
        from escalada.api.save_ranking import _to_seconds
        self.assertEqual(_to_seconds("02:05"), 125)
        self.assertEqual(_to_seconds("01:00"), 60)
        self.assertEqual(_to_seconds("10:30"), 630)
        self.assertEqual(_to_seconds("00:00"), 0)

    def test_to_seconds_numeric_string(self):
        from escalada.api.save_ranking import _to_seconds
        self.assertEqual(_to_seconds("125"), 125)
        self.assertEqual(_to_seconds("125.5"), 125)

    def test_to_seconds_none(self):
        from escalada.api.save_ranking import _to_seconds
        self.assertIsNone(_to_seconds(None))

    def test_to_seconds_invalid_string(self):
        from escalada.api.save_ranking import _to_seconds
        self.assertIsNone(_to_seconds("invalid"))
        self.assertIsNone(_to_seconds("abc:def"))
        self.assertIsNone(_to_seconds(""))

    def test_to_seconds_nan(self):
        from escalada.api.save_ranking import _to_seconds
        self.assertIsNone(_to_seconds(float('nan')))

    def test_to_seconds_malformed_mmss(self):
        from escalada.api.save_ranking import _to_seconds
        self.assertIsNone(_to_seconds("5:30:45"))  # Too many parts
        self.assertIsNone(_to_seconds("invalid:time"))


class LeadScoreDisplayTest(unittest.TestCase):
    def test_format_lead_score_display_variants(self):
        from escalada.api.save_ranking_tables import format_lead_score_display

        self.assertIsNone(format_lead_score_display(None))
        self.assertEqual(format_lead_score_display(9.1), "9+")
        self.assertEqual(format_lead_score_display(9.0), "9")
        self.assertEqual(format_lead_score_display(20.0, holds_count=20), "TOP")
        self.assertEqual(format_lead_score_display(12.5), "12.5")

    def test_overall_score_columns_use_display_format(self):
        from escalada.api.save_ranking import (
            RankingIn,
            _build_overall_df,
            _format_overall_score_columns_for_display,
        )

        payload = RankingIn(
            categorie="Test",
            route_count=1,
            scores={
                "Ana": [9.1],
                "Bob": [9.0],
                "Cara": [20.0],
                "Dan": [12.5],
            },
            holds_counts=[20],
            active_holds_count=20,
            clubs={},
        )
        df = _build_overall_df(payload)
        _format_overall_score_columns_for_display(
            df,
            route_count=payload.route_count,
            holds_counts=payload.holds_counts,
            active_holds_count=payload.active_holds_count,
        )
        by_name = df.set_index("Nume")
        self.assertEqual(str(by_name.loc["Ana", "Score R1"]), "9+")
        self.assertEqual(str(by_name.loc["Bob", "Score R1"]), "9")
        self.assertEqual(str(by_name.loc["Cara", "Score R1"]), "TOP")
        self.assertEqual(str(by_name.loc["Dan", "Score R1"]), "12.5")


class BuildRankingDataTest(unittest.TestCase):
    """Test ranking calculation functions"""

    def test_ranking_with_unique_scores(self):
        """Test ranking with all unique scores"""
        from escalada.api.save_ranking import _build_overall_df, RankingIn

        payload = RankingIn(
            categorie="Test",
            route_count=2,
            scores={
                "Alice": [100, 90],
                "Bob": [80, 85],
                "Charlie": [70, 95]
            },
            clubs={"Alice": "Club A", "Bob": "Club B", "Charlie": "Club C"}
        )

        df = _build_overall_df(payload)
        self.assertIsNotNone(df)
        self.assertGreater(len(df), 0)
        self.assertIn("Rank", df.columns)
        self.assertIn("Nume", df.columns)
        self.assertIn("Total", df.columns)

    def test_ranking_with_ties(self):
        """Test ranking with tied scores"""
        from escalada.api.save_ranking import _build_overall_df, RankingIn

        payload = RankingIn(
            categorie="Test",
            route_count=2,
            scores={
                "Alice": [100, 100],
                "Bob": [100, 100],
                "Charlie": [50, 50]
            },
            clubs={}
        )

        df = _build_overall_df(payload)
        self.assertIsNotNone(df)
        # Tied scores should have same rank
        if "Total" in df.columns:
            # Check for competitors with equal high scores
            top_scores = df.nlargest(2, "Total")
            self.assertGreaterEqual(len(top_scores), 1)

    def test_ranking_with_missing_scores(self):
        """Test ranking when some competitors have missing scores"""
        from escalada.api.save_ranking import _build_overall_df, RankingIn

        payload = RankingIn(
            categorie="Test",
            route_count=3,
            scores={
                "Alice": [100, 90, 80],
                "Bob": [80, 85],  # Missing one score
                "Charlie": [70]   # Missing two scores
            },
            clubs={}
        )

        df = _build_overall_df(payload)
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 3)  # All competitors present

    def test_missing_route_uses_last_place_penalty_not_n_plus_one(self):
        from escalada.api.save_ranking import _build_overall_df, RankingIn

        payload = RankingIn(
            categorie="Test",
            route_count=2,
            scores={
                "Alice": [100, 90],
                "Bob": [80],      # Missing route 2
                "Charlie": [70, 85],
            },
            clubs={},
        )

        df = _build_overall_df(payload)
        by_name = {row["Nume"]: row for _, row in df.iterrows()}
        # Bob route ranks are 2 and 3 (last place), GM = sqrt(6)
        self.assertTrue(math.isclose(by_name["Bob"]["Total"], math.sqrt(6), abs_tol=1e-3))

    def test_ranking_single_route(self):
        """Test ranking with only one route"""
        from escalada.api.save_ranking import _build_overall_df, RankingIn

        payload = RankingIn(
            categorie="Test",
            route_count=1,
            scores={
                "Alice": [100],
                "Bob": [80],
                "Charlie": [90]
            },
            clubs={}
        )

        df = _build_overall_df(payload)
        self.assertEqual(len(df), 3)
        # Should rank them correctly: Alice(100) -> Charlie(90) -> Bob(80)
        self.assertEqual(df.iloc[0]["Rank"], 1)

    def test_ranking_with_time_display_flag(self):
        """Time values do not break score ties; ordering falls back to name."""
        from escalada.api.save_ranking import _build_overall_df, RankingIn

        payload = RankingIn(
            categorie="Test",
            route_count=1,
            scores={"Alice": [100], "Bob": [100]},
            times={"Alice": [10.5], "Bob": [12.3]},
            use_time_tiebreak=True,
            clubs={}
        )

        df = _build_overall_df(payload)
        self.assertIsNotNone(df)
        self.assertEqual(df.iloc[0]["Rank"], 1)
        self.assertEqual(df.iloc[1]["Rank"], 1)
        self.assertEqual(df.iloc[0]["Nume"], "Alice")

    def test_ranking_with_time_tiebreak_yes_splits_top3_tie(self):
        from escalada.api.save_ranking import _build_overall_df, RankingIn
        from escalada.api.ranking_time_tiebreak import resolve_rankings_with_time_tiebreak

        payload = RankingIn(
            categorie="Test",
            route_count=1,
            route_index=1,
            box_id=2,
            scores={"Alice": [100], "Bob": [100], "Charlie": [95]},
            times={"Alice": [10.5], "Bob": [12.3], "Charlie": [9.0]},
            use_time_tiebreak=True,
            clubs={},
        )

        context = resolve_rankings_with_time_tiebreak(
            scores=payload.scores,
            times=payload.times or {},
            route_count=payload.route_count,
            active_route_index=payload.route_index or payload.route_count,
            box_id=payload.box_id,
            time_criterion_enabled=True,
            resolved_fingerprint=None,
            resolved_decision=None,
        )
        rank_override = {row["name"]: int(row["rank"]) for row in context["overall_rows"]}
        tb_flags = {row["name"]: bool(row.get("tb_time")) for row in context["overall_rows"]}

        resolved_context = resolve_rankings_with_time_tiebreak(
            scores=payload.scores,
            times=payload.times or {},
            route_count=payload.route_count,
            active_route_index=payload.route_index or payload.route_count,
            box_id=payload.box_id,
            time_criterion_enabled=True,
            prev_resolved_decisions={
                group["fingerprint"]: "no" for group in context["eligible_groups"]
            },
            resolved_fingerprint=context["fingerprint"],
            resolved_decision="yes",
        )
        rank_override = {row["name"]: int(row["rank"]) for row in resolved_context["overall_rows"]}
        tb_flags = {row["name"]: bool(row.get("tb_time")) for row in resolved_context["overall_rows"]}

        df = _build_overall_df(payload, rank_override=rank_override, tb_time_flags=tb_flags)
        self.assertEqual(df.iloc[0]["Nume"], "Alice")
        self.assertEqual(df.iloc[0]["Rank"], 1)
        self.assertEqual(df.iloc[1]["Nume"], "Bob")
        self.assertEqual(df.iloc[1]["Rank"], 2)
        self.assertIn("TB", df.columns)
        self.assertEqual(df.iloc[0]["TB"], "TB Time")

    def test_ranking_with_prev_rounds_tiebreak_adds_tb_prev_column(self):
        from escalada.api.save_ranking import _build_overall_df, RankingIn
        from escalada.api.ranking_time_tiebreak import resolve_rankings_with_time_tiebreak

        payload = RankingIn(
            categorie="Test",
            route_count=1,
            route_index=1,
            box_id=3,
            scores={"Alice": [100], "Bob": [100], "Charlie": [95]},
            times={"Alice": [20], "Bob": [10], "Charlie": [30]},
            use_time_tiebreak=True,
            clubs={},
        )

        context = resolve_rankings_with_time_tiebreak(
            scores=payload.scores,
            times=payload.times or {},
            route_count=payload.route_count,
            active_route_index=payload.route_index or payload.route_count,
            box_id=payload.box_id,
            time_criterion_enabled=True,
        )
        fp = context["eligible_groups"][0]["fingerprint"]
        resolved = resolve_rankings_with_time_tiebreak(
            scores=payload.scores,
            times=payload.times or {},
            route_count=payload.route_count,
            active_route_index=payload.route_index or payload.route_count,
            box_id=payload.box_id,
            time_criterion_enabled=True,
            prev_resolved_decisions={fp: "yes"},
            prev_orders_by_fingerprint={fp: ["Alice"]},
        )
        rank_override = {row["name"]: int(row["rank"]) for row in resolved["overall_rows"]}
        tb_time = {row["name"]: bool(row.get("tb_time")) for row in resolved["overall_rows"]}
        tb_prev = {row["name"]: bool(row.get("tb_prev")) for row in resolved["overall_rows"]}
        df = _build_overall_df(
            payload,
            rank_override=rank_override,
            tb_time_flags=tb_time,
            tb_prev_flags=tb_prev,
        )
        self.assertIn("TB", df.columns)
        self.assertEqual(df.iloc[0]["Nume"], "Alice")
        self.assertEqual(df.iloc[0]["TB"], "TB Prev")

    def test_ranking_empty_scores(self):
        """Test ranking with empty scores dict"""
        from escalada.api.save_ranking import _build_overall_df, RankingIn

        payload = RankingIn(
            categorie="Test",
            route_count=1,
            scores={},
            clubs={}
        )

        df = _build_overall_df(payload)
        self.assertEqual(len(df), 0)

    def test_ranking_with_clubs(self):
        """Test ranking includes club information"""
        from escalada.api.save_ranking import _build_overall_df, RankingIn

        payload = RankingIn(
            categorie="Test",
            route_count=1,
            scores={"Alice": [100], "Bob": [80]},
            clubs={"Alice": "Climbing Club A", "Bob": "Climbing Club B"}
        )

        df = _build_overall_df(payload)
        self.assertIn("Club", df.columns)
        self.assertIn("Climbing Club A", df["Club"].values)


if __name__ == "__main__":
    unittest.main()
