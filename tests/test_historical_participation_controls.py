import csv
from decimal import Decimal
import io
import unittest

from scripts.historical_participation_controls import ANCHORS, DATES, STATES, build, hawaii, wyoming, wyoming_statewide


def hi_source(year=2022):
    modes = ["Mail", "In-Person"] if year >= 2022 else ["Absentee Mail", "Absentee Walk-in", "Election"]
    header = ["Contest Title", "Candidate ID", "Registered Voters", "Total Precincts", "Counted Precincts"]
    header += [m + " " + category + " Votes" for m in modes for category in ("Blank", "Over", "Invalid")]
    header += [m + " Votes" for m in modes] + ["Total Votes"]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    if year >= 2022:
        writer.writerow(["Format#1"])
    writer.writerow(header)
    for cid in ("1", "2"):
        row = dict(zip(header, ["0"]*len(header)))
        row.update({"Contest Title": ANCHORS[year], "Candidate ID": cid, "Registered Voters": "1000",
                    "Total Precincts": "2", "Counted Precincts": "0" if year == 2022 else "2"})
        for mode in modes:
            row[mode + " Votes"] = "100"
            row[mode + " Blank Votes"] = "100"
        row["Total Votes"] = str(100*len(modes))
        writer.writerow([row[field] for field in header] + ([""] if year >= 2022 else []))
    encoding = "utf-16" if year == 2024 else "utf-16-le" if year == 2022 else "utf-8-sig"
    layout = dict(encoding=encoding, delimiter=",", source_format_metadata="Format#1" if year >= 2022 else None,
                  native_header=header, data_trailing_empty_field_absent_from_header=year >= 2022)
    ballots = 300*len(modes)
    pdf = (f"GENERAL ELECTION {year}\n{DATES[year]}\nFINAL REPORT\n"
           "Printed on: 11/22/2022 at 12:39:46 pm\n"
           f"TOTAL REGISTRATION 1,000\nTOTAL TURNOUT {ballots}\n"
           f"MAIL TURNOUT {ballots-300}\nIN-PERSON TURNOUT 300\n")
    return stream.getvalue().encode(encoding), layout, pdf


def historical(year=2022):
    return hawaii(year, *hi_source(year), "https://official.example/hi.pdf")


def fixture():
    current = [dict(state_code=state, control_id="") for state in STATES]
    for row in current:
        if row["state_code"] in {"HI", "WY"}:
            row.update(control_id=row["state_code"].lower()+"-current",
                       control_measure="reported_cast_ballots",
                       reported_cast_ballots="500" if row["state_code"] == "HI" else "200",
                       control_registered_denominator="1000" if row["state_code"] == "HI" else "",
                       control_denominator_basis="native-frame", control_native_time="2026-source-clock",
                       control_source_url="https://official.example/current")
    native = [dict(
        id=state.lower()+"-current", year="2026", state_code=state, geographic_level="state",
        measure="reported_cast_ballots", native_status="unofficial", native_measure="ballots",
        numerator="500" if state == "HI" else "200", denominator="1000" if state == "HI" else "",
        selected_state_reference="True", disposition="selected_state_reference_not_independent_validation",
        source_url="https://official.example/current", source_time_label="2026-source-clock", scope_notes="")
        for state in ("HI", "WY")]
    ap = dict(selected_rows=[dict(
        scope="HI", dimension="overall", group="all", weight_field="FINALVOTE_STATE_WEIGHT",
        positive_weight_n="1000", n="1000", year="2022", weight="100", modeled_voter_weight="60",
        modeled_nonvoter_weight="30", model_unknown_weight="10", inference_status="native qualifier")])
    civic = dict(participation=[dict(
        scope=s, dimension="overall", n=1000, weight="100", modeled_voter_weight="60",
        modeled_nonvoter_weight="40") for s in STATES if s != "DC"])
    hi, modes = historical()
    return current, native, [hi], modes, ap, civic


