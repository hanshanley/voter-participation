import copy
import gzip
import io
import json
import tempfile
from pathlib import Path
import unittest
import zipfile

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

    def test_native_json_queries_keep_zero_based_source_record_provenance(self):
        body = b'[{"unit":"A","ballots":"10","clock":"Native date"},'
        body += b'{"unit":"B","ballots":0,"clock":null}]'
        spec = dict(self.spec, kind="json_records", pin=pin(body), expected_rows=2)
        product = unpack(spec, body)
        selection = dict(self.selection, fields=dict(unit="unit", ballots="ballots", clock="clock"))
        result = query(product, selection)
        self.assertEqual(result["rows"][0]["source_rows"],
            [dict(table=None, workbook=None, record_index=0)])
        self.assertEqual(result["rows"][1]["ballots"], 0)
        self.assertIsNone(result["rows"][1]["clock"])
        self.assertEqual(product["tables"][0]["kind"], "json_records")

    def test_independent_json_verification_detects_changed_types_or_ordinals(self):
        from scripts.verify_native_products import verify

        body = b'[{"unit":"A","ballots":0,"flag":false}]'
        spec = dict(self.spec, path="native.json", kind="json_records", pin=pin(body), expected_rows=1)
        selection = dict(self.selection, fields=dict(unit="unit", ballots="ballots"))
        recipe = dict(contract="participation.native_product_recipe.v1",
            products=[spec], queries=[selection])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "native.json").write_bytes(body)
            compile_products(recipe, root, root / "compiled")
            self.assertEqual(verify(recipe, root, root / "compiled")["status"], "passed")
            path = root / "compiled/test.factual-tables.json.gz"
            original = json.loads(gzip.decompress(path.read_bytes()))
            for change in ("type", "ordinal"):
                factual = copy.deepcopy(original)
                if change == "type":
                    factual["tables"][0]["rows"][0]["values"][2] = 0
                else:
                    factual["tables"][0]["rows"][0]["row"] = 1
                path.write_bytes(gzip.compress(encoded(factual), mtime=0))
                manifest = json.loads((root / "compiled/manifest.json").read_bytes())
                manifest["outputs"][path.name] = pin(path.read_bytes())
                (root / "compiled/manifest.json").write_bytes(encoded(manifest))
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "JSON record"):
                    verify(recipe, root, root / "compiled")

    def native_reproduction_fixture(self):
        product = unpack(self.spec, self.body)
        recipe = dict(contract="participation.native_product_recipe.v1",
            products=[self.spec], queries=[self.selection])
        declaration = dict(recipe_input="recipe", products={
            self.spec["id"]: dict(original="original", facts="facts")}, queries_input="queries")
        spec = dict(election=dict(year=2026), geography=dict(state_code="HI"),
            format=dict(native_reproduction=declaration), inputs=dict(
                original=dict(url=self.spec["url"], pin=self.spec["pin"], publication="original"),
                recipe={}, facts={}, queries={}))
        inputs = dict(original=self.body, facts=encoded(product), recipe=encoded(recipe),
            queries=encoded(dict(contract="participation.native_queries.v1",
                queries={self.selection["id"]: query(product, self.selection)})))
        return spec, inputs

    def test_native_intake_reproduces_complete_originals_facts_and_queries(self):
        from scripts.participation_intake.adapters import verify_native_reproduction

        spec, inputs = self.native_reproduction_fixture()
        verify_native_reproduction(spec, inputs)
        spec["format"]["native_reproduction"]["products"]["test"]["compression"] = "gzip"
        inputs["facts"] = gzip.compress(inputs["facts"], mtime=0)
        verify_native_reproduction(spec, inputs)

    def test_native_intake_rejects_metadata_only_inputs_or_tampered_facts_and_queries(self):
        from scripts.participation_intake.adapters import verify_native_reproduction

        for change in ("original", "facts", "queries", "permission", "year"):
            spec, inputs = self.native_reproduction_fixture()
            if change == "permission":
                spec["inputs"]["original"]["publication"] = "metadata_only"
            elif change == "year":
                spec["election"]["year"] = 2024
            else:
                inputs[change] = b"{}"
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_native_reproduction(spec, inputs)

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

    def workbook_body(self):
        namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("xl/workbook.xml",
                f'<workbook xmlns="{namespace}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Month" sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr("xl/_rels/workbook.xml.rels",
                '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{namespace}"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>Stock</t></is></c>'
                '<c r="B1"><f>EXTERNAL_FUNCTION()</f><v>0</v></c>'
                '<c r="C1"/></row></sheetData></worksheet>')
        return stream.getvalue()

    def test_direct_workbook_preserves_cached_counts_formulas_and_blank_cells(self):
        body = self.workbook_body()
        spec = dict(self.spec, kind="xlsx", sheets=["Month"], pin=pin(body))
        product = unpack(spec, body)
        result = query(product, dict(id="stocks", product=self.spec["id"], tables=["Month"],
            fields=dict(label="A", stock="B", unknown="C"), counts=["stock"], keys=["label"]))
        row = result["rows"][0]
        self.assertEqual((row["label"], row["stock"], row["unknown"]), ("Stock", 0, None))
        cell = product["tables"][0]["rows"][0]["cells"][1]
        self.assertEqual(cell["formula"]["text"], "EXTERNAL_FUNCTION()")
        self.assertEqual(cell["cached_literal"], "0")

    def test_direct_workbook_requires_exact_declared_sheet_inventory(self):
        body = self.workbook_body()
        spec = dict(self.spec, kind="xlsx", sheets=["Different month"], pin=pin(body))
        with self.assertRaisesRegex(ValueError, "worksheet inventory"):
            unpack(spec, body)
        spec["sheets"] = ["Month", "Missing month"]
        with self.assertRaisesRegex(ValueError, "worksheet inventory"):
            unpack(spec, body)

    def test_direct_workbook_independent_reader_detects_changed_cached_facts(self):
        from openpyxl import Workbook
        from scripts.verify_native_products import verify

        workbook = Workbook()
        workbook.active.title = "Month"
        workbook.active.append(["Stock", 0])
        stream = io.BytesIO()
        workbook.save(stream)
        workbook.close()
        body = stream.getvalue()
        spec = dict(self.spec, path="stock.xlsx", kind="xlsx", sheets=["Month"], pin=pin(body))
        recipe = dict(contract="participation.native_product_recipe.v1", products=[spec],
            queries=[dict(id="stocks", product=spec["id"], tables=["Month"],
                fields=dict(label="A", stock="B"), counts=["stock"], keys=["label"])])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "stock.xlsx").write_bytes(body)
            compiled = root / "compiled"
            compile_products(recipe, root, compiled)
            self.assertEqual(verify(recipe, root, compiled)["status"], "passed")
            path = compiled / "test.factual-tables.json.gz"
            factual = json.loads(gzip.decompress(path.read_bytes()))
            factual["tables"][0]["rows"][0]["cells"][1]["value"] = 1
            path.write_bytes(gzip.compress(encoded(factual), mtime=0))
            manifest = json.loads((compiled / "manifest.json").read_bytes())
            manifest["outputs"][path.name] = pin(path.read_bytes())
            (compiled / "manifest.json").write_bytes(encoded(manifest))
            with self.assertRaisesRegex(ValueError, "Independent cached value differs"):
                verify(recipe, root, compiled)

    def test_existing_nested_workbook_reader_retains_independent_verification(self):
        from openpyxl import Workbook
        from scripts.verify_native_products import verify

        workbook = Workbook()
        workbook.active.title = "Month"
        workbook.active.append(["Stock", 7])
        inner = io.BytesIO()
        workbook.save(inner)
        workbook.close()
        outer = io.BytesIO()
        with zipfile.ZipFile(outer, "w") as archive:
            archive.writestr("source.xlsx", inner.getvalue())
        body = outer.getvalue()
        spec = dict(self.spec, path="source.zip", kind="xlsx_zip",
            members={"source.xlsx": ["Month"]}, pin=pin(body))
        recipe = dict(contract="participation.native_product_recipe.v1", products=[spec],
            queries=[dict(id="stocks", product=spec["id"], workbook="source.xlsx", tables=["Month"],
                fields=dict(label="A", stock="B"), counts=["stock"], keys=["label"])])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.zip").write_bytes(body)
            compile_products(recipe, root, root / "compiled")
            report = verify(recipe, root, root / "compiled")
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["reports"][0]["cells"], 2)

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
