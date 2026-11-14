import csv
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.historical_native_counts import compile_dataset, file_pin, native_count, project
from scripts.participation_intake.contract import encoded


def official():
    return {
        "year": "2018", "state_code": "AL", "county_literal": "Autauga",
        "unit_literal": "Example precinct", "unit_kind": "native_precinct_label_unjoined",
        "office_literal": "BALLOTS CAST - TOTAL ", "candidate_literal": "Ballots Cast - Total ",
        "measure": "ballots_cast", "count_literal": "0", "count_status": "reported",
        "source_sha256": "a" * 64, "source_member": "2018-General-Autauga.xls",
        "source_table": "Precinct Results", "source_row": "3", "source_column": "4",
        "source_fields_json": json.dumps({"contest": "BALLOTS CAST - TOTAL ",
                                         "value": 0.0, "unit": "Example precinct"}),
        "qualification": "registration_zeros_not_denominators;no_geometry",
    }


def official_sources():
    return {"a" * 64: {"year": 2018, "state_code": "AL",
                      "url": "https://example.org/2018-Official-General-Precinct-Results.zip"}}


def oe():
    return {
        "year": "2020", "state_code": "AR", "source_commit": "b" * 40,
        "source_file": "2020/counties/20201103__ar__general__example__precinct.csv",
        "source_row": "2", "county": "Example", "precinct": "Auburn",
        "office": "BALLOTS CAST", "candidate": "BALLOTS CAST - STYLE 00001",
        "votes": "17", "vote_count_status": "reported", "measure": "native_ballots_cast",
        "native_fields_json": json.dumps({
            "columns": ["county", "precinct", "office", "candidate", "votes", "mail"],
            "values": ["Example", "Auburn", "BALLOTS CAST", "BALLOTS CAST - STYLE 00001", "17", "5"],
        }),
        "qualification": "native_modes_not_added_to_totals;alternatives_not_merged",
    }


def oe_sources(row):
    return {(row["state_code"], int(row["year"]), row["source_commit"], row["source_file"]):
            {"source": {"sha256": "c" * 64}}}


