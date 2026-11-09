import copy
import json
from pathlib import Path
import unittest
import zipfile

from scripts.extract_mississippi_active_register import read_pdf
from scripts.mississippi_active_register import registration_frame


class MississippiActiveRegisterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/mississippi-active-register/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-mississippi-active-native-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.grid = read_pdf(archive.read("MS-2026-October-active-voter-count.pdf"))
            cls.independent = json.loads(archive.read("independent-pdf-rows.json"))
            cls.scope = json.loads(archive.read("source-scope.json"))

    def changed(self, field, value, row=0):
        grid, independent = copy.deepcopy(self.grid), copy.deepcopy(self.independent)
        grid["rows"][row][field] = independent["rows"][row][field] = value
        return grid, independent

    def result(self, grid, independent):
        return registration_frame(grid, independent, self.scope)

    def test_missing_active_count_does_not_create_partial_state_sum(self):
        total, rows, _, accounting = self.result(*self.changed("native_active_voters", None))
        self.assertIsNone(total)
        self.assertIsNone(rows[0]["native_active_count"])
        state = next(row for row in accounting if row["scope"] == "all82_counties"
                     and row["source_measure"] == "native_active_count")
        self.assertFalse(state["complete"])
        self.assertEqual(state["missing_count_slots"], 1)

    def test_zero_is_preserved_not_converted_to_unknown(self):
        total, rows, percentages, _ = self.result(*self.changed("native_active_voters", "0"))
        self.assertEqual(total, 1888362 - 17099)
        self.assertEqual(rows[0]["native_active_count"], 0)
        self.assertEqual(percentages[0]["exact_active_per_source_cvap_pct"], "0")

    def test_negative_or_fractional_native_counts_are_rejected(self):
        for value in ("-1", "1.5"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Invalid literal count"):
                self.result(*self.changed("native_active_voters", value))

    def test_missing_cvap_does_not_destroy_separate_active_frame(self):
        total, _, percentages, _ = self.result(*self.changed("native_cvap_estimate", None))
        self.assertEqual(total, 1888362)
        self.assertIsNone(percentages[0]["exact_active_per_source_cvap_pct"])

    def test_zero_cvap_ratio_is_undefined_not_zero_percent(self):
        percentages = self.result(*self.changed("native_cvap_estimate", "0"))[2]
        self.assertIsNone(percentages[0]["exact_active_per_source_cvap_pct"])

    def test_over100_source_percentages_are_not_clipped(self):
        percentages = self.result(self.grid, self.independent)[2]
        hancock = next(row for row in percentages if row["native_county_label"] == "23 - Hancock")
        self.assertEqual(hancock["source_percentage"], "102.292%")
        self.assertTrue(hancock["source_display_over100"])
        self.assertFalse(hancock["percentage_is_turnout"])

    def test_source_disagreement_is_preserved_not_repaired(self):
        percentages = self.result(*self.changed("native_percentage", "50.000%"))[2]
        self.assertEqual(percentages[0]["source_percentage"], "50.000%")
        self.assertFalse(percentages[0]["three_decimal_rounding_compatible"])

    def test_duplicate_county_is_not_complete_unique_source_coverage(self):
        with self.assertRaisesRegex(ValueError, "duplicate native"):
            self.result(*self.changed("native_county_label", "02 - Alcorn"))

    def test_independent_native_disagreement_is_rejected(self):
        peer = copy.deepcopy(self.independent)
        peer["rows"][0]["native_active_voters"] = "1"
        with self.assertRaisesRegex(ValueError, "Independent complete native"):
            self.result(self.grid, peer)

    def test_month_does_not_invent_first_monday_cutoff(self):
        scope = dict(self.scope, exact_registration_cutoff_date="2026-10-05")
        with self.assertRaisesRegex(ValueError, "unknown cutoff"):
            registration_frame(self.grid, self.independent, scope)

    def test_county_sum_is_not_promoted_to_printed_parent(self):
        scope = dict(self.scope, printed_statewide_total_present=True)
        with self.assertRaisesRegex(ValueError, "derived sum"):
            registration_frame(self.grid, self.independent, scope)

    def test_frame_transport_is_not_silently_validated(self):
        scope = dict(self.scope, registration_frame_transport_validated=True)
        with self.assertRaisesRegex(ValueError, "unvalidated transport"):
            registration_frame(self.grid, self.independent, scope)

    def test_cvap_is_not_a_turnout_or_model_denominator(self):
        for field in ("cvap_not_used_as_model_denominator", "native_percentages_not_turnout"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "scope"):
                registration_frame(self.grid, self.independent, dict(self.scope, **{field: False}))

    def test_asterisk_cvap_basis_is_retained_without_county_projection(self):
        rows = self.result(self.grid, self.independent)[1]
        benton = next(row for row in rows if row["native_county_label"] == "05 - Benton*")
        self.assertEqual(benton["native_cvap_source_basis"], "2020_Census_CVAP")
        self.assertFalse(benton["county_model_allocated"])
        self.assertFalse(benton["independent_legal_eligibility_certification"])


if __name__ == "__main__":
    unittest.main()
