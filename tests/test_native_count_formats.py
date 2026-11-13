import copy
import json
import unittest

from scripts.native_products import pin, query, unpack
from scripts.participation_intake.adapters import verify_fact_bindings


class NativeCountFormatTests(unittest.TestCase):
    def wide_fixture(self):
        source = dict(id="wide", url="https://example.test/native.zip", pin=pin(b"native"),
            state_code="AL", election_year=2026, retrieved_at_utc=None, native_updated_at=None)
        grid = [["Contest", "001", "ABSENTEE"], ["Registered", 0, None], ["Ballots", 7, 0]]
        table = dict(kind="worksheet", name="Counts", workbook="native.xls", ncols=3,
            rows=[dict(row=i, cells=[dict(address=chr(65+j)+str(i), value=value)
                for j, value in enumerate(row)]) for i, row in enumerate(grid, 1)])
        product = dict(contract="participation.native_factual_tables.v1", source=source, tables=[table])
        selection = dict(id="wide-counts", product="wide", workbook="native.xls", tables=["Counts"],
            axis="columns", first_column=2, last_column=3,
            fields=dict(column="$column", unit="$row:1", registered="$row:2", ballots="$row:3"),
            counts=["ballots"], keys=["column"], require={"3": {"A": "Ballots"}})
        binding = dict(record=dict(id="row"), input="facts", source_id="wide", query_recipe_input="recipe",
            native_query_id="wide-counts", source_role="native_registration_ballot_reported_turnout_statistics",
            measure="ballots", native_header_row=3, native_header_column="A", native_measure_header="Ballots",
            accepted_measure_literal="Ballots", same_measure_review_evidence="Direct physical ballot-statistics row",
            native_records=[dict(column="B"), dict(column="C")], operation="sum",
            native_sum_scope="complete_query",
            native_first_data_column=2,
            sum_review_evidence="Distinct complete source columns, no native parent added again",
            parse="count", path="count.value")
        spec = dict(inputs=dict(facts={}, recipe={}), geography=dict(state_code="AL"),
            election=dict(year=2026), format=dict(fact_bindings=[binding]))
        inputs = dict(facts=json.dumps(product).encode(), recipe=json.dumps(dict(
            contract="participation.native_product_recipe.v1", products=[source], queries=[selection])).encode())
        return product, selection, binding, spec, inputs

    def test_wide_statistical_rows_preserve_physical_columns_zero_and_unknown_registration(self):
        product, selection, _, _, _ = self.wide_fixture()
        rows = query(product, selection)["rows"]
        self.assertEqual([(r["unit"], r["ballots"], r["registered"]) for r in rows],
                         [("001", 7, 0), ("ABSENTEE", 0, None)])
        self.assertEqual(rows[1]["source_rows"][0]["column"], "C")
        self.assertEqual(rows[1]["source_rows"][0]["rows_by_field"]["ballots"], 3)

    def test_wide_native_sum_requires_complete_distinct_directly_guarded_source_records(self):
        _, _, binding, spec, inputs = self.wide_fixture()
        row = dict(id="row", count=dict(value=7), measure=dict(literal="Ballots"))
        verify_fact_bindings(spec, [row], inputs)
        for change in ("duplicate", "absent", "unguarded", "metadata", "count",
                       "omitted_zero", "omitted_nonzero", "truncated_query",
                       "leading_nonzero", "leading_zero", "rebound_leading_nonzero", "rebound_leading_zero"):
            changed_spec, changed_row = copy.deepcopy(spec), copy.deepcopy(row)
            changed_inputs = dict(inputs)
            b = changed_spec["format"]["fact_bindings"][0]
            if change == "duplicate":
                b["native_records"].append(dict(column="B"))
            elif change == "absent":
                b["native_records"][0] = dict(column="Z")
            elif change == "unguarded":
                b["native_header_row"] = 2
            elif change == "metadata":
                b["value_scope"] = "source"
            elif change in ("omitted_zero", "truncated_query"):
                b["native_records"].pop()
                if change == "truncated_query":
                    recipe = json.loads(inputs["recipe"])
                    recipe["queries"][0]["last_column"] = 2
                    changed_inputs["recipe"] = json.dumps(recipe).encode()
            elif change == "omitted_nonzero":
                b["native_records"].pop(0)
                changed_row["count"]["value"] = 0
            elif "leading" in change:
                recipe = json.loads(inputs["recipe"])
                recipe["queries"][0]["first_column"] = 3
                changed_inputs["recipe"] = json.dumps(recipe).encode()
                b["native_records"].pop(0)
                changed_row["count"]["value"] = 0
                if change.endswith("zero") and not change.endswith("nonzero"):
                    product = json.loads(inputs["facts"])
                    cells = product["tables"][0]["rows"][2]["cells"]
                    cells[1]["value"], cells[2]["value"] = 0, 7
                    changed_inputs["facts"] = json.dumps(product).encode()
                    changed_row["count"]["value"] = 7
                if change.startswith("rebound"):
                    b["native_first_data_column"] = 3
            else:
                changed_row["count"]["value"] = 8
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_fact_bindings(changed_spec, [changed_row], changed_inputs)

    def test_wide_axis_cannot_promote_column_addresses_or_missing_cells_to_counts(self):
        product, selection, _, _, _ = self.wide_fixture()
        for field in ("column", "registered"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                query(product, dict(selection, counts=[field]))

    def setUp(self):
        self.body = b"unit,ballots,reporting\nA,10,0\nB,0,1\n"
        self.spec = dict(id="test", path="native.csv", kind="delimited",
            pin=pin(self.body), reader={}, expected_rows=2,
            url="https://example.test/public-aggregate.csv", state_code="WA",
            election_year=2026, retrieved_at_utc=None, native_updated_at=None,
            redistribution="factual_tables")
        self.selection = dict(id="units", product="test",
            fields=dict(unit="unit", ballots="ballots", reporting="reporting"),
            counts=["ballots"], keys=["unit"], deduplicate=False)

    def test_explicit_grouped_counts_preserve_native_text_and_true_zero(self):
        body = b'unit,ballots,reporting\nA,"935,956",0\nB,0,1\n'
        product = unpack(dict(self.spec, pin=pin(body)), body)
        with self.assertRaises(ValueError):
            query(product, self.selection)
        selection = dict(self.selection, count_formats=dict(ballots="comma_grouped_integer"))
        result = query(product, selection)
        self.assertEqual([row["ballots"] for row in result["rows"]], [935956, 0])
        self.assertEqual(product["tables"][0]["rows"][0]["values"][1], "935,956")
        self.assertEqual(result["rows"][0]["source_rows"][0]["row"], 2)

    def test_grouped_format_rejects_malformed_values_and_noncount_fields(self):
        for value in ("1,20", "12,34,567", "1.234", "-1", "", " 1,234", "1,234 "):
            with self.subTest(value=value):
                body = ('unit,ballots,reporting\nA,"'+value+'",0\n').encode()
                product = unpack(dict(self.spec, pin=pin(body), expected_rows=1), body)
                selection = dict(self.selection, count_formats=dict(ballots="comma_grouped_integer"))
                with self.assertRaisesRegex(ValueError, "malformed grouped count"):
                    query(product, selection)
        product = unpack(self.spec, self.body)
        for declaration in (dict(unit="comma_grouped_integer"), dict(ballots="decimal"), []):
            with self.subTest(declaration=declaration), self.assertRaisesRegex(ValueError, "supported format"):
                query(product, dict(self.selection, count_formats=declaration))
