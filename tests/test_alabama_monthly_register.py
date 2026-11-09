import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

from scripts.alabama_monthly_register import registration_frames
from scripts.extract_alabama_monthly_register import read_workbook


class AlabamaMonthlyRegisterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/alabama-monthly-register/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-alabama-monthly-native-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.body = archive.read("ALVR-2026.xlsx")
            cls.independent = json.loads(archive.read("independent-cached-values.json"))
            cls.declaration = json.loads(archive.read("source-declaration.json"))
        cls.sheets = read_workbook(cls.body)

    def changed_native(self):
        return copy.deepcopy(self.sheets), copy.deepcopy(self.independent)

    def result(self, sheets, independent):
        with patch("scripts.alabama_monthly_register.read_workbook", return_value=sheets):
            return registration_frames(self.body, independent, self.declaration)

    def test_october_native_month_is_not_november_url_directory(self):
        selected, _, _, parents = registration_frames(self.body, self.independent, self.declaration)
        self.assertEqual(selected["native_month_label"], "October")
        self.assertEqual(len(parents), 10)
        self.assertIsNone(selected["registration_cutoff_date"])

    def test_active_combined_and_inactive_source_frames_are_distinct(self):
        selected, _, _, _ = registration_frames(self.body, self.independent, self.declaration)
        self.assertEqual(selected["native_active_parent"], 3390357)
        self.assertEqual(selected["native_inactive_parent"], 462824)
        self.assertEqual(selected["native_combined_parent"], 3853181)

    def test_blank_fine_count_is_unknown_and_equation_remains_incomplete(self):
        _, accounting, equations, _ = registration_frames(self.body, self.independent, self.declaration)
        blank = next(row for row in accounting if row["month_label"] == "October" and row["cell"] == "F4")
        self.assertIsNone(blank["native_count"])
        self.assertFalse(blank["missing_imputed_zero"])
        equation = next(row for row in equations if row["month_label"] == "October"
                        and row["parent_cell"] == "L4" and row["equation"] == "native_category_components_L")
        self.assertFalse(equation["complete"])
        self.assertIsNone(equation["difference"])

    def test_missing_cached_parent_is_not_recalculated_from_formula(self):
        sheets, independent = self.changed_native()
        sheets[-1]["cells"]["L3"]["value"] = None
        independent[-1]["values"]["L3"] = None
        self.assertTrue(sheets[-1]["cells"]["L3"]["is_formula"])
        with self.assertRaisesRegex(ValueError, "Missing explicit cached October parent"):
            self.result(sheets, independent)

    def test_source_discrepancy_is_retained_not_repaired_by_county_sum(self):
        sheets, independent = self.changed_native()
        sheets[-1]["cells"]["L3"]["value"] += 1
        independent[-1]["values"]["L3"] += 1
        selected, _, equations, _ = self.result(sheets, independent)
        self.assertEqual(selected["native_active_parent"], 3390358)
        equation = next(row for row in equations if row["month_label"] == "October"
                        and row["parent_cell"] == "L3" and row["equation"] == "explicit_parent_vs_all67_counties")
        self.assertEqual(equation["difference"], -1)

    def test_independent_reader_disagreement_is_rejected(self):
        independent = copy.deepcopy(self.independent)
        independent[-1]["values"]["L3"] += 1
        with self.assertRaisesRegex(ValueError, "readers disagree"):
            registration_frames(self.body, independent, self.declaration)

    def test_duplicate_county_is_not_treated_as_complete_coverage(self):
        sheets, independent = self.changed_native()
        value = sheets[-1]["cells"]["A4"]["value"]
        sheets[-1]["cells"]["A5"]["value"] = independent[-1]["values"]["A5"] = value
        with self.assertRaisesRegex(ValueError, "Missing or repeated native county"):
            self.result(sheets, independent)

    def test_active_inactive_column_swap_is_rejected(self):
        sheets, independent = self.changed_native()
        sheets[-1]["cells"]["L2"]["value"] = independent[-1]["values"]["L2"] = "Total Inactive"
        with self.assertRaisesRegex(ValueError, "active/inactive parent definitions"):
            self.result(sheets, independent)

    def test_negative_native_count_is_not_coerced_or_imputed(self):
        sheets, independent = self.changed_native()
        sheets[-1]["cells"]["C4"]["value"] = independent[-1]["values"]["C4"] = -1
        with self.assertRaisesRegex(ValueError, "Invalid native count"):
            self.result(sheets, independent)

    def test_invented_cutoff_date_is_rejected(self):
        declaration = dict(self.declaration, registration_cutoff_date="2026-11-01")
        with self.assertRaisesRegex(ValueError, "URL month or retrieval date"):
            registration_frames(self.body, self.independent, declaration)


if __name__ == "__main__":
    unittest.main()
