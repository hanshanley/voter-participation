import copy
import json
from pathlib import Path
import unittest
import zipfile

from scripts.kansas_register import decode_workbook, registration_frame


class KansasRegisterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/kansas-register/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-kansas-native-inputs.zip"
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

    def test_selects_direct_county_parent_and_counts_repeated_margins_once(self):
        total, accounting, diagnostics, parents = self.frame()
        self.assertEqual(total, 2027520)
        self.assertEqual(set(parents.values()), {total})
        self.assertEqual(len(parents), 4)
        self.assertEqual((len(accounting), len(diagnostics)), (1946, 278))

    def test_missing_native_total_cannot_use_county_or_party_fallback(self):
        cells, independent = self.changed("By County", "J107", kind="blank", value=None)
        with self.assertRaisesRegex(ValueError, "explicit numeric native total"):
            self.frame(cells, independent)

    def test_missing_parent_label_is_not_inferred_from_numeric_totals(self):
        cells, independent = self.changed("By County", "B107", value="Unknown")
        with self.assertRaisesRegex(ValueError, "Grand Total"):
            self.frame(cells, independent)

    def test_different_snapshot_date_requires_new_review(self):
        cells, independent = self.changed("By County", "A2", value="2026-11-03")
        with self.assertRaisesRegex(ValueError, "snapshot date"):
            self.frame(cells, independent)

    def test_independent_cell_disagreement_is_not_repaired(self):
        independent = copy.deepcopy(self.independent)
        next(cell for cell in independent if cell["sheet"] == "By County" and cell["cell"] == "J107")["value"] = "1"
        with self.assertRaisesRegex(ValueError, "cell readers disagree"):
            self.frame(independent=independent)

    def test_blank_and_empty_party_values_remain_unknown_not_zero(self):
        _, accounting, diagnostics, _ = self.frame()
        no_labels = [row for row in accounting if row["native_column_label"] == "No Labels Kansas"]
        self.assertTrue(all(row["native_count"] is None for row in no_labels))
        empty = next(row for row in accounting if row["sheet"] == "By County" and row["cell"] == "H5")
        self.assertEqual((empty["native_cell_kind"], empty["native_value"], empty["native_count"]), ("text", "", None))
        self.assertTrue(all(not row["exhaustive_party_partition_qualified"] for row in diagnostics))

    def test_shared_formula_caches_are_data_not_executed_formulas(self):
        first = next(cell for cell in self.cells if cell["sheet"] == "By County" and cell["cell"] == "C2")
        shared = next(cell for cell in self.cells if cell["sheet"] == "By County" and cell["cell"] == "C3")
        self.assertEqual(first["value"], "Allen County, KS")
        self.assertIn("CONCATENATE", first["formula_text"])
        self.assertEqual(shared["formula_text"], "")
        self.assertEqual(shared["value"], "Anderson County, KS")
        self.assertEqual(shared["formula_attributes"]["t"], "shared")

    def test_changed_party_header_is_not_renamed(self):
        cells, independent = self.changed("By County", "F1", value="Unreviewed party")
        with self.assertRaisesRegex(ValueError, "column semantics"):
            self.frame(cells, independent)

    def test_district_inventory_not_repaired_by_matching_totals(self):
        cells, independent = self.changed("By Congressional District", "B2", value="U.S. Representative 5")
        with self.assertRaisesRegex(ValueError, "district inventory"):
            self.frame(cells, independent)

    def test_four_state_parents_cannot_be_added_or_averaged(self):
        cells, independent = self.changed("By KS Senate", "I42", value="2027521")
        with self.assertRaisesRegex(ValueError, "totals disagree"):
            self.frame(cells, independent)


if __name__ == "__main__":
    unittest.main()
