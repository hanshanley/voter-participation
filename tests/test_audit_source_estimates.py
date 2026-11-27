import unittest
from scripts.audit_source_estimates import compare, share


class OutcomeAuditTests(unittest.TestCase):
    def example(self, eligible=True):
        model = dict(state_code="MO", point=dict(current_margin_pp=0, previous_margin_pp=-10, total_change_pp=10),
                     sensitivity=dict(total_change=dict(minimum=8, maximum=12)))
        actual = dict(state_code="MO", current=dict(D=50, R=50), previous=dict(D=40, R=60),
                      qualified_comparison=eligible, comparison_holds=[] if eligible else ["Changed competition"])
        old = dict(state_code="MO", democratic_two_party_share_pct=49)
        return [model], [actual], [old]

    def test_baseline_error_is_not_misattributed_to_new_switching(self):
        rows, summary = compare(*self.example())
        self.assertEqual(rows[0]["current_share_error_pp"], 0)
        self.assertEqual(rows[0]["previous_share_error_pp"], 5)
        self.assertEqual(rows[0]["change_error_pp"], -5)
        self.assertEqual(summary["change_MAE_pp"], 5)
        self.assertTrue(rows[0]["outside_model_sensitivity"])
        self.assertEqual(summary["primary_recorded_source_differences"], 1)

    def test_incompatible_comparisons_cannot_lower_the_error_score(self):
        models, actual, old = self.example()
        models.append({**models[0], "state_code": "TX"})
        actual.append({**actual[0], "state_code": "TX", "qualified_comparison": False})
        old.append({**old[0], "state_code": "TX"})
        rows, summary = compare(models, actual, old)
        self.assertEqual(summary["qualified_comparisons"], 1)
        self.assertIsNone(rows[1]["outside_model_sensitivity"])
        with self.assertRaisesRegex(ValueError, "No qualified"):
            compare(*self.example(False))

    def test_missing_votes_are_not_zero(self):
        self.assertIsNone(share(dict(D=None, R=50)))
        self.assertIsNone(share(dict(D=0, R=0)))
        self.assertEqual(share(dict(D=0, R=50)), 0)

    def test_duplicate_states_and_changed_accounting_fail_closed(self):
        models, actual, old = self.example()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            compare(models, actual + actual, old)
        models[0]["point"]["total_change_pp"] += 1
        with self.assertRaisesRegex(ValueError, "reconcile"):
            compare(models, actual, old)


if __name__ == "__main__":
    unittest.main()
