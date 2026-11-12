import copy
import json
import unittest

from scripts.house_panel_public import AP_QUERY, CES_QUERY, RATE, SELECTIONS, STATES, WEIGHTS, replay


def sufficient():
    decisions = [dict(source="CES_retained_panel", scope=scope, weight_frame=weight,
                      selection=selection, available=False,
                      reason="outside_prespecified_public_scope", cells=None)
                 for scope in (*STATES, "UNLOCATED", "ALL_SOURCE")
                 for weight in WEIGHTS for selection in SELECTIONS]
    decisions.append(dict(zip(("source", "scope", "weight_frame", "selection"), AP_QUERY),
                          available=False, reason="whole_table_source_support_hold", cells=None))
    for row in decisions:
        identity = tuple(row[key] for key in ("source", "scope", "weight_frame", "selection"))
        if identity in (AP_QUERY, CES_QUERY):
            row.update(available=True, reason=None, cells={
                key: dict(n=30, weight="30", squared_weight="30") for key in ("DD", "DR", "RD", "RR")})
    return dict(decisions=decisions)


class PublicReplayTests(unittest.TestCase):
    def test_complete_replay_and_correct_conditional_denominators(self):
        results = replay(sufficient())
        summary = json.loads(results["summary.json"])
        self.assertEqual(len(results), 5)
        self.assertEqual(summary["query_decisions"], 319)
        self.assertEqual(summary["whole_table_holds"], 317)
        self.assertEqual(summary["selected_source_rates"]["CES_retained_panel"][RATE], "50")
        self.assertFalse(summary["independent_population_validation"])

    def test_missing_query_rejected(self):
        value = sufficient()
        value["decisions"].pop()
        with self.assertRaises(ValueError):
            replay(value)

    def test_partial_suppression_and_state_release_rejected(self):
        value = sufficient()
        primary = next(row for row in value["decisions"] if row["source"] == "CES_retained_panel" and row["available"])
        held = value["decisions"][0]
        held.update(cells=copy.deepcopy(primary["cells"]))
        with self.assertRaises(ValueError):
            replay(value)
        held.update(available=True, reason=None)
        with self.assertRaises(ValueError):
            replay(value)

    def test_insufficient_or_inconsistent_sufficient_cells_rejected(self):
        for change in ({"n": 29}, {"squared_weight": "0.001"}):
            value = sufficient()
            next(row for row in value["decisions"] if row["available"])["cells"]["DR"].update(change)
            with self.assertRaises(ValueError):
                replay(value)


if __name__ == "__main__":
    unittest.main()
