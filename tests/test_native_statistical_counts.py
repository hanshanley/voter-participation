import copy
import unittest

from scripts.native_statistical_counts import observations
from scripts.participation_intake.contract import encoded


class NativeStatisticalCountsTests(unittest.TestCase):
    def setUp(self):
        self.spec = dict(id="native-statistics", adapter="native_statistics",
            review_evidence="Synthetic reviewed statistical source",
            geography=dict(state_code="MI"), notes=["No rates or unique people are qualified."],
            reporting_status="Unofficial",
            election=dict(id="general", year=2026, date="2026-11-03",
                          type="general", qualification="native"),
            measure=dict(id="reported-statistic", kind="participation_reported",
                         literal="Reviewed Voters Cast", mode="source_defined", unit="source_reported_count"),
            view=dict(identities={}), format=dict(native_statistics=dict(
                contract="participation.native_statistical_counts.v1",
                measure_review_evidence="Source statistical measure, not candidate votes",
                recipe_input="recipe", products={}, composite=dict(identity="county",
                    source_url="https://example.gov/index", disjoint_scope_review_evidence="Disjoint source regions",
                    different_clock_review_evidence="Different clocks retained, no common as-of time"))))
        recipe = dict(contract="participation.native_product_recipe.v1", products=[], queries=[])
        self.products = {}
        for index in range(2):
            name, value = "source-" + str(index), index
            source = dict(id=name, url="https://example.gov/" + name, pin=dict(bytes=10, sha256=str(index)*64),
                state_code="MI", election_year=2026, retrieved_at_utc="2026-11-13T00:00:00Z",
                native_updated_at=None, redistribution="complete_factual_tables_not_publisher_templates")
            recipe["products"].append(source)
            selection = dict(id=name+"-statistics", product=name, tables=["Stats"],
                fields=dict(row="$row", label="A", registered="B", cast="D", fraction="F"), keys=["row"],
                require={"1": {"A": "Precinct", "D": "Voters Cast"}})
            recipe["queries"].append(selection)
            config = dict(facts_input=name, query=selection["id"], header_row=1,
                native_measure_header="Voters Cast", expected_units=1,
                election_header=dict(cell="C1", literal="General November 3, 2026",
                    date_literal="November 3, 2026", date_format="%B %d, %Y"),
                grouping=dict(fields=dict(row="row", label="label", registered="registered",
                    cast="cast", fraction="fraction"), first_row=2, modes=["Election Day"],
                    parents=["Region - Total", "County - Total"]),
                clock=dict(table="Stats", cell="H1", number_format="m/d/yyyy h:mm:ss"))
            self.spec["format"]["native_statistics"]["products"][name] = config
            lines = [
                dict(A="Precinct", C="General November 3, 2026", D="Voters Cast", H="46332.5"),
                dict(A="Unit "+name), dict(A="Election Day", B=0, D=value),
                dict(A="Total", B=0, D=value), dict(A="Region - Total", B=0, D=value),
                dict(A="County - Total", B=0, D=value), dict(A="Election Day", B=0, D=value)]
            table = dict(name="Stats", kind="worksheet", workbook_properties={},
                workbook_cell_formats=[dict(numFmtId="164")],
                workbook_number_formats={"164": "m/d/yyyy h:mm:ss"},
                rows=[dict(row=number, cells=[
                    dict(address=column+str(number), value=value, formula=None,
                        attributes=dict(s="0"), storage_type="n" if column == "H" else "inlineStr",
                        cached_literal=value if column == "H" else None)
                    for column, value in line.items()]) for number, line in enumerate(lines, 1)])
            self.products[name] = dict(contract="participation.native_factual_tables.v1",
                                       source=source, tables=[table])
            self.identity(name+":4", "reporting_unit")
        self.identity("county", "county")
        self.recipe = recipe

    def identity(self, key, level):
        self.spec["view"]["identities"][key] = dict(
            canonical_geography=dict(id=key, name=key, state_code="MI", level=level, parent_id=None,
                join=dict(status="unreviewed", reference_id=None, feature_key=None, evidence=None)),
            maps_approved=False)

    def run_source(self):
        return observations(self.spec, dict(recipe=encoded(self.recipe),
                            **{name: encoded(value) for name, value in self.products.items()}))

    def test_zero_and_unknown_fraction_survive_without_registration_or_rate_promotion(self):
        rows = self.run_source()
        self.assertEqual([row["count"]["value"] for row in rows], [0, 1, 1])
        self.assertTrue(all(row["denominator"] is None and row["view"]["reported_pct"] is None for row in rows))
        self.assertTrue(all(row["view"]["denominator_basis"] == "electorate_not_qualified" for row in rows))
        self.assertIsNone(rows[0]["view"]["native_record"]["native_unit"]["native_fraction"])
        self.assertEqual(rows[1]["view"]["native_record"]["native_unit"]["registered"], 0)
        self.assertFalse(rows[-1]["view"]["native_record"]["native_county_parent"])
        self.assertIn("2026-11-06T12:00:00.000", rows[0]["source_clock"]["literal"])

    def test_missing_units_or_changed_count_header_cannot_be_authorized_by_metadata(self):
        config = self.spec["format"]["native_statistics"]["products"]["source-0"]
        config["expected_units"] = 2
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.run_source()
        config["expected_units"] = 1
        config["native_measure_header"] = "Candidate votes"
        with self.assertRaisesRegex(ValueError, "count column"):
            self.run_source()

    def test_overlapping_literal_units_and_unreviewed_composites_are_rejected(self):
        self.products["source-1"]["tables"][0]["rows"][1]["cells"][0]["value"] = "Unit source-0"
        with self.assertRaisesRegex(ValueError, "overlapping"):
            self.run_source()
        self.products["source-1"]["tables"][0]["rows"][1]["cells"][0]["value"] = "Unit source-1"
        self.spec["format"]["native_statistics"]["composite"]["different_clock_review_evidence"] = ""
        with self.assertRaisesRegex(ValueError, "disjoint source frames and clocks"):
            self.run_source()

    def test_parent_conflicts_clock_formulas_and_precinct_map_promotion_are_rejected(self):
        original = copy.deepcopy(self.products)
        self.products["source-1"]["tables"][0]["rows"][5]["cells"][-1]["value"] = 2
        with self.assertRaisesRegex(ValueError, "parent controls disagree"):
            self.run_source()
        self.products = original
        clock = self.products["source-0"]["tables"][0]["rows"][0]["cells"][-1]
        clock["formula"] = dict(text="NOW()")
        with self.assertRaisesRegex(ValueError, "clock format"):
            self.run_source()
        clock["formula"] = None
        self.spec["view"]["identities"]["source-0:4"]["maps_approved"] = True
        with self.assertRaisesRegex(ValueError, "precinct geometry"):
            self.run_source()

    def test_native_election_date_is_not_inferred_from_metadata_or_filename(self):
        self.products["source-0"]["tables"][0]["rows"][0]["cells"][1]["value"] = "General November 5, 2024"
        with self.assertRaisesRegex(ValueError, "election header"):
            self.run_source()


if __name__ == "__main__":
    unittest.main()
