import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts.openelections_history_rows import canonical,decode_source,compile_rows
from scripts.verify_openelections_history_rows import verify


class HistoricalCSVTests(unittest.TestCase):
    def test_blank_duplicate_columns_and_raw_values_are_not_lost(self):
        header=["county","precinct","office","votes","",""]
        values=["A","001","US House","0","","native"]
        result=canonical(header,values)
        self.assertEqual(json.loads(result["native_fields_json"]),dict(columns=header,values=values))
        self.assertEqual(result["votes"],"0")
        self.assertEqual(result["precinct"],"001")
        self.assertEqual(result["vote_count_status"],"reported")

    def test_differing_total_aliases_are_withheld_not_added_and_town_is_not_county(self):
        result=canonical(["town","precinct","office","votes","total_votes"],
            ["Town","1","US House","4","5"])
        self.assertEqual(result["county"],"")
        self.assertEqual(result["votes"],"")
        self.assertEqual(result["vote_count_status"],"unknown")
        self.assertIn("ambiguous_fields_withheld:votes",result["qualification"])

    def test_suppression_and_mode_components_never_replace_native_total(self):
        result=canonical(["county","precinct","office","votes","absentee","election_day"],
            ["A","1","US House","*","2","3"])
        self.assertEqual(result["vote_count_status"],"suppressed")
        self.assertEqual(result["votes"],"*")
        self.assertNotEqual(result["measure"],"native_ballots_cast")

    def test_legacy_bytes_and_utf8_bom_have_explicit_reversible_transport(self):
        body=b"candidate\nPe\xf1a\n"
        text,encoding=decode_source(body)
        self.assertEqual(text.encode("latin1"),body)
        self.assertIn("lossless",encoding)
        text,encoding=decode_source(b"\xef\xbb\xbfcounty,votes\nA,0\n")
        self.assertTrue(text.startswith("county"))
        self.assertEqual(encoding,"utf-8-sig")

    def test_independent_verifier_rejects_changed_canonical_field_with_raw_cells_intact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/"AL/originals/native.csv"
            source.parent.mkdir(parents=True)
            body=b"county,precinct,office,votes\nA,001,US House,0\n"
            source.write_bytes(body)
            product=dict(path="native.csv",year=2018,native_git_blob=hashlib.sha1(
                b"blob "+str(len(body)).encode()+b"\0"+body).hexdigest(),
                acquisition=dict(acquired=True,bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))
            (root/"complete-jurisdiction-query.json").write_text(json.dumps([
                dict(state_code="AL",commit="0"*40,acquired_files=[product])]))
            compile_rows(root,root/"derived")
            self.assertEqual(verify(root)["source_rows"],1)
            query=root/"derived/complete-source-row-query.csv.gz"
            with gzip.open(query,"rb") as stream:
                original=stream.read()
            changed=original.replace(b",A,001,",b",B,001,",1)
            self.assertNotEqual(changed,original)
            with gzip.open(query,"wb") as stream:
                stream.write(changed)
            with self.assertRaises(AssertionError):
                verify(root)


if __name__=="__main__":
    unittest.main()
