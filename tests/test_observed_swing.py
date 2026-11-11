import copy
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from observed_swing import (build, count, house_reference, margin, reconcile,
                            senate_references, TERMS)

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "data/return-attribution/20261110-02/inputs"


class ReportedSwingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build(INPUTS)
        cls.original = json.loads((INPUTS / "original-viewer.json").read_bytes())

    def test_texas_uses_actual_prior_house_not_recalled_president(self):
        row = next(r for r in self.data["rows"] if r["id"] == "TX-house")
        comparison = row["reported_comparison"]
        self.assertEqual(comparison["previous"], dict(D=4159293, R=6168664, O=129145))
        self.assertEqual(comparison["current"], dict(D=5147146, R=4591278, O=44093))
        self.assertAlmostEqual(comparison["reported_change_pp"], 25.16363563924734)
        self.assertAlmostEqual(row["components_pp"]["switching"], 3.5983884082676587)
        self.assertAlmostEqual(comparison["other_and_unallocated_pp"], 22.41207106277195)
        self.assertAlmostEqual(comparison["baseline_alignment_pp"], 14.62083777048145)
        self.assertEqual(comparison["county_count"], 254)
        self.assertGreater(comparison["competition_or_other_screened_counties"], 0)

    def test_all_original_models_and_ranges_are_unchanged(self):
        self.assertEqual(len(self.data["rows"]), 113)
        for before, after in zip(self.original["rows"], self.data["rows"]):
            without_comparison = {k: v for k, v in after.items() if k != "reported_comparison"}
            self.assertEqual(before, without_comparison)

    def test_each_available_comparison_has_both_reconciliations(self):
        for row in self.data["rows"]:
            comparison = row["reported_comparison"]
            if comparison["status"] == "unavailable":
                self.assertIsNone(comparison["reported_change_pp"])
                self.assertIsNone(comparison["other_and_unallocated_pp"])
                continue
            self.assertAlmostEqual(sum(row["components_pp"].values())
                + comparison["baseline_alignment_pp"], comparison["reported_change_pp"])
            self.assertAlmostEqual(row["components_pp"]["switching"]
                + row["components_pp"]["modeled_nonparticipation"]
                + comparison["other_and_unallocated_pp"], comparison["reported_change_pp"])

    def test_texas_senate_uses_senate_2020_and_governor_uses_2022_frame(self):
        senate = next(r for r in self.data["rows"] if r["state_code"] == "TX" and r["office"] == "senate")
        self.assertEqual(senate["reported_comparison"]["previous"]["R"], 5962983)
        self.assertEqual(senate["reported_comparison"]["previous"]["D"], 4888764)
        self.assertEqual(senate["reported_comparison"]["baseline_year"], 2020)
        governor = next(r for r in self.data["rows"] if r["state_code"] == "TX" and r["office"] == "governor")
        self.assertAlmostEqual(governor["reported_comparison"]["reported_change_pp"], 18.27655273823629)
        self.assertEqual(governor["reported_comparison"]["baseline_year"], 2022)

    def test_partial_frames_and_later_specials_are_not_silently_substituted(self):
        for state, office in (("AK", "house"), ("NE", "senate"), ("OK", "senate")):
            row = next(r for r in self.data["rows"] if r["state_code"] == state and r["office"] == office)
            self.assertEqual(row["reported_comparison"]["status"], "unavailable")

    def test_georgia_uses_final_full_term_runoff_only(self):
        row = next(r for r in self.data["rows"] if r["state_code"] == "GA" and r["office"] == "senate")
        comparison = row["reported_comparison"]
        self.assertEqual(comparison["previous"], dict(D=2269923, R=2214979, O=0))
        self.assertEqual(comparison["baseline_year"], 2021)
        self.assertEqual(comparison["baseline_stage"], "general_runoff")
        self.assertEqual({r["seat"] for r in comparison["native_candidate_facts"]}, {"S-FULL TERM"})

    def test_unknown_zero_and_invalid_counts_remain_distinct(self):
        self.assertEqual(count("0"), 0)
        self.assertIsNone(count(""))
        self.assertIsNone(margin(dict(D=None, R=7)))
        self.assertEqual(margin(dict(D=0, R=7)), Decimal(-100))
        for value in (True, -1, "NaN", "1.5"):
            with self.assertRaises(ValueError):
                count(value)

    def test_incomplete_counties_and_control_conflicts_are_held(self):
        native = dict(county_fips="48001", passes_known_descriptive_screens="True")
        for year in (2024, 2026):
            native.update({f"{year}_d_literal_votes": "10", f"{year}_r_literal_votes": "20",
                           f"{year}_other_literal_votes": "0"})
        control = dict(current=dict(D=10, R=20, O=0), missing_candidate_control_indices=[])
        self.assertEqual(house_reference(control, [native], {"48001", "48003"})["status"], "unavailable")
        missing = dict(native, **{"2024_d_literal_votes": ""})
        self.assertEqual(house_reference(control, [missing], {"48001"})["status"], "unavailable")
        bad = dict(control, current=dict(D=11, R=20, O=0))
        self.assertEqual(house_reference(bad, [native], {"48001"})["status"], "unavailable")

    def test_return_constraint_mismatch_is_rejected(self):
        row = copy.deepcopy(next(r for r in self.data["rows"] if r["id"] == "TX-house"))
        with self.assertRaisesRegex(ValueError, "return constraint"):
            reconcile(row, dict(current=dict(D=9, R=1), year=2026, source_scope="test"),
                      row["reported_comparison"])


if __name__ == "__main__":
    unittest.main()
