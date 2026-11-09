import copy
import csv
import io
import json
from pathlib import Path
import unittest
import zipfile

from scripts.idaho_monthly_register import registration_frame


class IdahoMonthlyRegisterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/idaho-monthly-register/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-idaho-monthly-native-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.bodies = {view: archive.read(view + ".csv")
                          for view in ("County", "Legislative", "Congressional")}
            cls.independent = json.loads(archive.read("pandas-tables.json"))
            cls.declarations = json.loads(archive.read("source-declarations.json"))

    def frame(self, bodies=None, independent=None, declarations=None):
        return registration_frame(self.bodies if bodies is None else bodies,
            self.independent if independent is None else independent,
            self.declarations if declarations is None else declarations)

    def changed(self, view, row, column, value):
        tables = {name: list(csv.reader(io.StringIO(body.decode())))
                  for name, body in self.bodies.items()}
        tables[view][row][column] = value
        bodies = dict(self.bodies)
        stream = io.StringIO(newline="")
        csv.writer(stream, lineterminator="\r\n").writerows(tables[view])
        bodies[view] = stream.getvalue().encode()
        independent = copy.deepcopy(self.independent)
        independent[view] = tables[view]
        return bodies, independent

    def test_selects_parent_once_not_three_geographic_populations(self):
        parent, cells, _ = self.frame()
        self.assertEqual(parent, 1056803)
        self.assertEqual(len(cells), 504)
        self.assertEqual(sum(row["geography_literal"] == "Total" for row in cells), 18)

    def test_missing_total_cannot_use_county_sum_fallback(self):
        bodies, independent = self.changed("County", -1, 0, "Unknown")
        with self.assertRaisesRegex(ValueError, "explicit Total"):
            self.frame(bodies, independent)

    def test_missing_numeric_cell_cannot_be_zero_or_complement(self):
        bodies, independent = self.changed("County", 1, 1, "")
        with self.assertRaisesRegex(ValueError, "no zero or component fallback"):
            self.frame(bodies, independent)

    def test_observed_zero_is_preserved_instead_of_missing(self):
        bodies, independent = self.changed("County", 1, 1, " 0 ")
        _, cells, diagnostics = self.frame(bodies, independent)
        row = next(row for row in cells if row["view"] == "County"
                   and row["geography_literal"] == "ADA" and row["native_column"] == "CON")
        self.assertEqual((row["native_registered_count"], row["raw_native_cell"]), (0, " 0 "))
        self.assertFalse(row["missing_imputed_zero"])
        self.assertNotEqual(next(row for row in diagnostics if row["scope"] == "County:ADA")["difference"], 0)

    def test_duplicate_county_is_not_complete_inventory(self):
        bodies, independent = self.changed("County", 2, 0, "ADA")
        with self.assertRaisesRegex(ValueError, "duplicate native geography"):
            self.frame(bodies, independent)

    def test_source_party_header_cannot_be_changed_to_votes(self):
        bodies, independent = self.changed("County", 0, 4, "Votes")
        with self.assertRaisesRegex(ValueError, "party/Total columns"):
            self.frame(bodies, independent)

    def test_independent_raw_whitespace_disagreement_is_not_silently_normalized(self):
        independent = copy.deepcopy(self.independent)
        independent["County"][1][1] = independent["County"][1][1].strip()
        with self.assertRaisesRegex(ValueError, "complete CSV readers disagree"):
            self.frame(independent=independent)

    def test_district_parent_conflict_cannot_be_repaired(self):
        bodies, independent = self.changed("Legislative", -1, -1, " 1,056,804 ")
        with self.assertRaisesRegex(ValueError, "repeated parents disagree"):
            self.frame(bodies, independent)

    def test_registry_cutoff_cannot_be_inferred_from_index_update(self):
        declarations = copy.deepcopy(self.declarations)
        declarations["native_registration_cutoff"] = "2026-11-02"
        with self.assertRaisesRegex(ValueError, "cutoff/status qualification"):
            self.frame(declarations=declarations)

    def test_archive_month_cannot_be_silently_changed(self):
        declarations = copy.deepcopy(self.declarations)
        declarations["selected_month"] = "10"
        with self.assertRaisesRegex(ValueError, "native archive selection"):
            self.frame(declarations=declarations)


if __name__ == "__main__":
    unittest.main()
