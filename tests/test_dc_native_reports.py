import copy
import json
from pathlib import Path
import unittest
import zipfile

from scripts.dc_native_reports import native_tables


class DCNativeReportsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/dc-native-reports/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-dc-native-factual-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.primary = json.loads(archive.read("primary-grids.json"))
            cls.independent = json.loads(archive.read("independent-grids.json"))
            cls.scope = json.loads(archive.read("source-scope.json"))
        cls.result = native_tables(cls.primary, cls.independent, cls.scope)

    def changed(self):
        return copy.deepcopy(self.primary), copy.deepcopy(self.independent)

    def test_dropbox_printed_total_zero_does_not_fill_blank_ward_counts(self):
        rows = [row for row in self.result[2] if row["report_id"] == "DC-dropbox"
                and row["native_period_label"] == "November 3, 2026"]
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[-1]["native_count"], 0)
        self.assertTrue(all(row["native_count"] is None for row in rows[:-1]))
        equation = next(row for row in self.result[3] if row["report_id"] == "DC-dropbox"
                        and row["identity"] == "source-row23")
        self.assertFalse(equation["complete"])
        self.assertIsNone(equation["difference"])

    def test_merged_detention_cells_do_not_shift_day_columns(self):
        rows = {row["native_period_label"]: row for row in self.result[2]
                if row["report_id"] == "DC-early" and row["native_geography_label"] == "CENTRAL DETENTION FACILITY"}
        self.assertIsNone(rows["26-Oct"]["native_count"])
        self.assertEqual(rows["27-Oct"]["native_count"], 61)
        self.assertEqual(rows["29-Oct"]["native_count"], 99)
        self.assertEqual(rows["TOTAL"]["native_count"], 261)

    def test_unknown_usps_dates_remain_distinct_from_printed_zeros(self):
        rows = {row["native_period_label"]: row for row in self.result[2] if row["report_id"] == "DC-usps"}
        self.assertIsNone(rows["November 13, 2026"]["native_count"])
        self.assertEqual(rows["November 4, 2026"]["native_count"], 0)
        equation = next(row for row in self.result[3] if row["report_id"] == "DC-usps")
        self.assertEqual(equation["missing_components"], 7)
        self.assertFalse(equation["complete"])
        self.assertIsNone(equation["difference"])

    def test_registration_does_not_create_an_absent_dc_survey_sample(self):
        scope = dict(self.scope, dc_has_no_civic_sample_no_pooled_state_projection=False)
        with self.assertRaisesRegex(ValueError, "model absence"):
            native_tables(self.primary, self.independent, scope)

    def test_received_mail_is_not_silently_promoted_to_cast_ballots(self):
        scope = dict(self.scope, mail_received_is_accepted_or_cast_ballot_qualified=True)
        with self.assertRaisesRegex(ValueError, "receipt"):
            native_tables(self.primary, self.independent, scope)

    def test_location_wards_are_not_promoted_to_voter_residence(self):
        scope = dict(self.scope, vote_center_ward_is_voter_residence_qualified=True)
        with self.assertRaisesRegex(ValueError, "location-versus-residence"):
            native_tables(self.primary, self.independent, scope)

    def test_independent_source_reader_disagreement_is_rejected(self):
        independent = copy.deepcopy(self.independent)
        independent["reports"][0]["pages"][0]["tables"][0]["rows"][2][3] = "1"
        with self.assertRaisesRegex(ValueError, "readers disagree"):
            native_tables(self.primary, independent, self.scope)

    def test_missing_explicit_election_day_parent_is_not_replaced_by_ward_sum(self):
        primary, independent = self.changed()
        for view in (primary, independent):
            view["reports"][2]["pages"][0]["external"]["native_election_day_parent"] = None
        with self.assertRaisesRegex(ValueError, "Missing explicit native Election Day parent"):
            native_tables(primary, independent, self.scope)

    def test_missing_registration_component_stays_unknown_without_column_shift(self):
        primary, independent = self.changed()
        for view in (primary, independent):
            view["reports"][0]["pages"][0]["tables"][0]["rows"][2][3] = None
        _, registrations, _, equations, _ = native_tables(primary, independent, self.scope)
        first = registrations[0]
        self.assertIsNone(first["DEM"])
        self.assertEqual(first["REP"], 1850)
        self.assertEqual(first["TOTALS"], 54691)
        equation = next(row for row in equations if row["identity"] == "page1-row3-party-accounting")
        self.assertFalse(equation["complete"])

    def test_missing_explicit_registration_parent_is_not_replaced_by_ward_sum(self):
        primary, independent = self.changed()
        for view in (primary, independent):
            view["reports"][0]["pages"][0]["tables"][0]["rows"][10][18] = None
        with self.assertRaisesRegex(ValueError, "Missing explicit citywide parent"):
            native_tables(primary, independent, self.scope)

    def test_native_ward_headers_not_page_ordinals_define_geography(self):
        primary, independent = self.changed()
        for view in (primary, independent):
            pages = view["reports"][0]["pages"]
            pages[1]["page"], pages[2]["page"] = pages[2]["page"], pages[1]["page"]
        registrations = native_tables(primary, independent, self.scope)[1]
        precinct = next(row for row in registrations if row["geographic_level"] == "precinct"
                        and row["native_geography_label"] == "20")
        self.assertEqual(precinct["native_ward_label"], "1")

    def test_missing_printed_ward_header_is_not_inferred_from_page_number(self):
        primary, independent = self.changed()
        for view in (primary, independent):
            view["reports"][0]["pages"][1]["external"]["native_registration_ward"] = None
        with self.assertRaisesRegex(ValueError, "explicit native registration ward headers"):
            native_tables(primary, independent, self.scope)


if __name__ == "__main__":
    unittest.main()
