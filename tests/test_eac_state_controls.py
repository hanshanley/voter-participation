from fractions import Fraction
import csv
import io
import unittest

from scripts.eac_state_controls import build, conditional, observation, reported, validate_registration


def native(state="AK", identifier="0200000000", name="ALASKA", proxy=False):
    fields = dict(f1a="60", f2_1="1", f2_4="1" if proxy else "0")
    source = dict(year=2024, state_code=state, jurisdiction_id=identifier, jurisdiction=name,
                  native_fields=fields, source_url="native-source", source_sha256="bound",
                  source_sheet="native.csv", source_row=2, retrieved_at="native-acquisition")
    local = dict(total_participation="60", registered="100", supplemental_unit="False",
                 source_details="{}", registration_comment="")
    registration = {(2024, state, identifier, name): dict(
        registered=100, active=80, inactive=20, field="a1a")}
    return source, local, registration


def survey():
    return dict(year="2024", scope="AK", dimension="overall", group="all",
                weight_field="FINALVOTE_STATE_WEIGHT", n="601", positive_weight_n="600",
                weight="100", modeled_voter_weight="60", modeled_nonvoter_weight="30",
                model_unknown_weight="10", inference_status="source descriptive")


def read(raw):
    return list(csv.DictReader(io.StringIO(raw.decode())))


class EacStateControlsTests(unittest.TestCase):
    def test_unavailable_flags_override_numbers_without_changing_zero(self):
        self.assertIsNone(reported({"f1a": "60", "f1a_notavailable": "1"}, "f1a"))
        self.assertEqual(reported({"f1a": "0", "f1a_notavailable": "0"}, "f1a"), 0)
        self.assertIsNone(reported({"f1a": "-88"}, "f1a"))

    def test_municipal_state_label_not_full_electorate(self):
        source, local, registration = native("NH", "0", "STATEWIDE")
        row = observation(source, local, registration, {})
        self.assertFalse(row["qualified_full_state_participation"])
        self.assertIn("held_state_label", row["scope_disposition"])

    def test_statewide_uocava_only_never_promoted(self):
        source, local, registration = native("ME", "2300000000", "STATE OF MAINE")
        local["supplemental_unit"] = "True"
        row = observation(source, local, registration, {})
        self.assertEqual(row["scope_disposition"], "held_supplemental_uocava_only")
        self.assertFalse(row["qualified_full_state_participation"])

    def test_highest_office_proxy_held_but_register_scenario_is_separate(self):
        row = observation(*native(proxy=True), {})
        self.assertIsNone(row["native_participation_per_native_register_pct"])
        self.assertIsNone(row["reported_cast_ballots"])
        scenario = conditional(row, survey())
        self.assertIsNone(scenario["conditional_minus_native_participation"])
        self.assertEqual(Fraction(scenario["conditional_modeled_voter_count"]), 60)

    def test_active_inactive_and_unknown_mass_are_not_discarded(self):
        row = observation(*native(), {})
        scenario = conditional(row, survey())
        self.assertEqual(scenario["native_registration_denominator"], 100)
        self.assertEqual(scenario["native_inactive_registered"], 20)
        self.assertEqual(Fraction(scenario["conditional_model_unknown_count"]), 10)
        self.assertEqual(sum(Fraction(scenario[key]) for key in (
            "conditional_modeled_voter_count", "conditional_modeled_nonvoter_count",
            "conditional_model_unknown_count")), 100)
        self.assertFalse(scenario["administrative_staying_home_observed"])
        self.assertFalse(scenario["geographic_allocation"])

    def test_complete_grid_and_source_dispositions_preserve_unmatched(self):
        row = observation(*native(), {})
        files, summary = build([row], dict(selected_rows=[
            dict(survey(), scope="WY"), dict(survey(), dimension="age"), survey()]))
        self.assertEqual(summary["complete_state_year_rows"], 561)
        self.assertEqual(summary["conditional_survey_rows"], 1)
        missing = next(item for item in read(files["complete-state-year-controls.csv"])
                       if item["state_code"] == "WY" and item["year"] == "2024")
        self.assertEqual(missing["native_registered"], "")
        self.assertFalse(missing["source_reference_selected"] == "True")
        self.assertEqual(len(read(files["complete-survey-dispositions.csv"])), 3)
        self.assertEqual(read(files["complete-native-time-comparisons.csv"]), [])
        self.assertIn(b"native_participation_count_difference", files["complete-native-time-comparisons.csv"])

    def test_registration_disagreement_holds_scaling_and_duplicate_source_rejected(self):
        source, local, registration = native()
        registration[(2024, "AK", "0200000000", "ALASKA")]["inactive"] = 21
        row = observation(source, local, registration, {})
        files, summary = build([row], dict(selected_rows=[survey(), dict(survey(), weight_field="POLLCLOSE_STATE_WEIGHT")]))
        self.assertEqual(summary["conditional_survey_rows"], 0)
        self.assertEqual(read(files["complete-source-weighted-scenarios.csv"]), [])
        self.assertIn(b"conditional_model_unknown_count", files["complete-source-weighted-scenarios.csv"])
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            build([row, row], dict(selected_rows=[]))

    def test_registration_cache_cannot_override_native_unavailable_flag(self):
        row = dict(year=2024, registered=100, active=None, inactive=None, field="a1a",
                   native_fields=dict(a1a="100", a1a_notavailable="1"))
        with self.assertRaisesRegex(ValueError, "unavailable flags"):
            validate_registration(row, {})
        row["registered"] = None
        validate_registration(row, {})

    def test_components_require_native_definitions_not_just_matching_sum(self):
        row = dict(year=2024, registered=100, active=80, inactive=20, field="a1a",
                   native_fields=dict(a1a="100", a1b="80", a1c="20"))
        with self.assertRaisesRegex(ValueError, "definition"):
            validate_registration(row, {})
        validate_registration(row, {2024: dict(a1b="Total Active", a1c="Total Inactive")})

    def test_invalid_or_unreconciled_survey_mass_rejected(self):
        row = observation(*native(), {})
        with self.assertRaisesRegex(ValueError, "survey mass"):
            conditional(row, dict(survey(), model_unknown_weight="11"))


if __name__ == "__main__":
    unittest.main()
