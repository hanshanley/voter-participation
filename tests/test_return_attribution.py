import sys
from decimal import Decimal, localcontext
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from return_attribution import estimate, scenario


MOMENTS = dict(scope="MN", dimension="overall", prior_election="2024", prior_office="president",
    current_office="house", m24="20", m26="30", t24="100", t26="80",
    switching="6", modeled_nonparticipation="2", no_prior_contest_vote_entry="4",
    other_choice="-1", unresolved="-1")
CONTROL = dict(id="MN-house", state_code="MN", office="house", year=2026,
    current=dict(D=54, R=46), previous=dict(D=48, R=52), previous_year=2024)
PARTICIPATION = dict(n=1000, source_effective_n="600", modeled_voter_weight="100")


class ReturnAttributionTests(unittest.TestCase):
    def test_return_and_denominator_gaps_reconcile_without_relabeling_them_switching(self):
        result = estimate(MOMENTS, CONTROL, PARTICIPATION)
        with localcontext() as context:
            context.prec = 80
            parts = result["reference"]["contributions_pp"]
            self.assertEqual(parts["switching"], Decimal("6.7500"))
            self.assertEqual(parts["modeled_nonparticipation"], Decimal("2.2500"))
            self.assertEqual(parts["return_frame_gap"], Decimal("-26.55000"))
            self.assertEqual(sum(parts.values()), Decimal("-12"))
            self.assertEqual(result["observed_same_office_change_pp"], Decimal("12"))
            self.assertEqual(result["prior_office_and_source_frame_gap_pp"], Decimal("24"))

    def test_sensitivity_varies_effects_not_totals_and_is_not_a_fake_confidence_interval(self):
        result = estimate(MOMENTS, CONTROL, PARTICIPATION)
        self.assertEqual(len(result["sensitivity_scenarios"]), 9)
        self.assertLess(result["assumption_ranges_pp"]["switching"]["minimum"],
                        result["assumption_ranges_pp"]["switching"]["maximum"])
        with localcontext() as context:
            context.prec = 80
            for case in result["sensitivity_scenarios"]:
                self.assertEqual(sum(case["contributions_pp"].values()), Decimal("-12"))

    def test_office_specific_switching_is_used_with_explicit_transport(self):
        control = dict(CONTROL, office="senate", id="MN-senate", previous=None, previous_year=None)
        poll = dict(state_code="MN", office="senate", status="published_joint_question_reviewed",
            arithmetic_from_rounded_percentages_per_100_current_group_voters=dict(
                reported_trump_to_dem="8", reported_harris_to_rep="3"))
        result = estimate(MOMENTS, control, PARTICIPATION, poll)
        self.assertEqual(result["reference"]["contributions_pp"]["switching"], Decimal("11.2500"))
        self.assertTrue(result["evidence"]["cross_office_transport"])
        self.assertIsNone(result["observed_same_office_change_pp"])
        with self.assertRaises(ValueError):
            estimate(MOMENTS, control, PARTICIPATION, dict(poll, state_code="WI"))

    def test_zero_change_does_not_invent_an_attribution_percentage(self):
        control = dict(CONTROL, current=dict(D=60, R=40))
        result = estimate(MOMENTS, control, PARTICIPATION)
        self.assertTrue(all(value is None for value in result["signed_share_of_source_frame_change_pct"].values()))

    def test_local_allocation_missing_counts_and_bad_frames_fail_closed(self):
        with self.assertRaises(ValueError):
            estimate(MOMENTS, dict(CONTROL, geography_level="county"), PARTICIPATION)
        with self.assertRaises(ValueError):
            estimate(MOMENTS, dict(CONTROL, current=dict(D=0, R=0)), PARTICIPATION)
        with self.assertRaises(ValueError):
            estimate(dict(MOMENTS, scope="WI"), CONTROL, PARTICIPATION)
        with self.assertRaises(ValueError):
            estimate(MOMENTS, dict(CONTROL, current=dict(D=1.5, R=2)), PARTICIPATION)


if __name__ == "__main__":
    unittest.main()
