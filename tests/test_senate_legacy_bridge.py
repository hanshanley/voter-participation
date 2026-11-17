import copy
import json
from pathlib import Path
import unittest

from scripts.participation_intake.contract import encoded, pin
from scripts.results_congress import normalize
from scripts.senate_legacy_bridge import build, exports, load_review


ROOT = Path(__file__).resolve().parents[1]
REVIEW_ROOT = ROOT if (ROOT / "data/results-intake/senate-legacy").exists() else (
    ROOT.parent / "inputs/reviewed-senate-sources")
KEY = "AL-senate-86907"
RACE = "npr:senate:AL:2:regular:general:not_ranked"


class SenateLegacyBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads((ROOT / "tests/fixtures/senate-legacy-alabama.json").read_bytes())
        cls.snapshot = {"congress": fixture["congress"]}
        cls.seed = {
            "senate_legacy_review": load_review(REVIEW_ROOT),
            "congressional_analytical_review": {"historical_senate": fixture["historical_senate"]},
        }

    def inputs(self):
        return copy.deepcopy(self.snapshot), copy.deepcopy(self.seed)

    def alabama(self, result):
        return next(row for row in result["result"]["rows"] if row["id"] == KEY)

    def revise(self, snapshot, mutation):
        entry = snapshot["congress"]["races"][RACE]
        raw = copy.deepcopy(entry["data"]["native_facts"])
        raw["updated"] += 1000
        mutation(raw)
        entry["data"] = normalize(raw, "senate")
        entry["source"].update(pin(encoded({"results": [raw]})))

    def test_partial_conditioning_preserves_unknown_other_and_all_holds(self):
        snapshot, seed = self.inputs()
        original = copy.deepcopy((snapshot, seed))
        result = build(snapshot, seed)
        row = self.alabama(result)
        self.assertEqual(row["status"], "fresh_partial_scenario")
        self.assertEqual(result["result"]["summary"]["fresh_sensitivity_fits"], 9)
        self.assertEqual(sum(bool(row["holds"]) for row in result["result"]["rows"]), 25)
        model = row["model"]
        self.assertEqual(model["observed_other_vote_endpoints"], [True, False])
        self.assertNotIn("O", model["reported_comparison"]["current"])
        self.assertEqual(model["reported_comparison"]["previous"]["O"], 3891)
        self.assertFalse(model["senate_respondent_model"])
        for case in model["complete_scenarios"]:
            self.assertAlmostEqual(sum(case["components_pp"].values()), 10.968434568823927, places=8)
            self.assertGreater(case["target_columns"][2], 0)
        self.assertEqual((snapshot, seed), original)

    def test_upward_downward_corrections_and_unchanged_repeat(self):
        snapshot, seed = self.inputs()
        initial = build(snapshot, seed)
        seed["senate_legacy_last_good"] = initial["last_good"]
        unchanged = build(snapshot, seed)
        self.assertEqual(self.alabama(unchanged)["status"], "fresh_unchanged_partial_scenario")
        self.assertEqual(unchanged["last_good"], initial["last_good"])
        previous = self.alabama(initial)["model"]["point"]["reported_change_pp"]
        self.revise(snapshot, lambda raw: raw["candidates"][1].update(
            votes=raw["candidates"][1]["votes"] + 7))
        higher = build(snapshot, seed)
        self.assertGreater(self.alabama(higher)["model"]["point"]["reported_change_pp"], previous)
        seed["senate_legacy_last_good"] = higher["last_good"]
        self.revise(snapshot, lambda raw: raw["candidates"][1].update(
            votes=raw["candidates"][1]["votes"] - 13))
        lower = build(snapshot, seed)
        self.assertLess(self.alabama(lower)["model"]["point"]["reported_change_pp"], previous)

    def test_source_failure_then_recovery_retains_model_and_own_clock(self):
        snapshot, seed = self.inputs()
        good = build(snapshot, seed)
        seed["senate_legacy_last_good"] = good["last_good"]
        snapshot["congress"]["races"][RACE].update(
            status="retained_after_failure", freshness="retained", error="source unavailable")
        held = build(snapshot, seed)
        self.assertEqual(self.alabama(held)["status"], "held_retain_last_good_partial_scenario")
        self.assertEqual(held["last_good"], good["last_good"])
        self.assertEqual(self.alabama(held)["model_source_clock"],
                         self.alabama(good)["model_source_clock"])
        recovered = build(self.snapshot, seed)
        self.assertEqual(self.alabama(recovered)["status"], "fresh_unchanged_partial_scenario")

    def test_missing_source_retains_last_good_without_inventing_clock(self):
        snapshot, seed = self.inputs()
        good = build(snapshot, seed)
        seed["senate_legacy_last_good"] = good["last_good"]
        snapshot.pop("congress")
        held = build(snapshot, seed)
        self.assertEqual(held["last_good"], good["last_good"])
        self.assertTrue(self.alabama(held)["holds"])

    def test_changed_inventory_identity_stage_and_unknown_or_zero_counts_hold(self):
        mutations = (
            lambda raw: raw["candidates"].append(
                {"id": "other-1755", "first": "", "last": "Other", "party": "Lib", "votes": 3}),
            lambda raw: raw["candidates"][0].update(id="another-native-id"),
            lambda raw: raw["candidates"][0].update(last="Different"),
            lambda raw: raw.update(type="General Runoff"),
            lambda raw: raw.update(round=2),
            lambda raw: raw["candidates"][0].update(votes=None),
            lambda raw: raw["candidates"][0].update(votes=0),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                snapshot, seed = self.inputs()
                good = build(snapshot, seed)
                seed["senate_legacy_last_good"] = good["last_good"]
                self.revise(snapshot, mutation)
                held = build(snapshot, seed)
                self.assertEqual(held["last_good"], good["last_good"])
                self.assertEqual(self.alabama(held)["status"], "held_retain_last_good_partial_scenario")

    def test_clock_rollback_and_unversioned_change_hold(self):
        for rollback in (False, True):
            with self.subTest(rollback=rollback):
                snapshot, seed = self.inputs()
                good = build(snapshot, seed)
                seed["senate_legacy_last_good"] = good["last_good"]
                clock = snapshot["congress"]["races"][RACE]["data"]["source_updated_epoch_ms"]
                self.revise(snapshot, lambda raw: raw.update(
                    updated=clock - int(rollback),
                    reporting=raw["reporting"] - 1))
                held = build(snapshot, seed)
                self.assertEqual(held["last_good"], good["last_good"])

    def test_native_mismatch_or_wrong_source_holds(self):
        for field in ("native", "source"):
            with self.subTest(field=field):
                snapshot, seed = self.inputs()
                if field == "native":
                    snapshot["congress"]["races"][RACE]["data"]["candidates"][0]["votes"] += 1
                else:
                    snapshot["congress"]["races"][RACE]["source"]["url"] = "https://example.org/results"
                row = self.alabama(build(snapshot, seed))
                self.assertIsNone(row["model"])
                self.assertTrue(row["holds"])

    def test_changed_historical_evidence_and_corrupt_last_good_refuse(self):
        snapshot, seed = self.inputs()
        seed["congressional_analytical_review"]["historical_senate"]["changed"] = True
        with self.assertRaisesRegex(ValueError, "historical"):
            build(snapshot, seed)
        snapshot, seed = self.inputs()
        seed["senate_legacy_last_good"] = build(snapshot, seed)["last_good"]
        seed["senate_legacy_last_good"][KEY]["model"]["point"]["reported_change_pp"] += 1
        with self.assertRaisesRegex(ValueError, "last-good"):
            build(snapshot, seed)
        saved = seed["senate_legacy_last_good"][KEY]
        saved["model_pin"] = pin(encoded(saved["model"]))
        with self.assertRaisesRegex(ValueError, "Last-good"):
            build(snapshot, seed)

    def test_complete_exports_keep_all_nine_scenarios_and_synthetic_cells(self):
        snapshot, seed = self.inputs()
        result = build(snapshot, seed)["result"]
        files = exports(result)
        import csv
        import io
        cases = list(csv.DictReader(io.StringIO(
            files["senate/legacy-partial-complete-scenarios.csv"].decode())))
        cells = list(csv.DictReader(io.StringIO(
            files["senate/legacy-partial-complete-synthetic-cells.csv"].decode())))
        self.assertEqual(len(cases), 9)
        self.assertEqual(len(cells), 144)
        self.assertEqual({row["source_joint_observation"] for row in cells}, {"False"})


if __name__ == "__main__":
    unittest.main()
