from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import transport_house_copula as transport


class TransportTests(unittest.TestCase):
    def setUp(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("Numerical transport stack optional")
        self.np = np

    def fixture(self):
        matrix = self.np.full((5, 5), .04)
        groups = [dict(dimension=dimension, group=str(i), available=True,
                       prior_joint=(matrix*mass).tolist())
                  for dimension in ("AGE6", "EDUC") for i, mass in enumerate((.4, .6))]
        return dict(prior_joint=matrix.tolist(), groups=groups,
                    direct_2022_house_prior_joint=matrix.tolist())

    def test_one_exactly_preserves_baseline_and_disclosure_fields(self):
        state = self.fixture()
        state["groups"].append(dict(dimension="AGE6", group="held", available=False, prior_joint=None))
        result, decision = transport.stress_state(state, 1.)
        self.assertEqual(result, state)
        self.assertFalse(decision["changed"])

    def test_all_partitions_and_group_year_margins_stay_coherent(self):
        state = self.fixture()
        result, decision = transport.stress_state(state, 4.)
        self.assertTrue(decision["changed"])
        target = self.np.asarray(result["prior_joint"])
        self.assertGreater(target[0, 0], state["prior_joint"][0][0])
        for dimension in ("AGE6", "EDUC"):
            chosen = [g["prior_joint"] for g in result["groups"] if g["dimension"] == dimension]
            self.np.testing.assert_allclose(self.np.asarray(chosen).sum(axis=0), target, atol=3e-12, rtol=0)
        for old, new in zip(state["groups"], result["groups"]):
            before, after = self.np.asarray(old["prior_joint"]), self.np.asarray(new["prior_joint"])
            self.np.testing.assert_allclose(before.sum(axis=0), after.sum(axis=0), atol=3e-12, rtol=0)
            self.np.testing.assert_allclose(before.sum(axis=1), after.sum(axis=1), atol=3e-12, rtol=0)
        self.assertEqual(result["direct_2022_house_prior_joint"], state["direct_2022_house_prior_joint"])

    def test_source_margin_bounds_reject_infeasible_party_retention(self):
        a = self.np.asarray([.9, .025, .025, .025, .025])
        b = self.np.asarray([.025, .9, .025, .025, .025])
        matrices = self.np.asarray([.5*a[:, None]*b[None, :], .5*b[:, None]*a[None, :]])
        original = matrices.sum(axis=0)
        target, iterations = transport.project_batch(original[None, :, :], original.sum(axis=1)[None, :],
                                                     original.sum(axis=0)[None, :], 64.)
        self.np.testing.assert_allclose(target[0].sum(axis=0), original.sum(axis=0), atol=3e-12, rtol=0)
        value, decision = transport.partition_projection(matrices, target[0], 64.)
        self.assertIsNone(value)
        self.assertEqual(decision["reason"], "fixed_group_margin_cell_bound")

    def test_zero_mass_opaque_remainder_stays_zero(self):
        state = self.fixture()
        state["groups"].append(dict(dimension="AGE6", group="unshown", available=True,
                                   prior_joint=self.np.zeros((5, 5)).tolist()))
        result, decision = transport.stress_state(state, 4.)
        self.assertTrue(decision["changed"])
        self.assertEqual(result["groups"][-1], state["groups"][-1])


if __name__ == "__main__":
    unittest.main()
