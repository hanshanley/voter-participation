from pathlib import Path
import copy
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import transport_house_copula as transport
from build_house_copula_profiles import check_prepared_projection


class PreparedReplayTests(unittest.TestCase):
    def fixture(self):
        state = dict(prior_joint=[[.04]*5 for i in range(5)],
            direct_2022_house_prior_joint=[[.04]*5 for i in range(5)],
            groups=[dict(dimension="AGE6", group="one", label="One", available=True,
                         prior_joint=[[.04]*5 for i in range(5)])])
        original = dict(states={"AA": state})
        prepared = copy.deepcopy(original)
        prepared["structural_association_stress"] = dict(profile="full", requested_theta=2,
                                                         current_return_targets_used=False)
        decisions = {"AA": dict(requested_theta=2, effective_theta=1, feasibility_exponent=0)}
        return original, prepared, decisions

    def test_prepared_source_constraints_need_no_numerical_dependencies(self):
        original, prepared, decisions = self.fixture()
        check_prepared_projection(original, prepared, decisions, 2, "full")

    def test_reject_prepared_margin_or_association_substitution(self):
        for kind in ("margin", "theta", "return"):
            original, prepared, decisions = self.fixture()
            if kind == "margin":
                prepared["states"]["AA"]["groups"][0]["prior_joint"][0][0] += .01
            elif kind == "theta":
                decisions["AA"]["effective_theta"] = 2
                decisions["AA"]["feasibility_exponent"] = 1
            else:
                prepared["structural_association_stress"]["current_return_targets_used"] = True
            with self.assertRaises(ValueError):
                check_prepared_projection(original, prepared, decisions, 2, "full")


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
