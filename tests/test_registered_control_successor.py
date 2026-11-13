import copy
import io
import json
import unittest
import zipfile

from scripts.registered_control_successor import encoded, native_control, packet, pin, revise


def fixture():
    annotations = dict(
        native_election_date="11/03/2026", native_report_date="11/09/2026",
        native_column_headers=dict(registered="Registered\nVoters", voted="Native Votes Cast"))
    def row(ordinal, name, registered=None, voted=None, part=None):
        return dict(row=ordinal, cells={key: dict(value=value)
                    for key, value in dict(native_unit=name, registered=registered,
                                           voted=voted, part=part).items()})
    tables = [
        dict(id="parts", source_role="native_registration_ballot_reported_turnout_statistics",
             source_page=1, source_annotations=copy.deepcopy(annotations),
             rows=[row(1, "County"), row(2, "Town", 20, 11, "A"),
                   row(3, "County Total", 20, 11)]),
        dict(id="summary", source_role="native_registration_ballot_reported_turnout_statistics",
             source_page=2, source_annotations=copy.deepcopy(annotations),
             rows=[row(1, "County", 20, 11), row(2, "State Total", 20, 11)]),
    ]
    grids = dict(contract="participation.reviewed_pdf_factual_grids.v1",
                 products=[dict(source=dict(id="source", url="https://example.gov/report.pdf"),
                                tables=tables)])
    group = dict(contract="participation.reviewed_pdf_group_queries.v1", source_id="source",
                 part_tables=["parts"], summary_tables=["summary"],
                 count_fields=["registered", "voted"], part_nonempty_fields=["part"],
                 parent_total_suffix=" Total", summary_total_label="State Total",
                 expected_rows=dict(parts=1, parent_controls=1, summary_parents=1,
                                    summary_total=1, grouped_units=1), percentages=[])
    review = dict(
        contract="participation.registered_control_successor.v1", version=29, year=2026,
        state_code="AL", control_id="existing-control",
        input_pins={}, expected_states=["AL", "VT"], expected_table_rows=[2, 2, 2],
        prior_measure="native_votes_not_qualified_ballots", denominator_basis="source_registered_unknown_status",
        source_id="source", source_url="https://example.gov/report.pdf",
        source_annotations=dict(native_election_date="11/03/2026", native_report_date="11/09/2026"),
        source_members={}, numerator_field="voted", denominator_field="registered",
        expected_native_rates=0, same_scope_review_evidence="Synthetic same native register frame")
    state = dict(
        year="2026", state_code="AL", civic_source_n="100", control_id="existing-control",
        control_measure=review["prior_measure"], control_registered_denominator="10",
        control_native_numerator="4", control_denominator_basis=review["denominator_basis"],
        reported_cast_ballots="", reported_ballots_per_native_registered_denominator_pct="",
        control_native_time="earlier native date", control_source_url="https://example.gov/old",
        civic_modeled_voter_pct="60", civic_modeled_nonvoter_pct="40")
    control = dict(
        id="existing-control", state_code="AL", year="2026", numerator="4", denominator="10",
        measure=review["prior_measure"], denominator_basis=review["denominator_basis"],
        native_measure="Native Votes Cast", denominator_label="Registered Voters",
        source_family="https://example.gov/old", source_url="https://example.gov/old",
        source_time_label="earlier native date", native_status="unofficial",
        source_kind="native", scope_notes="Old frame", selected_state_reference="True")
    scenario = dict(
        year="2026", state_code="AL", control_id="existing-control",
        control_measure=review["prior_measure"], native_registered_denominator="10",
        native_denominator_basis=review["denominator_basis"], civic_source_n="100",
        civic_weight="10", civic_modeled_voter_weight="6", civic_modeled_nonvoter_weight="4",
        conditional_modeled_voter_count="6", conditional_modeled_nonvoter_count="4",
        reported_cast_ballot_measure_control="", reported_cast_minus_conditional_modeled_voter_count="",
        assumption_validated="False", survey_weight_target_qualified="False",
        same_frame_and_cutoff_independently_qualified="False", bridge_outcome_calibration_applied="False",
        model_nonvoter_is_administratively_observed_staying_home="False",
        source_time_label="earlier native date", source_url="https://example.gov/old",
        control_native_status="unofficial")
    baseline = ([state, dict(state, state_code="VT", control_id="other-control")],
                [control, dict(control, state_code="VT", id="other-control")],
                [scenario, dict(scenario, state_code="VT", control_id="other-control")])
    return grids, group, review, baseline


