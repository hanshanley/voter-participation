import csv
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.participation_controls import HOUSE_OFFICE, build, export, held_controls


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


class ParticipationControlsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
