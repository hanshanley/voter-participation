import copy
from fractions import Fraction
import unittest

from scripts.house_round_context import FORBIDDEN_CLAIMS, calculate, outputs


def source():
    return {
        "contract": "participation.maine_house_round_source_facts.v1",
        "state_code": "ME", "district": "ME-02", "office": "house", "election_date": "2026-11-03",
        "publication_date": "2026-11-12", "native_status": "unofficial ranked-choice tabulation results",
        "candidate_names": {"D": "Matthew Dunlap", "R": "Paul LePage"},
        "party_labels_are_explicit_native_first_choice_markers": True,
        "raw_publisher_html_private_person_records_or_histories_included": False,
        "qualification": dict.fromkeys(FORBIDDEN_CLAIMS, False) |
            {"new_major_party_aggregate_context_qualified": True,
             "final_other_or_blank_counts_not_supplied_not_zero": True,
             "source_partial_not_metadata_only_query_input": True, "reason": "Incomplete final accounting"},
        "tabulation_original": {"url": "https://example.org/tabulation.csv",
                                "status": 403, "stopped": True, "bytes": None, "sha256": None},
        "snapshots": [
            {"id": "initial", "label": "Initial reported counts", "native_count_clock": None,
             "source_url": "https://example.org/announcement",
             "counts": {"D": 164845, "R": 170263, "O": 123, "blank": 6017},
             "native_percent_literals": {"D": "48.307", "R": "49.894", "O": ".036", "blank": "1.763"}},
            {"id": "final", "label": "Reported final major-party counts", "native_count_clock": None,
             "source_url": "https://example.org/announcement",
             "counts": {"D": 165432, "R": 170890, "O": None, "blank": None},
             "native_percent_literals": {"D": "49.18", "R": "50.81", "O": None, "blank": None},
             "full_candidate_or_exhausted_accounting_vector_qualified": False},
        ],
    }


