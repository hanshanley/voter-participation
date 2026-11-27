from decimal import Decimal
import json
import unittest

from scripts.civic_group_rates import aggregate, build


def previous(group="male", dimension="SEX", public=False):
    return dict(state_code="MO", dimension=dimension, group=group, label=group,
                modeled_voter_pct="50" if public else None, n=100 if public else None)


class RoundedRatesTests(unittest.TestCase):
    def reference(self, groups):
        return dict(codebook_sha256="a" * 64, groups=groups)

    def test_supported_complement_can_publish_a_rate_without_new_primitives(self):
        cells = {("MO", "SEX", "male"): [150, 100, Decimal(200), Decimal("101.15")]}
        result = build(cells, self.reference([previous()]))
        row = result["groups"][0]
        self.assertEqual(row["modeled_voter_pct"], "50.6")
        self.assertEqual(row["modeled_nonvoter_pct"], "49.4")
        self.assertIsNone(row["n"])
        self.assertIsNone(row["source_weight_concentration_effective_n"])
        self.assertEqual(result["newly_supported_rate_only_groups"], 1)
        self.assertNotIn("101.15", json.dumps(result))
        self.assertNotIn("weight_squared", json.dumps(result))

    def test_support_unknown_and_gender_guards_are_not_removed(self):
        groups = [previous(), previous("unknown"), previous("female", "GENDER3")]
        for n, voters in [(99, 50), (100, 29), (100, 71)]:
            cells = {("MO", item["dimension"], item["group"]): [n, voters, Decimal(100), Decimal(50)]
                     for item in groups}
            self.assertTrue(all(row["modeled_voter_pct"] is None
                                for row in build(cells, self.reference(groups))["groups"]))
        cells = {("MO", item["dimension"], item["group"]): [100, 50, Decimal(100), Decimal(50)]
                 for item in groups}
        rows = build(cells, self.reference(groups))["groups"]
        self.assertEqual(rows[0]["modeled_voter_pct"], "50.0")
        self.assertTrue(all(row["modeled_voter_pct"] is None for row in rows[1:]))

    def test_previous_public_rates_are_checked_not_silently_recomputed_on_different_bins(self):
        ref = self.reference([previous(public=True)])
        cells = {("MO", "SEX", "male"): [100, 50, Decimal(100), Decimal(50)]}
        self.assertEqual(build(cells, ref)["groups"][0]["modeled_voter_pct"], "50.0")
        cells["MO", "SEX", "male"][3] = Decimal(51)
        with self.assertRaisesRegex(ValueError, "no longer reconciles"):
            build(cells, ref)

    def test_native_groups_use_whole_weight_and_do_not_export_individual_rows(self):
        records = [dict(P_STATE="MO", LIKELYVOTER=str(1 + i % 2), CHEP_WEIGHT="2",
                        AGE6="1", EDUC="2", SEX="1", RACETH5="88", INCOME="3", RUCC="1")
                   for i in range(100)]
        cells, cases, states = aggregate(records)
        self.assertEqual(cases, 100)
        self.assertEqual(states, {"MO"})
        self.assertEqual(cells["MO", "overall", "all"], [100, 50, Decimal(200), Decimal(100)])
        self.assertIn(("MO", "RACETH5", "other_unknown"), cells)
        self.assertNotIn(("MO", "RACETH5", "88"), cells)


if __name__ == "__main__":
    unittest.main()