class RegisteredControlSuccessorTests(unittest.TestCase):
    def test_existing_scenario_reuses_weights_without_fitting_to_native_count(self):
        grids, group, review, baseline = fixture()
        original = copy.deepcopy(baseline)
        native, queries = native_control(grids, group, review)
        tables, delta, changes = revise(baseline, native, review)
        self.assertEqual(native["denominator"], 20)
        self.assertEqual(queries["queries"]["parts"]["rows"][0]["registered"], 20)
        self.assertEqual(queries["reconciliation"]["discrepancies"], 0)
        self.assertEqual(tables[2][0]["conditional_modeled_voter_count"], "12.0")
        self.assertEqual(tables[2][0]["conditional_modeled_nonvoter_count"], "8.0")
        self.assertEqual(tables[0][0]["control_native_numerator"], 11)
        self.assertEqual(tables[0][0]["reported_cast_ballots"], "")
        self.assertEqual(delta["native_count_minus_modeled_voter_units_nominal_not_validated_error"], "-1.0")
        self.assertFalse(delta["outcome_calibration_applied"])
        self.assertEqual(baseline, original)
        for before, after in zip(baseline, tables):
            self.assertEqual(before[1], after[1])
        self.assertEqual(sum(row["changed"] for row in changes), 1)

    def test_metadata_and_wrong_measure_cannot_authorize_new_counts(self):
        grids, group, review, _ = fixture()
        review["new_registered_denominator"] = 99999
        with self.assertRaisesRegex(ValueError, "metadata cannot"):
            native_control(grids, group, review)
        del review["new_registered_denominator"]
        review["denominator_field"] = "native_turnout_percent"
        with self.assertRaisesRegex(ValueError, "native count fields"):
            native_control(grids, group, review)
        review["denominator_field"] = "registered"
        grids["products"][0]["tables"][0]["source_role"] = "candidate_votes"
        with self.assertRaisesRegex(ValueError, "statistical table"):
            native_control(grids, group, review)

    def test_missing_counts_wrong_election_and_arithmetic_discrepancies_hold(self):
        for mutation, expected in (
                (lambda g, r: g["products"][0]["tables"][0]["rows"][1]["cells"]["registered"].update(value=None),
                 "Unknown native count"),
                (lambda g, r: g["products"][0]["tables"][0]["rows"][1]["cells"]["registered"].update(value=21),
                 "checks do not match"),
                (lambda g, r: r["source_annotations"].update(native_election_date="11/03/2024"),
                 "election year")):
            grids, group, review, _ = fixture()
            mutation(grids, review)
            with self.assertRaisesRegex(ValueError, expected):
                native_control(grids, group, review)

    def test_prior_case_identity_weights_and_qualifications_must_remain_exact(self):
        grids, group, review, baseline = fixture()
        native, _ = native_control(grids, group, review)
        for table, field, value, expected in (
                (2, "control_id", "unseen", "existing state/control/scenario"),
                (0, "reported_cast_ballots", "4", "cannot promote"),
                (2, "assumption_validated", "True", "cannot promote"),
                (2, "civic_modeled_nonvoter_weight", "5", "weight partition"),
                (2, "conditional_modeled_voter_count", "7", "no longer reproduces"),
                (0, "control_registered_denominator", "12", "disagree")):
            changed = copy.deepcopy(baseline)
            changed[table][0][field] = value
            with self.assertRaisesRegex(ValueError, expected):
                revise(changed, native, review)
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            revise((baseline[0][:-1], baseline[1], baseline[2]), native, review)

    def test_unchanged_native_source_does_not_issue_another_numerical_version(self):
        grids, group, review, baseline = fixture()
        native, _ = native_control(grids, group, review)
        native.update(numerator=4, denominator=10)
        with self.assertRaisesRegex(ValueError, "No changed native counts"):
            revise(baseline, native, review)

    def test_full_input_archive_checks_member_bytes_not_only_manifest(self):
        def archive(content, note=False):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as z:
                z.writestr("source.json", content)
                z.writestr("checksums.json", encoded({"source.json": pin(b"original")}))
                if note:
                    z.writestr("REPRODUCE.txt", b"Legacy explanatory instructions")
            return stream.getvalue()
        good = archive(b"original")
        self.assertEqual(packet(good, pin(good))["source.json"], b"original")
        changed = archive(b"tampered")
        with self.assertRaisesRegex(ValueError, "input member"):
            packet(changed, pin(changed))
        legacy = archive(b"original", note=True)
        with self.assertRaisesRegex(ValueError, "inventory"):
            packet(legacy, pin(legacy))
        self.assertIn("REPRODUCE.txt", packet(legacy, pin(legacy), ("REPRODUCE.txt",)))


if __name__ == "__main__":
    unittest.main()
