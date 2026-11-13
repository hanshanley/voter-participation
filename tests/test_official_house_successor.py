import copy
import unittest
from unittest.mock import patch

from scripts.official_house_successor import build


class OfficialHouseSuccessorTests(unittest.TestCase):
    def setUp(self):
        counts = dict(D=100, R=100, O=10)
        comparison = dict(status="reported_source_comparison",
            previous=counts.copy(), current=counts.copy(), reported_change_pp=0)
        self.previous = dict(rows=[
            dict(state_code="HI", reported_comparison=comparison,
                source_comparison_available=True,
                before_current_party_conditioning=dict(prediction_error_observed_minus_predicted_pp=1)),
            dict(state_code="MA", source_comparison_available=False, joint=[[123]],
                reported_comparison=dict(status="unavailable", reason="Existing coverage hold"))],
            comparison_policy={}, summary=dict(states=2, return_anchored=1),
            complete_assumption_cases=[dict(state_code=state, value=1) for state in ("HI", "MA")],
            complete_seed_cases=[dict(state_code=state, seed=7) for state in ("HI", "MA")],
            complete_demographic_seed_cases=[dict(state_code=state, dimension="age") for state in ("HI", "MA")])
        self.audit = dict(states=[
            dict(state_code="HI", like_for_like_statewide_source_comparison=True,
                previous_counts=counts.copy(), current_counts=dict(D=110, R=100, O=10),
                raw_reported_aggregate_margin_change_pp=1000/210),
            dict(state_code="MA", like_for_like_statewide_source_comparison=False)],
            reviewed_official_source_revisions=[dict(state_code="HI", stage="general",
                query_pin=dict(sha256="d"*64), native_updated_at=None,
                count_scope="Named source candidates, not ballots")])

    def test_only_changed_endpoint_is_recomputed_and_existing_hold_and_queries_are_reused(self):
        saved = copy.deepcopy(self.previous)

        def recalculate(priors, accepted, state_codes):
            self.assertEqual(state_codes, ["HI"])
            self.assertEqual(accepted["rows"][1]["reported_comparison"]["status"], "unavailable")
            return dict(rows=[dict(state_code="HI", source_comparison_available=True,
                before_current_party_conditioning=dict(prediction_error_observed_minus_predicted_pp=2))],
                complete_assumption_cases=[dict(state_code="HI", value=2)],
                complete_seed_cases=[dict(state_code="HI", seed=7)],
                complete_demographic_seed_cases=[dict(state_code="HI", dimension="age")])

        with patch("scripts.norc_house_model.build", side_effect=recalculate):
            result = build({}, self.previous, self.audit)
        self.assertEqual(self.previous, saved)
        self.assertEqual(result["rows"][1], saved["rows"][1])
        self.assertEqual(result["complete_assumption_cases"][1], saved["complete_assumption_cases"][1])
        self.assertTrue(result["endpoint_update"]["native_source_counts_revised_from_previous_release"])
        self.assertFalse(result["comparison_policy"]["native_source_counts_changed"])
        self.assertTrue(result["comparison_policy"]["input_source_counts_revised_from_previous_release"])
        self.assertIsNone(result["rows"][0]["reported_comparison"]["current_native_clock"])

    def test_source_revision_cannot_lift_or_ignore_a_hold(self):
        for held_before in (True, False):
            previous = copy.deepcopy(self.previous)
            audit = copy.deepcopy(self.audit)
            if held_before:
                previous["rows"][0]["source_comparison_available"] = False
            else:
                audit["states"][0]["like_for_like_statewide_source_comparison"] = False
            with self.subTest(held_before=held_before), self.assertRaises(ValueError):
                build({}, previous, audit)


if __name__ == "__main__":
    unittest.main()
