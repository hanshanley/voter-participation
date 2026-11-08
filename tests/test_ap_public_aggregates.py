import copy
import csv
import io
import json
import unittest

from scripts.ap_public_aggregates import assemble, select


def row(year="2024", **changes):
    scope = changes.get("scope", "US50_SOURCE")
    inference = ("publisher_national_registered_source_frame" if scope == "US50_SOURCE" else
                 "source_descriptive_only_publisher_reports_47_state_estimates" if year == "2018" else
                 "publisher_state_weight_descriptive_not_administrative_turnout")
    result = dict(year=year, weight_field="FINALVOTE_NATIONAL_WEIGHT", scope=scope,
                  dimension="overall", group="all", native_labels="All respondents",
                  n="2000", positive_weight_n="2000", weight="100", modeled_voter_weight="60",
                  modeled_nonvoter_weight="30", model_unknown_weight="10",
                  already_voted_self_report_weight="20", unlikely_intent_weight="5",
                  inference_status=inference)
    result.update(changes)
    return result


def selection(*rows):
    waves = {year: [] for year in ("2018", "2020", "2022", "2024")}
    for item in rows:
        waves[item["year"]].append(item)
    provenance = [dict(year=year, native_rows=2000, native_csv_sha256="0" * 64,
                       verified_aggregate_sha256="1" * 64, independent_native_checks=1)
                  for year in waves]
    return select(waves, provenance)


class PublicAPTests(unittest.TestCase):
    def test_unknowns_stay_in_full_denominator(self):
        files, _ = assemble(selection(row()))
        result = next(csv.DictReader(io.StringIO(files["participation.csv"].decode())))
        self.assertEqual(result["modeled_voter_pct"], "60")
        self.assertEqual(result["modeled_nonvoter_pct"], "30")
        self.assertEqual(result["model_unknown_pct"], "10")
        self.assertEqual(result["already_voted_self_report_pct"], "20")

    def test_no_state_demographics_or_disclosure_removed_export(self):
        value = selection(row(), row(scope="AL", weight_field="FINALVOTE_STATE_WEIGHT",
                                     dimension="AGE65", group="1"),
                          row(dimension="RACETH", group="88"),
                          row(dimension="EDUC", group="99"))
        self.assertEqual(len(value["selected_rows"]), 1)
        serialized = str(value["selection_dispositions"])
        self.assertNotIn("positive_weight_n", serialized)
        corrupt = copy.deepcopy(value)
        corrupt["selected_rows"].append(row(scope="AL", weight_field="FINALVOTE_STATE_WEIGHT",
                                           dimension="AGE65", group="1"))
        with self.assertRaises(ValueError):
            assemble(corrupt)

    def test_publisher_state_holds_and_2018_qualifier(self):
        value = selection(row("2018", scope="AL", weight_field="FINALVOTE_STATE_WEIGHT"),
                          row("2022", scope="DE", weight_field="FINALVOTE_STATE_WEIGHT"),
                          row("2022", scope="WV", weight_field="POLLCLOSE_STATE_WEIGHT"))
        files, _ = assemble(value)
        self.assertEqual(len(value["selected_rows"]), 1)
        self.assertIn(b"publisher_reports_47_state_estimates", files["participation.csv"])
        self.assertEqual(sum(r["disposition"] == "publisher_national_only_state_inference_withheld"
                             for r in value["selection_dispositions"]), 4)

    def test_low_support_and_absent_requested_groups_are_visible(self):
        value = selection(row(), row(dimension="GENDER", group="3", positive_weight_n="999"))
        self.assertEqual(len(value["selected_rows"]), 1)
        self.assertTrue(any(r["disposition"] == "below_broad_aggregate_positive_weight_support"
                            for r in value["selection_dispositions"]))
        self.assertTrue(any(r["year"] == "2022" and r["dimension"] == "RACETH5" and
                            r["disposition"] == "documented_dimension_absent_in_release"
                            for r in value["selection_dispositions"]))

    def test_native_labels_and_weight_frames_not_harmonized(self):
        value = selection(row(), row(weight_field="POLLCLOSE_NATIONAL_WEIGHT",
                                     modeled_voter_weight="70", modeled_nonvoter_weight="20"),
                          row(dimension="RACETH5", group="4",
                              native_labels="Asian, Native Hawaiian or Other Pacific Islander"))
        files, summary = assemble(value)
        self.assertEqual(summary["national_rows"], 3)
        self.assertIn(b"Native Hawaiian", files["participation.csv"])
        self.assertIn(b"FINALVOTE_NATIONAL_WEIGHT", files["participation.csv"])
        self.assertIn(b"POLLCLOSE_NATIONAL_WEIGHT", files["participation.csv"])

    def test_incomplete_dispositions_invalid_masses_and_inference_fail(self):
        value = selection(row())
        value["selection_dispositions"].pop()
        with self.assertRaises(ValueError):
            assemble(value)
        for changes in (dict(weight="99"), dict(modeled_voter_weight="NaN"),
                        dict(inference_status="nationally_validated_turnout")):
            with self.assertRaises(ValueError):
                assemble(selection(row(**changes)))

    def test_nonpermitted_fields_cannot_leak_through_public_input(self):
        value = selection(row())
        value["private_fine_cells"] = []
        with self.assertRaises(ValueError):
            assemble(value)
        value = selection(row())
        value["provenance"][0]["private_source_path"] = "/not/public"
        with self.assertRaises(ValueError):
            assemble(value)

    def test_serialized_input_reproduces_identical_query_headers_and_bytes(self):
        value = selection(row())
        first, _ = assemble(value)
        second, _ = assemble(json.loads(json.dumps(value, sort_keys=True)))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