def read(content):
    return list(csv.DictReader(io.StringIO(content.decode())))


def primary_fixture():
    counties = {f"county-{i}": 10 for i in range(23)}
    return dict(
        year=2022, state_code="WY", workbook_counties=counties, workbook_total=230,
        native_pdf_text="Wyoming General Election - November 8, 2022\n"
                        + "\n".join(f"{county} {total}" for county, total in counties.items()) + "\n230Total\n",
        native_ballot_issue_notes=[
            "The total ballots cast is 230. The majority needed is 116.",
            "The total ballots cast is 230. The majority needed is 116."],
        source_pdf_url="https://official.example/statewide.pdf")


class HistoricalParticipationControlsTests(unittest.TestCase):
    def test_native_encodings_and_repeated_registration_reconcile_without_addition(self):
        for year in (2018, 2020, 2022, 2024):
            with self.subTest(year=year):
                row, modes = historical(year)
                self.assertEqual(row["registered"], 1000)
                self.assertEqual(row["reported_cast_ballots"], 600 if year >= 2022 else 900)
                self.assertEqual(sum(m["ballots"] for m in modes if m["source_family"] == "native_state_pdf"),
                                 row["reported_cast_ballots"])
                self.assertTrue(all(not m["cross_year_mode_harmonized"] for m in modes))

    def test_zero_native_counted_field_does_not_make_ballots_zero(self):
        row, _ = historical(2022)
        self.assertEqual(row["native_counted_units"], 0)
        self.assertEqual(row["reported_cast_ballots"], 600)
        self.assertTrue(row["source_labeled_final"])

    def test_wrong_election_or_pdf_accounting_rejected(self):
        raw, layout, pdf = hi_source()
        with self.assertRaisesRegex(ValueError, "election identity"):
            hawaii(2022, raw, layout, pdf.replace("GENERAL ELECTION 2022", "GENERAL ELECTION 2024"), "source")
        with self.assertRaisesRegex(ValueError, "totals do not reconcile"):
            hawaii(2022, raw, layout, pdf.replace("TOTAL TURNOUT 600", "TOTAL TURNOUT 601"), "source")

    def test_complete_state_year_grid_and_full_unknown_model_mass(self):
        files, summary = build(*fixture())
        self.assertEqual(summary["state_year_query_rows"], 255)
        missing = next(r for r in read(files["complete-state-year-controls.csv"])
                       if r["state_code"] == "AL" and r["year"] == "2018")
        self.assertEqual(missing["reported_cast_ballots"], "")
        row = next(r for r in read(files["complete-source-specific-survey-comparison.csv"])
                   if r["study"] == "AP VoteCast")
        self.assertEqual(Decimal(row["conditional_modeled_voter_count"]), 600)
        self.assertEqual(Decimal(row["conditional_modeled_nonvoter_count"]), 300)
        self.assertEqual(Decimal(row["conditional_model_unknown_count"]), 100)
        self.assertEqual(row["exchangeability_assumption_validated"], "False")
        self.assertEqual(row["deaths"], "")

    def test_snapshot_change_is_not_individual_or_final_turnout_change(self):
        files, _ = build(*fixture())
        row = read(files["complete-administrative-time-comparisons.csv"])[0]
        self.assertEqual(row["native_ballot_count_change"], "-100")
        self.assertEqual(row["qualified_cast_ballot_snapshot_change"], "-100")
        self.assertEqual(row["both_source_labeled_final"], "False")
        self.assertEqual(row["individual_retention_or_switching_inferred"], "False")
        self.assertEqual(row["deaths"], "")

    def test_native_wyoming_missing_registration_never_filled(self):
        rows = [dict(year="2022", state_code="WY", county=f"county-{i}", precinct="1",
                     candidate="10", ballots="10", registered_voters="", turnout_rate="")
                for i in range(23)]
        audit = dict(category_labels=["candidate"], units=23, statewide_ballots=230,
                     printed_ballot_conflicts=[], ballot_approval="approved")
        row = wyoming(rows, audit)
        self.assertEqual(row["reported_cast_ballots"], 230)
        self.assertIsNone(row["registered"])

    def test_wyoming_printed_conflict_remains_held_not_repaired(self):
        rows = [dict(year="2022", state_code="WY", county=f"county-{i}", precinct="1",
                     candidate="10", ballots="10", registered_voters="", turnout_rate="")
                for i in range(23)]
        audit = dict(category_labels=["candidate"], units=23, statewide_ballots=230,
                     printed_ballot_conflicts=[dict(county="county-0", difference=2)], ballot_approval="withheld")
        row = wyoming(rows, audit)
        self.assertEqual(row["native_numerator"], 230)
        self.assertIsNone(row["reported_cast_ballots"])
        self.assertEqual(row["control_measure"], "native_workbook_ballot_sum_printed_conflict_held")
        args = fixture()
        args[2].append(row)
        files, _ = build(*args)
        transition = next(r for r in read(files["complete-administrative-time-comparisons.csv"])
                          if r["state_code"] == "WY")
        self.assertEqual(transition["native_ballot_count_change"], "-30")
        self.assertEqual(transition["qualified_cast_ballot_snapshot_change"], "")
        self.assertEqual(transition["includes_held_native_ballot_measure"], "True")

    def test_no_synthetic_dc_survey_or_mixed_weight_frame(self):
        args = fixture()
        args[-1]["participation"][0]["scope"] = "DC"
        with self.assertRaisesRegex(ValueError, "Civic state-only"):
            build(*args)
        args = fixture()
        args[-2]["selected_rows"][0]["weight_field"] = "FINALVOTE_NATIONAL_WEIGHT"
        with self.assertRaisesRegex(ValueError, "state survey aggregate"):
            build(*args)

    def test_direct_state_summary_selected_without_promoting_original_held_units(self):
        primary = primary_fixture()
        held = dict(
            year=2022, state_code="WY", control_id="wy-native-general-2022",
            control_measure="native_workbook_ballot_sum_printed_conflict_held",
            native_measure="native unit aggregate", native_numerator=230, reported_cast_ballots=None,
            registered=None, registration_basis="not supplied", source_time_label="native-clock",
            source_url="https://official.example/units", source_report_status="held",
            source_labeled_final=False, native_total_units=23, native_counted_units=None,
            source_scope_notes="Original conflicting printed county figure remains.")
        state = wyoming_statewide(primary, held)
        held["selected_state_reference"] = False
        args = fixture()
        args[2].extend([held, state])
        files, _ = build(*args)
        selected = next(r for r in read(files["complete-state-year-controls.csv"])
                        if r["state_code"] == "WY" and r["year"] == "2022")
        self.assertEqual(selected["control_id"], "wy-native-general-2022-statewide")
        self.assertEqual(selected["reported_cast_ballots"], "230")
        self.assertEqual(selected["native_registered"], "")
        ledger = next(r for r in read(files["complete-native-source-selection.csv"])
                      if r["observation_id"] == "wy-native-general-2022")
        self.assertEqual(ledger["selected_state_reference"], "False")
        self.assertEqual(ledger["native_aggregate_ballot_approval"], "withheld")
        self.assertEqual(ledger["native_numerator"], "230")
        self.assertIsNone(held["reported_cast_ballots"])

    def test_direct_state_pdf_total_and_county_changes_require_new_review(self):
        primary = primary_fixture()
        with self.assertRaisesRegex(ValueError, "PDF total"):
            wyoming_statewide(dict(primary, native_pdf_text=primary["native_pdf_text"].replace(
                "230Total", "231Total")), dict(native_numerator=230))
        with self.assertRaisesRegex(ValueError, "county vector"):
            wyoming_statewide(dict(primary, native_pdf_text=primary["native_pdf_text"].replace(
                "county-0 10", "county-0 11")), dict(native_numerator=230))


if __name__ == "__main__":
    unittest.main()
