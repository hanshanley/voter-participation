import copy
import unittest

from scripts.native_count_refresh import prepare_rows
from scripts.participation_batch import refresh_current_reporting
from scripts.participation_intake.adapters import make_row


class NativeCountRefreshTests(unittest.TestCase):
    def fixture(self):
        url = "https://example.gov/reporting.json"
        spec = dict(id="native", classification="public_aggregate", primary_input="data",
            inputs=dict(data=dict(url=url)), columns=dict(
                geography_id="county_id", geography_name="county", count="ballots", denominator="registered"),
            geography=dict(state_code="AR", level="county"), rate_levels=["county"],
            measure=dict(id="ballots", literal="Reported ballots", kind="participation_reported",
                mode="source_defined", unit="source_reported_count"),
            denominator=dict(literal="Registered source units", basis="registered_source_units"),
            election=dict(id="general", date=None, year=2026, type="general", qualification="previously_reviewed"))
        originals, native = [], []
        for index, name, previous, current, registered in [
                (1, "One", 10, 11, 100), (2, "Two", 20, 21, 200)]:
            row = make_row(spec, dict(county_id=str(index), county=name,
                ballots=previous, registered=registered), index, dict(sha256="a" * 64),
                dict(literal="Earlier source date", timezone=None), {})
            row["view"] = dict(year=2026, state_code="AR", county_id=str(index), county=name,
                ballots=previous, denominator=registered, reported_pct=10.0,
                source_url=url, source_update_label="Earlier source date")
            originals.append(row)
            native.append(dict(county_id=str(index), county=name, ballots=current,
                registered=registered, reported_units=1, total_units=1,
                source_clock="Own county date " + str(index), published_pct=str(100 * current / registered) + "%",
                source_rows=[dict(record_index=index)]))
        total = dict(county_id="0", county="STATE", ballots=32, registered=300,
            reported_units=2, total_units=2, source_clock="Own state date",
            published_pct="10.67%", source_rows=[dict(record_index=0)])
        fields = dict(ballots="bct", registered="rtl", reported_units="prt",
            total_units="ptl", source_clock="imp", published_pct="bpt")
        query = dict(id="counties", product="api", fields=fields)
        source = dict(id="api", kind="json_records", state_code="AR", election_year=2026,
            url=url, pin=dict(sha256="b" * 64), retrieved_at_utc="2026-11-13T00:00:00Z")
        recipe = dict(products=[source], queries=[query, dict(query, id="state")])
        counts = ["ballots", "registered", "reported_units", "total_units"]
        queries = dict(counties=dict(product="api", rows=native, count_fields=counts),
            state=dict(product="api", rows=[total], count_fields=counts))
        review = dict(contract="participation.native_count_refresh.v1",
            state_code="AR", year=2026, source_id="api", county_query="counties", state_query="state",
            identity_fields=dict(county_id="view.county_id", county="geography.name"),
            count_field="ballots", denominator_field="registered", reported_units_field="reported_units",
            total_units_field="total_units", clock_field="source_clock", published_pct_field="published_pct",
            scope_review="Reviewed same-source aggregate statistics; no new geography or registered frame",
            notes=["Source counts only; no individual behavior inferred"], release_tag="reviewed-source",
            refresh_current_reporting=True)
        return originals, recipe, queries, review

    def test_exact_native_source_refresh_preserves_ids_geography_registers_and_own_clocks(self):
        originals, recipe, queries, review = self.fixture()
        rows, bindings = prepare_rows(originals, recipe, queries, review)
        self.assertEqual([row["count"]["value"] for row in rows], [11, 21])
        for before, after in zip(originals, rows):
            self.assertEqual(before["id"], after["id"])
            self.assertEqual(before["geography"], after["geography"])
            self.assertEqual(before["denominator"], after["denominator"])
        self.assertEqual([row["source_clock"]["literal"] for row in rows],
            ["Own county date 1", "Own county date 2"])
        self.assertTrue(any(binding.get("value_scope") == "row" for binding in bindings))
        self.assertEqual(originals[0]["count"]["value"], 10)

    def test_changed_identity_or_registered_frame_and_reused_state_control_fail(self):
        for change in ("name", "register", "state_record", "metadata"):
            originals, recipe, queries, review = self.fixture()
            if change == "name":
                queries["counties"]["rows"][0]["county"] = "Alias"
            elif change == "register":
                queries["counties"]["rows"][0]["registered"] = 101
                queries["state"]["rows"][0]["registered"] = 301
            elif change == "state_record":
                queries["state"]["rows"][0]["source_rows"] = [dict(record_index=1)]
            else:
                review["replacement_count"] = 999
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_rows(originals, recipe, queries, review)

    def test_native_fraction_and_source_family_disagreements_require_review(self):
        for change in ("fraction", "source", "timezone"):
            originals, recipe, queries, review = self.fixture()
            if change == "fraction":
                queries["counties"]["rows"][0]["published_pct"] = "99%"
            elif change == "source":
                recipe["products"][0]["url"] = "https://different.example/source"
            else:
                originals[0]["source_clock"]["timezone"] = "UTC"
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_rows(originals, recipe, queries, review)

    def test_preexisting_withheld_fraction_is_not_promoted_by_a_new_count(self):
        originals, recipe, queries, review = self.fixture()
        originals[0]["view"]["reported_pct"] = None
        rows, _ = prepare_rows(originals, recipe, queries, review)
        self.assertIsNone(rows[0]["view"]["reported_pct"])

    def reporting_fixture(self):
        originals, recipe, queries, review = self.fixture()
        rows, bindings = prepare_rows(originals, recipe, queries, review)
        roles = {role: review[role + "_field"] for role in (
            "count", "denominator", "reported_units", "total_units", "clock", "published_pct")}
        source = dict(rows=rows, spec=dict(geography=dict(state_code="AR"), format=dict(
            fact_bindings=bindings, native_reproduction=dict(recipe_input="recipe"),
            current_reporting=dict(query_id="state", reference_path="view.native_state_reference", fields=roles))))
        record = dict(state_code="AR", source_url=recipe["products"][0]["url"],
            ballots=30, denominator=300, published_pct=10.0, validated_pct=10.0,
            source_snapshot="earlier")
        data = dict(snapshot=dict(reporting=[record, dict(record, state_code="NC")],
            early_voting=[dict(state_code="AR", ballots=5)],
            demographics=[dict(state_code="AR", ballots=3)], limitations=[]))
        return data, source

    def test_existing_state_and_counties_advance_together_without_touching_other_frames(self):
        data, source = self.reporting_fixture()
        before = copy.deepcopy(data)
        result, changed = refresh_current_reporting(data, [source])
        self.assertEqual(changed, 1)
        self.assertEqual(result["snapshot"]["reporting"][0]["ballots"], 32)
        self.assertEqual(result["snapshot"]["reporting"][0]["source_update_label"], "Own state date")
        self.assertEqual(result["snapshot"]["reporting"][1], before["snapshot"]["reporting"][1])
        for key in ("early_voting", "demographics"):
            self.assertEqual(result["snapshot"][key], before["snapshot"][key])
        self.assertEqual(data, before)

    def test_state_refresh_rejects_unbound_metadata_and_changed_registered_frames(self):
        for change in ("metadata", "binding", "register", "source", "fraction"):
            data, source = self.reporting_fixture()
            if change == "metadata":
                source["spec"]["format"].pop("native_reproduction")
            elif change == "binding":
                source["spec"]["format"]["fact_bindings"] = []
            elif change == "register":
                data["snapshot"]["reporting"][0]["denominator"] = 301
            elif change == "source":
                data["snapshot"]["reporting"][0]["source_url"] = "https://different.example/source"
            else:
                for row in source["rows"]:
                    row["view"]["native_state_reference"]["published_pct"] = "99%"
            with self.subTest(change=change), self.assertRaises(ValueError):
                refresh_current_reporting(data, [source])


if __name__ == "__main__":
    unittest.main()
