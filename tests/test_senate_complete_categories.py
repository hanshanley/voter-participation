import copy
from datetime import datetime, timedelta
import gzip
import json
import math
from pathlib import Path
import unittest

from scripts import senate_complete_categories as bridge
from scripts.congressional_complete_categories import clock, parse
from scripts.participation_intake.contract import encoded, pin
from scripts.results_congress import normalize


ROOT = Path(__file__).resolve().parents[1]
REVIEW_ROOT = ROOT if (ROOT / bridge.REVIEW_PATH).exists() else (
    ROOT.parent / "inputs/reviewed-senate-sources")
KEY = "RI-senate-87396"
RACE = "npr:senate:RI:2:regular:general:not_ranked"


class CompleteSenateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads((ROOT / "tests/fixtures/ri-official-senate.json").read_bytes())
        cls.fixture = fixture
        cls.review = bridge.load_review(REVIEW_ROOT)
        historical = json.loads((ROOT / "tests/fixtures/senate-legacy-alabama.json").read_bytes())["historical_senate"]
        cls.seed = {"senate_complete_review": cls.review,
                    "congressional_analytical_review": {"historical_senate": historical}}
        cls.snapshot = {"congress": {
            "races": {RACE: fixture["provider_entry"]},
            "official_candidate_evidence": {bridge.SENATE_IDENTITY: fixture["official_entry"]},
        }}
        cls.good = bridge.build(copy.deepcopy(cls.snapshot), copy.deepcopy(cls.seed))

    def inputs(self, saved=True):
        snapshot, seed = copy.deepcopy(self.snapshot), copy.deepcopy(self.seed)
        if saved:
            seed["senate_complete_last_good"] = copy.deepcopy(self.good["last_good"])
        return snapshot, seed

    def row(self, result):
        return next(row for row in result["result"]["rows"] if row["id"] == KEY)

    def revise(self, snapshot, delta):
        entry = snapshot["congress"]["races"][RACE]
        raw = copy.deepcopy(entry["data"]["native_facts"])
        raw["updated"] += 1000
        next(row for row in raw["candidates"] if row["party"] == "Dem")["votes"] += delta
        entry["data"] = normalize(raw, "senate")
        entry["source"].update(pin(encoded({"results": [raw]})))
        official = snapshot["congress"]["official_candidate_evidence"][bridge.SENATE_IDENTITY]
        native = copy.deepcopy(official["data"]["native_facts"])
        stamp = (clock(native["election"]["asOf"]) + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        native["election"]["asOf"] = stamp
        contest = native["ballotItems"][0]
        contest["reportingStatus"]["asOf"] = stamp
        candidate = next(row for row in contest["summaryResults"]["ballotOptions"]
                         if row["party"]["abbreviation"] == "DEM")
        candidate["voteCount"] += delta
        candidate["groupResults"][0]["voteCount"] += delta
        contest["voteTotal"] += delta
        official["data"] = parse(encoded(native), "senate")
        official["source"].update(pin(encoded(native)))

    def test_complete_other_and_original_prior_are_used_in_all_nine_scenarios(self):
        row = self.row(self.good)
        self.assertEqual(row["status"], "fresh_complete_scenario")
        self.assertEqual(self.good["result"]["summary"]["fresh_sensitivity_fits"], 9)
        model = row["model"]
        self.assertEqual(model["observed_other_vote_endpoints"], [True, True])
        self.assertEqual(model["reported_comparison"]["current"]["O"],
                         sum(row["votes"] for row in self.fixture["official_entry"]["data"]["races"][0]["candidates"]
                             if row["party_group"] == "O"))
        self.assertFalse(model["senate_respondent_model"])
        self.assertTrue(row["strict_legacy_model_refreshed"])
        expected = model["reported_comparison"]["current_margin_pp"] - model["reported_comparison"]["previous_margin_pp"]
        for scenario in model["complete_scenarios"]:
            self.assertAlmostEqual(sum(scenario["components_pp"].values()), expected, places=8)
        self.assertEqual(model["reported_comparison"]["previous"],
                         self.review["models"][KEY]["legacy_comparison"]["previous"])

    def test_both_signed_revisions_propagate_and_identical_rerun_is_unchanged(self):
        snapshot, seed = self.inputs()
        original = self.row(self.good)["model"]["point"]["reported_change_pp"]
        for delta in (7, -13):
            self.revise(snapshot, delta)
            revised = bridge.build(snapshot, seed)
            value = self.row(revised)["model"]["point"]["reported_change_pp"]
            self.assertTrue(value > original if delta > 0 else value < original)
            self.assertEqual(set(revised["last_good"]), {KEY})
            seed["senate_complete_last_good"] = revised["last_good"]
        unchanged = bridge.build(snapshot, seed)
        self.assertEqual(unchanged["last_good"], revised["last_good"])
        self.assertEqual(self.row(unchanged)["status"], "fresh_unchanged_complete_scenario")

    def test_newer_official_only_revisions_preserve_all_other_mass_and_both_sources(self):
        snapshot, seed = self.inputs()
        national = copy.deepcopy(snapshot["congress"]["races"][RACE])
        original = self.row(self.good)["model"]["point"]["reported_change_pp"]
        for delta in (7, -13):
            snapshot, seed = self.inputs()
            self.revise(snapshot, delta)
            snapshot["congress"]["races"][RACE] = copy.deepcopy(national)
            official = snapshot["congress"]["official_candidate_evidence"][bridge.SENATE_IDENTITY]
            raw = official["data"]["native_facts"]
            stamp = (max(clock(raw["election"]["asOf"]),
                         datetime.fromisoformat(
                             national["data"]["source_updated_at"]))
                     + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
            raw["election"]["asOf"] = raw["ballotItems"][0]["reportingStatus"]["asOf"] = stamp
            official["data"] = parse(encoded(raw), "senate")
            official["source"].update(pin(encoded(raw)))
            revised = bridge.build(snapshot, seed)
            row = self.row(revised)
            self.assertTrue(row["strict_legacy_model_refreshed"], row["holds"])
            comparison = row["model"]["reported_comparison"]
            audit = comparison["source_reconciliation"]
            self.assertEqual(audit["official_minus_national"], {"D": delta, "R": 0, "O": 0})
            self.assertFalse(audit["counts_agree"])
            self.assertFalse(audit["provider_and_official_counts_added"])
            self.assertEqual(comparison["current"]["O"],
                             self.row(self.good)["model"]["reported_comparison"]["current"]["O"])
            self.assertEqual(row["model_source_clock"], stamp)
            self.assertEqual(row["national_source_clock"], national["data"]["source_updated_at"])
            value = row["model"]["point"]["reported_change_pp"]
            self.assertTrue(value > original if delta > 0 else value < original)
            self.assertEqual(len(row["model"]["complete_scenarios"]), 9)

    def test_newer_official_other_revision_is_not_allocated_to_named_candidates(self):
        snapshot, seed = self.inputs()
        official = snapshot["congress"]["official_candidate_evidence"][bridge.SENATE_IDENTITY]
        raw = official["data"]["native_facts"]
        stamp = (datetime.fromisoformat(
            snapshot["congress"]["races"][RACE]["data"]["source_updated_at"])
            + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        raw["election"]["asOf"] = raw["ballotItems"][0]["reportingStatus"]["asOf"] = stamp
        contest = raw["ballotItems"][0]
        candidate = next(row for row in contest["summaryResults"]["ballotOptions"] if row["isWriteIn"])
        candidate["voteCount"] += 5
        candidate["groupResults"][0]["voteCount"] += 5
        contest["voteTotal"] += 5
        official["data"] = parse(encoded(raw), "senate")
        official["source"].update(pin(encoded(raw)))
        revised = self.row(bridge.build(snapshot, seed))
        self.assertTrue(revised["strict_legacy_model_refreshed"], revised["holds"])
        audit = revised["model"]["reported_comparison"]["source_reconciliation"]
        self.assertEqual(audit["official_minus_national"], {"D": 0, "R": 0, "O": 5})
        self.assertFalse(audit["individual_votes_allocated_from_Other"])

    def test_submicrosecond_official_revision_and_rollback_keep_exact_native_order(self):
        snapshot, seed = self.inputs()
        national = copy.deepcopy(snapshot["congress"]["races"][RACE])
        self.revise(snapshot, 7)
        snapshot["congress"]["races"][RACE] = national
        official = snapshot["congress"]["official_candidate_evidence"][bridge.SENATE_IDENTITY]
        raw = official["data"]["native_facts"]
        second = national["data"]["source_updated_at"][:19]
        national_fraction = national["data"]["source_updated_at"][19:].removesuffix("+00:00")
        later = second + national_fraction.ljust(7, "0") + "1Z"
        raw["election"]["asOf"] = raw["ballotItems"][0]["reportingStatus"]["asOf"] = later
        official["data"] = parse(encoded(raw), "senate")
        official["source"].update(pin(encoded(raw)))
        revised = bridge.build(snapshot, seed)
        self.assertTrue(self.row(revised)["strict_legacy_model_refreshed"], self.row(revised)["holds"])
        seed["senate_complete_last_good"] = revised["last_good"]
        earlier = later[:-2] + "0Z"
        raw["election"]["asOf"] = raw["ballotItems"][0]["reportingStatus"]["asOf"] = earlier
        official["data"] = parse(encoded(raw), "senate")
        official["source"].update(pin(encoded(raw)))
        held = bridge.build(snapshot, seed)
        self.assertEqual(self.row(held)["status"], "held_retain_last_good_complete_scenario")
        self.assertEqual(held["last_good"], revised["last_good"])
        self.assertIn("clock regressed", self.row(held)["holds"][0])

    def test_legacy_last_good_migrates_only_after_exact_original_model_validation(self):
        snapshot, seed = self.inputs()
        saved = seed["senate_complete_last_good"][KEY]
        saved["review_version"] = bridge.LEGACY_VERSION
        decision = self.review["models"][KEY]
        saved["model"] = bridge._estimate(
            saved["native"], saved["source"], decision, self.review["prior"])
        saved["model_pin"] = pin(encoded(saved["model"]))
        outage = copy.deepcopy(snapshot)
        outage["congress"]["official_candidate_evidence"][bridge.SENATE_IDENTITY]["status"] = "retained_after_failure"
        retained = bridge.build(outage, seed)
        self.assertEqual(retained["last_good"][KEY], saved)
        self.assertEqual(self.row(retained)["model"], saved["model"])
        self.assertEqual(self.row(retained)["model_review_version"], bridge.LEGACY_VERSION)
        self.assertEqual(self.row(retained)["status"], "held_retain_last_good_complete_scenario")
        migrated = bridge.build(snapshot, seed)
        self.assertEqual(migrated["last_good"][KEY]["review_version"], bridge.VERSION)
        self.assertEqual(self.row(migrated)["model_review_version"], bridge.VERSION)
        self.assertEqual(self.row(migrated)["model"]["point"], saved["model"]["point"])
        saved["model"]["point"]["components_pp"]["entry"] += 1
        saved["model_pin"] = pin(encoded(saved["model"]))
        with self.assertRaisesRegex(ValueError, "Last-good"):
            bridge.build(snapshot, seed)

    def test_outage_and_unsynchronized_official_counts_retain_own_last_good_clock(self):
        for cause in ("provider", "official", "different_counts"):
            with self.subTest(cause=cause):
                snapshot, seed = self.inputs()
                if cause == "provider":
                    snapshot["congress"]["races"][RACE]["status"] = "retained_after_failure"
                elif cause == "official":
                    snapshot["congress"]["official_candidate_evidence"][bridge.SENATE_IDENTITY]["status"] = "retained_after_failure"
                else:
                    old_official = copy.deepcopy(snapshot["congress"]["official_candidate_evidence"])
                    self.revise(snapshot, 7)
                    snapshot["congress"]["official_candidate_evidence"] = old_official
                held = bridge.build(snapshot, seed)
                self.assertEqual(held["last_good"], self.good["last_good"])
                self.assertEqual(self.row(held)["model_source_clock"], self.row(self.good)["model_source_clock"])
                self.assertEqual(self.row(held)["status"], "held_retain_last_good_complete_scenario")

    def test_rebound_native_other_role_or_candidate_inventory_never_discards_mass(self):
        for mutation in ("other", "candidate", "stage", "clock", "unversioned_official"):
            with self.subTest(mutation=mutation):
                snapshot, seed = self.inputs()
                entry = snapshot["congress"]["races"][RACE]
                raw = copy.deepcopy(entry["data"]["native_facts"])
                if mutation == "other":
                    next(row for row in raw["candidates"] if str(row["id"]).startswith("other"))["votes"] += 1
                    raw["updated"] += 1000
                elif mutation == "candidate":
                    raw["candidates"][0]["id"] = "another-candidate"
                    raw["updated"] += 1000
                elif mutation == "stage":
                    raw["type"] = "General Runoff"
                elif mutation == "clock":
                    raw["updated"] -= 1000
                else:
                    official = snapshot["congress"]["official_candidate_evidence"][bridge.SENATE_IDENTITY]
                    original_clock = official["data"]["source_updated_at"]
                    self.revise(snapshot, 7)
                    native = official["data"]["native_facts"]
                    native["election"]["asOf"] = native["ballotItems"][0]["reportingStatus"]["asOf"] = original_clock
                    official["data"] = parse(encoded(native), "senate")
                    official["source"].update(pin(encoded(native)))
                    raw = entry["data"]["native_facts"]
                entry["data"] = normalize(raw, "senate")
                entry["source"].update(pin(encoded({"results": [raw]})))
                held = bridge.build(snapshot, seed)
                self.assertEqual(held["last_good"], self.good["last_good"])
                self.assertEqual(self.row(held)["status"], "held_retain_last_good_complete_scenario")

    def test_historical_and_last_good_model_corruption_refuse(self):
        snapshot, seed = self.inputs()
        seed["congressional_analytical_review"]["historical_senate"]["changed"] = True
        with self.assertRaisesRegex(ValueError, "historical"):
            bridge.build(snapshot, seed)
        snapshot, seed = self.inputs()
        saved = seed["senate_complete_last_good"][KEY]
        saved["model"]["point"]["reported_change_pp"] += 1
        saved["model_pin"] = pin(encoded(saved["model"]))
        with self.assertRaisesRegex(ValueError, "Last-good"):
            bridge.build(snapshot, seed)

    def test_complete_exports_keep_all_candidates_scenarios_and_synthetic_cells(self):
        import csv
        import io
        files = bridge.exports(self.good["result"])
        scenarios = list(csv.DictReader(io.StringIO(
            files["senate/legacy-complete-complete-scenarios.csv"].decode())))
        cells = list(csv.DictReader(io.StringIO(
            files["senate/legacy-complete-complete-synthetic-cells.csv"].decode())))
        self.assertEqual(len(scenarios), 9)
        self.assertEqual(len(cells), 144)
        self.assertEqual({row["source_joint_observation"] for row in cells}, {"False"})

    def test_original_full_model_reproduces_before_return_reconditioning(self):
        import zipfile
        from scripts.senate_legacy_bridge import DATA_PATHS
        predecessor = next(path for path in DATA_PATHS if path.endswith("complete-predecessor.zip"))
        with zipfile.ZipFile(REVIEW_ROOT / predecessor) as packet:
            original = next(row for row in json.loads(
                packet.read("results/complete-result.json"))["rows"] if row["id"] == KEY)
        decision = self.review["models"][KEY]
        data = copy.deepcopy(self.fixture["provider_entry"]["data"])
        for candidate in data["candidates"]:
            candidate["votes"] = decision["legacy_comparison"]["current"][candidate["party_group"]]
        reproduced = bridge._estimate(
            data, self.fixture["provider_entry"]["source"], decision, self.review["prior"])

        def compare(actual, expected, path):
            self.assertIs(type(actual), type(expected), path)
            if isinstance(actual, dict):
                self.assertEqual(actual.keys(), expected.keys(), path)
                for key in actual:
                    compare(actual[key], expected[key], path + "/" + key)
            elif isinstance(actual, list):
                self.assertEqual(len(actual), len(expected), path)
                for index, (left, right) in enumerate(zip(actual, expected)):
                    compare(left, right, path + "/" + str(index))
            elif isinstance(actual, float):
                # The historical archive predates Python 3.12's improved float summation.
                self.assertTrue(math.isclose(actual, expected, rel_tol=2e-14, abs_tol=2e-12),
                                (path, actual, expected))
            else:
                self.assertEqual(actual, expected, path)

        for field in ("point", "ranges_pp", "complete_scenarios", "observed_other_vote_endpoints"):
            compare(reproduced[field], original[field], field)


if __name__ == "__main__":
    unittest.main()
