import csv
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.historical_precinct_rows import compile_rows, encoded, package, pin


class HistoricalRowTests(unittest.TestCase):
    def fixture(self,root):
        rows = []
        for value in ("0","*","","-2","NA"):
            rows.append(dict(year="2016",stage="gen",special="FALSE",state_postal="AL",
                county_fips="1001",jurisdiction="Autauga",                precinct="001",candidate="Pe\u00f1a",
                office="US House",district="2",party="Republican",mode="total",votes=value))
        rows.append(dict(rows[0],stage="pri",mode="election day",votes="4"))
        records = []
        for office in ("house","president","senate","state","local"):
            relative = f"2016-precinct-{office}/2016-precinct-{office}.zip"
            path = root/"source"/relative;path.parent.mkdir(parents=True)
            body = io.StringIO(newline="")
            writer = csv.DictWriter(body,fieldnames=list(rows[0]),lineterminator="\n")
            writer.writeheader();writer.writerows(rows)
            with zipfile.ZipFile(path,"w") as archive:
                archive.writestr(path.stem+".csv",body.getvalue().encode("latin1"))
                archive.writestr("__MACOSX/._"+path.stem+".csv",b"\xbd not a data file")
            records.append(dict(native_path=relative,acquired=True,**pin(path)))
        (root/"acquisition.json").write_bytes(encoded(dict(
            source_commit="5965d5e572dfb9affaf8b295e6ddee94773a6cf8",source_receipts=records)))
        return rows

    def test_literal_zero_suppression_missing_negative_modes_and_stage_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);native=self.fixture(root)
            output = root/"compiled"
            result = compile_rows(root,output)
            self.assertEqual(result["source_candidate_rows"],18)
            with gzip.open(output/"complete-source-row-query.csv.gz","rt",newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["votes"] for row in rows[:6]],[row["votes"] for row in native])
            self.assertEqual([row["vote_count_status"] for row in rows[:5]],
                ["reported","suppressed","unknown","negative_correction","unknown"])
            self.assertEqual(rows[0]["county_fips"],"1001")
            self.assertEqual(rows[0]["precinct"],"001")
            self.assertEqual(rows[0]["candidate"],native[0]["candidate"])
            self.assertEqual(rows[5]["general_non_special"],"false")
            self.assertIn("straight_ticket",rows[0]["analysis_qualification"])
            self.assertFalse(result["ballots_cast_or_group_turnout_derived"])

    def test_cached_query_verifies_all_bytes_without_reparsing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);self.fixture(root)
            compile_rows(root,root/"compiled")
            with patch("scripts.historical_precinct_rows.rows_from_partition",side_effect=AssertionError("reparse")):
                self.assertEqual(compile_rows(root,root/"compiled")["source_parses"],0)
                (root/"compiled/jurisdiction-office-inventory.csv").write_bytes(b"tampered")
                with self.assertRaises(ValueError):
                    compile_rows(root,root/"compiled")

    def test_complete_download_contains_actual_originals_full_query_and_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);self.fixture(root)
            compile_rows(root,root/"compiled")
            destination = root/"complete.zip"
            result = package(root,root/"compiled",destination)
            self.assertTrue(result["complete_originals_and_queries"])
            with zipfile.ZipFile(destination) as archive:
                manifest = json.loads(archive.read("checksums.json"))
                self.assertIn("queries/complete-source-row-query.csv.gz",manifest)
                self.assertEqual(len([name for name in manifest if name.startswith("source/")]),5)
                for name,expected in manifest.items():
                    import hashlib
                    body = archive.read(name)
                    self.assertEqual(expected,dict(bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))
            with self.assertRaises(ValueError):
                package(root,root/"compiled",destination)


if __name__=="__main__":
    unittest.main()
