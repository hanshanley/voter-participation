import math
import unittest

from scripts import norc_house_model as model
from scripts.fit_norc_house_model import choice, features


class NorcHouseModelTests(unittest.TestCase):
    def test_r_plus_four_to_d_plus_twelve_is_sixteen_points(self):
        joint = [[.38, .02, 0, .08, 0], [.05, .40, 0, .07, 0],
            [0]*5, [.13, .04, 0, .03, 0], [0]*5]
        rows, columns = [.48, .52, 0, .3, 0], [.56, .44, 0, .3, 0]
        point, _ = model.project([[v+1e-4 for v in r] for r in joint],
            [v/sum(rows) for v in rows], [v/sum(columns) for v in columns])
        result = model.accounting(point)
        self.assertAlmostEqual(result["previous_margin_pp"], -4)
        self.assertAlmostEqual(result["current_margin_pp"], 12)
        self.assertAlmostEqual(sum(result["contributions_pp"].values()), 16)

    def test_switching_entry_exit_and_unknown_have_distinct_roles(self):
        self.assertEqual(model.mechanism("D", "R"), "switching")
        self.assertEqual(model.mechanism("N", "D"), "entry")
        self.assertEqual(model.mechanism("R", "N"), "exit")
        self.assertEqual(model.mechanism("U", "D"), "unresolved")
        self.assertEqual(model.mechanism("D", "U"), "unresolved")
        self.assertEqual(model.mechanism("O", "D"), "other_choice")

    def test_symmetric_denominator_effects_reconcile_and_group_allocations_add(self):
        joint = [[.1, .02, .01, .07, .01], [.08, .2, .01, .14, .02],
            [.01, .02, .01, .01, .01], [.1, .02, .01, .1, .01], [.01, .01, .01, .01, .01]]
        result = model.accounting(joint)
        self.assertAlmostEqual(result["allocated_change_pp"], result["total_change_pp"])
        rows = [sum(row) for row in joint]
        columns = [sum(joint[i][j] for i in range(5)) for j in range(5)]
        left = model.accounting([[v*.3 for v in row] for row in joint], rows, columns)
        right = model.accounting([[v*.7 for v in row] for row in joint], rows, columns)
        for key in model.MECHANISMS:
            self.assertAlmostEqual(left["contributions_pp"][key]+right["contributions_pp"][key],
                result["contributions_pp"][key])

    def test_endpoint_calibration_keeps_real_zero_and_unknown_separate(self):
        prior = [[.04]*5 for _ in range(5)]
        rows, columns = [.2, .3, 0, .4, .1], [.3, .25, 0, .35, .1]
        result, _ = model.project(prior, rows, columns)
        self.assertTrue(all(result[2][j] == 0 and result[j][2] == 0 for j in range(5)))
        self.assertAlmostEqual(sum(result[4]), .1)
        self.assertAlmostEqual(sum(result[i][4] for i in range(5)), .1)
        self.assertTrue(all(math.isclose(sum(row), rows[i], abs_tol=1e-10)
            for i, row in enumerate(result)))

    def test_unanchored_source_sensitivity_does_not_change_source_endpoint_margins(self):
        state = dict(prior_joint=[[.04]*5 for _ in range(5)])
        q, _, rows, columns, frame, _ = model.fit_state(state, dict(status="unavailable"), affinity=2)
        self.assertIsNone(frame)
        for i in range(5):
            self.assertAlmostEqual(sum(q[i]), rows[i])
            self.assertAlmostEqual(sum(q[j][i] for j in range(5)), columns[i])

    def test_retention_does_not_create_margin_points(self):
        joint = [[0.0]*5 for _ in range(5)]
        for i, value in enumerate((.3, .4, .1, .1, .1)):
            joint[i][i] = value
        self.assertTrue(all(v == 0 for v in model.accounting(joint)["contributions_pp"].values()))

    def test_native_ap_recalled_house_codes_are_not_chep_party_codes(self):
        self.assertEqual(choice("(1) The Republican candidate", reversed_parties=True), "R")
        self.assertEqual(choice("1"), "D")
        self.assertEqual(choice("4"), "N")
        self.assertEqual(choice("99"), "U")
        self.assertEqual(choice(""), "U")

    def test_current_outcomes_and_identifiers_never_enter_prediction_features(self):
        row = dict(state="TX", p24="D", h22="D", AGE6="3",
            HOUSEVOTE="2", LIKELYVOTER="2", LVB="5", SU_ID="private")
        values = features(row, ("AGE6",))
        self.assertEqual(set(values), {"state", "p24", "h22", "AGE6", "p24_AGE6", "h22_AGE6"})

    def test_preconditioning_prediction_never_uses_current_party_split(self):
        prior = [[.04]*5 for _ in range(5)]
        a = dict(D=60, R=40, O=2)
        b = dict(D=40, R=60, O=2)
        previous = dict(D=45, R=55, O=3)
        self.assertEqual(model.predict_without_current_party_totals(prior, previous, sum(a.values())),
            model.predict_without_current_party_totals(prior, previous, sum(b.values())))


if __name__ == "__main__":
    unittest.main()
