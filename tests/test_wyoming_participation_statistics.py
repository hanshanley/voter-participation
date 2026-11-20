import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
import unittest

from scripts.wyoming_participation_statistics import build, parse_profile


def fixture():
    rows = [
        f"{year} 100,000 20,000 20% 15,000 15.0% 30,000 30% 35,000 35.0%"
        for year in range(1978, 2026, 2)]
    return (
        "Wyoming Voter Registration and Voter Turnout Statistics Primary Election General Election\n"
        "2026 100,000 20,000 20% 15,000 15.0%\n" + "\n".join(reversed(rows))
        + "\n* Voting Age Population figures are source estimates.\n"
        "Registered by close of business on the day before the Primary and General Elections; "
        "this number does not include election day registrations.\nRevised: 08/2026\n")


def read(raw):
    return list(csv.DictReader(io.StringIO(raw.decode())))


def test_scheduled_profile_accepts_revision_and_retains_last_good(tmp_path, monkeypatch):
    from scripts import results_intake as intake, results_turnout_history as history

    source = fixture()
    full = source.replace("15.0%\n", "15.0% 29,000 29% 42,000 42.0%\n", 1)
    editions = iter((source, full, full, full.replace("42,000 42.0%", "40,000 40.0%"),
                     source, full.replace("08/2026", "07/2026"), None))
    monkeypatch.setattr(history, "wyoming_profile", lambda body: parse_profile(body.decode()))
    prior = {}

    def collect(day):
        body = next(editions)
        collector = intake.Collector(tmp_path, prior, {"hosts": [], "prefixes": [], "urls": []},
                                     datetime(2026, 11, day, tzinfo=timezone.utc))

        def acquire(url):
            assert url == history.wy_profile.SOURCE_URL
            if body is None:
                raise intake.IntakeError("source_unavailable", "Fixture outage")
            return body.encode(), {"origin": "test"}

        monkeypatch.setattr(collector, "acquire", acquire)
        result = history.collect_wyoming_history(collector)
        prior[history.WY_HISTORY_FEED] = result
        return result

    def general(entry):
        _, csv_body = history.wyoming_history_exports(entry)
        return next(row for row in read(csv_body) if row["year"] == "2026" and row["election_type"] == "general")

    assert history.WY_HISTORY_FEED in intake.late_archive_sources()
    assert general(collect(12))["native_voter_turnout"] == ""
    published = collect(13)
    assert general(published)["native_voter_turnout"] == "42000"
    assert collect(14) == published
    correction = collect(15)
    assert general(correction)["native_voter_turnout"] == "40000"
    assert general(correction)["registered_voter_turnout_rate"] == ""
    for day, stage in ((16, "parsing"), (17, "parsing"), (18, "acquisition")):
        retained = collect(day)
        assert retained["status"] == "retained_after_failure"
        assert retained["error_stage"] == stage
        for field in ("data", "source", "first_observed_at"):
            assert retained[field] == correction[field]


class WyomingParticipationStatisticsTests(unittest.TestCase):
    def test_primary_general_and_unreported_cells_remain_distinct(self):
        rows = parse_profile(fixture())
        general = next(row for row in rows if row["year"] == 2026 and row["election_type"] == "general")
        primary = next(row for row in rows if row["year"] == 2026 and row["election_type"] == "primary")
        self.assertIsNone(general["native_voter_turnout"])
        self.assertIsNone(general["native_day_before_registered"])
        self.assertEqual(primary["native_voter_turnout"], 15000)

    def test_pre_election_register_does_not_create_registered_turnout(self):
        rows = parse_profile(fixture())
        row = next(row for row in rows if row["year"] == 2024 and row["election_type"] == "general")
        self.assertGreater(row["native_voter_turnout"], row["native_day_before_registered"])
        self.assertIsNone(row["registered_voter_turnout_rate"])
        self.assertIsNone(row["election_time_registered"])
        self.assertIsNone(row["eligible_citizen_turnout_rate"])

    def test_source_disagreement_is_preserved_not_repaired(self):
        rows = parse_profile(fixture().replace(
            "2024 100,000 20,000 20%", "2024 100,000 20,000 54%"))
        row = next(row for row in rows if row["year"] == 2024 and row["election_type"] == "primary")
        self.assertEqual(row["native_registered_percent_of_vap"], "54")
        self.assertEqual(Decimal(row["calculated_registration_percent_of_vap"]), 20)
        self.assertEqual(row["registration_percentage_check"], "source_disagreement")

    def test_pdf_decimal_whitespace_does_not_change_native_selection(self):
        self.assertEqual(parse_profile(fixture()), parse_profile(fixture().replace("15.0%", "15. 0%")))

    def test_changed_qualification_or_incomplete_table_is_rejected(self):
        for text in (
            fixture().replace("does not include election day registrations", "includes election day registrations"),
            fixture().replace("2026 100,000 20,000 20% 15,000 15.0%", "2026 100,000 20,000"),
            fixture().replace("1980 100,000", "1982 100,000"),
        ):
            with self.subTest(text=text[:60]), self.assertRaises(ValueError):
                parse_profile(text)

    def test_primary_not_joined_to_general_and_source_equality_not_independence(self):
        files, _ = build(parse_profile(fixture()), [
            dict(year="2022", state_code="WY", reported_cast_ballots="35000", control_id="primary-source",
                 native_registered="", source_time_label="native-clock")])
        comparisons = read(files["complete-selected-control-comparison.csv"])
        primary = next(row for row in comparisons if row["year"] == "2022" and row["election_type"] == "primary")
        general = next(row for row in comparisons if row["year"] == "2022" and row["election_type"] == "general")
        self.assertEqual(primary["selected_reported_cast_ballots"], "")
        self.assertEqual(general["disposition"], "equal_counts_separate_source_meanings_not_independent_validation")
        self.assertEqual(general["independent_outcome_validation"], "False")
        self.assertEqual(general["selected_control_registered"], "")
        self.assertEqual(general["selected_source_time"], "native-clock")

    def test_missing_endpoint_never_becomes_zero_or_individual_change(self):
        files, _ = build(parse_profile(fixture()), [])
        row = next(row for row in read(files["complete-same-election-type-changes.csv"])
                   if row["to_year"] == "2026" and row["election_type"] == "general")
        self.assertEqual(row["native_turnout_count_change"], "")
        self.assertEqual(row["voting_age_population_rate_change_pp"], "")
        self.assertEqual(row["disposition"], "missing_native_endpoint")
        self.assertEqual(row["individual_retention_or_switching_inferred"], "False")


if __name__ == "__main__":
    unittest.main()
