import copy
import io
import json
from pathlib import Path
import unittest
import zipfile

from scripts.extract_state_age_register import CA_BINS, SC_BINS, cells, matching_bins, register_frames
from scripts.state_age_register import query_rows


class StateAgeRegisterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        path = root / "data/state-age-register/20261109-01/sufficient-inputs.zip"
        if not path.exists():
            path = root / "inputs/complete-age-register-sufficient-inputs.zip"
        with zipfile.ZipFile(path) as archive:
            cls.scope = json.loads(archive.read("source-scope.json"))
            cls.snapshot = json.loads(archive.read("civic-selected-inputs.json"))
            with zipfile.ZipFile(io.BytesIO(archive.read("sc-native-inputs.zip"))) as source:
                cls.cells = cells(source.read("registration.xlsx"))
        cls.frames = register_frames(cls.cells)[2]

    def test_exact_native_open_age_boundary_is_compatible(self):
        self.assertEqual(matching_bins(SC_BINS, "65_plus"), ["65 - Up"])

    def test_66plus_cannot_be_substituted_for65plus(self):
        self.assertIsNone(matching_bins(CA_BINS, "65_plus"))

    def test_incomplete_or_crossing_bins_are_not_split(self):
        for group in ("18_29", "30_49", "50_64"):
            for bins in (SC_BINS, CA_BINS):
                with self.subTest(group=group, bins=bins):
                    self.assertIsNone(matching_bins(bins, group))

    def test_unknown_gender_counts_are_included_without_sex_crosswalk(self):
        _, native, frames, _ = register_frames(self.cells)
        older = next(row for row in frames if row["native_age_label"] == "65 - Up")
        self.assertEqual(older["derived_all_gender_age_register"], 1045477)
        self.assertEqual(sum(r["native_registered_count"] for r in native if r["native_age_label"] == "65 - Up"), 1045477)
        self.assertEqual(older["source_gender_cells"], 3)

    def test_missing_child_does_not_create_partial_group_frame(self):
        changed = copy.deepcopy(self.cells)
        changed["AA58"] = dict(kind="blank", value=None)
        frames = register_frames(changed)[2]
        older = next(row for row in frames if row["native_age_label"] == "65 - Up")
        self.assertIsNone(older["derived_all_gender_age_register"])
        self.assertEqual(older["observed_registered_subtotal"], 1045327)
        rows = query_rows(self.snapshot, frames, self.scope)[0]
        target = next(row for row in rows if row["state_code"] == "SC" and row["group"] == "65_plus")
        self.assertIsNone(target["conditional_participant_source_units"])

    def test_numeric_zero_is_not_missing_or_recovered_complement(self):
        changed = copy.deepcopy(self.cells)
        changed["AA58"] = dict(kind="number", value="0")
        older = next(r for r in register_frames(changed)[2] if r["native_age_label"] == "65 - Up")
        self.assertEqual(older["derived_all_gender_age_register"], 1045327)
        self.assertEqual(older["missing_gender_cells"], 0)

    def test_negative_or_fractional_native_child_is_rejected(self):
        for value in ("-1", "1.5"):
            changed = copy.deepcopy(self.cells)
            changed["AA58"] = dict(kind="number", value=value)
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Invalid native"):
                register_frames(changed)

    def test_missing_native_overall_is_not_county_or_gender_fallback(self):
        changed = copy.deepcopy(self.cells)
        changed["H58"] = dict(kind="blank", value=None)
        with self.assertRaisesRegex(ValueError, "explicit positive statewide"):
            register_frames(changed)

    def test_unknown_age_and_dc_are_holds_not_zero(self):
        rows = query_rows(self.snapshot, self.frames, self.scope)[0]
        for row in rows:
            if row["group"] == "unknown" or row["state_code"] == "DC":
                self.assertIsNone(row["derived_native_age_register"])
                self.assertIsNone(row["conditional_participant_source_units"])
                self.assertIsNone(row["source_n"])

    def test_unsupported_public_source_is_not_recovered_by_complement(self):
        rows = query_rows(self.snapshot, self.frames, self.scope)[0]
        younger = next(r for r in rows if r["state_code"] == "SC" and r["group"] == "18_29")
        self.assertIsNone(younger["source_weight"])
        self.assertIsNone(younger["source_modeled_participant_pct"])
        self.assertIsNone(younger["conditional_participant_source_units"])

    def test_native_parent_discrepancy_is_retained_not_repaired(self):
        changed = copy.deepcopy(self.cells)
        changed["H58"] = dict(kind="number", value="3470221")
        accounting = register_frames(changed)[3]
        self.assertEqual(accounting[-1]["complete_sum_minus_parent"], -1)

    def test_label_match_does_not_validate_population_or_age_clock(self):
        for key, value in (("source_population_frame_equivalence_validated", True),
                           ("source_age_reference_dates_harmonized", True),
                           ("sc_embedded_registration_cutoff", "2026-11-02")):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "unvalidated population"):
                query_rows(self.snapshot, self.frames, dict(self.scope, **{key: value}))

    def test_other_state_input_not_selected_is_not_world_absence(self):
        rows = query_rows(self.snapshot, self.frames, self.scope)[0]
        nc = next(r for r in rows if r["state_code"] == "NC" and r["group"] == "65_plus")
        self.assertEqual(nc["native_frame_disposition"], "no_native_age_register_selected_in_this_package")
        self.assertIsNone(nc["derived_native_age_register"])

    def test_full_query_has_one_distinct_unvalidated_target_no_allocation(self):
        rows, boundaries = query_rows(self.snapshot, self.frames, self.scope)
        selected = [row for row in rows if row["conditional_participant_source_units"] is not None]
        self.assertEqual(len(rows), 255)
        self.assertEqual(len(boundaries), 10)
        self.assertEqual([(r["state_code"], r["group"]) for r in selected], [("SC", "65_plus")])
        self.assertTrue(all(not r["local_probability_allocated"] and not r["population_point_estimate_approved"] for r in rows))

    def test_missing_or_duplicate_source_identity_is_not_silently_accepted(self):
        source = copy.deepcopy(self.snapshot)
        age = next(row for row in source["groups"] if row["dimension"] == "AGE6")
        source["groups"].append(age)
        with self.assertRaisesRegex(ValueError, "Incomplete 255"):
            query_rows(source, self.frames, self.scope)
        source["groups"] = [row for row in source["groups"] if row is not age]
        with self.assertRaisesRegex(ValueError, "Incomplete 255"):
            query_rows(source, self.frames, self.scope)


if __name__ == "__main__":
    unittest.main()
