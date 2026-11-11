import copy
from fractions import Fraction
import json
from pathlib import Path
import unittest
import zipfile

from scripts.extract_mississippi_register_history import read_pdf
from scripts.mississippi_register_history import csv_rows, native_frame, participation, stock_comparisons


class MississippiRegisterHistoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/mississippi-register-history/20261109-01"
        native = fixture / "native-inputs.zip"
        cps = fixture / "cps-inputs.zip"
        if not native.exists():
            native = root / "inputs/complete-register-history-inputs.zip"
            cps = root / "inputs/complete-cps-state-inputs.zip"
        with zipfile.ZipFile(native) as archive:
            cls.grid = read_pdf(archive.read("MS-October-2022.pdf"), 2022)
            cls.peer = json.loads(archive.read("independent-2022-rows.json"))["rows"]
            cls.scope = json.loads(archive.read("report-scopes.json"))["2022"]
            cls.civic = json.loads(archive.read("civic-selected-aggregates.json"))
            cls.existing = csv_rows(archive.read("existing-2026-frame.csv"))[0]
            old = csv_rows(archive.read("existing-2026-county-query.csv"))
            cls.states = [native_frame(2022, cls.grid, cls.peer, cls.scope)[0]]
            grid24 = read_pdf(archive.read("MS-October-2024.pdf"), 2024)
            cls.grid24 = grid24
            cls.states.append(native_frame(2024, grid24,
                json.loads(archive.read("independent-2024-rows.json"))["rows"],
                json.loads(archive.read("report-scopes.json"))["2024"])[0])
            cls.states.append(dict(year=2026, derived_active_register=sum(int(row["native_active_voters"]) for row in old),
                                   election_type="midterm"))
        with zipfile.ZipFile(cps) as archive:
            cls.references = csv_rows(archive.read("complete-state-year-population-pairs.csv"))

    def changed(self, field, value):
        rows, peer = copy.deepcopy(self.grid), copy.deepcopy(self.peer)
        rows[0][field] = peer[0][field] = value
        return rows, peer

    def frame(self, rows, peer):
        return native_frame(2022, rows, peer, self.scope)

    def scenarios(self, references=None, states=None):
        return participation(states or self.states, self.references if references is None else references,
                             self.civic, self.existing)

    def test_missing_active_count_never_creates_partial_state_sum(self):
        state, rows, _ = self.frame(*self.changed("native_active_voters", None))
        self.assertIsNone(state["derived_active_register"])
        self.assertEqual(state["missing_active_cells"], 1)
        self.assertIsNone(rows[0]["native_active_voters"])

    def test_layout_reader_preserves_split_carroll_label_without_dropping_county(self):
        row = next(row for row in self.grid24 if row["native_county_label"] == "08 - Carroll")
        self.assertEqual(row["native_active_voters"], "7316")
        self.assertEqual(len(self.grid24), 82)

    def test_observed_zero_count_remains_observed(self):
        state, rows, _ = self.frame(*self.changed("native_active_voters", "0"))
        self.assertEqual(rows[0]["native_active_voters"], "0")
        self.assertEqual(state["derived_active_register"], self.states[0]["derived_active_register"] - 18719)

    def test_invalid_counts_are_not_coerced(self):
        for value in ("-1", "1.5"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Invalid native count"):
                self.frame(*self.changed("native_active_voters", value))

    def test_independent_native_disagreement_is_rejected(self):
        peer = copy.deepcopy(self.peer)
        peer[0]["native_active_voters"] = "1"
        with self.assertRaisesRegex(ValueError, "Independent complete"):
            self.frame(self.grid, peer)

    def test_month_policy_does_not_invent_actual_cutoff(self):
        with self.assertRaisesRegex(ValueError, "unknown cutoff"):
            native_frame(2022, self.grid, self.peer, dict(self.scope, exact_cutoff_date="2022-10-03"))

    def test_derived_county_sum_not_printed_parent(self):
        with self.assertRaisesRegex(ValueError, "derived stock"):
            native_frame(2022, self.grid, self.peer, dict(self.scope, printed_statewide_total=1))

    def test_duplicate_county_is_not_complete_native_coverage(self):
        with self.assertRaisesRegex(ValueError, "county coverage"):
            self.frame(*self.changed("native_county_label", "02 - Alcorn"))

    def test_over100_percentage_remains_unclipped_not_turnout(self):
        values = self.frame(self.grid, self.peer)[2]
        row = next(row for row in values if row["native_county_label"] == "27 - Humphreys")
        self.assertEqual(row["source_percentage"], "106.198%")
        self.assertTrue(row["over100_preserved"])
        self.assertFalse(row["percentage_is_turnout"])

    def test_changed_source_percentage_is_diagnosed_not_repaired(self):
        diagnostics = self.frame(*self.changed("native_percentage", "50.000%"))[2]
        self.assertEqual(diagnostics[0]["source_percentage"], "50.000%")
        self.assertFalse(diagnostics[0]["three_decimal_rounding_compatible"])

    def test_native_cvap_header_not_promoted_to_population_denominator(self):
        rows = self.frame(self.grid, self.peer)[1]
        self.assertEqual(rows[0]["source_cvap_header"], "2020 CVAP Estimate")
        self.assertFalse(rows[0]["cvap_used_as_model_denominator"])
        self.assertFalse(rows[0]["geographic_codes_inferred"])

    def test_cps_ratio_uses_original_percentage_lexemes_not_prerounded_ratio(self):
        references = copy.deepcopy(self.references)
        source = next(row for row in references if row["year"] == "2022"
                      and row["reference_state_code"] == "MS" and row["population_frame"] == "cvap")
        source["reported_vote_to_registration_ratio_pct"] = "0"
        row = next(row for row in self.scenarios(references)[1] if row["year"] == 2022)
        expected = Fraction(self.states[0]["derived_active_register"]) * Fraction("46.4") / Fraction("72.6")
        self.assertLess(abs(Fraction(row["conditional_voting_signal_units"]) - expected), Fraction(1, 10**60))

    def test_cps_complement_does_not_invent_observed_nonvoters_or_unknown_mass(self):
        row = next(row for row in self.scenarios()[1] if row["year"] == 2022)
        self.assertIn("not_identified_reported_nonvoters_or_unknown", row["complement_interpretation"])
        self.assertIsNone(row["reported_unknown_response_units"])
        self.assertFalse(row["source_ratio_is_individual_registered_joint"])

    def test_missing_cps_pair_is_held_not_zero_signal(self):
        refs = [row for row in self.references if not (row["year"] == "2022"
                and row["reference_state_code"] == "MS" and row["population_frame"] == "cvap")]
        decisions, scenarios, _ = self.scenarios(refs)
        self.assertFalse(next(row for row in decisions if row["year"] == 2022
                              and row["source_view"] == "CPS_cvap_marginal_ratio")["selected"])
        self.assertNotIn(2022, [row["year"] for row in scenarios])

    def test_vap_and_cvap_are_preserved_separately_not_pooled(self):
        decisions, scenarios, _ = self.scenarios()
        row = next(row for row in decisions if row["year"] == 2022 and row["source_view"] == "CPS_vap_marginal_ratio")
        self.assertEqual(row["source_voted_pct"], "45.7")
        self.assertFalse(row["selected"])
        self.assertEqual(next(row for row in scenarios if row["year"] == 2022)["source_voted_pct"], "46.4")

    def test_existing_2026_model_units_are_reused_byte_exact(self):
        row = next(row for row in self.scenarios()[1] if row["year"] == 2026)
        self.assertEqual(row["conditional_voting_signal_units"], self.existing["conditional_model_participant_units"])
        self.assertEqual(row["conditional_complement_units"], self.existing["conditional_model_nonparticipant_units"])

    def test_same_midterm_type_does_not_validate_cps_to_civic_comparison(self):
        row = next(row for row in self.scenarios()[2] if row["from_year"] == 2022 and row["to_year"] == 2026)
        self.assertIn("CPS_selfreport_vs_Civic_model_not_harmonized", row["disposition"])
        self.assertIsNone(row["conditional_participation_unit_difference"])
        self.assertIsNone(row["observed_turnout_change"])

    def test_stock_changes_do_not_infer_person_retention_or_demographics(self):
        rows = stock_comparisons(self.states)
        row = next(row for row in rows if row["from_year"] == 2022 and row["to_year"] == 2026)
        self.assertEqual(row["registration_stock_difference"],
                         self.states[-1]["derived_active_register"] - self.states[0]["derived_active_register"])
        self.assertFalse(row["matched_person_panel"])
        self.assertIsNone(row["retained_voters"])
        self.assertIsNone(row["deaths"])

    def test_missing_state_frame_holds_projection_instead_of_using_partial_counts(self):
        states = copy.deepcopy(self.states)
        states[0]["derived_active_register"] = None
        decisions, scenarios, _ = self.scenarios(states=states)
        self.assertNotIn(2022, [row["year"] for row in scenarios])
        self.assertIn("incomplete_native_active_stock_no_partial_count_projection",
                      [row["disposition"] for row in decisions])


if __name__ == "__main__":
    unittest.main()
