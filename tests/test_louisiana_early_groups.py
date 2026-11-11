"""Source-frame and arithmetic-preservation regressions for Louisiana early statistics."""

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts import louisiana_early_groups as primary
from scripts import verify_louisiana_early_groups as independent


INPUTS = Path(os.environ.get("LOUISIANA_EARLY_INPUTS",
    Path(__file__).resolve().parents[1] / "data/participation-louisiana-early-groups/20261111-01"))


class LouisianaEarlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = primary.load_inputs(INPUTS)
        cls.result = primary.build(*cls.inputs)

    def test_sex_residual_is_not_renormalized_or_called_a_source_class(self):
        parent = next(row for row in self.result["source_profiles"] if row["scope_kind"] == "state_parent")
        audit = next(row for row in self.result["margin_accounting"]
            if row["source_key"] == parent["source_key"] and row["dimension"] == "sex")
        self.assertEqual(audit["signed_arithmetic_residual"], 278)
        self.assertFalse(audit["residual_is_identified_source_category"])
        rows = [row for row in self.result["group_compositions"]
            if row["source_key"] == parent["source_key"] and row["dimension"] == "sex"]
        self.assertEqual({row["own_source_votes"] for row in rows}, {536190})
        self.assertLess(sum(float(row["source_composition_pct"]) for row in rows), 100)

    def test_no_registration_turnout_full_ballots_or_person_history_is_inferred(self):
        for row in self.result["source_profiles"]:
            for field in ("registered_population", "group_turnout_rate", "full_election_ballots",
                    "unique_voters", "observed_staying_home", "geographic_FIPS", "sampling_n"):
                self.assertIsNone(row[field])
            self.assertFalse(row["native_ABS_relabelled_mail_returned"])

    def test_overlapping_literal_subset_fields_do_not_become_unions_or_joint_cells(self):
        self.assertEqual(len(self.result["literal_subset_decisions"]), 130)
        for row in self.result["literal_subset_decisions"]:
            self.assertIsNone(row["union_count"])
            self.assertIsNone(row["intersection_with_race_sex_or_method"])
            self.assertFalse(row["category_meanings_qualified"])
        self.assertNotIn("registration_affiliation", {row["dimension"] for row in self.result["group_compositions"]})

    def test_native_zeros_survive_and_unreported_states_are_not_zero(self):
        row = next(row for row in self.result["native_count_cells"]
            if row["native_label"] == "TENSAS-54" and row["native_field"] == "UOCAVA IN")
        self.assertEqual(row["literal_count"], 0)
        self.assertIsNone(next(row for row in self.result["state_coverage"] if row["state_code"] == "MS")["native_VOTES"])

    def test_printed_clock_and_filter_do_not_borrow_metadata_timezone_or_actual_start(self):
        row = self.result["source_profiles"][0]
        self.assertEqual(row["report_filter_begin"], "1900-01-01")
        self.assertIsNone(row["source_print_timezone"])
        self.assertIn("-06", self.inputs[0]["pdf_creation_metadata"])
        policy = copy.deepcopy(self.inputs[1])
        policy["registration_denominators_supplied"] = True
        with self.assertRaises(ValueError):
            primary.build(self.inputs[0], policy, self.inputs[2])

    def test_zero_source_denominator_is_missing_not_zero_share(self):
        facts = copy.deepcopy(self.inputs[0])
        facts["rows"][0]["counts"]["VOTES"] = 0
        result = primary.build(facts, *self.inputs[1:])
        rows = [row for row in result["group_compositions"] if row["source_key"] == facts["rows"][0]["source_key"]]
        self.assertTrue(all(row["source_composition_pct"] is None for row in rows))
        self.assertTrue(all(row["disposition"] == "held_zero_native_denominator" for row in rows))

    def test_all_query_bytes_roundtrip_and_independent_verifier_rejects_repaired_residual(self):
        self.assertEqual(primary.result_files(self.result),
            primary.result_files(json.loads(primary.encoded(self.result))))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, body in primary.result_files(self.result).items():
                (root / name).write_bytes(body)
            self.assertEqual(independent.verify(INPUTS, root)["native_numeric_cells"], 1040)
            changed = copy.deepcopy(self.result)
            row = next(row for row in changed["margin_accounting"]
                if row["scope_kind"] == "state_parent" and row["dimension"] == "sex")
            row["signed_arithmetic_residual"] = 0
            for name, body in primary.result_files(changed).items():
                (root / name).write_bytes(body)
            with self.assertRaises(ValueError):
                independent.verify(INPUTS, root)


if __name__ == "__main__":
    unittest.main()
