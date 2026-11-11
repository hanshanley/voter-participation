import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.participation_controls import HOUSE_OFFICE, build, export, florida_control, held_controls


STATES = "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()


def data():
    civic = dict(participation=[dict(scope=s, dimension="overall", group="all", n=2000,
                  weight="100", modeled_voter_weight="60", modeled_nonvoter_weight="40") for s in STATES])
    uf = [dict(STATE_ABV=s, geographic_level="state", ballots_status="estimate", year=2026,
               TOTAL_BALLOTS_COUNTED=450, VEP=900, VEP_TURNOUT_RATE=50) for s in [*STATES, "DC"]]
    reporting = [dict(state_code="NC", state="North Carolina", denominator_basis="active_and_inactive_registered_voters",
                     ballots=500, denominator=1000, source_update_label="native-clock",
                     source_url="https://official.example/nc", status="unofficial")]
    return civic, uf, reporting, dict(observations=[]), []


def read(content):
    return list(csv.DictReader(io.StringIO(content.decode())))


def held_archive(hi_pdf_ballots=600, wy_registration="", mn_all_reported=False):
    fields = ["Contest Title", "Candidate ID", "Registered Voters", "Total Votes", "Mail Votes",
              "In-Person Votes", "Mail Blank Votes", "In-Person Blank Votes", "Mail Over Votes",
              "In-Person Over Votes", "Mail Invalid Votes", "In-Person Invalid Votes"]
    stream = io.StringIO(newline="")
    stream.write("#FormatVersion 1\n")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(fields)
    for contest in ("I", "II"):
        writer.writerow(["U.S. Representative, Dist " + contest, "1", 1000, 200, 190, 10, 100, 0, 0, 0, 0, 0])
    files = {
        "HI/originals/summary.txt.gz": gzip.compress(stream.getvalue().encode(), mtime=0),
        "HI/audit.json": json.dumps(dict(
            year=2026, state_code="HI", source_certified=False, reporting_units=2,
            source_summary_ballots=600, ballots=606)).encode(),
        "HI/pdf-observations.json.gz": gzip.compress(json.dumps({"histatewide.pdf": dict(
            printed_on="native-clock", records=[dict(participation={
                "TOTAL TURNOUT": hi_pdf_ballots, "TOTAL REGISTRATION": 1000})])}).encode(), mtime=0),
        "HI/participation.json.gz": gzip.compress(json.dumps([
            dict(ballots=400, registered=1000), dict(ballots=206, registered=0)]).encode(), mtime=0),
        "MN/participation-audit.json": json.dumps(dict(rows=2, ballot_mode_discrepancies=0)).encode(),
        "MN/pctstats.txt": ("MN;01;1;reported;1;100;2;30;20;0;0;50\n"
                            f"MN;01;2;not-reported;{int(mn_all_reported)};200;0;0;0;0;0;0\n").encode(),
    }
    rows = [dict(year=2026, state_code="WY", county=f"county-{i}", precinct="1",
                 candidate=10, ballots=10, registered_voters=wy_registration, turnout_rate="")
            for i in range(23)]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    files["WY/precinct-counts.csv"] = stream.getvalue().encode()
    files["WY/counts-review.json"] = json.dumps(dict(
        year=2026, state_code="WY", units=23, statewide_ballots=230, category_labels=["candidate"],
        counties=[dict(county=r["county"], printed_county_ballots=10) for r in rows],
        candidate_county_state_conflicts=[dict(county="unresolved-native-conflict")])).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def florida_archive(clock=None, state_flag=None, first_count=10):
    headers = [
        "County SOE Website", "Voter Turnout", "Eligible Active Registered Voters",
        "Turnout Percentage", "Precincts Reporting", "Precincts Completed",
        "Vote-by-Mail Ballots Completed", "Early Voting Ballots Completed",
        "Provisional Ballots Completed", "10-day Overseas Vote-by-Mail Completed",
    ]
    source_rows, query, cells, catalog = [], [], [], []
    flags = ("native_precincts_completed", "native_vote_by_mail_completed",
             "native_early_voting_completed", "native_provisional_completed",
             "native_10_day_overseas_completed")
    for ordinal in range(68):
        county = ordinal < 67
        name = "county-" + str(ordinal) if county else "TOTAL"
        count = (first_count if ordinal == 0 else 10) if county else 670
        register = 100 if county else 6700
        status = ["Y", "Y", "Y", "N", "N"] if county else [state_flag] * 5
        texts = [name, format(count, ","), format(register, ","), f"{count}%" if county else "10%",
                 "100%", "", "", "", "", ""]
        source_row = [dict(text=text, hrefs=[], span_classes=(
            [[status[column - 5]]] if column >= 5 and status[column - 5] else []))
            for column, text in enumerate(texts)]
        source_rows.append(source_row)
        row = dict(native_county=name, native_county_code="ABC" if county else "",
                   reported_participants=count, eligible_active_registered_voters=register,
                   native_turnout_percentage=texts[3], independently_derived_registered_fraction_percent="unused",
                   native_precincts_reporting="100%", **dict(zip(flags, status)),
                   source_as_of=None, source_timezone=None, native_fips=None,
                   analysis_rate_approved=False, map_approved=False)
        query.append(row)
        if county:
            catalog.append(dict(county_literal=name))
        for column, cell in enumerate(source_row):
            cells.append(dict(
                source_row_ordinal=ordinal, column_ordinal=column, literal_text=cell["text"],
                native_span_classes=json.dumps(cell["span_classes"]),
                declared_hrefs=json.dumps(cell["hrefs"])))

    def csv_content(rows):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode()

    source = dict(
        election_date="2026-11-03", source_as_of=clock, source_timezone=None,
        generic_turnout_approved=False, county_fips_join_approved=False,
        map_approved=False, certified=False, headers=headers,
        source_definition=dict(native_registration_deadline_date="2026-10-05"),
        county_rows=source_rows[:67], statewide_row=source_rows[67],
        source_url="https://official.example/florida", source_status="Unofficial Election Night Results",
    )
    files = {name: b"{}" for name in ("methods.json", "audit.json",
                                     "review-counties.py", "test_review_counties.py")}
    files.update({
        "source-qualification.json": json.dumps(source).encode(),
        "county-participation.csv": csv_content(query[:67]),
        "statewide-participation.csv": csv_content(query[67:]),
        "source-native-cells.csv": csv_content(cells),
        "native-county-catalog.csv": csv_content(catalog),
    })
    files["checksums.json"] = json.dumps(dict(files=[
        dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        for name, raw in files.items()])).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    return output.getvalue()


