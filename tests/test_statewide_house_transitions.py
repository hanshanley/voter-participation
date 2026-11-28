import unittest
from scripts.statewide_house_transitions import association_kernel, endpoint, fit, statistics


def source_prior():
    values = [[4 if i == j else 1 for j in range(5)] for i in range(5)]
    total = sum(map(sum, values))
    return [[value/total for value in row] for row in values]


class StatewideTransitionTests(unittest.TestCase):
    def test_house_omission_is_not_staying_home(self):
        before = endpoint(dict(D=40, R=40, O=10), dict(ballots=100, eligible=100))
        after = endpoint(dict(D=20, R=20, O=10), dict(ballots=100, eligible=100))
        result = fit(source_prior(), before, after, churn=0)
        self.assertEqual(result['gross_pct']['no_ballot'], 0)
        self.assertGreater(result['gross_pct']['house_choice'], 0)
        self.assertEqual(result['contributions_pp']['staying_home'], 0)
        self.assertAlmostEqual(sum(result['gross_pct'].values()), 100)

    def test_actual_house_baselines_and_all_six_targets_are_retained(self):
        before = endpoint(dict(D=40, R=60, O=5), dict(ballots=110, eligible=200))
        after = endpoint(dict(D=50, R=50, O=10), dict(ballots=120, eligible=210))
        result = fit(source_prior(), before, after)
        for i in range(6):
            self.assertAlmostEqual(sum(result['joint'][i]), result['rows'][i], places=7)
            self.assertAlmostEqual(sum(row[i] for row in result['joint']), result['columns'][i], places=7)
        self.assertAlmostEqual(result['previous_D_share'], 40)
        self.assertAlmostEqual(result['current_D_share'], 50)
        self.assertAlmostEqual(sum(result['contributions_pp'].values()), 10)
        self.assertGreater(result['gross_pct']['no_ballot'], 0)

    def test_zero_candidate_party_is_a_constraint_not_a_missing_state(self):
        before = endpoint(dict(D=100, R=0, O=0), dict(ballots=100, eligible=100))
        after = endpoint(dict(D=0, R=100, O=0), dict(ballots=100, eligible=100))
        result = fit(source_prior(), before, after, churn=0)
        self.assertAlmostEqual(result['gross_pct']['switching'], 100)
        self.assertEqual(result['gross_pct']['no_ballot'], 0)
        self.assertAlmostEqual(result['contributions_pp']['switching'], -100)

    def test_unknown_counts_and_incompatible_ballots_cannot_be_zero_filled(self):
        with self.assertRaisesRegex(ValueError, 'Unknown House'):
            endpoint(dict(D=None, R=30, O=0), dict(ballots=50, eligible=100))
        with self.assertRaisesRegex(ValueError, 'Incompatible'):
            endpoint(dict(D=40, R=30, O=0), dict(ballots=60, eligible=100))

    def test_unlearned_house_recording_and_eligibility_associations_stay_neutral(self):
        kernel = association_kernel(source_prior())
        for index in range(6):
            self.assertEqual(kernel[3][index], 1)
            self.assertEqual(kernel[index][3], 1)
            self.assertEqual(kernel[5][index], 1)
            self.assertEqual(kernel[index][5], 1)


if __name__ == '__main__':
    unittest.main()
