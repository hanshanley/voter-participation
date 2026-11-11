from decimal import Decimal as D
import json
import unittest

from scripts import flow_identification as flow


def tables(rows, columns, index=0, prefix=()):
    n = len(rows)
    if index == n*n:
        if not any(rows + columns):
            yield [list(prefix[i*n:(i+1)*n]) for i in range(n)]
        return
    i, j = divmod(index, n)
    for count in range(min(rows[i], columns[j])+1):
        rr, cc = rows[:], columns[:]
        rr[i] -= count
        cc[j] -= count
        yield from tables(rr, cc, index+1, prefix+(count,))


class FlowIdentificationTests(unittest.TestCase):
    def test_bounds_match_exhaustively_enumerated_integer_tables(self):
        rows, columns = [2, 1, 1], [1, 2, 1]
        all_tables = list(tables(rows, columns))
        self.assertGreater(len(all_tables), 1)
        for metric in flow.METRICS[:4]:
            mask = flow.mask_for("DRX", metric)
            values = [sum(q[i][j] for i in range(3) for j in range(3) if mask[i][j])
                for q in all_tables]
            bounds = flow.bounds(list(map(D, rows)), list(map(D, columns)), "DRX", metric)
            self.assertEqual(D(bounds["lower"]["value"]), min(values))
            self.assertEqual(D(bounds["upper"]["value"]), max(values))

    def test_forced_switching_and_real_zero_other_row(self):
        result = flow.bounds(list(map(D, (8, 1, 0, 1))),
            list(map(D, (1, 8, 0, 1))), "DRON", "switching")
        self.assertEqual(D(result["lower"]["value"]), 6)
        self.assertEqual(D(result["upper"]["value"]), 9)

    def test_unknown_other_is_not_zero_or_no_vote(self):
        comparison = dict(previous=dict(D=4, R=6), current=dict(D=5, R=5))
        categories, targets = flow.endpoints(comparison, D("12.5"))
        self.assertEqual(categories, "DRX")
        for metric in ("other_choice", "no_current_contest_vote"):
            self.assertIsNone(flow.bounds(*targets, categories, metric)["lower"])
        comparison["previous"]["O"] = comparison["current"]["O"] = 0
        self.assertEqual(flow.endpoints(comparison, D("12.5"))[0], "DRON")

    def test_disjoint_frame_allows_no_retention_and_no_switching(self):
        comparison = dict(previous=dict(D=4, R=6, O=1), current=dict(D=8, R=3, O=2))
        categories, targets = flow.endpoints(comparison, D(24))
        for metric in ("retention", "switching"):
            self.assertEqual(D(flow.bounds(*targets, categories, metric)["lower"]["value"]), 0)

    def test_invalid_marginals_fail_closed(self):
        with self.assertRaises(ValueError):
            flow.maximum(list(map(D, (1, 2, 3))), list(map(D, (1, 2, 4))), [[True]*3]*3)
        with self.assertRaises(ValueError):
            flow.endpoints(dict(previous=dict(D=2, R=3), current=dict(D=3, R=4)), D(6))
        with self.assertRaises(ValueError):
            flow.endpoints(dict(previous=dict(D=2, R=3, O=0), current=dict(D=3, R=4)), D(10))

    def test_entry_uses_current_not_previous_major_party_denominator(self):
        values = flow.bounds(list(map(D, (4, 2, 4))), list(map(D, (3, 1, 6))),
            "DRX", "entry_to_major_party")
        self.assertEqual(values["denominator"], "4")
        self.assertEqual(values["denominator_definition"], "current_D_plus_R")

    def test_viewer_preserves_holds_and_omits_witness_not_semantics(self):
        bounds = flow.bounds(list(map(D, (4, 2, 4))), list(map(D, (3, 1, 6))),
            "DRX", "switching")
        unavailable = dict(id="AK-house", state_code="AK", office="house",
            status="unavailable", reason="No compatible endpoints")
        available = dict(id="TX-house", state_code="TX", office="house",
            status="conditional_bounds_not_identified_histories")
        result = dict(accepted_science_sha256="accepted", decisions=[unavailable, available],
            cases=[dict(id="TX-house", frame_name="accepted_frame_1.0", frame_units="10",
                unknown_other_is_opaque_X=True, metrics=dict(switching=bounds))])
        selected = flow.viewer(result)["rows"]
        self.assertIsNone(selected[0]["bounds"])
        self.assertEqual(selected[1]["bounds"]["switching"]["lower_percent"], bounds["lower_percent"])
        self.assertNotIn("upper", selected[1]["bounds"]["switching"])
        self.assertTrue(selected[1]["unknown_other_is_opaque_X"])

    def test_complete_query_bytes_survive_saved_json_round_trip(self):
        rows, columns = list(map(D, (4, 2, 4))), list(map(D, (3, 1, 6)))
        identity = dict(id="TX-house", state_code="TX", office="house")
        case = dict(identity, case_id="TX-house|accepted_frame_1.0", frame_name="accepted_frame_1.0",
            frame_units="10", unknown_other_is_opaque_X=True, categories=list("DRX"),
            target_rows=list(map(str, rows)), target_columns=list(map(str, columns)),
            metrics={key: flow.bounds(rows, columns, "DRX", key) for key in flow.METRICS})
        result = dict(accepted_science_sha256="accepted",
            decisions=[dict(identity, status="conditional_bounds_not_identified_histories")],
            cases=[case])
        self.assertEqual(flow.result_files(result), flow.result_files(json.loads(flow.encoded(result))))


if __name__ == "__main__":
    unittest.main()
