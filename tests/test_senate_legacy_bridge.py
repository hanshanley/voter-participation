import copy
import gzip
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.congressional_candidate_identity import DATA_PATHS as FEC_PATHS, Evidence
from scripts.participation_intake.contract import encoded, pin
from scripts.results_congress import normalize
from scripts import senate_legacy_bridge as bridge
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


class SenateFecIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads((ROOT / "tests/fixtures/senate-legacy-new-mexico.json").read_bytes())
        cls.snapshot = {"congress": fixture["congress"]}
        cls.review = load_review(REVIEW_ROOT)
        cls.seed = {"senate_legacy_review": cls.review,
                    "congressional_analytical_review": {"historical_senate": fixture["historical_senate"]}}
        cls.fec = json.loads(gzip.decompress((REVIEW_ROOT / FEC_PATHS[1]).read_bytes()))
        cls.evidence = Evidence(cls.fec)
        cls.key = "NM-senate-87288"
        cls.race = "npr:senate:NM:2:regular:general:not_ranked"
        cls.frame = cls.review["models"][cls.key]["identity"]
        cls.old = cls.review["models"][cls.key]["legacy_native_control"]["full_candidate_rows"][0]
        cls.current = next(row for row in cls.snapshot["congress"]["races"][cls.race]["data"]["candidates"]
                           if row["party_group"] == "D")

    def test_full_fec_identity_resolves_diacritic_and_middle_name_without_ballot_inference(self):
        proof = bridge.fec_identity(self.old, self.current, self.frame, self.evidence)
        self.assertEqual(proof["fec_candidate"]["candidate_id"], "S0NM00058")
        self.assertEqual(proof["legacy_literal_name"], "Ben Ray Luján")
        self.assertEqual(proof["provider_literal_name"], "Ben Lujan")
        self.assertFalse(proof["ballot_inventory_counts_seat_or_stage_qualified_by_FEC"])
        self.assertEqual(self.old["name"], "Ben Ray Luján")

    def test_ambiguous_wrong_office_state_party_cycle_and_district_do_not_resolve(self):
        for field, value in (("office", "H"), ("office_state", "AZ"), ("literal_party", "REP"),
                             ("election_year", "2028"), ("district", "01"), ("ambiguous", None)):
            with self.subTest(field=field):
                source = copy.deepcopy(self.fec)
                candidate = next(row for row in source["candidates"]
                                 if row["candidate_id"] == "S0NM00058")
                if field == "ambiguous":
                    source["candidates"].append({**candidate, "candidate_id": "S9NM99999"})
                else:
                    candidate[field] = value
                self.assertIsNone(bridge.fec_identity(
                    self.old, self.current, self.frame, Evidence(source)))

    def test_initials_nicknames_partial_surnames_and_unsupported_stages_stay_held(self):
        for name in ("B. Lujan", "Ben Luj", "Benny Lujan", "Ben Ray"):
            with self.subTest(name=name):
                self.assertIsNone(bridge.fec_identity(
                    self.old, {**self.current, "name": name}, self.frame, self.evidence))
        for field, value in (("stage", "runoff"), ("election_kind", "special"),
                             ("ranked_choice", True), ("election_date", "2026-06-02")):
            with self.subTest(field=field):
                self.assertIsNone(bridge.fec_identity(
                    self.old, self.current, {**self.frame, field: value}, self.evidence))

    def test_all_other_decisions_and_original_other_mass_are_preserved(self):
        previous = json.loads((REVIEW_ROOT / bridge.PREVIOUS_REVIEW_PATH).read_bytes())
        current = json.loads((REVIEW_ROOT / bridge.REVIEW_PATH).read_bytes())
        for key in previous["models"]:
            if key != self.key:
                self.assertEqual(current["models"][key], previous["models"][key])
        result = build(copy.deepcopy(self.snapshot), copy.deepcopy(self.seed))
        self.assertEqual(result["result"]["summary"]["fresh_sensitivity_fits"], 18)
        self.assertEqual(sum(bool(row["holds"]) for row in result["result"]["rows"]), 24)
        model = result["last_good"][self.key]["model"]
        self.assertEqual(model["reported_comparison"]["previous"]["O"], 24271)
        self.assertNotIn("O", model["reported_comparison"]["current"])
        self.assertEqual(model["observed_other_vote_endpoints"], [True, False])

    def test_fec_rule_cannot_erase_added_other_even_when_zero(self):
        previous = json.loads((REVIEW_ROOT / bridge.PREVIOUS_REVIEW_PATH).read_bytes())
        controls = {key: row["legacy_native_control"] for key, row in self.review["models"].items()}
        for votes in (0, 3):
            with self.subTest(votes=votes):
                context = copy.deepcopy(self.review["candidate_identity_successor"]["context"])
                raw = context["races"][self.race]["data"]["native_facts"]
                raw["candidates"].append({"id": "other-added", "first": "", "last": "Other",
                                          "party": "Lib", "votes": votes})
                context["races"][self.race]["data"] = normalize(raw, "senate")
                result = bridge.fec_successor(
                    previous, controls, context, self.evidence,
                    self.review["candidate_identity_successor"]["files"])
                self.assertEqual(result["models"][self.key], previous["models"][self.key])

    def test_both_model_revisions_failure_and_unchanged_repeat(self):
        snapshot, seed = copy.deepcopy(self.snapshot), copy.deepcopy(self.seed)
        original = build(snapshot, seed)
        seed["senate_legacy_last_good"] = original["last_good"]
        initial = original["last_good"][self.key]["model"]["point"]["reported_change_pp"]
        for delta in (7, -13):
            raw = snapshot["congress"]["races"][self.race]["data"]["native_facts"]
            raw["updated"] += 1000
            next(row for row in raw["candidates"] if row["party"] == "Dem")["votes"] += delta
            entry = snapshot["congress"]["races"][self.race]
            entry["data"] = normalize(raw, "senate")
            entry["source"].update(pin(encoded({"results": [raw]})))
            revised = build(snapshot, seed)
            point = revised["last_good"][self.key]["model"]["point"]["reported_change_pp"]
            self.assertTrue(point > initial if delta > 0 else point < initial)
            self.assertEqual(revised["last_good"][KEY]["model"], original["last_good"][KEY]["model"])
            seed["senate_legacy_last_good"] = revised["last_good"]
        repeated = build(snapshot, seed)
        self.assertEqual(repeated["last_good"], revised["last_good"])
        entry["status"] = "retained_after_failure"
        held = build(snapshot, seed)
        self.assertEqual(held["last_good"], revised["last_good"])
        row = next(row for row in held["result"]["rows"] if row["id"] == self.key)
        self.assertEqual(row["model_source_clock"], entry["data"]["source_updated_at"])
        self.assertEqual(row["status"], "held_retain_last_good_partial_scenario")

    def test_previous_alabama_checkpoint_migrates_but_new_mexico_cannot_claim_old_review(self):
        snapshot, seed = copy.deepcopy(self.snapshot), copy.deepcopy(self.seed)
        original = build(snapshot, seed)
        saved = copy.deepcopy(original["last_good"][KEY])
        saved["review_version"] = bridge.PREVIOUS_VERSION
        seed["senate_legacy_last_good"] = {KEY: saved}
        migrated = build(snapshot, seed)
        self.assertEqual(migrated["last_good"][KEY]["model"], saved["model"])
        self.assertEqual(migrated["last_good"][KEY]["review_version"], bridge.VERSION)
        seed["senate_legacy_last_good"][self.key] = copy.deepcopy(original["last_good"][self.key])
        seed["senate_legacy_last_good"][self.key]["review_version"] = bridge.PREVIOUS_VERSION
        with self.assertRaisesRegex(ValueError, "last-good"):
            build(snapshot, seed)

    def test_changed_review_or_fec_evidence_refuses_before_fitting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in bridge.DATA_PATHS:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REVIEW_ROOT / path, target)
            path = root / bridge.REVIEW_PATH
            original = path.read_bytes()
            review = json.loads(original)
            review["models"][self.key]["checkpoint"]["data"]["candidates"][0]["votes"] += 1
            path.write_bytes(encoded(review))
            with self.assertRaisesRegex(ValueError, "reproduce"):
                load_review(root)
            path.write_bytes(original)
            evidence = root / FEC_PATHS[1]
            evidence.write_bytes(evidence.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "FEC identity evidence"):
                load_review(root)


if __name__ == "__main__":
    unittest.main()
