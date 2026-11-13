import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

import fitz

from scripts.compile_pdf_grids import compile_grids
from scripts.native_products import pin
from scripts.pdf_measure_queries import csv_body, queries
from scripts.pdf_control_checks import ADMINISTRATIVE, build
from scripts.pdf_group_queries import build as group_queries
from scripts.native_reconciliation import reconcile
from scripts.verify_pdf_grids import verify


class ReviewedPdfGridTests(unittest.TestCase):
    def fixture(self, root):
        with fitz.open() as document:
            page = document.new_page(width=200, height=100)
            page.insert_text((70, 20), "Votes", fontsize=8)
            page.insert_text((10, 40), "County", fontsize=8)
            page.insert_text((70, 40), "731", fontsize=8)
            page.insert_text((10, 55), "Other", fontsize=8)
            body = document.tobytes()
        (root / "source.pdf").write_bytes(body)
        grid = dict(id="votes", page=1, source_role="unqualified_native_facts",
            require=[dict(reading_bbox=[60, 0, 120, 25], decoded_text="Votes")],
            fields=[dict(id="native_unit", kind="literal", band=[0, 60]),
                dict(id="votes", kind="count", band=[60, 120])],
            rows=[[25, 45], [45, 65]])
        return dict(contract="participation.reviewed_pdf_grids.v1",
            sources=[dict(id="source", filename="source.pdf", url="https://example.invalid/source.pdf", pin=pin(body),
                expected_pages=1, grids=[grid])])

    def test_pinned_compilation_and_independent_blank_or_numeric_corruption_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recipe = self.fixture(root)
            compiled = compile_grids(recipe, root)
            self.assertTrue(verify(recipe, compiled, root)["passed"])
            for row, wrong_value in ((0, 732), (1, 0)):
                with self.subTest(row=row):
                    corrupted = copy.deepcopy(compiled)
                    corrupted["products"][0]["tables"][0]["rows"][row]["cells"]["votes"]["value"] = wrong_value
                    result = verify(recipe, corrupted, root)
                    self.assertFalse(result["passed"])
                    self.assertEqual(len(result["failures"]), 1)

    def test_changed_source_body_and_incomplete_query_inventory_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recipe = self.fixture(root)
            compiled = compile_grids(recipe, root)
            compiled["products"][0]["tables"][0]["rows"].pop()
            with self.assertRaises(ValueError):
                verify(recipe, compiled, root)
            body = (root / "source.pdf").read_bytes()
            (root / "source.pdf").write_bytes(body + b"\n")
            with self.assertRaises(ValueError):
                compile_grids(recipe, root)

    def test_complete_json_and_csv_preserve_unknown_versus_zero_without_creating_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compiled = compile_grids(self.fixture(root), root)
            result = queries(compiled)
            self.assertEqual([row["value"] for row in result["rows"]], [731, None])
            exported = list(csv.DictReader(io.StringIO(csv_body(result).decode())))
            self.assertEqual([json.loads(row["value_json"]) for row in exported], [731, None])
            self.assertEqual(exported[1]["native_status"], "blank")
            self.assertEqual({row["measure"] for row in exported}, {"votes"})
            compiled["products"][0]["tables"][0]["rows"][1]["cells"]["votes"].update(
                value=0, native_status="reported", decoded_text="0")
            changed = list(csv.DictReader(io.StringIO(csv_body(queries(compiled)).decode())))
            self.assertEqual(json.loads(changed[1]["value_json"]), 0)
            self.assertEqual(changed[1]["native_status"], "reported")

    def test_repeated_controls_require_equality_and_missing_controls_are_not_zero(self):
        def row(number, name, early, mail):
            return dict(row=number, cells={key: dict(value=value) for key, value in
                dict(native_unit=name, early_votes_cast=early, mail_ballots_tallied=mail).items()})
        table = dict(id="same-native-grid", source_role=ADMINISTRATIVE,
            source_annotations=dict(native_table_clock_literal="11/12/26 4:41 PM"),
            rows=[row(1, "Example County", 731, None),
                row(2, "Example County", 731, None),
                row(3, "Municipality TOTALS", 732, 0)])
        grids = dict(products=[dict(source=dict(id="source"), tables=[table])])
        result = build(grids)
        self.assertEqual(len(result["observations"]), 1)
        self.assertEqual(len(result["equality_checked_repeated_controls"]), 1)
        self.assertEqual(len(result["excluded_comparisons"]), 1)
        checked = reconcile(result["queries"], result["checks"])
        self.assertEqual(checked["checks"][0]["rows"][0]["signed_left_minus_right"], 1)
        table["rows"][1]["cells"]["early_votes_cast"]["value"] = 730
        with self.assertRaises(ValueError):
            build(grids)
        table["rows"][1]["cells"]["early_votes_cast"]["value"] = 731
        grids["products"].append(dict(source=dict(id="second-source"), tables=[copy.deepcopy(table)]))
        combined = build(grids)
        self.assertEqual(len(combined["observations"]), 2)
        self.assertEqual(len(combined["checks"]), 2)

    def grouping_fixture(self):
        def row(index, name, district, registered, votes, pct):
            return dict(row=index, cells={key: dict(value=value) for key, value in dict(
                native_unit=name, district=district, registered=registered, votes=votes, pct=pct).items()})
        tables = [
            dict(id="first", source_page=1, rows=[row(0, "A", "", None, None, ""),
                row(1, "One\nTown", "1", 10, 6, "60%")]),
            dict(id="second", source_page=2, rows=[row(0, "One Town", "2", 20, 12, "60%"),
                row(1, "A Total", "", 30, 18, "60%")]),
            dict(id="summary", source_page=2, rows=[row(0, "A", "", 30, 18, "60%"),
                row(1, "State Total", "", 30, 18, "60%")])]
        for table in tables:
            table["source_role"] = "native_registration_ballot_reported_turnout_statistics"
        grids = dict(contract="participation.reviewed_pdf_factual_grids.v1",
            products=[dict(source=dict(id="source"), tables=tables)])
        recipe = dict(contract="participation.reviewed_pdf_group_queries.v1", source_id="source",
            part_tables=["first", "second"], summary_tables=["summary"],
            reading_whitespace_normalized=True, count_fields=["registered", "votes"],
            part_nonempty_fields=["district"], parent_total_suffix=" Total",
            summary_total_label="State Total",
            expected_rows=dict(parts=2, parent_controls=1, summary_parents=1, summary_total=1, grouped_units=1),
            percentages=[dict(field="pct", numerator="votes", denominator="registered")])
        return grids, recipe

    def test_native_groups_reconcile_cross_page_parts_without_averaging_printed_rates(self):
        grids, recipe = self.grouping_fixture()
        result = group_queries(grids, recipe)
        grouped = result["queries"]["grouped_units"]["rows"]
        self.assertEqual((len(grouped), grouped[0]["votes"], grouped[0]["registered"]), (1, 18, 30))
        self.assertNotIn("pct", grouped[0])
        self.assertEqual(grouped[0]["source_parts"], 2)
        self.assertTrue(all(row["status"] == "matched" for row in result["native_rate_checks"]))
        self.assertTrue(reconcile(result["queries"], result["checks"])["required_checks_passed"])
        grids["products"][0]["tables"][2]["rows"][1]["cells"]["votes"]["value"] = 19
        changed = group_queries(grids, recipe)
        self.assertFalse(reconcile(changed["queries"], changed["checks"])["required_checks_passed"])

    def test_native_groups_reject_missing_counts_headers_controls_and_duplicate_rows(self):
        for defect in ("count", "header", "control", "duplicate", "part_identity"):
            with self.subTest(defect=defect):
                grids, recipe = self.grouping_fixture()
                tables = grids["products"][0]["tables"]
                if defect == "count":
                    tables[1]["rows"][0]["cells"]["votes"]["value"] = None
                elif defect == "header":
                    tables[0]["rows"].pop(0)
                elif defect == "control":
                    tables[1]["rows"].pop()
                elif defect == "duplicate":
                    tables[1]["rows"].append(copy.deepcopy(tables[1]["rows"][0]))
                else:
                    tables[1]["rows"][0]["cells"]["district"]["value"] = "1"
                with self.assertRaises(ValueError):
                    group_queries(grids, recipe)

    def test_zero_denominator_percentage_is_unqualified_not_reported_zero(self):
        grids, recipe = self.grouping_fixture()
        cells = grids["products"][0]["tables"][0]["rows"][1]["cells"]
        cells["registered"]["value"] = 0
        cells["votes"]["value"] = 0
        result = group_queries(grids, recipe)
        check = result["native_rate_checks"][0]
        self.assertEqual(check["status"], "unqualified_native_fraction")
        self.assertNotIn("exact_percent", check)


if __name__ == "__main__":
    unittest.main()
