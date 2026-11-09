import copy
import json
from pathlib import Path
import unittest
import zipfile

from scripts.south_carolina_register import decode_workbook, registration_frame


class SouthCarolinaRegisterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/south-carolina-register/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-south-carolina-native-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.cells = decode_workbook(archive.read("registration.xlsx"))
            cls.independent = json.loads(archive.read("openpyxl-cells.json"))

    def frame(self, cells=None, independent=None):
        return registration_frame(self.cells if cells is None else cells,
                                  self.independent if independent is None else independent)

    def changed(self, sheet, address, **updates):
        cells, independent = copy.deepcopy(self.cells), copy.deepcopy(self.independent)
        next(cell for cell in cells if cell["sheet"] == sheet and cell["cell"] == address).update(updates)
        next(cell for cell in independent if cell["sheet"] == sheet and cell["cell"] == address).update(
            {key: value for key, value in updates.items() if key in ("kind", "value")})
        return cells, independent

    def test_selects_direct_overall_parent_not_sum_of_nine_views(self):
        total, margins, _ = self.frame()
        self.assertEqual(total, 3470220)
        self.assertEqual(len(margins), 6768)
        self.assertEqual(len(self.cells), 14121)

    def test_missing_native_total_cannot_use_county_or_demographic_fallback(self):
        cells, independent = self.changed("Sheet1", "H58", kind="blank", value=None)
        with self.assertRaisesRegex(ValueError, "explicit numeric native total"):
            self.frame(cells, independent)

    def test_missing_total_scope_is_not_relabelled(self):
        cells, independent = self.changed("Sheet1", "D58", value="Unknown")
        with self.assertRaisesRegex(ValueError, "native statewide TOTAL"):
            self.frame(cells, independent)

    def test_independent_numeric_disagreement_is_not_repaired(self):
        independent = copy.deepcopy(self.independent)
        next(cell for cell in independent if cell["sheet"] == "Sheet1" and cell["cell"] == "H58")["value"] = "1"
        with self.assertRaisesRegex(ValueError, "workbook readers disagree"):
            self.frame(independent=independent)

    def test_unknown_gender_blank_is_not_zero_or_complement_recovery(self):
        _, margins, diagnostics = self.frame()
        row = next(row for row in margins if row["sheet"] == "Sheet6" and row["cell"] == "W55")
        self.assertIsNone(row["native_registered_count"])
        self.assertFalse(row["missing_is_zero"])
        check = next(row for row in diagnostics if row["scope"] == "Sheet6:46:gender")
        self.assertFalse(check["complete_equation_qualified"])
        self.assertIn("W", check["unknown_child_cells"])

    def test_observed_numeric_zero_is_not_missing(self):
        _, margins, _ = self.frame()
        row = next(row for row in margins if row["sheet"] == "Sheet4" and row["cell"] == "AA55")
        self.assertEqual((row["native_cell_kind"], row["native_registered_count"]), ("number", 0))

    def test_hispanic_race_label_is_not_renamed_to_survey_ethnicity(self):
        cells, independent = self.changed("Sheet5", "C6", value="Race: Non-Hispanic")
        with self.assertRaisesRegex(ValueError, "native race category"):
            self.frame(cells, independent)

    def test_age_bins_are_not_adjusted_to_match_survey_bins(self):
        cells, independent = self.changed("Sheet1", "K10", value="18 - 29")
        with self.assertRaisesRegex(ValueError, "age column semantics"):
            self.frame(cells, independent)

    def test_administrative_gender_header_is_not_survey_relabelled(self):
        cells, independent = self.changed("Sheet1", "I9", value="Self-reported sex")
        with self.assertRaisesRegex(ValueError, "administrative gender"):
            self.frame(cells, independent)

    def test_native_county_code_is_not_padded_to_fips(self):
        cells, independent = self.changed("Sheet1", "D11", value="45001")
        with self.assertRaisesRegex(ValueError, "county code inventory"):
            self.frame(cells, independent)


if __name__ == "__main__":
    unittest.main()
