import io
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

from scripts.native_tabular import column, delimited, json_records, values, xls, xlsx


class NativeTabularTests(unittest.TestCase):
    def test_biff_cached_zeros_blanks_dates_errors_and_booleans_remain_distinct(self):
        xlrd = SimpleNamespace(XL_CELL_EMPTY=0, XL_CELL_TEXT=1, XL_CELL_NUMBER=2,
            XL_CELL_DATE=3, XL_CELL_BOOLEAN=4, XL_CELL_ERROR=5, XL_CELL_BLANK=6,
            error_text_from_code={7: "#DIV/0!"})
        native = [(xlrd.XL_CELL_NUMBER, 0.0), (xlrd.XL_CELL_BLANK, ""),
                  (xlrd.XL_CELL_DATE, 45000.0), (xlrd.XL_CELL_ERROR, 7),
                  (xlrd.XL_CELL_BOOLEAN, 1), (xlrd.XL_CELL_TEXT, "001")]
        sheet = SimpleNamespace(name="Counts", nrows=1, ncols=len(native),
            cell=lambda row, column: SimpleNamespace(
                ctype=native[column][0], value=native[column][1], xf_index=0))
        released = []
        workbook = SimpleNamespace(datemode=0, format_map={}, xf_list=[],
            sheets=lambda: [sheet], release_resources=lambda: released.append(True))
        xlrd.open_workbook = lambda **kwargs: workbook
        with patch.dict(sys.modules, xlrd=xlrd):
            table = xls(b"reviewed native BIFF")[0]
        self.assertEqual(values(table, 1),
            dict(A=0, B=None, C=45000.0, D="#DIV/0!", E=True, F="001"))
        self.assertIs(type(values(table, 1)["C"]), float)
        self.assertEqual(table["rows"][0]["cells"][1]["cached_value"], "")
        self.assertEqual(table["rows"][0]["cells"][3]["cached_value"], 7)
        self.assertNotIn("formula", table["rows"][0]["cells"][0])
        self.assertEqual(released, [True])

    def test_native_json_preserves_scalar_types_nulls_and_record_indices(self):
        table = json_records(b'{"data":[{"id":"001","count":0,"unknown":null,"flag":false},'
            b'{"flag":true,"count":"0","id":"002","unknown":""}]}', items_path="data")
        self.assertEqual(table["header"], ["id", "count", "unknown", "flag"])
        self.assertEqual(table["rows"], [
            dict(row=0, values=["001", 0, None, False]),
            dict(row=1, values=["002", "0", "", True])])

    def test_native_json_rejects_duplicate_keys_missing_fields_nested_records_and_nonfinite_values(self):
        for body in (b'[{"id":"1","id":"2"}]', b'[{"id":"1"},{"other":"2"}]',
                b'[{"id":{"nested":0}}]', b'[{"id":NaN}]', b'[]'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                json_records(body)

    def test_native_json_guards_native_election_literals_not_metadata(self):
        body = b'[{"election":"2026 general","count":"0"}]'
        self.assertEqual(json_records(body, record_guards={
            "election": "2026 general"})["rows"][0]["values"][1], "0")
        with self.assertRaisesRegex(ValueError, "record guard"):
            json_records(body, record_guards={"election": "2024 general"})
        with self.assertRaisesRegex(ValueError, "record path"):
            json_records(body, items_path="missing")

    def test_logical_preamble_multiline_names_and_empty_final_column_preserved(self):
        body = b'#Format 1\t\t\nname\tvotes\t\n"First\nLast"\t0\t\nOther\t\t\n'
        table = delimited(body, delimiter="\t", preamble_rows=1)
        self.assertEqual(table["preamble"], [["#Format 1", "", ""]])
        self.assertEqual(table["header"], ["name", "votes", ""])
        self.assertEqual(table["rows"][0], dict(row=3, values=["First\nLast", "0", ""]))
        self.assertEqual(table["rows"][1]["values"], ["Other", "", ""])
        self.assertEqual(column(table, "votes"), 1)

    def test_duplicate_required_header_and_truncated_row_rejected(self):
        with self.assertRaises(ValueError):
            column(delimited(b"votes,votes\n1,2\n"), "votes")
        with self.assertRaises(ValueError):
            delimited(b"a,b\n1\n")

    def test_formula_cached_zero_shared_strings_and_explicit_blank_preserved(self):
        namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("xl/workbook.xml",
                f'<workbook xmlns="{namespace}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Counts" sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr("xl/_rels/workbook.xml.rels",
                '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            archive.writestr("xl/sharedStrings.xml",
                f'<sst xmlns="{namespace}"><si><r><t>County</t></r><r><t> name</t></r></si></sst>')
            archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{namespace}"><sheetData>'
                '<row r="1"><c r="A1" t="s"><v>0</v></c>'
                '<c r="B1"><f t="normal">EXTERNAL_FUNCTION()</f><v>0</v></c>'
                '<c r="C1" s="7"/><c r="D1" t="e"><v>#N/A</v></c></row>'
                '<row r="2"/></sheetData></worksheet>')
        table = xlsx(stream.getvalue())[0]
        self.assertEqual(values(table, 1), dict(A="County name", B=0, C=None, D="#N/A"))
        self.assertEqual(table["rows"][0]["cells"][1]["formula"],
            dict(text="EXTERNAL_FUNCTION()", attributes=dict(t="normal")))
        self.assertEqual(table["rows"][0]["cells"][1]["cached_literal"], "0")
        self.assertEqual(table["rows"][1], dict(row=2, cells=[]))


if __name__ == "__main__":
    unittest.main()
