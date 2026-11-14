import unittest

from scripts.compile_jefferson_native import (
    HEADER, PREFIX, integer, joined_sovc_statistics, joined_statistics, report_clock,
    sovc_statistics, statistics,
)


def block(values=("10", "7", "1", "0", "2", "0"), blank=None, unit="V120 MID"):
    lines = [*PREFIX]
    if unit is not None:
        lines.append(unit)
    lines.extend(["Statistics", *HEADER, "Ballots Cast - Total", *values])
    if blank is not None:
        lines.extend(["Ballots Cast - Blank", *blank])
    return "\n".join(lines)


class NativeStatisticsTests(unittest.TestCase):
    def test_native_suffix_and_mode_zeros_are_preserved(self):
        parsed = statistics(block(blank=("0",) * 6), True)
        self.assertEqual(parsed["native_unit"], "V120 MID")
        self.assertEqual(parsed["measures"]["Ballots Cast - Total"]["Provisional"]["value"], 0)
        self.assertEqual(parsed["measures"]["Ballots Cast - Total"]["Walk-in Excuse"]["literal"], "0")

    def test_missing_blank_measure_is_unknown_not_zero(self):
        parsed = statistics(block(unit=None), False)
        self.assertIsNone(parsed["measures"]["Ballots Cast - Blank"])

    def test_candidate_votes_are_not_used_as_ballots(self):
        text = block().replace("Ballots Cast - Total", "Total Votes Cast")
        with self.assertRaisesRegex(ValueError, "Missing native Ballots"):
            statistics(text, True)

    def test_election_and_column_changes_are_rejected(self):
        for text in (block().replace("2026 General Election", "2026 Primary Election"),
                     block().replace("Walk-in\nEarly", "Returned\nMail")):
            with self.assertRaises(ValueError):
                statistics(text, True)

    def test_mode_residual_or_excess_blank_is_not_repaired(self):
        for text in (block(values=("11", "7", "1", "0", "2", "0")),
                     block(blank=("11", "8", "1", "0", "2", "0"))):
            with self.assertRaises(ValueError):
                statistics(text, True)

    def test_strict_native_integer_format(self):
        self.assertEqual(integer("268,257"), 268257)
        for value in ("26,8257", "1.5", "-", "", "0,001", "1e3"):
            with self.assertRaises(ValueError):
                integer(value)

    def test_sovc_preserves_unit_suffix_and_stops_at_separate_parent(self):
        text = ("STATIST\nICS\nBallots Cast -\nTotal\nV120 MID\n565\nV123\n2\nTotals\n567\n"
                "Straight Party\n123\n")
        self.assertEqual([(row["native_unit"], row["value"]) for row in sovc_statistics(text)],
                         [("V120 MID", 565), ("V123", 2), ("Totals", 567)])

    def test_printed_clock_keeps_unknown_zone_and_checks_native_page(self):
        text = "Precinct Summary - 11/06/2026     9:52 AM\n4,773 of 4,773\n"
        result = report_clock(text, "Precinct Summary", 4773, 4773)
        self.assertIsNone(result["timezone"])
        self.assertEqual(result["literal"], "11/06/2026     9:52 AM")
        with self.assertRaises(ValueError):
            report_clock(text, "Precinct Summary", 4772, 4773)

    def test_independent_joined_reader_preserves_native_columns_and_suffix(self):
        text = ("\n".join(PREFIX) + "\nV120 MID\nStatistics TOTAL Election\nDay\nMail Walk-in\n"
                "Excuse\nWalk-in\nEarly\nProvision\nal\nBallots Cast - Total 10 7 1 0 2 0\n"
                "Ballots Cast - Blank 0 0 0 0 0 0\n")
        parsed = joined_statistics(text, True)
        self.assertEqual(parsed["native_unit"], "V120 MID")
        self.assertEqual(parsed["measures"]["Ballots Cast - Total"]["Mail"]["value"], 1)
        self.assertEqual(parsed["text_reader"], "pypdf")
        with self.assertRaises(ValueError):
            joined_statistics(text.replace("10 7 1 0 2 0", "10 7 1 0 2"), True)

    def test_joined_sovc_and_clock_are_not_split_into_new_geographies(self):
        text = ("STATIST\nICS\nBallots Cast -\nTotal\nV120 MID 565\nV123 2\nTotals 567\n"
                "Straight Party 99\n")
        self.assertEqual([row["native_unit"] for row in joined_sovc_statistics(text)],
                         ["V120 MID", "V123", "Totals"])
        clock = report_clock("Custom Table Report - 11/05/2026 02:44PM Page 21 of 539\n",
                             "Custom Table Report", 21, 539)
        self.assertEqual(clock["literal"], "11/05/2026 02:44PM")


if __name__ == "__main__":
    unittest.main()