class HouseRoundContextTests(unittest.TestCase):
    def test_changed_printed_percentage_basis_is_not_used_as_swing(self):
        data = source()
        before = copy.deepcopy(data)
        result = calculate(data)
        change = result["source_snapshot_comparisons"][0]
        actual = change["D_share_among_reported_D_R_change_pp"]
        expected = Fraction(100 * 165432, 336322) - Fraction(100 * 164845, 335108)
        self.assertEqual(Fraction(int(actual["numerator"]), int(actual["denominator"])), expected)
        self.assertLess(expected, 0)
        self.assertNotEqual(expected, Fraction(873, 1000))
        margin = change["D_minus_R_margin_among_reported_D_R_change_pp"]
        self.assertEqual(Fraction(int(margin["numerator"]), int(margin["denominator"])), 2 * expected)
        self.assertEqual(change["D_reported_count_difference"], 587)
        self.assertEqual(change["R_reported_count_difference"], 627)
        self.assertEqual(data, before)

    def test_unknown_final_accounting_remains_unknown_and_not_zero(self):
        result = calculate(source())
        final = result["major_party_diagnostics"][-1]
        self.assertIsNone(final["four_supplied_field_sum"])
        self.assertEqual(final["unknown_categories"], ["O", "blank"])
        self.assertEqual([row["source_count"] for row in result["source_rows"][-2:]], [None, None])
        for category in ("O", "blank"):
            data = source()
            data["snapshots"][-1]["counts"][category] = 0
            with self.assertRaisesRegex(ValueError, "must not be filled"):
                calculate(data)

    def test_real_source_zeros_are_retained_without_a_false_positive_rate(self):
        data = source()
        data["snapshots"][0]["counts"].update(D=0, R=10, O=0, blank=0)
        result = calculate(data)
        self.assertEqual(result["source_rows"][0]["source_count"], 0)
        self.assertEqual(result["source_rows"][0]["count_status"], "reported")
        self.assertEqual(result["major_party_diagnostics"][0]["four_supplied_field_sum"], 10)
        self.assertEqual(result["major_party_diagnostics"][0]["D_share_among_reported_D_R_percent"]["decimal"], "0")

    def test_invalid_counts_empty_major_total_and_duplicate_snapshots_fail(self):
        for value in (-1, 1.5, True, "165432", None):
            data = source()
            data["snapshots"][-1]["counts"]["D"] = value
            with self.assertRaises(ValueError):
                calculate(data)
        for mutate in (
            lambda data: data["snapshots"][0]["counts"].update(D=0, R=0),
            lambda data: data["snapshots"][-1].update(id="initial"),
            lambda data: data["snapshots"][0]["native_percent_literals"].update(D="NaN"),
        ):
            data = source()
            mutate(data)
            with self.assertRaises(ValueError):
                calculate(data)

    def test_source_context_cannot_promote_behavior_or_endpoint_eligibility(self):
        for key in FORBIDDEN_CLAIMS:
            data = source()
            data["qualification"][key] = True
            with self.assertRaisesRegex(ValueError, "withholding changed"):
                calculate(data)
        result = calculate(source())
        self.assertFalse(result["model_endpoint_update"])
        self.assertFalse(result["source_extraction_replayed"])
        for row in result["source_snapshot_comparisons"]:
            self.assertFalse(row["individual_vote_transfers_or_behavior_identified"])
            self.assertFalse(row["matched_round_boundary_or_population_qualified"])

    def test_complete_queries_keep_every_snapshot_and_missing_category_decision(self):
        data = source()
        middle = copy.deepcopy(data["snapshots"][0])
        middle.update(id="frozen_provider")
        middle["counts"] = {"D": 164855, "R": 170360, "O": 165, "blank": None}
        data["snapshots"].insert(1, middle)
        result = calculate(data)
        self.assertEqual(len(result["source_rows"]), 12)
        self.assertEqual(len(result["major_party_diagnostics"]), 3)
        self.assertEqual(len(result["source_snapshot_comparisons"]), 3)
        self.assertEqual(len(outputs(data)), 4)

    def test_unexpected_record_payloads_are_not_copied_into_public_outputs(self):
        data = source()
        data["respondents"] = []
        with self.assertRaisesRegex(ValueError, "source payload"):
            calculate(data)
        data = source()
        data["snapshots"][0]["voter_id"] = "not-a-source-context-field"
        with self.assertRaisesRegex(ValueError, "snapshot metadata"):
            calculate(data)

    def test_nested_payloads_and_wrong_container_types_are_rejected(self):
        for location in ("candidate_names", "qualification", "tabulation_original"):
            data = source()
            data[location]["unexpected_record"] = {"private_payload": "sentinel"}
            with self.subTest(location=location), self.assertRaises(ValueError):
                calculate(data)
        for location in ("counts", "native_percent_literals", "source_pin"):
            data = source()
            snapshot = data["snapshots"][0]
            snapshot["source_pin"] = {"bytes": 1, "sha256": "a" * 64}
            snapshot[location]["unexpected_record"] = {"private_payload": "sentinel"}
            with self.subTest(location=location), self.assertRaises(ValueError):
                calculate(data)
        for value in ("https://example.org/source", [None], [{"private_payload": "sentinel"}]):
            data = source()
            snapshot = data["snapshots"][0]
            del snapshot["source_url"]
            snapshot["source_urls"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate(data)
        data = source()
        data["candidate_names"]["D"] = {"private_payload": "sentinel"}
        with self.assertRaises(ValueError):
            calculate(data)

    def test_source_contract_dates_status_and_access_semantics_are_enforced(self):
        for location, key, value in (
            (None, "contract", "wrong.contract"),
            (None, "native_status", "official"),
            (None, "publication_date", "not-a-date"),
            (None, "election_date", "2026-02-30"),
            (None, "party_labels_are_explicit_native_first_choice_markers", False),
            ("tabulation_original", "status", 200),
            ("tabulation_original", "stopped", False),
            ("tabulation_original", "bytes", 100),
            ("qualification", "final_other_or_blank_counts_not_supplied_not_zero", False),
        ):
            data = source()
            (data if location is None else data[location])[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                calculate(data)
        data = source()
        data["snapshots"][0]["source_url"] = "file:///private/original"
        with self.assertRaises(ValueError):
            calculate(data)

    def test_output_source_facts_are_independent_validated_containers(self):
        data = source()
        snapshot = data["snapshots"][0]
        del snapshot["source_url"]
        snapshot["source_urls"] = ["https://example.org/announcement"]
        snapshot["source_pin"] = {"bytes": 1, "sha256": "a" * 64}
        result = calculate(data)
        result["source_facts"]["candidate_names"]["D"] = "Changed"
        result["source_facts"]["snapshots"][0]["counts"]["D"] = 0
        result["source_facts"]["snapshots"][0]["source_urls"].append("https://example.org/another")
        result["source_facts"]["snapshots"][0]["source_pin"]["bytes"] = 2
        result["source_facts"]["tabulation_original"]["stopped"] = False
        result["qualification"]["reason"] = "Changed"
        self.assertEqual(data["candidate_names"]["D"], "Matthew Dunlap")
        self.assertEqual(snapshot["counts"]["D"], 164845)
        self.assertEqual(snapshot["source_urls"], ["https://example.org/announcement"])
        self.assertEqual(snapshot["source_pin"]["bytes"], 1)
        self.assertTrue(data["tabulation_original"]["stopped"])
        self.assertEqual(data["qualification"]["reason"], "Incomplete final accounting")


if __name__ == "__main__":
    unittest.main()