class ParticipationControlsTests(unittest.TestCase):
    def test_florida_native_parser_preserves_clock_and_unfinished_flags(self):
        observation, reconciliation = florida_control(florida_archive())
        self.assertEqual(observation["numerator"], 670)
        self.assertEqual(observation["denominator"], 6700)
        self.assertIsNone(reconciliation["native_source_as_of"])
        self.assertEqual(reconciliation["native_statewide_completion_flags"], [None] * 5)
        self.assertTrue(all(row["flags"][-2:] == ["N", "N"]
                            for row in reconciliation["county_completion_flags"]))
        self.assertFalse(reconciliation["native_generic_turnout_approval"])

    def test_florida_native_parser_rejects_invented_clock_or_state_completion(self):
        for content in (florida_archive(clock="new-clock"), florida_archive(state_flag="Y")):
            with self.subTest():
                with self.assertRaises(ValueError):
                    florida_control(content)

    def test_florida_native_parser_does_not_repair_conflicting_county_and_state_totals(self):
        with self.assertRaisesRegex(ValueError, "county sums differ"):
            florida_control(florida_archive(first_count=11))

    def test_conditional_counts_reconcile_and_observed_difference_not_fitted_away(self):
        files, summary = build(*data())
        row = read(files["complete-conditional-registered-scenarios.csv"])[0]
        self.assertEqual(row["conditional_modeled_voter_count"], "600.0")
        self.assertEqual(row["conditional_modeled_nonvoter_count"], "400.0")
        self.assertEqual(row["reported_cast_minus_conditional_modeled_voter_count"], "-100.0")
        self.assertEqual(row["assumption_validated"], "False")
        self.assertEqual(row["death_component"], "")
        self.assertEqual(summary["conditional_registered_frame_scenarios"], 1)

    def test_vep_and_unsupplied_eligible_denominators_do_not_fill_registration(self):
        civic, uf, reporting, evidence, house = data()
        reporting.append(dict(reporting[0], state_code="ND", state="North Dakota", denominator=None,
                              denominator_basis="eligible_voters_source_estimate", source_url="https://official.example/nd"))
        files, _ = build(civic, uf, reporting, evidence, house)
        row = next(r for r in read(files["complete-state-control-query.csv"]) if r["state_code"] == "ND")
        self.assertEqual(row["uf_vep_estimate"], "900")
        self.assertEqual(row["control_registered_denominator"], "")
        self.assertEqual(row["conditional_registered_frame_scenario_available"], "False")

    def test_florida_native_participants_support_only_a_conditional_register_scenario(self):
        civic, uf, reporting, evidence, house = data()
        evidence["observations"] = [dict(
            id="fl-2026-held-statewide-eligible-active-register", scope="statewide native TOTAL",
            jurisdiction="Florida", source_url="https://official.example/florida",
            measure="native Voter Turnout", numerator=650, denominator=1000,
            denominator_label="Eligible Active Registered Voters; source deadline frame",
            source_time_label="Native update time missing", status="unofficial")]
        files, summary = build(civic, uf, reporting, evidence, house)
        row = next(row for row in read(files["complete-conditional-registered-scenarios.csv"])
                   if row["state_code"] == "FL")
        self.assertEqual(row["conditional_modeled_voter_count"], "600.0")
        self.assertEqual(row["conditional_modeled_nonvoter_count"], "400.0")
        self.assertEqual(row["reported_cast_ballot_measure_control"], "")
        self.assertEqual(row["reported_cast_minus_conditional_modeled_voter_count"], "")
        self.assertEqual(row["control_native_status"], "unofficial")
        self.assertEqual(row["assumption_validated"], "False")
        state = next(row for row in read(files["complete-state-control-query.csv"])
                     if row["state_code"] == "FL")
        self.assertEqual(state["control_native_numerator"], "650")
        self.assertEqual(state["reported_cast_ballots"], "")
        self.assertEqual(state["reported_ballots_per_native_registered_denominator_pct"], "")
        self.assertNotIn("FL", summary["official_cast_control_states"])

    def test_florida_zero_register_never_creates_a_scenario(self):
        civic, uf, reporting, evidence, house = data()
        evidence["observations"] = [dict(
            id="fl-2026-held-statewide-eligible-active-register", scope="statewide native TOTAL",
            jurisdiction="Florida", source_url="https://official.example/florida",
            measure="native Voter Turnout", numerator=0, denominator=0,
            denominator_label="Eligible active register", source_time_label="Missing", status="unofficial")]
        with self.assertRaisesRegex(ValueError, "Invalid native registration denominator"):
            build(civic, uf, reporting, evidence, house)

    def test_same_north_carolina_source_not_added_twice(self):
        civic, uf, reporting, evidence, house = data()
        evidence["observations"] = [dict(
            id="nc-2026-reported-ballots-20261106", scope="statewide", jurisdiction="North Carolina",
            source_url=reporting[0]["source_url"], measure="reported ballots cast", numerator=500, denominator=1000,
            denominator_label="native rtl", source_time_label="native-clock", status="unofficial")]
        files, summary = build(civic, uf, reporting, evidence, house)
        self.assertEqual(summary["exact_same_source_duplicates_not_added"], 1)
        self.assertEqual(len(read(files["complete-conditional-registered-scenarios.csv"])), 1)

    def test_county_control_never_receives_state_survey_scaling(self):
        civic, uf, reporting, evidence, house = data()
        evidence["observations"] = [dict(
            id="tx-harris-2026-counted-ballots-20261104", scope="Harris County only", jurisdiction="Texas-Harris",
            source_url="https://official.example/harris", measure="counted ballots", numerator=500, denominator=1000,
            denominator_label="native registered", source_time_label="native-clock", status="unofficial")]
        files, summary = build(civic, uf, reporting, evidence, house)
        self.assertEqual(summary["county_controls_retained_not_allocated"], 1)
        self.assertFalse(any(r["state_code"] == "TX" for r in read(files["complete-conditional-registered-scenarios.csv"])))

    def test_returned_processed_and_native_turnout_do_not_become_cast_ballots(self):
        civic, uf, reporting, evidence, house = data()
        evidence["observations"] = [
            dict(id=identifier, scope="statewide", jurisdiction=state, source_url="https://official.example/" + state,
                 measure="native-not-proven-cast", numerator=500, denominator=1000, denominator_label="native registered",
                 source_time_label="native-clock", status="preliminary")
            for identifier, state in (("co-2026-returned-processed-20261105", "Colorado"),
                                      ("ca-2026-native-voter-turnout-20261106", "California"))]
        files, _ = build(civic, uf, reporting, evidence, house)
        for row in read(files["complete-conditional-registered-scenarios.csv"]):
            if row["state_code"] in ("CO", "CA"):
                self.assertEqual(row["reported_cast_ballot_measure_control"], "")
                self.assertEqual(row["reported_cast_minus_conditional_modeled_voter_count"], "")

    def test_dc_and_house_votes_are_not_synthetic_survey_or_ballot_controls(self):
        civic, uf, reporting, evidence, house = data()
        house.append(dict(year="2026", office=HOUSE_OFFICE, state_code="AL", votes="350"))
        files, _ = build(civic, uf, reporting, evidence, house)
        rows = {r["state_code"]: r for r in read(files["complete-state-control-query.csv"])}
        self.assertEqual(rows["DC"]["civic_modeled_voter_pct"], "")
        self.assertEqual(rows["AL"]["house_candidate_vote_sum_context"], "350")
        self.assertEqual(rows["AL"]["reported_cast_ballots"], "")

    def test_unapproved_input_cannot_be_carried_into_public_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "source-manifest.json").write_text(json.dumps(dict(
                inputs={"private-voters.csv": {}}, original_raw_survey_or_voter_records_included=False)))
            with self.assertRaisesRegex(ValueError, "Unapproved or nonpublic"):
                export(root, root / "output")
            self.assertFalse((root / "output").exists())

    def test_held_hawaii_registration_not_multiplied_and_ballot_difference_preserved(self):
        observations, reconciliation = held_controls(held_archive())
        civic, uf, reporting, evidence, house = data()
        evidence["observations"] = observations
        files, _ = build(civic, uf, reporting, evidence, house)
        row = next(r for r in read(files["complete-conditional-registered-scenarios.csv"])
                   if r["state_code"] == "HI")
        self.assertEqual(row["native_registered_denominator"], "1000")
        self.assertEqual(row["reported_cast_ballot_measure_control"], "600")
        self.assertEqual(reconciliation["HI"]["unit_minus_summary_ballots"], 6)
        self.assertTrue(reconciliation["HI"]["precinct_rates_remain_withheld"])

    def test_held_partial_minnesota_and_missing_wyoming_registration_not_scaled(self):
        observations, reconciliation = held_controls(held_archive())
        civic, uf, reporting, evidence, house = data()
        evidence["observations"] = observations
        files, summary = build(civic, uf, reporting, evidence, house)
        rows = {r["state_code"]: r for r in read(files["complete-state-control-query.csv"])}
        self.assertEqual(rows["WY"]["reported_cast_ballots"], "230")
        self.assertEqual(rows["WY"]["control_registered_denominator"], "")
        self.assertEqual(rows["WY"]["conditional_registered_frame_scenario_available"], "False")
        self.assertEqual(rows["MN"]["reported_cast_ballots"], "")
        self.assertEqual(rows["MN"]["control_registered_denominator"], "")
        self.assertEqual(summary["partial_state_controls_retained_not_allocated"], 1)
        self.assertEqual(reconciliation["MN"]["reported_units"], 1)
        self.assertEqual(reconciliation["MN"]["native_units"], 2)
        self.assertEqual(len(reconciliation["WY"]["candidate_conflicts_retained"]), 1)

    def test_held_hawaii_text_and_pdf_disagreement_requires_review(self):
        with self.assertRaisesRegex(ValueError, "Hawaii source-bound"):
            held_controls(held_archive(hi_pdf_ballots=601))

    def test_held_wyoming_new_registration_is_not_silently_adopted(self):
        with self.assertRaisesRegex(ValueError, "Wyoming native ballot scope"):
            held_controls(held_archive(wy_registration="100"))

    def test_changed_minnesota_complete_reporting_requires_new_scope_review(self):
        with self.assertRaisesRegex(ValueError, "Minnesota partial-reporting scope"):
            held_controls(held_archive(mn_all_reported=True))

    def test_vermont_native_votes_cast_not_turned_into_ballots(self):
        civic, uf, reporting, evidence, house = data()
        evidence["observations"] = [dict(
            id="vt-2026-held-municipal-registration", scope="statewide municipal source frame",
            jurisdiction="Vermont", source_url="https://official.example/vt", measure="Votes Cast",
            numerator=500, denominator=1000, denominator_label="municipal registered",
            source_time_label="native-clock", status="unofficial")]
        files, _ = build(civic, uf, reporting, evidence, house)
        row = next(r for r in read(files["complete-conditional-registered-scenarios.csv"])
                   if r["state_code"] == "VT")
        self.assertEqual(row["native_registered_denominator"], "1000")
        self.assertEqual(row["conditional_modeled_voter_count"], "600.0")
        self.assertEqual(row["reported_cast_ballot_measure_control"], "")

    def test_missing_additional_denominators_never_scale_native_sums(self):
        civic, uf, reporting, evidence, house = data()
        evidence["observations"] = [dict(
            id=identifier, scope="statewide native source", jurisdiction=state,
            source_url="https://official.example/" + state, measure="ballots",
            numerator=500, denominator=None, denominator_label="native denominator unqualified",
            source_time_label="native-clock", status="unofficial")
            for identifier, state in (("id-2026-held-separate-ballot-report", "ID"),
                                      ("ri-2026-held-all-locality-ballots", "RI"))]
        files, _ = build(civic, uf, reporting, evidence, house)
        for row in read(files["complete-state-control-query.csv"]):
            if row["state_code"] in {"ID", "RI"}:
                self.assertEqual(row["reported_cast_ballots"], "500")
                self.assertEqual(row["control_registered_denominator"], "")
                self.assertEqual(row["conditional_registered_frame_scenario_available"], "False")

    def test_dc_citywide_registration_does_not_create_civic_sample(self):
        civic, uf, reporting, evidence, house = data()
        evidence["observations"] = [dict(
            id="dc-2026-held-citywide-ballots", scope="statewide citywide native summary",
            jurisdiction="District of Columbia", source_url="https://official.example/dc",
            measure="ballots", numerator=500, denominator=1000, denominator_label="native registered",
            source_time_label="native-clock", status="unofficial")]
        files, _ = build(civic, uf, reporting, evidence, house)
        row = next(r for r in read(files["complete-state-control-query.csv"]) if r["state_code"] == "DC")
        self.assertEqual(row["reported_cast_ballots"], "500")
        self.assertEqual(row["control_registered_denominator"], "1000")
        self.assertEqual(row["civic_source_n"], "")
        self.assertEqual(row["conditional_registered_frame_scenario_available"], "False")

    def test_explicit_rhode_island_parent_registration_supports_its_own_scenario(self):
        civic, uf, reporting, evidence, house = data()
        evidence["observations"] = [dict(
            id="ri-2026-held-all-locality-ballots", scope="statewide declared parent registered frame",
            jurisdiction="Rhode Island", source_url="https://official.example/ri",
            measure="ballots", numerator=500, denominator=1000, denominator_label="native totalVoters",
            source_time_label="native-clock", status="unofficial",
            scope_notes="Native Federal registration zero retained; no allocation or source-field repair.")]
        files, _ = build(civic, uf, reporting, evidence, house)
        row = next(r for r in read(files["complete-conditional-registered-scenarios.csv"])
                   if r["state_code"] == "RI")
        self.assertEqual(row["native_registered_denominator"], "1000")
        self.assertEqual(row["reported_cast_ballot_measure_control"], "500")
        self.assertEqual(row["conditional_modeled_voter_count"], "600.0")


if __name__ == "__main__":
    unittest.main()
