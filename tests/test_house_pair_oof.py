import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import house_pair_oof as paired


class PriorFeatureTests(unittest.TestCase):
    def test_only_contemporaneous_baseline_fields_used(self):
        row = dict(CC20_410="1", birthyr_20="1980", educ_20="5", inputstate_20="48",
                   CC22_412="2", CC24_412="1", TS_g2024="7")
        result = paired.features(row, True)
        self.assertEqual(result["age20"], "30_44")
        self.assertEqual(result["educ20"], "5")
        for key in ("CC22_412", "CC24_412", "TS_g2024", "weights"):
            self.assertNotIn(key, result)
        row.update(CC22_412="1", CC24_412="2", TS_g2024="1")
        self.assertEqual(result, paired.features(row, True))

    def test_distinct_prior_contest_and_election_nonvote_preserved(self):
        self.assertEqual(paired.prior("5"), "CONTEST_NONVOTE")
        self.assertEqual(paired.prior("6"), "REPORTED_NONVOTE")
        self.assertEqual(paired.prior("NA"), "UNKNOWN")

    def test_unknown_baseline_profile_is_not_dropped(self):
        result = paired.features(dict(CC20_410="NA", birthyr_20="NA", educ_20="NA", inputstate_20="-1"), True)
        self.assertEqual(result["age20"], "UNKNOWN")
        self.assertEqual(result["educ20"], "UNKNOWN")
        self.assertEqual(result["state20"], "UNKNOWN")


class NumericalTests(unittest.TestCase):
    def setUp(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("Private numerical-stack test; standard-library feature tests still run")
        self.np = np

    def test_prior_only_split_is_deterministic_and_exhaustive(self):
        first = paired.folds(["D"] * 53 + ["R"] * 57, 123, 5)
        self.np.testing.assert_array_equal(first, paired.folds(["D"] * 53 + ["R"] * 57, 123, 5))
        self.assertEqual(set(first), set(range(5)))

    def test_unobserved_training_classes_have_explicit_prior_support(self):
        values = paired.smoothed(self.np.asarray([[1., 0., 0.]]),
                                 self.np.asarray([0, 0]), self.np.ones(2), 3)
        self.assertTrue((values > 0).all())
        self.assertAlmostEqual(values.sum(), 1)

    def test_pooled_predictions_use_only_training_outcomes(self):
        result = paired.pooled(["D", "D"], ["D", "UNKNOWN"], self.np.asarray([0, 0]), self.np.ones(2), 3)
        self.assertTrue((result > 0).all())
        self.np.testing.assert_allclose(result.sum(axis=1), self.np.ones(2))

    def test_joint_brier_and_logloss_use_full_pair_distribution(self):
        result = paired.metrics(self.np.asarray([[.75, .25], [.25, .75]]),
                                self.np.asarray([0, 1]), self.np.ones(2))
        self.assertAlmostEqual(result["brier_sum"], .25)
        self.assertAlmostEqual(result["nll_sum"], -2 * self.np.log(.75))

    def test_completed_prediction_cache_never_refits(self):
        try:
            import sklearn
        except ImportError:
            self.skipTest("Private fitting stack is optional")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "completed.npz"
            paired.secure_npz(path, probabilities=self.np.asarray([[.75, .25]]),
                              metadata=self.np.asarray("frozen"))
            with patch("sklearn.linear_model.LogisticRegression") as constructor:
                values, reused = paired.cached_head(path, None, self.np.zeros((1, 1)), None, None, 2, "frozen")
                constructor.assert_not_called()
            self.assertTrue(reused)
            self.np.testing.assert_allclose(values, [[.75, .25]])
            with self.assertRaises(ValueError):
                paired.cached_head(path, None, self.np.zeros((1, 1)), None, None, 2, "different")


if __name__ == "__main__":
    unittest.main()
