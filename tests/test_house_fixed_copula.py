from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import house_fixed_copula as copula


class SelectionTests(unittest.TestCase):
    def test_ties_prefer_independence_without_changing_the_grid(self):
        self.assertEqual(copula.select_theta({value: 1. for value in copula.THETAS}), 1)

    def test_incomplete_calibration_curve_rejected(self):
        with self.assertRaises(ValueError):
            copula.select_theta({1.: 1.})


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("Private numerical stack optional")
        self.np = np

    def test_independence_exactly_reuses_original_outer_product(self):
        rows = self.np.asarray([[.2, .5, .3]])
        columns = self.np.asarray([[.4, .1, .2, .3]])
        expected = rows[:, :, None]*columns[:, None, :]
        joint, iterations = copula.couple(rows, columns, 1.)
        self.np.testing.assert_array_equal(joint, expected)
        self.assertEqual(iterations, 0)

    def test_association_changes_joint_but_preserves_every_marginal(self):
        rows = self.np.asarray([[.2, .5, .3], [.6, .3, .1]])
        columns = self.np.asarray([[.4, .1, .2, .3], [.2, .5, .1, .2]])
        joint, iterations = copula.couple(rows, columns, 16.)
        self.np.testing.assert_allclose(joint.sum(axis=2), rows, atol=3e-12, rtol=0)
        self.np.testing.assert_allclose(joint.sum(axis=1), columns, atol=3e-12, rtol=0)
        diagnostic = copula.prediction_diagnostics(joint, rows, columns, 16.)
        self.assertLess(diagnostic["maximum_dual_certificate_error"], 1e-10)
        self.assertGreater(float(joint[0, 0, 0]), rows[0, 0]*columns[0, 0])

    def test_invalid_shapes_and_nonpositive_values_rejected(self):
        with self.assertRaises(ValueError):
            copula.couple(self.np.asarray([[0., 1.]]), self.np.asarray([[.5, .5]]), 2.)
        with self.assertRaises(ValueError):
            copula.couple(self.np.asarray([[.5, .5]]), self.np.asarray([[.5, .5]]), -1.)


if __name__ == "__main__":
    unittest.main()
