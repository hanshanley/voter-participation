import math
import unittest

from scripts import calibrated_swing as model


class CalibratedSwingTests(unittest.TestCase):
    def test_both_endpoints_and_nonnegative_cells(self):
        prior = [[.1 if i == j else .05 for j in range(4)] for i in range(4)]
        prior = [[v/sum(map(sum, prior)) for v in row] for row in prior]
        rows, columns = [.2, .4, .05, .35], [.35, .3, .04, .31]
        q, _ = model.fit(prior, rows, columns)
        self.assertTrue(all(v >= 0 for row in q for v in row))
        for i in range(4):
            self.assertAlmostEqual(sum(q[i]), rows[i], places=11)
            self.assertAlmostEqual(sum(q[j][i] for j in range(4)), columns[i], places=11)

    def test_all_mechanisms_reconcile_without_a_residual_component(self):
        q = [[.2, .03, .01, .06], [.1, .2, .02, .08], [.01, .01, .01, .02],
            [.07, .03, .01, .04]]
        total = sum(map(sum, q))
        q = [[v/total for v in row] for row in q]
        result = model.summarize(q)
        self.assertAlmostEqual(sum(result["components_pp"].values()), result["reported_change_pp"], places=10)
        self.assertNotIn("other_and_unallocated", result["components_pp"])
        self.assertAlmostEqual(sum(result["gross_shares_of_modeled_previous_major_party"].values()), 1)

    def test_pure_retention_has_no_effect(self):
        q = [[0.0]*4 for _ in range(4)]
        for i, value in enumerate((.3, .4, .1, .2)):
            q[i][i] = value
        result = model.summarize(q)
        self.assertTrue(all(math.isclose(v, 0, abs_tol=1e-12) for v in result["components_pp"].values()))

    def test_unavailable_baseline_never_becomes_a_zero_fitted_model(self):
        row = dict(id="AK-house", office="house", state_code="AK",
            reported_comparison=dict(status="unavailable", reason="No compatible endpoints"))
        result = model.estimate(row, {})
        self.assertIsNone(result["point"])
        self.assertEqual(result["status"], "unavailable")

    def test_negative_counts_unknown_other_and_invalid_targets_fail_closed(self):
        for counts in (dict(D=1, R=2, O=None), dict(D=1, R=2, O=-1), dict(D=1, R=0, O=2)):
            with self.assertRaises(ValueError):
                model.counts(counts)
        with self.assertRaises(ValueError):
            model.fit([[1/16]*4 for _ in range(4)], [.2,.2,.2,-.1], [.25]*4)


if __name__ == "__main__":
    unittest.main()
