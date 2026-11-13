import copy
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.ballot_control_successor import build, export, native_facts, revise
from scripts.registered_control_successor import TABLES, csv_bytes, encoded, pin


def fixture():
    source = dict(id="native", url="https://example.gov/2026.xlsx",
        pin=dict(bytes=10, sha256="a" * 64), state_code="AA", election_year=2026,
        retrieved_at_utc="2026-11-12T00:00:00Z", native_updated_at=None)
    def row(number, **cells):
        return dict(row=number, cells=[dict(address=column + str(number), value=value)
                                     for column, value in cells.items()])
    facts = dict(contract="participation.native_factual_tables.v1", source=source, tables=[
        dict(name="State", workbook="native.xlsx", kind="worksheet", rows=[
            row(1, B="Total Ballots Cast"), row(2, A="One", B=11), row(3, A="Total", B=11)]),
        dict(name="One", workbook="units.xlsx", kind="worksheet", rows=[
            row(1, B="Total Ballots Cast"), row(2, A="u1", B=5), row(3, A="u2", B=6),
            row(4, A="Total", B=11)]),
        dict(name="Contest", workbook="native.xlsx", kind="worksheet", rows=[
            row(1, B="Named choice", C="Unassigned write-ins", D="Over", E="Under"),
            row(2, A="Total", B=8, C=1, D=1, E=1)])])
    state_query = dict(id="state", product="native", workbook="native.xlsx", tables=["State"],
        require={"1": {"B": "Total Ballots Cast"}}, first_row=2, last_row=3,
        fields=dict(county="A", ballots="B"), keys=["county"], counts=["ballots"])
    county_query = dict(state_query, id="county", workbook="units.xlsx", tables=["One"],
        first_row=4, last_row=4, fields=dict(county="$table", ballots="B"))
    unit_query = dict(county_query, id="unit", first_row=2, last_row=3,
        fields=dict(county="$table", unit="A", ballots="B"), keys=["county", "unit"])
    contest_query = dict(id="contest", product="native", workbook="native.xlsx", tables=["Contest"],
        first_row=2, last_row=2, fields=dict(county="A", R="B", write_ins="C", over="D", under="E"),
        keys=["county"], counts=["R", "write_ins", "over", "under"])
    recipe = dict(contract="participation.native_product_recipe.v1", products=[source],
                  queries=[state_query, county_query, unit_query, contest_query])
    def state_runtime(count):
        return gzip.compress(encoded(dict(
            views=dict(official=dict(counties=["one"])), records=[
                dict(id="one", geography=dict(name="One"), count=dict(value=count))])), mtime=0)
    files = {"facts": gzip.compress(encoded(facts), mtime=0), "recipe": encoded(recipe),
        "old/index.json": encoded(dict(states=dict(AA=dict(file="AA.json.gz")))),
        "old/AA.json.gz": state_runtime(10),
        "new/index.json": encoded(dict(states=dict(AA=dict(file="AA.json.gz")))),
        "new/AA.json.gz": state_runtime(11),
        "native/index.json": encoded(dict(reporting_tables=dict(AA=dict(file="AA.json.gz")))),
        "native/AA.json.gz": gzip.compress(encoded(dict(records=[
            dict(properties=dict(county="One", source_precinct_label="u1", ballots=5)),
            dict(properties=dict(county="One", source_precinct_label="u2", ballots=6))])), mtime=0)}
    state = dict(year="2026", state_code="AA", control_id="ballot-only",
        control_measure="reported_cast_ballots", control_native_numerator="10",
        control_registered_denominator="", control_native_time="prior", control_source_url="prior",
        reported_cast_ballots="10", reported_ballots_per_native_registered_denominator_pct="",
        conditional_registered_frame_scenario_available="False",
        house_candidate_vote_sum_context="8", civic_prior="69.3917", weight_qualified="False")
    control = dict(id="ballot-only", state_code="AA", year="2026", measure="reported_cast_ballots",
        selected_state_reference="True", geographic_level="state", numerator="10", denominator="",
        native_measure="Native ballots", source_time_label="prior", source_family="prior",
        source_url="prior", source_kind="prior", native_status="prior", scope_notes="prior")
    tables = ([state, dict(state, state_code="BB", control_id="other")],
              [control, dict(control, id="other", state_code="BB")],
              [dict(state_code="BB", control_id="other", modeled_voter="7.125", modeled_nonvoter="2.875")])
    review = dict(contract="participation.ballot_control_successor.v1", version=31, year=2026,
        state_code="AA", control_id="ballot-only", input_pins={}, source_id="native",
        source_members=dict(facts="facts", recipe="recipe", old_count_root="old",
                            new_count_root="new", new_native_root="native"),
        native_queries=dict(state="state", county="county", unit="unit", contest="contest"),
        count_field="ballots", county_field="county", unit_field="unit",
        native_measure_literal="Total Ballots Cast", state_total_selector=dict(county="Total"),
        expected_counties=1, expected_units=2, choice_fields=["R", "write_ins"],
        nonchoice_fields=["over", "under"], expected_states=["AA", "BB"],
        expected_table_rows=[2, 2, 1],
        scope_review="Existing ballot-only source count; valid-choice scope includes unassigned write-ins, "
                     "not people, turnout probability or a registered frame.")
    return files, tables, review


def packed(files, note=False):
    files = dict(files)
    files["checksums.json"] = encoded({name: pin(body) for name, body in files.items()})
    if note:
        files["REPRODUCE.txt"] = b"Complete source batch, not metadata only\n"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return stream.getvalue()


