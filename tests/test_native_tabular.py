import io
import unittest
import zipfile

from scripts.native_tabular import column, delimited, values, xlsx


class NativeTabularTests(unittest.TestCase):
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
