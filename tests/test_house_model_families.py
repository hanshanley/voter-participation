"""Focused guards for fair model-family comparisons and demographic privacy."""

import unittest
from importlib.util import find_spec

if find_spec("numpy") and find_spec("sklearn"):
    import numpy as np
    from scripts import fit_house_model_families as family
else:
    np = family = None


@unittest.skipIf(family is None, "Private fitting tests require the optional numpy/scikit-learn stack")
class HouseModelFamilyTests(unittest.TestCase):
    def test_outcomes_and_identifiers_never_become_predictors(self):
        for field in ("HOUSEVOTE", "LIKELYVOTER", "LVB", "respondent_ID", "QVOTE2022S"):
            with self.assertRaises(ValueError):
                family.checked_predictors([{field: "1"}], [field])

    def test_bridge_application_projects_current_sex_and_context_out(self):
        fields = ["state", "p24", "h22", "AGE6"]
        rows = [dict(state="AA", p24="D", h22="D", AGE6="1"),
                dict(state="BB", p24="R", h22="R", AGE6="2")]
        for name in family.FAMILIES:
            encoder, expected = family.design(rows, fields, name, "house24_bridge")
            current = [dict(row, SEX="1", RUCC="3") for row in rows]
            actual = family.transform(encoder, current, fields, name, "house24_bridge")
            if hasattr(expected, "toarray"):
                expected, actual = expected.toarray(), actual.toarray()
            np.testing.assert_array_equal(expected, actual)
            current[0]["HOUSEVOTE"] = "D"
            with self.assertRaises(ValueError):
                family.transform(encoder, current, fields, name, "house24_bridge")

    def test_unseen_historical_state_is_missing_not_another_state(self):
        fields = ["state", "prior_2020_president", "age", "education"]
        rows = [dict(state="AA", prior_2020_president="D", age="1", education="1")]
        encoder, _ = family.design(rows, fields, family.FAMILIES[0], "historical_transfer")
        result = family.transform(encoder, [dict(rows[0], state="BB")], fields,
                                  family.FAMILIES[0], "historical_transfer")
        self.assertEqual(result[0, 0], -1)
        self.assertTrue(np.all(result[0, 1:] == 0))

    def test_synthetic_support_floor_preserves_probability_partition(self):
        result = family.support_probabilities(np.asarray([[0., 1., 0., 0., 0.]]), 1e-8)
        self.assertTrue(np.all(result > 0))
        self.assertAlmostEqual(result.sum(), 1)
        self.assertGreater(result[0, 1], .99999)
        with self.assertRaises(ValueError):
            family.support_probabilities(result, 0)

    def test_metric_rejects_missing_classes_or_invalid_probability_mass(self):
        labels, weights = np.arange(5), np.ones(5)
        for values in (np.ones((5, 4)) / 4, np.ones((5, 5)), np.full((5, 5), np.nan)):
            with self.assertRaises(ValueError):
                family.metrics(labels, values, weights)


if __name__ == "__main__":
    unittest.main()
