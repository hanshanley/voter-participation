from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from review_jefferson_wi_participation import parse


class NativeTests(unittest.TestCase):
    def fixture(self):
        return b"""Jefferson County WI Official Results Fall General Election
        Number of votes reflect Jefferson County only AS OF 11-06-2026 01:13 pm
        REGISTERED VOTERS TOTAL 20 BALLOTS CAST TOTAL 9 Precincts Reporting 2 of 2 for 100%
        <table><tr><th></th><th>Registered Voters</th><th>Ballots Cast</th><th>Ballots Cast %</th></tr>
        <tr><td>Town W1,3</td><td>20</td><td>9</td><td>45%</td></tr>
        <tr><td>Village W12</td><td>0</td><td>0</td><td>0%</td></tr></table>"""

    def test_native_zeros_and_grouped_wards_remain_literal(self):
        result = parse(self.fixture())
        self.assertEqual(result["reporting_units"][0]["reporting_unit"], "Town W1,3")
        self.assertTrue(result["reporting_units"][1]["zero_denominator"])
        self.assertEqual(result["zero_count_units"], 1)
        self.assertIsNone(result["native_fips"])
        self.assertFalse(result["certification_verified"])
        self.assertFalse(result["precinct_geometry_approved"])

    def test_changed_totals_missing_rows_and_wrong_county_fail(self):
        for before, after in ((b"CAST TOTAL 9", b"CAST TOTAL 10"), (b"<td>9</td>", b"<td></td>"),
                              (b"Jefferson County WI", b"Jefferson County PA"),
                              (b"<td>45%</td>", b"<td>50%</td>")):
            with self.assertRaises(ValueError):
                parse(self.fixture().replace(before, after))


if __name__ == "__main__":
    unittest.main()
