import unittest

from scripts.native_reconciliation import reconcile


class NativeReconciliationTests(unittest.TestCase):
    def test_signed_gap_retained_without_repairing_either_source(self):
        queries = {"units": dict(rows=[dict(ballots=100)]),
            "candidates": dict(rows=[dict(votes=80)]),
            "accounting": dict(rows=[dict(blanks=12, overvotes=1)])}
        checks = [dict(id="accounting", policy="record_discrepancy",
            left=[dict(query="units", fields=["ballots"])],
            right=[dict(query="candidates", fields=["votes"]),
                   dict(query="accounting", fields=["blanks", "overvotes"])])]
        result = reconcile(queries, checks)
        self.assertTrue(result["required_checks_passed"])
        self.assertEqual(result["checks"][0]["rows"][0]["signed_left_minus_right"], 7)
        self.assertEqual(queries["units"]["rows"][0]["ballots"], 100)

    def test_missing_group_is_not_zero_and_repeated_stock_is_not_summed(self):
        queries = {"units": dict(rows=[dict(county="A", stock=10), dict(county="A", stock=10)]),
            "control": dict(rows=[dict(county="A", stock=10), dict(county="B", stock=0)])}
        checks = [dict(id="stocks", keys=["county"],
            left=[dict(query="units", fields=["stock"], operation="unique")],
            right=[dict(query="control", fields=["stock"], operation="unique")])]
        result = reconcile(queries, checks)
        self.assertFalse(result["required_checks_passed"])
        rows = result["checks"][0]["rows"]
        self.assertEqual(rows[0]["signed_left_minus_right"], 0)
        self.assertIsNone(rows[1]["left"])
        self.assertIsNone(rows[1]["signed_left_minus_right"])
        queries["units"]["rows"][1]["stock"] = 11
        with self.assertRaises(ValueError):
            reconcile(queries, checks)

    def test_separate_fields_detect_offsetting_errors_and_policy_typos_fail_closed(self):
        queries = {"a": dict(rows=[dict(D=9, R=11)]), "b": dict(rows=[dict(D=10, R=10)])}
        check = dict(id="parties", each_field=["D", "R"],
            left=[dict(query="a", fields=["$field"])],
            right=[dict(query="b", fields=["$field"])])
        result = reconcile(queries, [check])
        self.assertFalse(result["required_checks_passed"])
        self.assertEqual([row["rows"][0]["signed_left_minus_right"] for row in result["checks"]], [-1, 1])
        with self.assertRaises(ValueError):
            reconcile(queries, [dict(check, policy="required_match")])
        check["left"][0]["exclude_total"] = True
        with self.assertRaises(ValueError):
            reconcile(queries, [check])


if __name__ == "__main__":
    unittest.main()
