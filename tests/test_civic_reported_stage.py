import copy
from fractions import Fraction
import json
from pathlib import Path
import unittest
import zipfile

from scripts.extract_civic_reported_stage import LABELS, STAGES, aggregate, close_age_masks, supported
from scripts.civic_reported_stage import build_profiles


class CivicReportedStageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        path = root / "data/civic-reported-stage/20261109-01/sufficient-inputs.zip"
        if not path.exists():
            path = root / "inputs/complete-reported-stage-sufficient-inputs.zip"
        with zipfile.ZipFile(path) as archive:
            cls.snapshot = json.loads(archive.read("selected-stage-inputs.json"))
            cls.parents = json.loads(archive.read("public-civic-parents.json"))

    def native(self, code, prior="D", n=1):
        return dict(scope="SC", dimension="overall", group="all", prior_choice=prior,
                    LVB=code, LVB_label=LABELS[code], n=str(n), weight=str(n))

    def parent(self, n=200, voter=120):
        return dict(disposition="selected_broad_source_model", n=n, weight=str(n),
                    native_model_voter_cases=voter, native_model_nonvoter_cases=n-voter)

    def stage(self, already, other):
        return dict(already_voted=dict(n=already, weight=Fraction(already)),
                    other_or_unresolved=dict(n=other, weight=Fraction(other)))

    def test_all_prior_responses_aggregated_no_party_or_prior_voter_filter(self):
        source = [self.native("5", prior, 40) for prior in ("D", "R", "O", "N", "U")]
        self.assertEqual(aggregate(source)["SC", "overall", "all"]["already_voted"]["n"], 200)

    def test_future_intention_and_unknown_are_other_not_already_or_nonvoters(self):
        source = [self.native(code) for code in ("1", "2", "3", "4", "99")]
        value = aggregate(source)["SC", "overall", "all"]
        self.assertEqual(value["already_voted"]["n"], 0)
        self.assertEqual(value["other_or_unresolved"]["n"], 5)
        self.assertEqual(set(value), set(STAGES))

    def test_native_five_is_the_only_already_category(self):
        value = aggregate([self.native("5"), self.native("1", n=2)])["SC", "overall", "all"]
        self.assertEqual(value["already_voted"]["n"], 1)
        self.assertEqual(value["other_or_unresolved"]["n"], 2)

    def test_duplicate_private_reduction_cell_is_rejected(self):
        row = self.native("5")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            aggregate([row, row])

    def test_changed_native_label_is_not_imputed(self):
        row = self.native("5")
        row["LVB_label"] = "Intends voting"
        with self.assertRaisesRegex(ValueError, "never impute"):
            aggregate([row])

    def test_incomplete_group_is_not_renormalized(self):
        with self.assertRaisesRegex(ValueError, "complete LVB group|Complete LVB group"):
            supported(self.parent(), self.stage(60, 130))

    def test_small_positive_stage_is_held_but_observed_zero_is_not_missing(self):
        self.assertFalse(supported(self.parent(), self.stage(20, 180)))
        self.assertTrue(supported(self.parent(), self.stage(0, 200)))

    def test_existing_parent_hold_is_never_recovered(self):
        parent = self.parent()
        parent["disposition"] = "held_source_support_or_complementary_disclosure"
        self.assertFalse(supported(parent, self.stage(60, 140)))

    def test_legacy_marginal_small_difference_is_held(self):
        self.assertFalse(supported(self.parent(voter=150), self.stage(140, 60)))
        self.assertTrue(supported(self.parent(voter=150), self.stage(150, 50)))

    def test_single_positive_age_complement_requires_second_whole_table_hold(self):
        keys = [("SC", "AGE6", group) for group in ("18_29", "30_49", "50_64", "65_plus")]
        overall = "SC", "overall", "all"
        raw = {key: self.stage(50, 50) for key in keys}
        raw[overall] = self.stage(200, 200)
        parents = {key: self.parent(n=100, voter=60) for key in keys}
        parents[overall] = self.parent(n=400, voter=240)
        selected, held = close_age_masks({overall, *keys[:3]}, raw, parents)
        self.assertEqual(len(held), 1)
        self.assertEqual(len([key for key in keys if key in selected]), 2)

    def test_small_unreleased_age_bundle_is_not_exposed(self):
        keys = [("SC", "AGE6", group) for group in ("18_29", "30_49", "50_64")]
        overall = "SC", "overall", "all"
        raw = {keys[0]: self.stage(50, 50), keys[1]: self.stage(1, 99), keys[2]: self.stage(1, 99)}
        raw[overall] = self.stage(52, 248)
        parents = {key: self.parent(n=100, voter=60) for key in keys}
        parents[overall] = self.parent(n=300, voter=180)
        selected, _ = close_age_masks({overall, keys[0]}, raw, parents)
        self.assertNotIn(keys[0], selected)

    def test_held_stage_statistics_remain_null(self):
        snapshot = copy.deepcopy(self.snapshot)
        held = next(row for row in snapshot["profiles"] if row["disposition"].startswith("held"))
        held["stages"]["already_voted"]["n"] = 1
        with self.assertRaisesRegex(ValueError, "must remain absent"):
            build_profiles(snapshot, self.parents)

    def test_dc_is_absence_not_zero_already_voting(self):
        profiles, cells, _ = build_profiles(self.snapshot, self.parents)
        for row in profiles:
            if row["state_code"] == "DC":
                self.assertIsNone(row["already_voted_response_pct"])
                self.assertIsNone(row["source_parent_n"])
        self.assertTrue(all(row["source_stage_n"] is None for row in cells if row["state_code"] == "DC"))

    def test_unknown_field_period_cannot_be_promoted_to_common_cutoff(self):
        snapshot = dict(self.snapshot, field_period="2026-11-02")
        with self.assertRaisesRegex(ValueError, "unknown timing"):
            build_profiles(snapshot, self.parents)

    def test_full_source_denominators_and_interpretation_are_preserved(self):
        profiles, cells, _ = build_profiles(self.snapshot, self.parents)
        selected = [row for row in profiles if row["disposition"] == "selected_coarse_reported_stage"]
        self.assertEqual(len(profiles), 306)
        self.assertEqual(len(cells), 612)
        self.assertEqual(len(selected), 124)
        for row in selected:
            self.assertLess(abs(Fraction(row["already_voted_response_pct"]) +
                                Fraction(row["other_or_unresolved_response_pct"]) - 100), Fraction(1, 10**60))
            self.assertFalse(row["already_response_administratively_verified"])
            self.assertFalse(row["other_is_nonvoter_class"])
            self.assertFalse(row["native_LVB_model_joint_inferred"])

    def test_pooled_source_is_never_published_as_a_national_profile(self):
        row = self.native("5")
        row["scope"] = "POOLED_SOURCE"
        self.assertEqual(aggregate([row]), {})


if __name__ == "__main__":
    unittest.main()
