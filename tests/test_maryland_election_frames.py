import copy
import json
from pathlib import Path
import unittest
import zipfile

from scripts.extract_maryland_election_frames import read_cards, read_workbook
from scripts.maryland_election_frames import queries


class MarylandElectionFramesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/maryland-election-frames/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-maryland-election-native-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.grids = {s: read_workbook(archive.read("general-eligible-" + s.lower() + ".xlsx"), s)
                         for s in ("ACTIVE", "INACTIVE")}
            cls.cards = read_cards(archive.read("general-election-night-turnout.pdf"))
            cls.scope = json.loads(archive.read("source-scope.json"))
            cls.independent_grids = json.loads(archive.read("independent-workbook-grids.json"))
            cls.independent_cards = json.loads(archive.read("independent-card-grid.json"))

    def result(self, grids=None, cards=None, scope=None):
        return queries(grids or self.grids, cards or self.cards, scope or self.scope)

    def test_native_parsers_agree_with_independent_grids(self):
        self.assertEqual(self.grids, self.independent_grids)
        self.assertEqual(self.cards, self.independent_cards)
        stocks, refs, accounting = self.result()
        self.assertEqual((len(stocks), len(refs), len(accounting)), (350, 25, 66))
        self.assertTrue(all(r["derived_minus_printed"] == 0 for r in accounting))

    def test_missing_register_is_not_zero(self):
        grids = copy.deepcopy(self.grids)
        grids["ACTIVE"]["rows"][0]["counts"]["DEM"] = None
        with self.assertRaisesRegex(ValueError, "never impute zero"):
            self.result(grids=grids)

    def test_native_zero_is_kept(self):
        stocks = self.result()[0]
        kent = next(r for r in stocks if r["status"] == "INACTIVE" and
                    r["native_county_label"] == "Kent" and r["native_party_label"] == "WCP")
        self.assertEqual(kent["native_count"], 0)
        self.assertEqual(kent["source_register_share_pct"], "0")

    def test_duplicate_county_is_not_complete_coverage(self):
        grids = copy.deepcopy(self.grids)
        grids["ACTIVE"]["rows"][0]["native_county_label"] = "Kent"
        with self.assertRaisesRegex(ValueError, "duplicate county"):
            self.result(grids=grids)

    def test_negative_or_fractional_native_counts_are_rejected(self):
        for value in (-1, 1.5, True):
            grids = copy.deepcopy(self.grids)
            grids["INACTIVE"]["rows"][0]["counts"]["DEM"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "invalid native count"):
                self.result(grids=grids)

    def test_source_discrepancy_is_retained_not_repaired(self):
        grids = copy.deepcopy(self.grids)
        grids["ACTIVE"]["rows"][-1]["counts"]["TOTAL"] += 1
        refs, accounting = self.result(grids=grids)[1:]
        self.assertEqual(refs[-1]["eligible_minus_active"], -1)
        self.assertTrue(any(r["derived_minus_printed"] != 0 for r in accounting))

    def test_rounding_disagreement_is_preserved(self):
        cards = copy.deepcopy(self.cards)
        cards["rows"][0]["native_percentage"] = "50.00%"
        ref = self.result(cards=cards)[1][0]
        self.assertEqual(ref["native_percentage"], "50.00%")
        self.assertFalse(ref["two_decimal_rounding_compatible"])

    def test_partial_reporting_does_not_certify_final_turnout(self):
        cards = copy.deepcopy(self.cards)
        cards["rows"][0]["reported_source_units"] = 29
        ref = self.result(cards=cards)[1][0]
        self.assertEqual(ref["reported_source_units"], 29)
        self.assertFalse(ref["final_turnout_certified"])
        self.assertTrue(ref["source_reporting_units_not_precinct_records"])

    def test_source_clock_is_not_collection_clock_or_assumed_timezone(self):
        scope = dict(self.scope, card_report_timezone="America/New_York")
        with self.assertRaisesRegex(ValueError, "unknown timezone"):
            self.result(scope=scope)
        scope = dict(self.scope, card_report_native_run_date="11/9/2026")
        with self.assertRaisesRegex(ValueError, "never substitute retrieval time"):
            self.result(scope=scope)

    def test_no_model_transport_or_unique_voter_certification(self):
        for field, value in (("registry_frame_transport_validated", True),
                             ("cards_not_certified_unique_voters", False),
                             ("registration_party_counts_not_participation_by_party", False),
                             ("active_and_inactive_kept_separate", False)):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "separate"):
                self.result(scope=dict(self.scope, **{field: value}))

    def test_unmatched_county_is_not_guessed(self):
        cards = copy.deepcopy(self.cards)
        cards["rows"][0]["native_county_label"] = "Unknown County"
        with self.assertRaisesRegex(ValueError, "never guess"):
            self.result(cards=cards)

    def test_exact_baltimore_county_and_city_labels_are_distinct(self):
        refs = {r["native_county_label"]: r for r in self.result()[1]}
        self.assertEqual(refs["Baltimore County"]["native_register_county_label"], "Baltimore County")
        self.assertEqual(refs["Baltimore City"]["native_register_county_label"], "Baltimore City")
        self.assertNotEqual(refs["Baltimore City"]["register_active_reference"],
                            refs["Baltimore County"]["register_active_reference"])

    def test_card_source_party_and_status_are_not_inferred(self):
        for ref in self.result()[1]:
            self.assertFalse(ref["unique_voters_certified"])
            self.assertFalse(ref["registration_status_of_cards_known"])
            self.assertFalse(ref["registration_party_participation_available"])
            self.assertFalse(ref["model_allocated"])

    def test_mib2_title_survives_election_night_filename(self):
        self.assertIn("MIB2", self.cards["title"])
        self.assertEqual(self.result()[1][-1]["native_run_date"], "11/8/2026")


if __name__ == "__main__":
    unittest.main()
