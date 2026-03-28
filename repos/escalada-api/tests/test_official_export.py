import json
import unittest
import zipfile
from io import BytesIO


class OfficialExportZipTest(unittest.TestCase):
    def test_build_official_results_zip_contains_expected_files(self):
        from escalada.api.official_export import build_official_results_zip

        snapshot = {
            "boxId": 7,
            "competitionId": 3,
            "categorie": "U13F",
            "routesCount": 2,
            "timeCriterionEnabled": True,
            "scores": {"Ana": [3.5, 4.0], "Bob": [3.5, 3.0]},
            "times": {"Ana": [12.34, 11.0], "Bob": [13.0, 10.0]},
        }

        zip_bytes = build_official_results_zip(snapshot)
        self.assertIsInstance(zip_bytes, (bytes, bytearray))
        self.assertGreater(len(zip_bytes), 200)

        zf = zipfile.ZipFile(BytesIO(zip_bytes))
        names = set(zf.namelist())

        expected = {
            "U13F/overall.xlsx",
            "U13F/overall.pdf",
            "U13F/route_1.xlsx",
            "U13F/route_1.pdf",
            "U13F/route_2.xlsx",
            "U13F/route_2.pdf",
            "U13F/metadata.json",
        }
        self.assertTrue(expected.issubset(names))

        meta = json.loads(zf.read("U13F/metadata.json").decode("utf-8"))
        self.assertEqual(meta["boxId"], 7)
        self.assertEqual(meta["competitionId"], 3)
        self.assertEqual(meta["categorie"], "U13F")
        self.assertEqual(meta["routesCount"], 2)
        self.assertTrue(meta["timeCriterionEnabled"])
        self.assertIn("exportedAt", meta)

    def test_build_official_results_zip_formats_plus_scores_in_overall_and_route(self):
        import pandas as pd
        from escalada.api.official_export import build_official_results_zip

        snapshot = {
            "boxId": 4,
            "competitionId": 99,
            "categorie": "U15M",
            "routesCount": 1,
            "routeIndex": 1,
            "holdsCount": 20,
            "holdsCounts": [20],
            "timeCriterionEnabled": False,
            "scores": {
                "Ana": [9.1],
                "Bob": [9.0],
                "Cara": [20.0],
                "Dan": [12.5],
            },
            "times": {},
        }

        zip_bytes = build_official_results_zip(snapshot)
        zf = zipfile.ZipFile(BytesIO(zip_bytes))

        overall_df = pd.read_excel(BytesIO(zf.read("U15M/overall.xlsx")))
        route_df = pd.read_excel(BytesIO(zf.read("U15M/route_1.xlsx")))

        overall_by_name = overall_df.set_index("Nume")
        route_by_name = route_df.set_index("Name")

        self.assertEqual(str(overall_by_name.loc["Ana", "Score R1"]), "9+")
        self.assertEqual(str(overall_by_name.loc["Bob", "Score R1"]), "9")
        self.assertEqual(str(overall_by_name.loc["Cara", "Score R1"]), "TOP")
        self.assertEqual(str(overall_by_name.loc["Dan", "Score R1"]), "12.5")

        self.assertEqual(str(route_by_name.loc["Ana", "Score"]), "9+")
        self.assertEqual(str(route_by_name.loc["Bob", "Score"]), "9")
        self.assertEqual(str(route_by_name.loc["Cara", "Score"]), "TOP")
        self.assertEqual(str(route_by_name.loc["Dan", "Score"]), "12.5")

    def test_build_official_results_zip_requires_scores(self):
        from escalada.api.official_export import build_official_results_zip

        snapshot = {"boxId": 1, "competitionId": 1, "categorie": "U13F", "routesCount": 1}
        with self.assertRaises(ValueError):
            build_official_results_zip(snapshot)

    def test_build_official_results_zip_applies_tiebreak_state_from_snapshot(self):
        import pandas as pd
        from escalada.api.backup import _snapshot_from_state
        from escalada.api.official_export import build_official_results_zip
        from escalada.api.ranking_time_tiebreak import resolve_rankings_with_time_tiebreak

        scores = {"Ana": [10.0], "Bob": [10.0], "Cris": [9.0]}
        times = {"Ana": [120], "Bob": [140], "Cris": [150]}

        initial = resolve_rankings_with_time_tiebreak(
            scores=scores,
            times=times,
            route_count=1,
            active_route_index=1,
            box_id=9,
            time_criterion_enabled=True,
            active_holds_count=10,
        )
        prev_fp = initial["eligible_groups"][0]["fingerprint"]
        after_prev_no = resolve_rankings_with_time_tiebreak(
            scores=scores,
            times=times,
            route_count=1,
            active_route_index=1,
            box_id=9,
            time_criterion_enabled=True,
            active_holds_count=10,
            prev_resolved_decisions={prev_fp: "no"},
        )
        time_fp = next(
            group["fingerprint"]
            for group in after_prev_no["eligible_groups"]
            if group.get("stage") == "time"
        )

        state = {
            "initiated": True,
            "holdsCount": 10,
            "holdsCounts": [10],
            "routeIndex": 1,
            "routesCount": 1,
            "currentClimber": "",
            "started": False,
            "timerState": "idle",
            "holdCount": 0.0,
            "competitors": [
                {"nume": "Ana", "club": "Club A"},
                {"nume": "Bob", "club": "Club B"},
                {"nume": "Cris", "club": "Club C"},
            ],
            "categorie": "U13F",
            "remaining": None,
            "timeCriterionEnabled": True,
            "scores": scores,
            "times": times,
            "prevRoundsTiebreakDecisions": {prev_fp: "no"},
            "prevRoundsTiebreakResolvedFingerprint": prev_fp,
            "prevRoundsTiebreakResolvedDecision": "no",
            "timeTiebreakDecisions": {time_fp: "yes"},
            "timeTiebreakResolvedFingerprint": time_fp,
            "timeTiebreakResolvedDecision": "yes",
        }

        snapshot = _snapshot_from_state(9, state)
        zip_bytes = build_official_results_zip(snapshot)
        zf = zipfile.ZipFile(BytesIO(zip_bytes))
        overall_df = pd.read_excel(BytesIO(zf.read("U13F/overall.xlsx")))

        by_name = overall_df.set_index("Nume")
        self.assertEqual(int(by_name.loc["Ana", "Rank"]), 1)
        self.assertEqual(int(by_name.loc["Bob", "Rank"]), 2)
        self.assertIn("TB", overall_df.columns)
        self.assertEqual(by_name.loc["Ana", "TB"], "TB Time")
        self.assertEqual(by_name.loc["Bob", "TB"], "TB Time")

    def test_build_official_results_zip_requires_routes_count(self):
        from escalada.api.official_export import build_official_results_zip

        snapshot = {
            "boxId": 1,
            "competitionId": 1,
            "categorie": "U13F",
            "scores": {"Ana": []},
            "times": {"Ana": []},
        }
        with self.assertRaises(ValueError):
            build_official_results_zip(snapshot)


if __name__ == "__main__":
    unittest.main()
