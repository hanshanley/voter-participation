import unittest

from scripts.senate_geography import resolve


def evidence(cnn_votes="10", house_id="27085"):
    native = []
    for provider in ("civic", "cnn"):
        for candidate, votes in (("First Candidate", "10"), ("Second Candidate", "5")):
            native.append(dict(provider=provider, state="MN", contest="SG",
                               native_unit_id="mcleod" if provider == "civic" else "45",
                               native_unit_type="County" if provider == "civic" else "publisher_county_races_unit",
                               native_unit_name="Mcleod" if provider == "civic" else "McLeod County",
                               fips="" if provider == "civic" else "27085",
                               county_equivalent_scope="True" if provider == "civic" else "",
                               candidate=candidate, party="literal", votes=cnn_votes if
                               provider == "cnn" and candidate == "First Candidate" else votes,
                               native_round="1" if provider == "civic" else "",
                               native_updated="clock-" + provider,
                               eligible_for_fips_name_count_comparison="True" if provider == "cnn" else "False"))
    house = [dict(year=2026, level="county", state_code="MN", district_fragments=[
        dict(source_key="mcleod", native_name="Mcleod", native_type="County", geography=house_id,
             join_strategy="unique_census_name_casefold_periods",
             source_url="https://civicapi.org/api/v2/race/12345")])]
    return native, house


class SenateGeographyTests(unittest.TestCase):
    def test_reference_join_preserves_native_blanks_and_every_original_field(self):
        native, house = evidence()
        result, joins, checks, summary = resolve(native, house, {"MN": "27"})
        self.assertEqual(summary["reference_joined_county_units"], 1)
        self.assertEqual(summary["candidate_rows_with_reference_join"], 2)
        for original, enriched in zip(native, result):
            self.assertTrue(all(enriched[k] == v for k, v in original.items()))
        self.assertEqual(result[0]["fips"], "")
        self.assertEqual(result[0]["resolved_fips"], "27085")
        self.assertEqual(joins[0]["status"], "reference_joined_not_native_declared")
        self.assertEqual(len(checks), 2)

    def test_count_and_clock_disagreement_not_silently_repaired(self):
        native, house = evidence(cnn_votes="9")
        result, _, checks, summary = resolve(native, house, {"MN": "27"})
        self.assertEqual(summary["reference_joined_county_units"], 1)
        self.assertEqual(summary["additional_different_named_counts"], 1)
        self.assertEqual(result[0]["votes"], "10")
        self.assertTrue(any(r["civic_minus_cnn"] == 1 for r in checks))
        self.assertTrue(all(not r["same_round_independently_qualified"] for r in checks))

    def test_names_alone_and_conflicting_ids_do_not_resolve(self):
        native, house = evidence(house_id="27001")
        _, _, _, summary = resolve(native, house, {"MN": "27"})
        self.assertEqual(summary["reference_joined_county_units"], 0)
        native, _ = evidence()
        _, _, _, summary = resolve(native, [], {"MN": "27"})
        self.assertEqual(summary["reference_joined_county_units"], 0)

    def test_wrong_state_and_noncounty_house_reference_do_not_resolve(self):
        native, house = evidence(house_id="01001")
        _, _, _, summary = resolve(native, house, {"MN": "27"})
        self.assertEqual(summary["reference_joined_county_units"], 0)
        native, house = evidence()
        house[0]["district_fragments"][0]["native_type"] = "Town"
        _, _, _, summary = resolve(native, house, {"MN": "27"})
        self.assertEqual(summary["reference_joined_county_units"], 0)

    def test_nonmatching_candidate_identity_keeps_identifier_withheld(self):
        native, house = evidence()
        native[-1]["candidate"] = "Different Candidate"
        _, _, _, summary = resolve(native, house, {"MN": "27"})
        self.assertEqual(summary["reference_joined_county_units"], 0)

    def test_other_official_house_fragments_do_not_enter_civic_namespace(self):
        native, house = evidence()
        house[0]["district_fragments"].append(dict(source_key="official-total", votes="3"))
        _, _, _, summary = resolve(native, house, {"MN": "27"})
        self.assertEqual(summary["reference_joined_county_units"], 1)
        house[0]["district_fragments"][0]["source_url"] = "https://official.example/results"
        _, _, _, summary = resolve(native, house, {"MN": "27"})
        self.assertEqual(summary["reference_joined_county_units"], 0)


if __name__ == "__main__":
    unittest.main()
