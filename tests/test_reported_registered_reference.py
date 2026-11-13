import copy
import unittest

from scripts.registered_control_successor import FLAGS
from scripts.reported_registered_reference import group_controls, revise


class ReportedRegisteredReferenceTests(unittest.TestCase):
    def fixture(self):
        url = "https://example.gov/reporting.json"
        state = dict(year="2026", state_code="AR", control_id="reporting-AR",
            civic_source_n="10", control_measure="reported_cast_ballots",
            control_native_numerator="30", reported_cast_ballots="30",
            control_registered_denominator="300", control_denominator_basis="registered_source_units",
            control_source_url=url, control_native_time="Earlier result",
            reported_ballots_per_native_registered_denominator_pct="10",
            house_candidate_vote_sum_context="25")
        control = dict(id="reporting-AR", year="2026", state_code="AR",
            selected_state_reference="True", geographic_level="state", measure="reported_cast_ballots",
            denominator="300", denominator_basis="registered_source_units", numerator="30",
            source_url=url, source_time_label="Earlier result", scope_notes="", disposition="selected")
        scenario = dict(year="2026", state_code="AR", control_id="reporting-AR",
            civic_source_n="10", control_measure="reported_cast_ballots",
            native_registered_denominator="300", native_denominator_basis="registered_source_units",
            civic_weight="10", civic_modeled_voter_weight="5", civic_modeled_nonvoter_weight="5",
            conditional_modeled_voter_count="150", conditional_modeled_nonvoter_count="150",
            reported_cast_ballot_measure_control="30", reported_cast_minus_conditional_modeled_voter_count="-120",
            source_time_label="Earlier result", control_native_status="reported",
            **{flag: "False" for flag in FLAGS})
        tables = ([state, dict(state, state_code="NC", control_id="reporting-NC")],
            [control, dict(control, id="reporting-NC", state_code="NC"),
             dict(control, id="older-AR", selected_state_reference="False",
                  disposition="same_source_same_counts_duplicate_not_added")],
            [scenario, dict(scenario, state_code="NC", control_id="reporting-NC")])
        facts = dict(total=32, registered=300, clock="New native result", source_url=url,
            previous_county_runtime_total=29, current_county_runtime_total=32)
        review = dict(expected_table_rows=[2, 3, 2], expected_states=["AR", "NC"],
            state_code="AR", year=2026, control_id="reporting-AR",
            historical_same_source_controls=["older-AR"],
            scope_review="Same source; old county and selected model snapshots have distinct dates")
        return tables, facts, review

    def test_reference_bookkeeping_advances_without_reweighting_or_changing_means(self):
        tables, facts, review = self.fixture()
        original = copy.deepcopy(tables)
        current, changes, delta = revise(tables, facts, review)
        self.assertEqual(current[0][0]["reported_cast_ballots"], "32")
        self.assertEqual(current[2][0]["reported_cast_minus_conditional_modeled_voter_count"], "-118")
        for field in ("conditional_modeled_voter_count", "conditional_modeled_nonvoter_count",
                "native_registered_denominator", "civic_weight", "civic_modeled_voter_weight"):
            self.assertEqual(current[2][0][field], tables[2][0][field])
        self.assertEqual(current[0][0]["house_candidate_vote_sum_context"], "25")
        self.assertEqual(current[0][1], tables[0][1])
        self.assertEqual(current[1][1], tables[1][1])
        self.assertEqual(current[2][1], tables[2][1])
        self.assertEqual(sum(row["changed"] for row in changes), 2)
        self.assertEqual(delta["selected_reference_difference"], 2)
        self.assertEqual(delta["previous_county_runtime_total"], 29)
        self.assertEqual(tables, original)

    def test_changed_registered_stock_weights_means_or_behavior_qualifications_fail(self):
        for change in ("register", "weight", "mean", "flag", "source", "excess", "negative"):
            tables, facts, review = self.fixture()
            if change == "register":
                facts["registered"] = 301
            elif change == "weight":
                tables[2][0]["civic_weight"] = "11"
            elif change == "mean":
                tables[2][0]["conditional_modeled_voter_count"] = "149"
            elif change == "flag":
                tables[2][0][FLAGS[0]] = "True"
            elif change == "source":
                facts["source_url"] = "https://different.example/source"
            else:
                facts["total"] = 301 if change == "excess" else -1
            with self.subTest(change=change), self.assertRaises(ValueError):
                revise(tables, facts, review)

    def test_historical_native_snapshot_is_preserved_not_claimed_current_duplicate(self):
        tables, facts, review = self.fixture()
        current, _, _ = revise(tables, facts, review)
        old = current[1][2]
        self.assertEqual(old["numerator"], "30")
        self.assertEqual(old["source_time_label"], "Earlier result")
        self.assertEqual(old["disposition"], "retained_older_same_source_snapshot_not_current_duplicate")
        tables[1][2]["numerator"] = "29"
        with self.assertRaises(ValueError):
            revise(tables, facts, review)

    def test_unchanged_counter_and_clock_reuses_accepted_analysis(self):
        tables, facts, review = self.fixture()
        facts.update(total=30, clock="Earlier result")
        with self.assertRaisesRegex(ValueError, "reuse"):
            revise(tables, facts, review)

    def group_fixture(self):
        first = dict(method="SOURCE_MODE", party="A", sex="F", race="W", ethnicity="N", ballots=2)
        zero = dict(first, party="B", sex="U", race="U", ballots=0)
        state = dict(rows=[first, zero], count_fields=["ballots"])
        county = dict(rows=[dict(first, county=name, ballots=1) for name in ("One", "Two")]
            + [dict(zero, county=name) for name in ("One", "Two")], count_fields=["ballots"])
        declaration = dict(state_query="state", county_query="county", count_field="ballots",
            county_field="county", method_field="method",
            joint_fields=["method", "party", "sex", "race", "ethnicity"],
            dimensions=dict(race="race", native_gender="sex"))
        return dict(state=state, county=county), declaration

    def test_group_controls_reconcile_full_joint_cells_and_keep_reported_zeros(self):
        queries, declaration = self.group_fixture()
        rows, audit = group_controls(queries, declaration, "AR", {"One", "Two"})
        self.assertEqual(audit["native_state_joint_cells"], 2)
        self.assertEqual(audit["native_county_joint_cells"], 4)
        self.assertTrue(any(row["reported_source_ballots"] == 0 for row in rows))
        self.assertTrue(all(row["demographic_registered_denominator"] == "" for row in rows))
        self.assertTrue(all(row["full_demographic_turnout_qualified"] is False for row in rows))
        self.assertTrue(all(row["deduplicated_or_added_to_enr"] is False for row in rows))

    def test_missing_zero_group_or_different_native_county_cell_cannot_be_ignored(self):
        for change in ("missing", "count", "duplicate"):
            queries, declaration = self.group_fixture()
            if change == "missing":
                queries["county"]["rows"].pop()
            elif change == "count":
                queries["county"]["rows"][0]["ballots"] = 2
            else:
                queries["county"]["rows"].append(copy.deepcopy(queries["county"]["rows"][0]))
            with self.subTest(change=change), self.assertRaises(ValueError):
                group_controls(queries, declaration, "AR", {"One", "Two"})


if __name__ == "__main__":
    unittest.main()
