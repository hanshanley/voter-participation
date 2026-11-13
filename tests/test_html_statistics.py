import copy
import json
import unittest

from scripts.html_statistics import binding_cells, extract, pin, validate
from scripts.participation_intake.adapters import verify_fact_bindings
from scripts.participation_intake.contract import IntakeError


class HtmlStatisticsTests(unittest.TestCase):
    def fixture(self):
        body = b"""<html><body>
<input id="date" value="11/3/2026"><input id="stage" value="General">
<input id="backend" value="0">
<h1><span class="label">Ballots Counted</span><span class="number">1,234</span>
<span class="label">Active Registered Voters</span><span class="number">2,000</span></h1>
<div class="pct"><span>61</span><span>.70%</span></div>
<div class="pct"><span>61</span><span>.70%</span></div>
<div class="clock">Updated: November 13, 2026 1:45 AM PT</div>
<script>var ignored = 'private application text';</script>
</body></html>"""
        fields = []
        for name, label in (("ballots", "Ballots Counted"), ("registered", "Active Registered Voters")):
            fields.append(dict(name=name, kind="count", native_label=label,
                selector=dict(tag="span", classes=["label"], text=label),
                following_sibling=dict(tag="span", classes=["number"])))
        fields.extend([
            dict(name="pct", kind="percentage", native_label="Statewide Voter Turnout",
                 selector=dict(tag="div", classes=["pct"]), expected_matches=2),
            dict(name="clock", kind="literal", native_label="Updated:",
                 selector=dict(tag="div", classes=["clock"]), prefix="Updated:"),
        ])
        recipe = dict(
            contract="participation.native_html_statistics_recipe.v1",
            source=dict(id="state-statistics", state_code="AR", election_year=2026,
                        url="https://example.gov/results", pin=pin(body)), encoding="utf-8",
            roles=dict(count="ballots", denominator="registered", percentage="pct", clock="clock"),
            fields=fields, assertions=[
                dict(selector=dict(tag="input", id="date"), attribute="value", expected="11/3/2026"),
                dict(selector=dict(tag="input", id="stage"), attribute="value", expected="General")],
            opaque_context=[dict(selector=dict(tag="input", id="backend"), attribute="value")])
        return body, recipe

    def test_native_labels_counts_clock_duplicates_and_opaque_context_are_preserved(self):
        body, recipe = self.fixture()
        result = extract(body, recipe)
        self.assertEqual(result["fields"]["ballots"]["value"], 1234)
        self.assertEqual(result["fields"]["ballots"]["literal"], "1,234")
        self.assertEqual(result["fields"]["registered"]["value"], 2000)
        self.assertEqual(result["fields"]["pct"]["value"], "61.70%")
        self.assertEqual(len(result["fields"]["pct"]["source_elements"]), 2)
        self.assertEqual(result["fields"]["clock"]["value"], "November 13, 2026 1:45 AM PT")
        self.assertEqual(result["opaque_context"][0]["value"], "0")
        self.assertFalse(result["opaque_context"][0]["statistical_role_qualified"])
        self.assertNotIn("private application text", str(result))
        self.assertFalse(result["whole_publisher_html_redistributed"])

    def test_changed_original_or_native_election_is_rejected(self):
        body, recipe = self.fixture()
        with self.assertRaises(ValueError):
            extract(body + b"\n", recipe)
        changed = body.replace(b'11/3/2026', b'11/3/2025')
        recipe["source"]["pin"] = pin(changed)
        with self.assertRaises(ValueError):
            extract(changed, recipe)

    def test_missing_ambiguous_label_or_disagreeing_duplicate_is_rejected(self):
        for old, new in ((b"Ballots Counted", b"Candidate Votes"),
                         (b'<input id="date"', b'<input id="date" value="duplicate"><input id="date"'),
                         (b".70%", b".80%")):
            body, recipe = self.fixture()
            body = body.replace(old, new, 1)
            recipe["source"]["pin"] = pin(body)
            with self.subTest(change=new), self.assertRaises(ValueError):
                extract(body, recipe)

    def test_zero_is_not_missing_and_no_source_field_is_inverted(self):
        body, recipe = self.fixture()
        body = body.replace(b"1,234", b"0").replace(b"61</span><span>.70%", b"0</span><span>.00%")
        recipe["source"]["pin"] = pin(body)
        result = extract(body, recipe)
        self.assertEqual(result["fields"]["ballots"]["value"], 0)
        self.assertEqual(result["fields"]["registered"]["value"], 2000)

    def test_malformed_or_blank_native_count_is_rejected(self):
        for replacement in (b"", b"1,23", b"-1", b"N/A"):
            body, recipe = self.fixture()
            body = body.replace(b"1,234", replacement)
            recipe["source"]["pin"] = pin(body)
            with self.subTest(value=replacement), self.assertRaises(ValueError):
                extract(body, recipe)

    def test_selected_count_metadata_or_opaque_role_promotion_is_rejected(self):
        body, recipe = self.fixture()
        original = extract(body, recipe)
        for change in ("count", "boolean", "opaque", "assertion"):
            result = copy.deepcopy(original)
            if change == "count":
                result["fields"]["ballots"]["value"] = 9999
            elif change == "boolean":
                result["fields"]["ballots"]["value"] = True
            elif change == "opaque":
                result["opaque_context"][0]["statistical_role_qualified"] = True
            else:
                result["assertions"][0]["value"] = "11/3/2025"
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate(result)

    def test_app_selectors_and_nonadjacent_count_fields_are_rejected(self):
        body, recipe = self.fixture()
        recipe["fields"][0]["selector"] = dict(tag="script")
        with self.assertRaises(ValueError):
            extract(body, recipe)
        body, recipe = self.fixture()
        body = body.replace(b'</span><span class="number">1,234',
                            b'</span><i>Not a count</i><span class="number">1,234')
        recipe["source"]["pin"] = pin(body)
        with self.assertRaises(ValueError):
            extract(body, recipe)

    def binding_fixture(self):
        body, recipe = self.fixture()
        selected = extract(body, recipe)
        binding = dict(input="statistics", source_id="state-statistics", measure="ballots",
            native_measure_header="Ballots Counted", record=dict(id="row"),
            path="count.value", parse="count",
            source_role="native_registration_ballot_reported_turnout_statistics",
            accepted_measure_literal="Previously reviewed reported ballots",
            same_measure_review_evidence="Same source field and election; no new geography or population approval")
        spec = dict(inputs=dict(statistics={}, recipe={}),
            geography=dict(state_code="AR"), election=dict(year=2026),
            format=dict(html_statistics_recipe_input="recipe", fact_bindings=[binding]))
        row = dict(id="row", count=dict(value=1234),
                   measure=dict(literal="Previously reviewed reported ballots"))
        inputs = dict(statistics=json.dumps(selected).encode(), recipe=json.dumps(recipe).encode())
        return selected, binding, spec, row, inputs

    def test_selected_html_counts_bind_through_the_shared_intake_without_fake_worksheet_cells(self):
        selected, binding, spec, row, inputs = self.binding_fixture()
        verify_fact_bindings(spec, [row], inputs)
        row["count"]["value"] = 1235
        with self.assertRaises(IntakeError):
            verify_fact_bindings(spec, [row], inputs)

    def test_metadata_cannot_supply_a_count_and_changed_recipe_or_source_scope_fails(self):
        for change in ("metadata", "recipe", "state", "label", "year"):
            selected, binding, spec, row, inputs = self.binding_fixture()
            if change == "metadata":
                binding.update(value_scope="source", value_path="election_year")
                row["count"]["value"] = 2026
            elif change == "recipe":
                inputs["recipe"] = b"{}"
            elif change == "state":
                spec["geography"]["state_code"] = "OR"
            elif change == "label":
                binding["native_measure_header"] = "Candidate Votes"
            else:
                spec["election"]["year"] = 2024
            with self.subTest(change=change), self.assertRaises(IntakeError):
                verify_fact_bindings(spec, [row], inputs)

    def test_literal_source_clock_and_original_pin_bind_without_retrieval_time_substitution(self):
        selected, binding, spec, row, inputs = self.binding_fixture()
        binding.update(measure="clock", native_measure_header="Updated:",
                       path="clock", parse="literal")
        row["clock"] = selected["fields"]["clock"]["value"]
        verify_fact_bindings(spec, [row], inputs)
        row["clock"] = "Retrieval clock"
        with self.assertRaises(IntakeError):
            verify_fact_bindings(spec, [row], inputs)

    def count_only_fixture(self):
        body = b"""<h1>2026 General Election</h1>
<p>Early Voting: 12 (60.0%)</p><p>Total Voter Turnout: 20</p>
<p>Turnout of Active Registered Voters: 59.8%</p>"""
        recipe = dict(
            contract="participation.native_html_statistics_recipe.v2",
            source=dict(id="state-statistics", state_code="AR", election_year=2026,
                        url="https://example.gov/release", pin=pin(body)), encoding="utf-8",
            roles=dict(count="turnout", denominator=None, percentage="pct", clock=None),
            fields=[
                dict(name="turnout", kind="count", native_label="Total Voter Turnout:",
                     selector=dict(tag="p", text="Total Voter Turnout: 20"),
                     prefix="Total Voter Turnout:"),
                dict(name="early", kind="count", native_label="Early Voting:",
                     selector=dict(tag="p", text="Early Voting: 12 (60.0%)"),
                     prefix="Early Voting:", suffix=" (60.0%)"),
                dict(name="pct", kind="percentage", native_label="Turnout of Active Registered Voters:",
                     selector=dict(tag="p", text="Turnout of Active Registered Voters: 59.8%"),
                     prefix="Turnout of Active Registered Voters:"),
            ],
            assertions=[dict(selector=dict(tag="h1"), expected="2026 General Election")],
            opaque_context=[])
        return body, recipe

    def test_count_only_preserves_printed_percentage_without_inventing_denominator_or_clock(self):
        body, recipe = self.count_only_fixture()
        selected = extract(body, recipe)
        self.assertEqual(selected["fields"]["turnout"]["value"], 20)
        self.assertEqual(selected["fields"]["early"]["value"], 12)
        self.assertEqual(selected["fields"]["pct"]["value"], "59.8%")
        self.assertIsNone(selected["recipe"]["roles"]["denominator"])
        self.assertIsNone(selected["recipe"]["roles"]["clock"])
        self.assertNotIn("registered", selected["fields"])
        self.assertEqual(selected["contract"], "participation.selected_html_statistics.v2")

    def test_count_only_roles_do_not_relax_legacy_contract_or_allow_percentage_counts(self):
        for change in ("legacy", "percentage_count", "absent_count", "undeclared_count"):
            body, recipe = self.count_only_fixture()
            if change == "legacy":
                recipe["contract"] = "participation.native_html_statistics_recipe.v1"
            elif change == "percentage_count":
                recipe["roles"]["count"] = "pct"
                recipe["roles"]["percentage"] = None
            elif change == "absent_count":
                recipe["roles"]["count"] = None
            else:
                recipe["roles"]["count"] = "missing"
            with self.subTest(change=change), self.assertRaises(ValueError):
                extract(body, recipe)

    def test_count_only_suffix_cannot_drop_unreviewed_native_context(self):
        body, recipe = self.count_only_fixture()
        recipe["fields"][1]["suffix"] = " (61.0%)"
        with self.assertRaises(ValueError):
            extract(body, recipe)

    def test_count_only_statistics_bind_through_shared_intake(self):
        body, recipe = self.count_only_fixture()
        selected = extract(body, recipe)
        binding = dict(input="statistics", source_id="state-statistics", measure="turnout",
            native_measure_header="Total Voter Turnout:", record=dict(id="row"),
            path="count.value", parse="count",
            source_role="native_registration_ballot_reported_turnout_statistics",
            accepted_measure_literal="Total Voter Turnout",
            same_measure_review_evidence="Directly reported participation, not candidate votes")
        spec = dict(inputs=dict(statistics={}, recipe={}),
            geography=dict(state_code="AR"), election=dict(year=2026),
            format=dict(html_statistics_recipe_input="recipe", fact_bindings=[binding]))
        row = dict(id="row", count=dict(value=20), measure=dict(literal="Total Voter Turnout"))
        inputs = dict(statistics=json.dumps(selected).encode(), recipe=json.dumps(recipe).encode())
        verify_fact_bindings(spec, [row], inputs)
        row["count"]["value"] = 21
        with self.assertRaises(IntakeError):
            verify_fact_bindings(spec, [row], inputs)


if __name__ == "__main__":
    unittest.main()
