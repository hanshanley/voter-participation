import copy
import json
from pathlib import Path
import unittest
import zipfile

from scripts.extract_indiana_primary_register import read_workbook
from scripts.indiana_primary_register import registration_frame


class IndianaPrimaryRegisterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/indiana-primary-register/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-indiana-primary-native-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.grid = read_workbook(archive.read("IN-2026-primary.xlsx"))
            cls.independent = json.loads(archive.read("independent-workbook.json"))
            cls.scope = json.loads(archive.read("source-scope.json"))

    def changed(self):
        return copy.deepcopy(self.grid), copy.deepcopy(self.independent)

    def set_cell(self, grid, independent, address, value):
        cell = grid["cells"][address]
        cell["value"] = value
        if cell["source_type"] != "s":
            cell["raw_value"] = str(value) if value is not None else None
        independent["cells"][address]["value"] = value

    def result(self, grid, independent):
        return registration_frame(grid, independent, self.scope)

    def test_missing_county_registration_remains_unknown_not_zero(self):
        grid, independent = self.changed()
        self.set_cell(grid, independent, "B3", None)
        parent, raw, contexts, equations, _ = self.result(grid, independent)
        self.assertIsNone(contexts[0]["registered_voters"])
        self.assertEqual(parent["registered_voters"], 4713746)
        equation = next(row for row in equations if row["identity"] == "statewide-registered_voters-vs-all92-counties")
        self.assertEqual(equation["missing_components"], 1)
        self.assertFalse(equation["complete"])
        self.assertIsNone(equation["difference"])
        self.assertFalse(next(row for row in raw if row["cell"] == "B3")["missing_imputed_zero"])

    def test_missing_statewide_parent_is_not_replaced_by_county_sum(self):
        grid, independent = self.changed()
        self.set_cell(grid, independent, "B95", None)
        with self.assertRaisesRegex(ValueError, "no county-sum replacement"):
            self.result(grid, independent)

    def test_whole_percent_source_values_remain_separate_from_exact_ratio(self):
        _, _, _, _, percentages = self.result(self.grid, self.independent)
        source = next(row for row in percentages if row["source_cell"] == "D3")
        self.assertEqual(source["source_display_pct"], "22")
        self.assertNotEqual(source["exact_source_count_ratio_pct"], "22")
        self.assertTrue(source["whole_percent_rounding_compatible"])
        self.assertIsNone(source["design_confidence_interval"])

    def test_source_percentage_disagreement_is_preserved_not_repaired(self):
        grid, independent = self.changed()
        self.set_cell(grid, independent, "D3", 0.5)
        _, _, _, _, percentages = self.result(grid, independent)
        source = next(row for row in percentages if row["source_cell"] == "D3")
        self.assertEqual(source["source_display_pct"], "50")
        self.assertFalse(source["whole_percent_rounding_compatible"])

    def test_zero_ratio_denominator_is_undefined_not_zero_percent(self):
        grid, independent = self.changed()
        for address in ("C3", "D3", "E3", "F3", "G3"):
            self.set_cell(grid, independent, address, 0)
        percentages = self.result(grid, independent)[-1]
        source = next(row for row in percentages if row["source_cell"] == "G3")
        self.assertIsNone(source["exact_source_count_ratio_pct"])
        self.assertIsNone(source["whole_percent_rounding_compatible"])

    def test_primary_title_is_not_relabelled_general_election(self):
        grid, independent = self.changed()
        self.set_cell(grid, independent, "A1", "2026 General Registration and Turnout Data")
        with self.assertRaisesRegex(ValueError, "Changed native election title"):
            self.result(grid, independent)

    def test_report_context_does_not_invent_a_registration_cutoff(self):
        scope = dict(self.scope, registration_cutoff_date="2026-05-05")
        with self.assertRaisesRegex(ValueError, "unknown cutoff"):
            registration_frame(self.grid, self.independent, scope)

    def test_cross_election_transport_is_not_silently_validated(self):
        scope = dict(self.scope, cross_election_registration_frame_transport_validated=True)
        with self.assertRaisesRegex(ValueError, "unvalidated transport"):
            registration_frame(self.grid, self.independent, scope)

    def test_total_voters_is_not_silently_relabelled_ballots_cast(self):
        grid, independent = self.changed()
        self.set_cell(grid, independent, "C2", "Ballots Cast")
        with self.assertRaisesRegex(ValueError, "column meanings"):
            self.result(grid, independent)

    def test_negative_native_count_is_rejected(self):
        grid, independent = self.changed()
        self.set_cell(grid, independent, "B3", -1)
        with self.assertRaisesRegex(ValueError, "Invalid native count"):
            self.result(grid, independent)

    def test_duplicate_county_is_not_complete_unique_source_coverage(self):
        grid, independent = self.changed()
        self.set_cell(grid, independent, "A4", grid["cells"]["A3"]["value"])
        with self.assertRaisesRegex(ValueError, "repeated native county"):
            self.result(grid, independent)

    def test_independent_native_grid_disagreement_is_rejected(self):
        independent = copy.deepcopy(self.independent)
        independent["cells"]["B95"]["value"] += 1
        with self.assertRaisesRegex(ValueError, "native cells or number formats disagree"):
            self.result(self.grid, independent)

    def test_binary_percentage_lexeme_is_preserved_but_display_uses_native_format(self):
        percentages = self.result(self.grid, self.independent)[-1]
        source = next(row for row in percentages if row["source_cell"] == "D6")
        self.assertEqual(source["source_stored_fraction"], "0.28000000000000003")
        self.assertEqual(source["source_preformat_pct"], "28.000000000000003")
        self.assertEqual(source["source_display_pct"], "28")


if __name__ == "__main__":
    unittest.main()
