"""Regressions for native frames, nonresponse, wrapped geography and rounded zeros."""

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts import cps_1996_state_points as primary
from scripts import verify_cps_1996_state_points as independent


INPUTS = Path(os.environ.get("CPS_1996_STATE_INPUTS",
    Path(__file__).resolve().parents[1] / "data/participation-cps-1996-state-points/20261112-01"))


class Cps1996StatePointsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = primary.load_inputs(INPUTS)
        cls.result = primary.build(*cls.inputs)

    def record(self, table, state, group, age="18_plus"):
        return next(row for row in self.result["records"] if
            (row["table"], row["reference_state_code"], row["native_group"], row["age"]) == (table, state, group, age))

    def test_adult_and_citizen_rates_are_not_merged(self):
        adult, citizen = self.record("A", "US", "ALL RACES"), self.record("C", "US", "ALL")
        self.assertEqual(adult["measures"]["voted"]["selected_percentage"], "54.2")
        self.assertEqual(citizen["measures"]["voted"]["selected_percentage"], "58.4")
        self.assertNotEqual(adult["population_frame"], citizen["population_frame"])
        self.assertIsNone(citizen["measures"]["voted"]["sample_n"])

    def test_suppression_and_rounded_zero_bases_are_not_recovered(self):
        row = self.record("A", "AL", "HISPANIC ORIGIN", "45_64")
        self.assertEqual(row["raw_values"]["voted_pct"], "(B)")
        self.assertIsNone(row["measures"]["voted"]["selected_percentage"])
        row = self.record("A", "ND", "BLACK", "18_24")
        self.assertEqual(row["raw_values"]["voted_pct"], "100.0")
        self.assertEqual(row["measures"]["voted"]["disposition"], "withheld_rounded_zero_base")
        self.assertIsNone(row["measures"]["voted"]["selected_percentage"])

    def test_zero_rounded_count_does_not_override_valid_printed_percentage(self):
        row = self.record("A", "SD", "HISPANIC ORIGIN", "25_44")
        self.assertEqual(row["raw_values"]["voted_thousands"], "0")
        self.assertEqual(row["measures"]["voted"]["selected_percentage"], "21.9")

    def test_wrapped_district_of_columbia_and_missing_citizen_totals(self):
        self.assertEqual(self.record("C", "DC", "Male")["geography"], "DISTRICT OF COLUMBIA")
        self.assertEqual(self.record("C", "DC", "Female")["native_group"], "Female")
        missing = [row for row in self.result["metric_decisions"]
                   if row["reference_state_code"] == "DC" and row["table"] == "C" and row["native_group"] == "ALL"]
        self.assertEqual(len(missing), 6)
        self.assertTrue(all(row["selected_percentage"] is None for row in missing))

    def test_nonresponse_and_one_thousand_rounding_residual_stay_distinct(self):
        row = next(row for row in self.result["nonresponse_scenarios"]
                   if row["reference_state_code"] == "US" and row["measure"] == "voted")
        self.assertEqual(row["reported_no_thousands"], "61568")
        self.assertEqual(row["reported_unknown_thousands"], "13350")
        self.assertEqual(row["rounding_residual_thousands"], "1")
        self.assertFalse(row["unknown_assigned_to_observed_nonvoters"])
        self.assertFalse(row["residual_assigned"])
        self.assertIsNone(row["confidence_interval"])

    def test_duplicate_totals_and_cross_election_type_are_not_independent_histories(self):
        self.assertEqual(len(self.result["duplicate_total_checks"]), 2600)
        self.assertTrue(all(row["literal_equal"] and not row["summed"] for row in self.result["duplicate_total_checks"]))
        self.assertTrue(all(not row["same_election_type"] for row in self.result["group_snapshot_comparisons"]))
        self.assertTrue(all(row["election_type"] == "presidential" for row in self.result["overall_snapshot_comparisons"]))
        changed = copy.deepcopy(self.inputs[-1])
        changed["unknown_voting_is_nonvote"] = True
        with self.assertRaises(ValueError):
            primary.build(*self.inputs[:-1], changed)

    def test_json_roundtrip_preserves_every_query_byte(self):
        self.assertEqual(primary.result_files(self.result),
                         primary.result_files(json.loads(primary.encoded(self.result))))

    def test_independent_verifier_rejects_repaired_percentage_and_nonresponse(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name, body in primary.result_files(self.result).items():
                (output / name).write_bytes(body)
            self.assertEqual(independent.verify(INPUTS, output)["native_metric_cells"], 19539)
            for kind in ("percentage", "nonresponse"):
                altered = copy.deepcopy(self.result)
                if kind == "percentage":
                    row = next(row for row in altered["records"] if row["source_key"] == "tab4a.txt:91")
                    row["measures"]["voted"]["selected_percentage"] = "0.0"
                else:
                    altered["nonresponse_scenarios"][0]["reported_unknown_thousands"] = "0"
                for name, body in primary.result_files(altered).items():
                    (output / name).write_bytes(body)
                with self.assertRaises(ValueError):
                    independent.verify(INPUTS, output)


if __name__ == "__main__":
    unittest.main()
