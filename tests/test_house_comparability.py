import unittest
from unittest.mock import patch

from scripts.house_comparability import district_rows, margin, requalify_model


def previous(district, name, party, votes):
    return dict(district=district, candidate=name, counted_as=party, votes=votes,
        literal_affiliations=[party], source_lines=[dict(role="named_candidate")])


def current(district, name, party, votes, race):
    return dict(year="2026", state_code="MA", district=district, office="U.S. House",
        name=name, party=party, votes=str(votes),
        source_url="https://civicapi.org/api/v2/race/"+str(race),
        source_updated_at="2026-11-07T12:40:50Z")


class ComparabilityTests(unittest.TestCase):
    def test_new_republican_candidate_is_not_a_statewide_preference_swing(self):
        before = [previous("MA-01", "A", "D", 600), previous("MA-01", "B", "R", 400),
                  previous("MA-02", "C", "D", 1000)]
        after = [current("MA-01", "A", "Democratic", 600, 1),
                 current("MA-01", "B", "Republican", 400, 1),
                 current("MA-02", "C", "Democratic", 600, 2),
                 current("MA-02", "D", "Republican", 400, 2)]
        rows = district_rows(before, after)
        self.assertFalse(rows[0]["major_party_coverage_changed"])
        self.assertTrue(rows[1]["major_party_coverage_changed"])
        self.assertFalse(rows[1]["common_reported_DR_district_id"])
        self.assertTrue(rows[1]["absent_party_is_not_zero_voter_preference"])
        self.assertEqual(margin(dict(D=1200, R=800))-margin(dict(D=1600, R=400)), -40)

    def test_missing_native_count_is_not_absent_candidate_or_zero_support(self):
        before = [previous("MA-01", "A", "D", 600), previous("MA-01", "B", "R", None)]
        after = [current("MA-01", "A", "Democratic", 600, 1),
                 current("MA-01", "B", "Republican", 400, 1)]
        row = district_rows(before, after)[0]
        self.assertTrue(row["previous"]["major_party_presence"]["R"])
        self.assertTrue(row["missing_major_party_counts"])
        self.assertFalse(row["common_reported_DR_district_id"])

    def test_reported_zero_does_not_remove_a_named_party(self):
        before = [previous("MA-01", "A", "D", 600), previous("MA-01", "B", "R", 0)]
        after = [current("MA-01", "A", "Democratic", 600, 1),
                 current("MA-01", "B", "Republican", 0, 1)]
        row = district_rows(before, after)[0]
        self.assertFalse(row["major_party_coverage_changed"])
        self.assertTrue(row["current"]["major_party_presence"]["R"])
        self.assertEqual(row["current"]["reported_counts"]["R"], 0)

    def test_duplicate_candidate_and_noncandidate_accounting_rejected(self):
        before = [previous("MA-01", "A", "D", 600)]
        candidate = current("MA-01", "A", "Democratic", 600, 1)
        with self.assertRaises(ValueError):
            district_rows(before, [candidate, candidate])
        accounting = current("MA-01", "Blanks", "Nonpartisan", 10, 1)
        with self.assertRaises(ValueError):
            district_rows(before, [candidate, accounting])

    def test_incompatible_target_is_removed_before_resimulation_other_states_reused(self):
        baseline = dict(rows=[
            dict(state_code=code, source_comparison_available=True, groups=[],
                 reported_comparison=dict(status="reported_source_comparison", reported_change_pp=-22.9),
                 before_current_party_conditioning=dict(prediction_error_observed_minus_predicted_pp=2))
            for code in ("MA", "VT")], summary={},
            complete_assumption_cases=[dict(state_code=code) for code in ("MA", "VT")],
            complete_seed_cases=[], complete_demographic_seed_cases=[])
        review = dict(contract="participation.house_comparability.v1", states=[
            dict(state_code="MA", like_for_like_statewide_source_comparison=False,
                 hold_reasons=["Named party coverage changed"]),
            dict(state_code="VT", like_for_like_statewide_source_comparison=True, hold_reasons=[])])

        def recalculate(priors, accepted, state_codes):
            self.assertEqual(state_codes, ["MA"])
            ma = next(row for row in accepted["rows"] if row["state_code"] == "MA")
            self.assertEqual(ma["reported_comparison"]["status"], "unavailable")
            self.assertIsNone(ma["reported_comparison"]["reported_change_pp"])
            return dict(rows=[dict(state_code="MA", source_comparison_available=False, groups=[])],
                        complete_assumption_cases=[dict(state_code="MA", source_scenario=True)],
                        complete_seed_cases=[], complete_demographic_seed_cases=[])

        with patch("scripts.norc_house_model.build", side_effect=recalculate):
            result = requalify_model({}, baseline, review)
        vt = next(row for row in result["rows"] if row["state_code"] == "VT")
        self.assertEqual(vt["before_current_party_conditioning"], baseline["rows"][1]["before_current_party_conditioning"])
        self.assertEqual(result["summary"]["return_anchored"], 1)
        ma = next(row for row in result["rows"] if row["state_code"] == "MA")
        self.assertEqual(ma["source_aggregate_comparison"], baseline["rows"][0]["reported_comparison"])
        self.assertEqual(baseline["rows"][0]["reported_comparison"]["reported_change_pp"], -22.9)


if __name__ == "__main__":
    unittest.main()
