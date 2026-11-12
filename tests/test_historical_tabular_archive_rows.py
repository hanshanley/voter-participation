import csv
import gzip
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.historical_precinct_rows import pin
from scripts.historical_tabular_archive_rows import build


class NativeTabularTests(unittest.TestCase):
    def fixture(self,root):
        body=b"Date\tCounty\tUnit\tRace\tName\tParty\tTotal\tMail\tFlag\t\n2018\tA\t001\tHouse\tName\tI\t0\t7\tN\t\n"
        with zipfile.ZipFile(root/"source.zip","w") as archive:
            archive.writestr("source.txt",body)
        source=dict(original_path="source.zip",original_pin=pin(root/"source.zip"),
            member="source.txt",encoding="ascii",delimiter="\t",
            expected_header=body.decode().splitlines()[0].split("\t"),year=2018,state_code="NC",
            source_url="https://example.gov/source.zip",measure="native_candidate_or_question_votes",
            required_values={"Date":"2018"},canonical_columns=dict(
                county="County",unit="Unit",office="Race",candidate="Name",party="Party",votes="Total"))
        spec=root/"spec.json";spec.write_text(json.dumps(dict(sources=[source])))
        return spec,source

    def test_native_zero_and_component_modes_and_administrative_flag_are_not_reinterpreted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);spec,_=self.fixture(root)
            self.assertEqual(build(spec,root,root/"out")["source_rows"],1)
            with gzip.open(root/"out/complete-native-row-query.csv.gz","rt") as stream:
                row=next(csv.DictReader(stream))
            self.assertEqual(row["votes"],"0")
            native=json.loads(row["native_fields_json"])
            self.assertEqual(native["values"][-3:],["7","N",""])
            self.assertIn("no_turnout_denominator",row["qualification"])

    def test_wrong_native_election_identity_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);spec,source=self.fixture(root)
            source["required_values"]["Date"]="2020"
            spec.write_text(json.dumps(dict(sources=[source])))
            with self.assertRaises(ValueError):
                build(spec,root,root/"out")

    def test_plain_csv_preserves_the_original_filename_and_full_native_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);spec,source=self.fixture(root)
            with zipfile.ZipFile(root/"source.zip") as archive:
                body=archive.read("source.txt")
            (root/"source.txt").write_bytes(body)
            source.update(container="plain",original_path="source.txt",original_pin=pin(root/"source.txt"))
            del source["member"]
            spec.write_text(json.dumps(dict(sources=[source])))
            build(spec,root,root/"out")
            with gzip.open(root/"out/complete-native-row-query.csv.gz","rt") as stream:
                row=next(csv.DictReader(stream))
            self.assertEqual(row["source_member"],"source.txt")


if __name__=="__main__":
    unittest.main()
