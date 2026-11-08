import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.participation_controls import HOUSE_OFFICE, build, export


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


if __name__ == "__main__":
    unittest.main()
