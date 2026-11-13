import copy
import tempfile
from pathlib import Path
import unittest

from scripts.native_products import compile_products, displayed_cell, encoded, integer, pin, query, unpack


class NativeProductsTests(unittest.TestCase):
    def setUp(self):
        self.body = b"unit,ballots,reporting,votes\nA,10,0,3\nA,10,0,0\nB,0,1,0\n"
        self.spec = dict(id="test", path="native.csv", kind="delimited",
            pin=pin(self.body), reader={}, expected_rows=3,
            url="https://example.test/public-aggregate.csv", state_code="HI",
            election_year=2026, retrieved_at_utc="2026-11-12T23:00:00Z",
            native_updated_at=None, redistribution="factual_tables")
        self.selection = dict(id="units", product="test",
            fields=dict(unit="unit", ballots="ballots", reporting="reporting"),
            counts=["ballots"], keys=["unit"], deduplicate=True)

    def test_native_zero_reporting_does_not_remove_positive_counts(self):
        product = unpack(self.spec, self.body)
        result = query(product, self.selection)
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(result["rows"][0]["ballots"], 10)
        self.assertEqual(result["rows"][0]["reporting"], "0")
        self.assertEqual(len(result["rows"][0]["source_rows"]), 2)
        self.assertEqual(result["rows"][1]["ballots"], 0)
        self.assertEqual(len(product["tables"][0]["rows"]), 3)

    def test_disagreeing_stock_or_duplicate_candidate_cannot_be_deduplicated(self):
        product = unpack(self.spec, self.body)
        product["tables"][0]["rows"][1]["values"][1] = "11"
        with self.assertRaises(ValueError):
            query(product, self.selection)
        selection = dict(self.selection, deduplicate=False)
        with self.assertRaises(ValueError):
            query(unpack(self.spec, self.body), selection)

    def test_missing_and_nonapplicability_are_never_zero_counts(self):
        for value in (None, "", "-", True, -1, "1.5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                integer(value)
        self.assertEqual(integer("0"), 0)

    def test_native_date_format_is_required_and_raw_precinct_value_is_unchanged(self):
        table = dict(workbook_properties={}, workbook_number_formats={"164": r"mm\-dd"},
            workbook_cell_formats=[dict(numFmtId="164")])
        cells = {"A": dict(value=44562, attributes={"s": "0"})}
        selector = dict(column="A", display="excel_month_day")
        self.assertEqual(displayed_cell(table, cells, selector), "01-01")
        self.assertEqual(displayed_cell(table, cells, "A"), 44562)
        table["workbook_number_formats"]["164"] = r"m\-d"
        self.assertEqual(displayed_cell(table, cells, selector), "1-1")
        table["workbook_number_formats"]["164"] = "General"
        self.assertEqual(displayed_cell(table, cells, selector), 44562)
        table["workbook_number_formats"]["164"] = r"mm\-dd"
        cells["A"]["value"] = 60
        with self.assertRaises(ValueError):
            displayed_cell(table, cells, selector)
        table["workbook_properties"]["date1904"] = "1"
        cells["A"]["value"] = 1
        self.assertEqual(displayed_cell(table, cells, selector), "01-02")

    def test_pins_and_paths_fail_before_output_and_full_grids_reproduce(self):
        recipe = dict(contract="participation.native_product_recipe.v1",
            products=[self.spec], queries=[self.selection])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "native.csv").write_bytes(self.body)
            broken = copy.deepcopy(recipe)
            broken["products"][0]["pin"] = pin(b"changed")
            with self.assertRaises(ValueError):
                compile_products(broken, root, root / "broken")
            self.assertFalse((root / "broken").exists())
            unsafe = copy.deepcopy(recipe)
            unsafe["products"][0]["path"] = "../native.csv"
            with self.assertRaises(ValueError):
                compile_products(unsafe, root, root / "unsafe")
            first = compile_products(recipe, root, root / "first")
            second = compile_products(recipe, root, root / "second")
            self.assertEqual(first, second)
            for name in first["outputs"]:
                self.assertEqual((root / "first" / name).read_bytes(),
                    (root / "second" / name).read_bytes())
            self.assertIn(b'"source_acquisitions":0', encoded(first))


if __name__ == "__main__":
    unittest.main()
