"""Focused preservation and source-frame regressions for the new native midterm table."""

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts import cps_1998_state_points as primary
from scripts import verify_cps_1998_state_points as independent


INPUTS = Path(os.environ.get("CPS_1998_STATE_INPUTS",
    Path(__file__).resolve().parents[1] / "data/participation-cps-1998-state-points/20261111-01"))


class Cps1998StatePointsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = primary.load_inputs(INPUTS)
        cls.result = primary.build(*cls.inputs)

    def record(self, state, group):
        return next(row for row in self.result["records"]
            if row["reference_state_code"] == state and row["native_group"] == group)

    def test_suppression_is_metric_specific_and_dot_counts_are_not_zero(self):
        row = self.record("VA", "Hispanic")
        self.assertEqual(row["measures"]["registered"]["selected_percentage"], "17.2")
        self.assertIsNone(row["measures"]["voted"]["selected_percentage"])
        self.assertEqual(row["raw_values"]["voted_thousands"], ".")
        self.assertEqual(row["count_symbols"]["voted_thousands"], ".")
        self.assertIsNone(self.record("WV", "N-H White")["measures"]["citizen_adults"]["selected_percentage"])
        self.assertEqual(self.record("WV", "N-H White")["measures"]["voted"]["selected_percentage"], "35.9")

    def test_literal_percentage_and_standard_error_defects_are_not_repaired(self):
        row = self.record("NJ", "Male")
        self.assertEqual(row["raw_values"]["citizen_adults_pct"], "900.")
        self.assertIsNone(row["measures"]["citizen_adults"]["selected_percentage"])
        self.assertEqual(row["measures"]["voted"]["selected_percentage"], "36.1")
        row = self.record("NM", "Total")
        self.assertEqual(row["measures"]["citizen_adults"]["selected_percentage"], "93.5")
        self.assertEqual(row["measures"]["citizen_adults"]["raw_standard_error"], "0.8.")
        self.assertIsNone(row["measures"]["citizen_adults"]["selected_source_standard_error_pp"])

    def test_real_count_and_standard_error_zeros_survive(self):
        row = self.record("WY", "N-H Black")
        self.assertEqual(row["raw_values"]["voted_thousands"], "0")
        self.assertNotIn("voted_thousands", row["count_symbols"])
        row = self.record("AZ", "N-H Black")
        self.assertEqual(row["measures"]["citizen_adults"]["selected_source_standard_error_pp"], "0")

    def test_non_hispanic_api_never_becomes_all_api(self):
        rows = [row for row in self.result["group_snapshot_comparisons"] if row["native_1998_group"] == "N-H API"]
        self.assertEqual(len(rows), 104)
        self.assertTrue(all(row["difference_pp"] is None and row["native_2002_group"] is None for row in rows))

    def test_native_all_adult_rates_do_not_become_citizen_or_individual_turnout(self):
        row = self.record("US", "Total")
        self.assertEqual(row["measures"]["voted"]["selected_percentage"], "41.9")
        self.assertIsNone(row["citizen_turnout"])
        self.assertEqual({row["population_frame"] for row in self.result["overall_snapshot_comparisons"]}, {"vap"})
        policy = copy.deepcopy(self.inputs[-1])
        policy["derived_citizen_turnout"] = True
        with self.assertRaises(ValueError):
            primary.build(*self.inputs[:-1], policy)

    def test_json_roundtrip_keeps_every_complete_csv_byte(self):
        original = primary.result_files(self.result)
        after = primary.result_files(json.loads(primary.encoded(self.result)))
        self.assertEqual(original, after)

    def test_independent_verifier_rejects_repaired_suppression_and_api_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, body in primary.result_files(self.result).items():
                (root / name).write_bytes(body)
            self.assertEqual(independent.verify(INPUTS, root)["native_metric_cells"], 4680)
            changed = copy.deepcopy(self.result)
            row = next(row for row in changed["records"] if row["geography"] == "NEW JERSEY"
                and row["native_group"] == "Male")
            row["measures"]["citizen_adults"]["selected_percentage"] = "90.0"
            for name, body in primary.result_files(changed).items():
                (root / name).write_bytes(body)
            with self.assertRaises(ValueError):
                independent.verify(INPUTS, root)
            changed = copy.deepcopy(self.result)
            row = next(row for row in changed["group_snapshot_comparisons"]
                if row["native_1998_group"] == "N-H API")
            row["native_2002_group"], row["difference_pp"] = ".Asian and Pacific Islander", "0"
            for name, body in primary.result_files(changed).items():
                (root / name).write_bytes(body)
            with self.assertRaises(ValueError):
                independent.verify(INPUTS, root)


if __name__ == "__main__":
    unittest.main()