class BallotControlSuccessorTests(unittest.TestCase):
    def test_native_counter_requires_complete_unit_county_state_and_runtime_agreement(self):
        files, _, review = fixture()
        facts = native_facts(files, review)
        self.assertEqual((facts["previous_runtime_total"], facts["total"], facts["valid_choice_context"]), (10, 11, 9))
        damaged = json.loads(gzip.decompress(files["native/AA.json.gz"]))
        damaged["records"][0]["properties"]["ballots"] = 4
        files["native/AA.json.gz"] = gzip.compress(encoded(damaged), mtime=0)
        with self.assertRaisesRegex(ValueError, "reporting-unit runtime"):
            native_facts(files, review)

    def test_footer_query_uses_same_workbook_column_guard_not_an_unchecked_label(self):
        files, _, review = fixture()
        recipe = json.loads(files["recipe"])
        recipe["queries"][1].pop("require")
        files["recipe"] = encoded(recipe)
        self.assertEqual(native_facts(files, review)["total"], 11)
        recipe["queries"][2].pop("require")
        files["recipe"] = encoded(recipe)
        with self.assertRaisesRegex(ValueError, "guarded statistical column"):
            native_facts(files, review)

    def test_selected_count_only_changes_without_registered_model_or_other_state_changes(self):
        files, tables, review = fixture()
        before = copy.deepcopy(tables)
        updated, changes, delta = revise(tables, native_facts(files, review), review)
        self.assertEqual(tables, before)
        self.assertEqual(updated[0][1], tables[0][1])
        self.assertEqual(updated[1][1], tables[1][1])
        self.assertEqual(updated[2], tables[2])
        self.assertEqual(updated[0][0]["civic_prior"], tables[0][0]["civic_prior"])
        self.assertEqual(updated[0][0]["reported_cast_ballots"], "11")
        self.assertEqual(updated[0][0]["house_candidate_vote_sum_context"], "9")
        self.assertEqual(sum(r["changed"] for r in changes), 1)
        self.assertEqual(delta["ballot_reference_difference"], 1)
        self.assertFalse(delta["study_fit_weights_source_probability_or_registered_means_changed"])

    def test_registered_frame_scenario_or_nonselected_reference_cannot_be_promoted(self):
        for change in ("register", "scenario", "selected"):
            files, tables, review = fixture()
            if change == "register":
                tables[0][0]["control_registered_denominator"] = "15"
            elif change == "scenario":
                tables[2][0]["control_id"] = "ballot-only"
            else:
                tables[1][0]["selected_state_reference"] = "False"
            with self.subTest(change=change), self.assertRaises(ValueError):
                revise(tables, native_facts(files, review), review)

    def test_prior_counter_and_unknown_native_clock_must_remain_explicit(self):
        for change in ("prior", "clock", "noop"):
            files, tables, review = fixture()
            facts = native_facts(files, review)
            if change == "prior":
                tables[0][0]["reported_cast_ballots"] = "9"
            elif change == "clock":
                facts["native_source"]["native_updated_at"] = "unreviewed clock"
            else:
                facts.update(total=10, valid_choice_context=8)
            with self.subTest(change=change), self.assertRaises(ValueError):
                revise(tables, facts, review)

    def test_native_ballot_header_and_choice_accounting_are_not_interchangeable(self):
        for change in ("header", "accounting", "year"):
            files, _, review = fixture()
            if change == "header":
                review["native_measure_literal"] = "Candidate votes"
            elif change == "accounting":
                review["choice_fields"] = ["R"]
            else:
                review["year"] = 2024
            with self.subTest(change=change), self.assertRaises(ValueError):
                native_facts(files, review)

    def test_complete_packet_keeps_entire_inputs_and_all_existing_scenario_bytes(self):
        files, tables, review = fixture()
        baseline = {name: csv_bytes(rows) for name, rows in zip(TABLES, tables)}
        baseline.update({"summary.json": encoded(dict(native_control_version=30)),
                         "source-qualification.json": encoded(dict(prior_holds=True)),
                         "complete-extra-query.csv": b"value\n7\n"})
        previous, current = packed(baseline), packed(files, note=True)
        review["input_pins"] = dict(baseline=pin(previous), native_batch=pin(current))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / "inputs"
            inputs.mkdir()
            (inputs / "baseline-complete-analysis.zip").write_bytes(previous)
            (inputs / "native-batch-complete-analysis.zip").write_bytes(current)
            (inputs / "reviewed-successor.json").write_bytes(encoded(review))
            summary = export(inputs, root / "result")
            self.assertEqual(summary["changed_existing_scenarios"], 0)
            with zipfile.ZipFile(root / "result/complete-analysis.zip") as archive:
                self.assertEqual(archive.read(TABLES[2]), baseline[TABLES[2]])
                self.assertEqual(archive.read("complete-extra-query.csv"), baseline["complete-extra-query.csv"])
                self.assertEqual(archive.read("inputs/baseline-complete-analysis.zip"), previous)
                self.assertEqual(archive.read("inputs/native-batch-complete-analysis.zip"), current)
            review["replacement_count"] = 999
            (inputs / "reviewed-successor.json").write_bytes(encoded(review))
            with self.assertRaisesRegex(ValueError, "metadata cannot"):
                build(inputs)


if __name__ == "__main__":
    unittest.main()