class HistoricalNativeCountsTests(unittest.TestCase):
    def test_exact_zero_unknown_and_noninteger_remain_distinct(self):
        self.assertEqual(native_count("0", "reported")["value"], 0)
        self.assertEqual(native_count("1,234.0", "reported")["value"], 1234)
        self.assertEqual(native_count("", "unknown")["status"], "unknown")
        held = native_count("12.5", "noninteger_native_literal")
        self.assertEqual(held["literal"], "12.5")
        self.assertEqual(held["status"], "withheld")
        self.assertIsNone(held["value"])
        for value in ("-1", "12.5", "1,23", "NaN", str(2**53)):
            with self.assertRaises((ValueError, TypeError)):
                native_count(value, "reported")

    def test_official_ballot_cell_is_not_a_rate_or_geography_join(self):
        row = project(official(), "official-state", official_sources())
        self.assertEqual(row["count"]["value"], 0)
        self.assertEqual(row["source"]["selector"]["source_column"], "4")
        self.assertEqual(row["source"]["native_fields"]["value"], 0.0)
        self.assertIsNone(row["rate"])
        self.assertIsNone(row["denominator"])
        self.assertEqual(row["geography_join"], "unreviewed")
        self.assertFalse(row["cross_year_identity_approved"])

    def test_native_style_modes_and_alternative_files_are_not_summed_or_merged(self):
        original = oe()
        first = project(original, "openelections-supplements", oe_sources(original))
        second = project(original, "openelections-statewide", oe_sources(original))
        self.assertNotEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["native_category"], "BALLOTS CAST - STYLE 00001")
        self.assertEqual(first["count"]["value"], 17)
        self.assertEqual(first["source"]["native_fields"]["values"][-1], "5")

    def test_candidate_rows_are_excluded_and_forged_administrative_labels_rejected(self):
        candidate = oe()
        candidate["measure"] = "native_candidate_or_question_votes"
        self.assertIsNone(project(candidate, "openelections-statewide", {}))
        forged = oe()
        fields = json.loads(forged["native_fields_json"])
        fields["values"][2] = "President"
        forged["native_fields_json"] = json.dumps(fields)
        with self.assertRaisesRegex(ValueError, "Candidate"):
            project(forged, "openelections-statewide", oe_sources(forged))

    def test_primary_wrong_year_and_non_general_workbooks_are_rejected(self):
        for name in ("20200519__ar__primary.csv", "20181106__ar__general.csv"):
            row = oe()
            row["source_file"] = name
            with self.assertRaisesRegex(ValueError, "historical source"):
                project(row, "openelections-statewide", {})
        row = official()
        row["source_member"] = "2018-Primary-Autauga.xls"
        with self.assertRaisesRegex(ValueError, "general-election"):
            project(row, "official-state", official_sources())

    def test_native_value_or_election_changes_are_not_silently_repaired(self):
        row = official()
        row["count_literal"] = "1"
        with self.assertRaisesRegex(ValueError, "disagree"):
            project(row, "official-state", official_sources())
        source = official_sources()
        source["a" * 64]["year"] = 2020
        with self.assertRaisesRegex(ValueError, "election differs"):
            project(official(), "official-state", source)

    def test_duplicate_native_count_columns_are_not_qualified(self):
        row = oe()
        fields = json.loads(row["native_fields_json"])
        fields["columns"].append("total_votes")
        fields["values"].append("17")
        row["native_fields_json"] = json.dumps(fields)
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            project(row, "openelections-statewide", oe_sources(row))

    def test_projection_is_deterministic_and_keeps_all_state_decisions_and_stock_cells(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ballot = official()
            registration = dict(ballot, measure="registration_stock", source_row="2",
                                office_literal="REGISTERED VOTERS - TOTAL",
                                source_fields_json=json.dumps({"contest": "REGISTERED VOTERS - TOTAL",
                                                              "value": 0.0}))
            text = io.StringIO(newline="")
            writer = csv.DictWriter(text, fieldnames=list(ballot), lineterminator="\n")
            writer.writeheader()
            writer.writerows([ballot, registration])
            component = root / "official.zip"
            with zipfile.ZipFile(component, "w") as archive:
                archive.writestr("queries/complete-source-cell-query.csv.gz",
                                 gzip.compress(text.getvalue().encode(), mtime=0))
                archive.writestr("originals/product-provenance.json", json.dumps([{
                    **official_sources()["a" * 64],
                    "acquisition": {"acquired": True, "sha256": "a" * 64},
                }]))
            spec = root / "inputs.json"
            spec.write_bytes(encoded({"inputs": [{"collection": "official-state",
                                                 "file": "official.zip", **file_pin(component)}]}))
            first = compile_dataset(spec, root / "first")
            second = compile_dataset(spec, root / "second")
            self.assertEqual(first, second)
            self.assertEqual(first["records"], 2)
            self.assertEqual(first["decisions"], 102)
            for path in (root / "first").rglob("*"):
                if path.is_file():
                    self.assertEqual(path.read_bytes(), (root / "second" / path.relative_to(root / "first")).read_bytes())
            data = json.loads(gzip.decompress((root / "first/states/AL.json.gz").read_bytes()))
            self.assertEqual({row["measure"] for row in data["records"]},
                             {"ballots_cast", "registration_stock"})
            self.assertTrue(all(row["rate"] is None for row in data["records"]))
            index = json.loads((root / "first/index.json").read_bytes())
            self.assertEqual(len(index["jurisdictions"]), 51)
            self.assertEqual(index["years"], [2018, 2020])
            self.assertTrue(index["outside_projection_years_are_not_classified_as_missing"])


if __name__ == "__main__":
    unittest.main()
