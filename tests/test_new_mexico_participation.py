import copy
from pathlib import Path
import unittest

from openpyxl import load_workbook

from scripts.new_mexico_participation import turnout


class NewMexicoParticipationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixtures = root / "data/new-mexico-participation/20261108-01"
        if not fixtures.exists():
            fixtures = root / "inputs"
        workbook = load_workbook(fixtures / "official-native-turnout-export.xlsx", read_only=True, data_only=True)
        cls.sheets = {sheet.title: [list(row) for row in sheet.values] for sheet in workbook}
        workbook.close()

    def test_native_zero_percentage_is_not_an_analytic_rate(self):
        _, _, precincts, _ = turnout(self.sheets)
        zero = next(row for row in precincts if row["native_registered_voters"] == 0)
        self.assertEqual(zero["native_printed_turnout"], "0.00%")
        self.assertIsNone(zero["source_defined_participation_pct"])
        self.assertFalse(zero["map_approved"])

    def test_candidate_header_cannot_be_substituted(self):
        sheets = copy.deepcopy(self.sheets)
        sheets["Voter Turnout"][6][2] = "Candidate Votes"
        with self.assertRaisesRegex(ValueError, "population or numerator"):
            turnout(sheets)

    def test_duplicate_precinct_is_not_summed(self):
        sheets = copy.deepcopy(self.sheets)
        sheets["Bernalillo"][8][0] = sheets["Bernalillo"][7][0]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            turnout(sheets)

    def test_county_source_total_is_not_repaired(self):
        sheets = copy.deepcopy(self.sheets)
        row = sheets["Voter Turnout"][7]
        row[1] += 1
        from decimal import Decimal, ROUND_HALF_UP
        row[3] = str((100 * Decimal(row[2]) / row[1]).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)) + "%"
        with self.assertRaisesRegex(ValueError, "precinct sums"):
            turnout(sheets)

    def test_different_download_snapshots_are_not_joined(self):
        sheets = copy.deepcopy(self.sheets)
        sheets["Bernalillo"][3][0] = "Downloaded at a different source snapshot"
        with self.assertRaisesRegex(ValueError, "Different native election snapshots"):
            turnout(sheets)

    def test_partial_reporting_does_not_become_complete(self):
        sheets = copy.deepcopy(self.sheets)
        for rows in sheets.values():
            rows[2][0] = "Precincts 2203 of 2204 Reporting (Precincts Partially Reported: 1/2204)"
        with self.assertRaisesRegex(ValueError, "reporting coverage"):
            turnout(sheets)


if __name__ == "__main__":
    unittest.main()
