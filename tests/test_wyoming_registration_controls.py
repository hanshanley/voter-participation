import csv
from fractions import Fraction
import io
import unittest

from scripts.wyoming_registration_controls import COUNTIES, PARTIES, build, conditional, parse_page


def page(date="11/3/2026", label="General Election Day"):
    return (
        f"State of Wyoming {date}\nCounty " + " ".join(PARTIES) + " TOTAL\n"
        + "\n".join(f"{county} 1 2 3 4 5 0 15" for county in COUNTIES)
        + "\nTOTAL 23 46 69 92 115 0 345\n* Other includes former parties.\n"
        + "Statewide Summary Wyoming Voter Registration " + label)


def survey():
    return dict(year=2026, study="Civic", scope="WY", dimension="overall", group="all",
                n=781, weight_field="source_weight", weight="100", modeled_voter_weight="60",
                modeled_nonvoter_weight="30", model_unknown_weight="10")


def fixture():
    rows, accounting = [], []
    for date in ("11/8/2022", "11/3/2026"):
        parsed, sums = parse_page(page(date), "native-source", 1)
        rows.extend(parsed)
        accounting.extend(sums)
    controls = [dict(year=year, state_code="WY", reported_cast_ballots="200",
                     source_time_label="native-ballot-clock", source_url="native-ballot-source")
                for year in (2022, 2026)]
    profile = [dict(year=year, election_type="general", native_day_before_registered=value)
               for year, value in ((2022, "345"), (2026, ""))]
    civic = dict(participation=[survey()])
    return rows, accounting, controls, profile, dict(selected_rows=[]), civic


def read(raw):
    return list(csv.DictReader(io.StringIO(raw.decode())))


class WyomingRegistrationControlsTests(unittest.TestCase):
    def test_native_parent_children_and_literal_other_are_not_double_counted(self):
        rows, sums = parse_page(page(), "native-source", 1)
        self.assertEqual(next(row for row in rows if row["native_unit"] == "TOTAL")["native_registration_total"], 345)
        self.assertEqual(len([row for row in rows if row["geographic_level"] == "county"]), 23)
        self.assertTrue(all(row["difference"] == 0 for row in sums))
        self.assertIn("Other*", rows[0])
        self.assertIsNone(rows[0]["election_time_registered"])

    def test_monthly_primary_and_general_labels_stay_distinct(self):
        for label, expected in (("", "monthly_snapshot"), ("Primary Election Day", "primary_election_day_label"),
                                ("General Election Day", "general_election_day_label")):
            self.assertEqual(parse_page(page(label=label), "source", 1)[0][0]["snapshot_kind"], expected)

    def test_missing_duplicate_or_malformed_county_is_not_zero_filled(self):
        for text in (page().replace("ALBANY 1 2 3 4 5 0 15", ""),
                     page().replace("ALBANY", "BIG HORN"),
                     page().replace("ALBANY 1 2", "ALBANY -1 2")):
            with self.assertRaises(ValueError):
                parse_page(text, "source", 1)

    def test_source_disagreement_retained_and_conditional_is_held(self):
        args = list(fixture())
        rows, sums = parse_page(page().replace("ALBANY 1 2 3 4 5 0 15", "ALBANY 1 2 3 4 5 0 16"),
                                "native-source", 1)
        args[0] = [row for row in args[0] if row["year"] != 2026] + rows
        args[1] = [row for row in args[1] if row["snapshot_date"] != "2026-11-03"] + sums
        files, _ = build(*args)
        held = next(row for row in read(files["complete-survey-dispositions.csv"]) if row["year"] == "2026")
        self.assertEqual(held["disposition"], "native_registration_accounting_hold")
        self.assertEqual(rows[0]["native_party_sum_difference"], -1)
        self.assertIn(b"conditional_model_unknown_count", files["complete-source-weighted-conditional-scenarios.csv"])
        self.assertEqual(read(files["complete-source-weighted-conditional-scenarios.csv"]), [])

    def test_full_unknown_mass_reconciles_without_staying_home_or_allocation(self):
        snapshot = next(row for row in fixture()[0] if row["year"] == 2026 and row["native_unit"] == "TOTAL")
        row = conditional(snapshot, survey(), fixture()[2][0])
        self.assertEqual(Fraction(row["conditional_model_unknown_count"]), Fraction(345, 10))
        self.assertEqual(sum(Fraction(row[key]) for key in (
            "conditional_modeled_voter_count", "conditional_modeled_nonvoter_count",
            "conditional_model_unknown_count")), 345)
        self.assertFalse(row["administrative_staying_home_observed"])
        self.assertFalse(row["county_or_precinct_allocation"])

    def test_ap_weight_frames_preserved_and_primary_not_used_for_general(self):
        args = list(fixture())
        args[4] = dict(selected_rows=[
            dict(survey(), year=2022, weight_field=field)
            for field in ("FINALVOTE_STATE_WEIGHT", "POLLCLOSE_STATE_WEIGHT")])
        files, _ = build(*args)
        rows = read(files["complete-source-weighted-conditional-scenarios.csv"])
        self.assertEqual({row["weight_field"] for row in rows},
                         {"source_weight", "FINALVOTE_STATE_WEIGHT", "POLLCLOSE_STATE_WEIGHT"})
        self.assertTrue(all(row["election_time_registered"] == "" for row in rows))
        args[0] = [dict(row, snapshot_kind="primary_election_day_label") for row in args[0]]
        with self.assertRaisesRegex(ValueError, "Missing declared general"):
            build(*args)

    def test_other_state_demographic_and_low_support_are_held(self):
        args = list(fixture())
        args[5] = dict(participation=[dict(survey(), scope="HI"), dict(survey(), dimension="age"),
                                     dict(survey(), n=499), survey()])
        files, _ = build(*args)
        rows = read(files["complete-survey-dispositions.csv"])
        self.assertEqual([row["disposition"] for row in rows[:3]],
                         ["not_matching_whole_state_overall", "not_matching_whole_state_overall",
                          "whole_state_support_hold"])
        self.assertEqual(len(read(files["complete-source-weighted-conditional-scenarios.csv"])), 1)


if __name__ == "__main__":
    unittest.main()
