import copy
from decimal import Decimal
import unittest

from scripts.registered_control_successor import FLAGS
from scripts.state_reference_model import revise


class StateReferenceModelTests(unittest.TestCase):
    def fixture(self):
        url = "https://example.gov/state"
        state = dict(year="2026", state_code="AR", control_id="reporting-AR", civic_source_n="10",
            control_measure="reported_cast_ballots", control_native_numerator="30", reported_cast_ballots="30",
            control_registered_denominator="300", control_denominator_basis="active_registered_voters",
            control_native_time="Model old time", control_source_url=url,
            reported_ballots_per_native_registered_denominator_pct="10", house_candidate_vote_sum_context="25")
        control = dict(year="2026", id="reporting-AR", state_code="AR", geographic_level="state",
            selected_state_reference="True", measure="reported_cast_ballots", numerator="30", denominator="300",
            denominator_basis="active_registered_voters", source_url=url, source_time_label="Model old time")
        scenario = dict(year="2026", state_code="AR", control_id="reporting-AR", civic_source_n="10",
            control_measure="reported_cast_ballots", native_registered_denominator="300",
            native_denominator_basis="active_registered_voters", source_url=url, source_time_label="Model old time",
            civic_weight="10", civic_modeled_voter_weight="6", civic_modeled_nonvoter_weight="4",
            conditional_modeled_voter_count="180", conditional_modeled_nonvoter_count="120",
            reported_cast_ballot_measure_control="30", reported_cast_minus_conditional_modeled_voter_count="-150",
            **{flag: "False" for flag in FLAGS})
        tables = ([state, dict(state, state_code="NC", control_id="reporting-NC")],
            [control, dict(control, id="monthly-AR", selected_state_reference="False"),
             dict(control, id="held-envelopes", selected_state_reference="False")],
            [scenario, dict(scenario, control_id="monthly-AR")])
        native = dict(numerator=100, denominator=310, source_url=url, source_time_label="New native time",
            native_measure="Ballots Counted", denominator_label="Active Registered Voters",
            native_status="Unofficial; finality unknown", previous_runtime_ballots=20,
            previous_runtime_registered=299)
        review = dict(expected_states=["AR", "NC"], expected_table_rows=[2, 3, 2],
            state_code="AR", control_id="reporting-AR", year=2026,
            previous_model_reference=dict(ballots=30, registered=300, clock="Model old time",
                                          denominator_basis="active_registered_voters"),
            registered_frame_review="Reviewed changed source active stock; survey transport unvalidated")
        return tables, native, review

    def test_only_selected_model_frame_changes_with_unchanged_source_probabilities(self):
        tables, native, review = self.fixture()
        original = copy.deepcopy(tables)
        result, delta, changes = revise(tables, native, review)
        scenario = result[2][0]
        self.assertEqual(scenario["conditional_modeled_voter_count"], "186")
        self.assertEqual(scenario["conditional_modeled_nonvoter_count"], "124")
        self.assertEqual(scenario["reported_cast_minus_conditional_modeled_voter_count"], "-86")
        self.assertEqual(sum(Decimal(scenario[key]) for key in (
            "conditional_modeled_voter_count", "conditional_modeled_nonvoter_count")), 310)
        for key in ("civic_weight", "civic_modeled_voter_weight", "civic_modeled_nonvoter_weight", *FLAGS):
            self.assertEqual(scenario[key], original[2][0][key])
        self.assertEqual(result[0][0]["house_candidate_vote_sum_context"], "25")
        self.assertEqual(result[0][1:], original[0][1:])
        self.assertEqual(result[1][1:], original[1][1:])
        self.assertEqual(result[2][1:], original[2][1:])
        self.assertEqual(sum(row["changed"] for row in changes), 1)
        self.assertEqual(tables, original)
        self.assertEqual((delta["model_reference_count_difference"], delta["runtime_reference_count_difference"]), (70, 80))
        self.assertEqual((delta["model_registered_difference"], delta["runtime_registered_difference"]), (10, 11))

    def test_stale_model_preimage_or_missing_review_cannot_authorize_new_register(self):
        for change in ("register", "clock", "basis", "review", "count", "source"):
            tables, native, review = self.fixture()
            if change == "review":
                review["registered_frame_review"] = ""
            elif change == "source":
                native["source_url"] = "https://different.example/source"
            else:
                key, value = dict(register=("registered", 299), clock=("clock", "Other"),
                                  basis=("denominator_basis", "VEP"), count=("ballots", 29))[change]
                review["previous_model_reference"][key] = value
            with self.subTest(change=change), self.assertRaises(ValueError):
                revise(tables, native, review)

    def test_weight_changes_nonreproducing_means_and_new_behavioral_qualification_fail(self):
        for key, value in (("civic_weight", "11"), ("conditional_modeled_voter_count", "179"), (FLAGS[0], "True")):
            tables, native, review = self.fixture()
            tables[2][0][key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                revise(tables, native, review)

    def test_native_zero_is_kept_but_negative_boolean_or_excess_count_fails(self):
        tables, native, review = self.fixture()
        native["numerator"] = 0
        result, _, _ = revise(tables, native, review)
        self.assertEqual(result[0][0]["reported_cast_ballots"], "0")
        for value in (-1, True, 311):
            native["numerator"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                revise(tables, native, review)

    def test_unchanged_native_reference_does_not_create_another_version(self):
        tables, native, review = self.fixture()
        native.update(numerator=30, denominator=300, source_time_label="Model old time")
        with self.assertRaisesRegex(ValueError, "reuse"):
            revise(tables, native, review)


if __name__ == "__main__":
    unittest.main()
