from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import house_four_axis as model


class FeatureTests(unittest.TestCase):
    def test_hypothetical_predictions_enumerate_all_pairs_without_outcomes(self):
        features = [{"p20": "D"}, {"p20": "UNKNOWN"}]
        values = model.hypothetical_features(features)
        self.assertEqual(len(values), 18)
        self.assertEqual([x["admin_pair"] for x in values], list(map(str, range(9)))*2)
        self.assertEqual([x["p20"] for x in values], ["D"]*9+["UNKNOWN"]*9)
        self.assertEqual(features, [{"p20": "D"}, {"p20": "UNKNOWN"}])
        with self.assertRaises(ValueError):
            model.augmented(dict(p20="D", actual_admin24="N"), 1)

    def test_coarse_categories_keep_nonvote_and_unknown_even_with_reported_party(self):
        self.assertEqual(model.observed_coarse([0, 1, 0, 0], "previous_voter_major"), 4)
        self.assertEqual(model.observed_coarse([0, 2, 0, 1], "previous_voter_major"), 5)
        self.assertEqual(model.observed_coarse([0, 0, 0, 1], "previous_voter_major"), 1)
        self.assertEqual(model.observed_coarse([0, 0, 0, 3], "previous_voter_major"), 2)
        self.assertEqual(model.observed_coarse([0, 0, 0, 4], "previous_voter_major"), 3)


class NumericalTests(unittest.TestCase):
    def setUp(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("Private numerical stack optional")
        self.np = np

    def test_full_four_axis_projection_preserves_both_accepted_pairs(self):
        rng = self.np.random.default_rng(42)
        a = rng.dirichlet(self.np.ones(9), 4)
        h = rng.dirichlet(self.np.ones(30), 4)
        conditional = rng.dirichlet(self.np.ones(30), (4, 9))
        values, diagnostics = model.joints(a, h, conditional)
        fixed = values["fixed_pair_marginals"]
        self.np.testing.assert_allclose(fixed.sum(axis=2), a, atol=2.1e-12, rtol=0)
        self.np.testing.assert_allclose(fixed.sum(axis=1), h, atol=2.1e-12, rtol=0)
        self.assertLess(diagnostics["maximum_dual_certificate_error"], 1e-10)
        self.assertGreater(float(abs(fixed-values["independent_pairs"]).max()), .001)

    def test_past_conditioning_uses_correct_axes_and_all15_future_categories(self):
        values = self.np.arange(1, 541, dtype=float).reshape(2, 9, 30)
        values /= values.sum(axis=(1, 2))[:, None, None]
        a, h = self.np.asarray([0, 2]), self.np.asarray([1, 5])
        probabilities = model.future_given_past(values, a, h)
        expected = [[values[i, a[i]*3+aa, h[i]*5+hh] for aa in range(3) for hh in range(5)] for i in range(2)]
        expected = self.np.asarray(expected)
        expected /= expected.sum(axis=1)[:, None]
        self.np.testing.assert_array_equal(probabilities, expected)

    def test_coarse_forecasts_partition_probability_without_repairing_conflicts(self):
        future = self.np.arange(1, 31, dtype=float).reshape(2, 15)
        future /= future.sum(axis=1)[:, None]
        output = model.coarse_forecasts(future, self.np.asarray([0, 1]), "previous_voter_major")
        self.np.testing.assert_allclose(output.sum(axis=1), 1)
        self.np.testing.assert_array_equal(output[:, 4], future[:, 5:10].sum(axis=1))
        self.np.testing.assert_array_equal(output[:, 5], future[:, 10:15].sum(axis=1))
        entry = model.coarse_forecasts(future, self.np.asarray([0, 5]), "previous_nonvoter")
        self.np.testing.assert_allclose(entry.sum(axis=1), 1)


if __name__ == "__main__":
    unittest.main()
