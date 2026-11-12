import copy
import unittest

from scripts import compare_house_model_families as comparison


class HouseFamilyComparisonTests(unittest.TestCase):
    def metrics(self):
        return {family: {
            "historical_transfer": {"source_weighted_log_loss": .7, "source_weighted_multiclass_brier": .3},
            "house26_response": {"source_weighted_multiclass_brier": .2}}
            for family in comparison.FAMILIES}

    def test_better_current_fit_or_return_error_cannot_override_historical_failure(self):
        values = self.metrics()
        values[comparison.FAMILIES[1]]["historical_transfer"]["source_weighted_log_loss"] = .8
        values[comparison.FAMILIES[1]]["house26_response"]["source_weighted_multiclass_brier"] = .1
        values[comparison.FAMILIES[1]]["current_party_error"] = 0
        values[comparison.FAMILIES[2]]["house26_response"]["source_weighted_multiclass_brier"] = .21
        self.assertEqual(comparison.select_family(values)["preferred_family"], comparison.BASELINE)

    def test_declared_source_only_rule_can_choose_an_admissible_family(self):
        values = self.metrics()
        values[comparison.FAMILIES[1]]["historical_transfer"]["source_weighted_log_loss"] = .68
        self.assertEqual(comparison.select_family(values)["preferred_family"], comparison.FAMILIES[1])

    def test_share_change_is_half_margin_but_retained_percentage_is_not(self):
        row = dict(state_code="AA", source_comparison_available=True,
            reported_comparison=dict(previous_margin_pp=-4, current_margin_pp=12, reported_change_pp=16),
            point=dict(net_participation_pp=6, contributions_pp=dict(
                switching=10, exit=4, entry=2, other_choice=0, unresolved=0)),
            before_current_party_conditioning=dict(current_margin_pp=10, prediction_error_observed_minus_predicted_pp=2),
            gross_outcomes=dict(retaining=.8, switching=.1, exit=.05))
        values = comparison.state_comparisons({family: dict(rows=[copy.deepcopy(row)]) for family in comparison.FAMILIES})
        self.assertEqual(values[0]["observed_Democratic_two_party_share_previous_pct"], 48)
        self.assertEqual(values[0]["observed_Democratic_two_party_share_current_pct"], 56)
        self.assertEqual(values[0]["observed_Democratic_two_party_share_change_pp"], 8)
        self.assertEqual(values[0]["switching_Democratic_two_party_share_pp"], 5)
        self.assertEqual(values[0]["gross_retained_share_pct"], 80)
        self.assertEqual(values[0]["observed_minus_predicted_Democratic_two_party_share_pp"], 1)


if __name__ == "__main__":
    unittest.main()
