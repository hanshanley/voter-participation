"""Regressions for native-to-context binding without source or semantic replacement."""

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts import louisiana_early_spatial as primary
from scripts import verify_louisiana_early_spatial as independent


INPUTS = Path(os.environ.get("LOUISIANA_SPATIAL_INPUTS",
    Path(__file__).resolve().parents[1] / "data/participation-louisiana-early-spatial/20261111-01"))


class LouisianaSpatialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = primary.load_inputs(INPUTS)
        cls.result, cls.geometry = primary.build(cls.data)

    def test_numeric_disagreements_are_kept_without_overwriting_either_source(self):
        rows = [r for r in self.result["provider_comparisons"] if r["native_minus_provider"]]
        self.assertEqual({(r["native_label"], r["native_field"]): r["native_minus_provider"] for r in rows},
            {("BOSSIER-08", "ABS"): -1, ("EAST FELICIANA-19", "INPER"): 1,
                ("JEFFERSON-26", "ABS"): 4, ("LAFAYETTE-28", "ABS"): 1})
        self.assertTrue(all(not r["automatic_source_replacement"] for r in rows))

    def test_numeric_matches_do_not_qualify_modes_clocks_populations_or_independence(self):
        rows = [r for r in self.result["provider_comparisons"] if r["native_minus_provider"] == 0]
        self.assertEqual(len(rows), 124)
        for row in rows:
            for field in ("method_equivalence_qualified", "clock_equivalence_qualified",
                    "population_equivalence_qualified", "independent_validation"):
                self.assertFalse(row[field])
            self.assertIsNone(row["native_source_print_timezone"])

    def test_native_ordinal_is_not_interpreted_as_FIPS_and_shapes_are_unchanged(self):
        acadia = next(r for r in self.result["bindings"] if r["native_code"] == "01")
        self.assertEqual(acadia["reference_key"], "22001")
        self.assertFalse(acadia["native_code_is_FIPS"])
        old = {f["properties"]["key"]: f["geometry"] for f in self.data["reference"]["features"]}
        self.assertEqual({f["id"]: f["geometry"] for f in self.geometry["features"]}, old)

    def test_unknown_name_is_retained_unbound_not_fuzzy_matched_or_dropped(self):
        data = copy.deepcopy(self.data)
        data["source"]["source_profiles"][0]["native_label"] = "UNQUALIFIED-01"
        result, geometry = primary.build(data)
        self.assertEqual(result["summary"]["held_source_bindings"], 1)
        self.assertEqual(result["bindings"][0]["disposition"], "held_no_reference_name_match")
        self.assertIsNone(result["bindings"][0]["reference_key"])
        self.assertEqual(len(geometry["unbound_source_profiles"]), 1)
        self.assertEqual(len(geometry["features"]), 63)
        data = copy.deepcopy(self.data)
        data["source"]["source_profiles"][0]["native_label"] = "ALLEN-01"
        result, geometry = primary.build(data)
        self.assertEqual(result["summary"]["held_source_bindings"], 2)
        self.assertEqual(result["bindings"][0]["disposition"], "held_ambiguous_native_name")
        self.assertEqual(len({f["id"] for f in geometry["features"]}), 62)

    def test_group_source_profiles_and_unallocated_sex_margin_are_not_recomputed(self):
        self.assertEqual(self.result["summary"]["source_sex_residual"], 278)
        for f in self.geometry["features"]:
            profile = f["properties"]["native_source_profile"]
            self.assertIsNone(profile["group_turnout_rate"])
            self.assertIsNone(profile["geographic_FIPS"])
            self.assertFalse(profile["native_ABS_relabelled_mail_returned"])
            for row in f["properties"]["native_compositions"]:
                self.assertEqual(f["properties"][row["native_group"] + "_count"], row["native_count"])
        self.assertEqual(self.result["source_state_coverage"], self.data["source"]["state_coverage"])

    def test_missing_provider_count_is_not_an_inferred_zero_or_native_replacement(self):
        data = copy.deepcopy(self.data)
        selected = data["counts"]["views"]["in_person_early"]["counties"][0]
        row = next(r for r in data["counts"]["records"] if r["id"] == selected)
        row["count"] = dict(value=None, literal=None, status="unknown")
        result, _ = primary.build(data)
        comparison = next(r for r in result["provider_comparisons"] if r["provider_observation_id"] == selected)
        self.assertIsNone(comparison["provider_count"])
        self.assertIsNone(comparison["native_minus_provider"])
        self.assertEqual(comparison["disposition"], "held_provider_missing_count")

    def test_unknown_reference_scope_and_native_semantic_promotion_fail_closed(self):
        data = copy.deepcopy(self.data)
        data["reference"]["features"][0]["properties"]["state_code"] = "MS"
        with self.assertRaises(ValueError):
            primary.build(data)
        data = copy.deepcopy(self.data)
        data["policy"]["provider_method_or_clock_requalified"] = True
        with self.assertRaises(ValueError):
            primary.build(data)

    def test_independent_roundtrip_rejects_a_repaired_discrepancy(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            files = primary.result_files(self.result, self.geometry)
            for name, body in files.items():
                (output / name).write_bytes(body)
            proof = independent.verify(INPUTS, output)
            self.assertEqual(proof["numerical_differences"], 4)
            changed = copy.deepcopy(self.result)
            next(r for r in changed["provider_comparisons"] if r["native_minus_provider"])["native_minus_provider"] = 0
            (output / "complete-result.json").write_bytes(primary.encoded(changed))
            with self.assertRaises(ValueError):
                independent.verify(INPUTS, output)


if __name__ == "__main__":
    unittest.main()
