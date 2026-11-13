import copy
import gzip
import json
import unittest

from scripts.html_statistics import extract, pin
from scripts.participation_batch import compile_counts, compressed
from scripts.participation_intake.contract import STATES, encoded
from scripts.state_reporting_successor import ROLE_PATHS, refresh


class StateReportingSuccessorTests(unittest.TestCase):
    def fixture(self):
        body = b"""<div><input id="year" value="2026">
<b>Ballots Counted</b><i>100</i><b>Active Registered Voters</b><i>200</i>
<p>50.00%</p><time>Updated: Native time PT</time><input id="opaque" value="0"></div>"""
        recipe = dict(contract="participation.native_html_statistics_recipe.v1",
            source=dict(id="statistics", state_code="AR", election_year=2026,
                        url="https://example.gov/state", pin=pin(body)), encoding="utf-8",
            fields=[dict(name=name, kind="count", native_label=label,
                selector=dict(tag="b", text=label), following_sibling=dict(tag="i"))
                for name, label in (("count", "Ballots Counted"), ("denominator", "Active Registered Voters"))]
                + [dict(name="percentage", kind="percentage", native_label="Turnout", selector=dict(tag="p")),
                   dict(name="clock", kind="literal", native_label="Updated:", selector=dict(tag="time"), prefix="Updated:")],
            roles={key: key for key in ROLE_PATHS},
            assertions=[dict(selector=dict(tag="input", id="year"), attribute="value", expected="2026")],
            opaque_context=[dict(selector=dict(tag="input", id="opaque"), attribute="value")])
        selected = extract(body, recipe)
        previous = dict(ballots=90, denominator=199, source_update_label="Old native time",
                        denominator_basis="active_registered_voters")
        row = dict(id="state", geography=dict(level="state", state_code="AR"),
            election=dict(year=2026), count=dict(value=100, status="reported"),
            denominator=dict(value=200, basis="active_registered_voters"),
            source=dict(url=recipe["source"]["url"], input_sha256=pin(body)["sha256"]),
            source_clock=dict(literal="Native time PT", timezone=None),
            view=dict(ballots=100, denominator=200, native_published_pct="50.00%",
                source_update_label="Native time PT", source_update_timezone=None,
                source_retrieved_at="Separate retrieval", complete_download_url="https://example.gov/complete.zip",
                native_statistics=selected))
        bindings = [dict(record={"id": "state"}, path=path, source_id="statistics",
            measure=role, parse="count" if role in ("count", "denominator") else "literal")
            for role, paths in ROLE_PATHS.items() for path in paths]
        spec = dict(election=dict(year=2026), geography=dict(state_code="AR"),
            format=dict(html_statistics_recipe_input="recipe", fact_bindings=bindings,
                state_reporting=dict(statistics_path="view.native_statistics", previous_reference=previous,
                    registered_frame_review="Same native active-stock role; cutoff/transport remain unvalidated",
                    source_status_literal="Native unofficial result; finality unknown")))
        current = dict(snapshot=dict(reporting=[
            dict(previous, state_code="AR", source_url=recipe["source"]["url"], validated_pct=45.226,
                 reported_units=None, total_units=None),
            dict(state_code="NC", ballots=5)], early=[dict(ballots=7)],
            demographic_rows=[dict(ballots=0)]), unrelated="retained")
        return current, dict(spec=spec, rows=[row], target="state_reporting")

    def test_native_state_and_reviewed_register_change_preserve_other_modes_and_unknown_completeness(self):
        original, source = self.fixture()
        saved = copy.deepcopy(original)
        result, changed = refresh(original, [source])
        self.assertEqual(changed, 1)
        row = result["snapshot"]["reporting"][0]
        self.assertEqual((row["ballots"], row["denominator"], row["published_pct"]), (100, 200, 50.0))
        self.assertEqual(row["source_update_label"], "Native time PT")
        self.assertIsNone(row["reported_units"])
        self.assertIsNone(row["total_units"])
        self.assertEqual(result["snapshot"]["reporting"][1], saved["snapshot"]["reporting"][1])
        self.assertEqual(result["snapshot"]["early"], saved["snapshot"]["early"])
        self.assertEqual(result["snapshot"]["demographic_rows"], saved["snapshot"]["demographic_rows"])
        self.assertEqual(original, saved)

    def test_unreviewed_registration_or_changed_actual_preimage_is_refused(self):
        for change in ("review", "preimage", "basis"):
            current, source = self.fixture()
            if change == "review":
                source["spec"]["format"]["state_reporting"]["registered_frame_review"] = ""
            elif change == "preimage":
                current["snapshot"]["reporting"][0]["denominator"] = 198
            else:
                source["rows"][0]["denominator"]["basis"] = "eligible_population"
            with self.subTest(change=change), self.assertRaises(ValueError):
                refresh(current, [source])

    def test_count_register_percentage_and_clock_require_direct_native_fact_bindings(self):
        for role, paths in ROLE_PATHS.items():
            current, source = self.fixture()
            source["spec"]["format"]["fact_bindings"] = [
                item for item in source["spec"]["format"]["fact_bindings"] if item["path"] != paths[0]]
            with self.subTest(role=role), self.assertRaises(ValueError):
                refresh(current, [source])

    def test_partial_counties_duplicate_sources_opaque_counts_and_changed_pin_fail(self):
        for change in ("county", "extra_row", "duplicate", "opaque", "pin"):
            current, source = self.fixture()
            sources = [source]
            row = source["rows"][0]
            if change == "county":
                row["geography"]["level"] = "county"
            elif change == "extra_row":
                source["rows"].append(copy.deepcopy(row))
            elif change == "duplicate":
                sources.append(copy.deepcopy(source))
            elif change == "opaque":
                row["view"]["native_statistics"]["opaque_context"][0]["statistical_role_qualified"] = True
            else:
                row["source"]["input_sha256"] = "0" * 64
            with self.subTest(change=change), self.assertRaises(ValueError):
                refresh(current, sources)

    def test_compiler_changes_only_current_snapshot_and_index_retaining_every_state_shard(self):
        current, source = self.fixture()
        files = {"states/" + code + ".json.gz": compressed(dict(state_code=code, historical=True)) for code in STATES}
        files["current.json.gz"] = compressed(current)
        index = dict(current_snapshot=dict(file="current.json.gz", **pin(files["current.json.gz"])), states={})
        files["index.json"] = encoded(index)
        descriptor = dict(record_contract="participation.count_snapshot.v1", version="baseline",
            files={name: pin(body) for name, body in files.items()}, complete_download={})
        updated, result, changed = compile_counts(descriptor, files, index, [source])
        self.assertEqual(changed, 1)
        self.assertNotEqual(updated["version"], "baseline")
        self.assertEqual({name for name in files if files[name] != result[name]}, {"current.json.gz", "index.json"})
        self.assertEqual(json.loads(gzip.decompress(result["current.json.gz"]))["snapshot"]["reporting"][0]["ballots"], 100)


if __name__ == "__main__":
    unittest.main()
