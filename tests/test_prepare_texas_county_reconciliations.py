import unittest

from scripts.prepare_texas_county_reconciliations import (
    SOURCES,
    append_visual_controls,
    bindings,
    fact_table,
    observation,
)


def row(native_unit, measure, value):
    return {
        "row": 1,
        "cells": {
            "native_unit": {"value": native_unit, "native_status": "literal"},
            measure: {
                "value": value,
                "native_status": (
                    "blank" if value is None else "reported" if type(value) is int else "literal"
                ),
            },
        },
    }


def facts():
    products = []
    for name, source in SOURCES.items():
        tables = {}

        def add(kind, unit, measure, value):
            identifier = fact_table(name, kind)
            tables.setdefault(identifier, []).append(row(unit, measure, value))

        add("counted", source["ballots_unit"], "ballots", source["ballots"])
        add("registered", source["registered_unit"], "registered", source["registered_value"])
        add("voters", source["voters_unit"], "voters", source["total_voters"])
        add("rejected", source["rejected_unit"], "rejected", source["total_rejected"])
        add("difference", source["difference_unit"], "difference", source["difference"])
        add("clock", source["clock_unit"], "source_time", source["clock_value"])
        add("status", source["status_unit"], "status", source["status_literal"])
        add("county", source["county_unit"], "county", source["native_county"])
        add(
            "election-date",
            source["election_date_unit"],
            "election_date",
            source["native_election_date"],
        )
        products.append(
            {
                "source": {
                    "id": source["source_id"],
                    "url": source["url"],
                    "pin": source["pin"],
                },
                "tables": [
                    {"id": identifier, "rows": rows}
                    for identifier, rows in tables.items()
                ],
            }
        )
    return {"contract": "participation.reviewed_pdf_factual_grids.v1", "products": products}


class TexasCountyReconciliationTests(unittest.TestCase):
    def test_inventory_is_eight_distinct_county_products(self):
        self.assertEqual(
            {source["fips"] for source in SOURCES.values()},
            {"48009", "48061", "48211", "48291", "48341", "48353", "48391", "48497"},
        )
        self.assertEqual(len({source["url"] for source in SOURCES.values()}), 8)
        self.assertEqual(len({source["pin"]["sha256"] for source in SOURCES.values()}), 8)
        self.assertEqual(
            [source["stage"] for source in SOURCES.values()].count("preliminary"), 3
        )

    def test_observations_keep_rates_and_count_update_clocks_null(self):
        compiled = facts()
        for name, source in SOURCES.items():
            with self.subTest(name=name):
                result = observation(name, compiled)
                self.assertEqual(result["count"]["value"], source["ballots"])
                self.assertIsNone(result["denominator"])
                self.assertIsNone(result["view"]["denominator"])
                self.assertIsNone(result["view"]["reported_pct"])
                self.assertIsNone(result["source_clock"]["literal"])
                self.assertIsNone(result["view"]["source_update_label"])
                self.assertEqual(result["view"]["source_time_kind"], source["source_time_kind"])
                self.assertEqual(result["view"]["source_time_literal"], source["clock_value"])
                self.assertIn("not a count-as-of update", result["view"]["source_reporting_label"])
                self.assertEqual(result["view"]["registered"], source["registered_value"])
                self.assertTrue(result["view"]["maps_approved"])
                self.assertFalse(result["view"]["unique_voter_count_qualified"])
                self.assertFalse(result["view"]["cast_ballot_count_qualified"])

    def test_bindings_cover_counts_and_typed_provenance_not_update_clocks(self):
        compiled = facts()
        for name in SOURCES:
            result = observation(name, compiled)
            paths = {item["path"] for item in bindings(name, result)}
            self.assertTrue(
                {
                    "count.value",
                    "count.literal",
                    "view.ballots",
                    "source.fields.ballots",
                    "view.native_record.ballots",
                    "view.registered",
                    "source.fields.source_time_literal",
                    "view.source_time_literal",
                }
                <= paths
            )
            self.assertNotIn("source_clock.literal", paths)
            self.assertNotIn("view.source_update_label", paths)

    def test_hemphill_native_difference_conflict_is_structured_and_unrepaired(self):
        result = observation("hemphill", facts())
        self.assertEqual(
            result["quality"]["conflicts"],
            [
                {
                    "code": "native_reconciliation_difference_disagrees",
                    "repaired": False,
                    "actual_native": 3,
                    "computed": 0,
                    "expression": "E-H-M",
                }
            ],
        )
        self.assertIn(
            "Native printed reconciliation difference 3 disagrees with computed E-H-M=0",
            result["view"]["source_reporting_label"],
        )

    def test_refugio_mode_vectors_remain_distinct_and_pending_counts_are_not_added(self):
        result = observation("refugio", facts())
        notes = " ".join(result["quality"]["notes"])
        self.assertIn("in-person voters 2,364 versus 2,354 counted", notes)
        self.assertIn("mail voters 84 versus 94 counted", notes)
        self.assertEqual(result["count"]["value"], 2448)
        self.assertNotEqual(result["count"]["value"], 2448 + 14 + 1)

    def test_cameron_registration_equality_does_not_promote_a_rate(self):
        result = observation("cameron", facts())
        notes = " ".join(result["quality"]["notes"])
        self.assertIn(
            "Registered Voters 103,976 exactly equals M. Total ballots counted 103,976",
            notes,
        )
        self.assertIn("E. Total voters 104,206 exceeds that registration stock by 230", notes)
        self.assertIn("no 100% turnout inference, analytical rate or repair", notes)
        self.assertIsNone(result["denominator"])
        self.assertIsNone(result["view"]["reported_pct"])

    def test_visual_controls_require_every_exact_source_pin(self):
        visual_names = [
            name
            for name, source in SOURCES.items()
            if source.get("visual_only") or name == "refugio"
        ]
        compiled = {
            "products": [
                {
                    "source": {
                        "id": SOURCES[name]["source_id"],
                        "pin": SOURCES[name]["pin"],
                    },
                    "tables": [],
                }
                for name in SOURCES
            ]
        }
        transcription = {
            "contract": "participation.reviewed_visual_pdf_transcriptions.v1",
            "sources": [
                {
                    "source_id": SOURCES[name]["source_id"],
                    "source_pin": SOURCES[name]["pin"],
                    "page_bbox": [0, 0, 1, 1],
                    "visual_header_review_evidence": "Reviewed complete pinned page",
                    "rows": [
                        {
                            "native_unit": "Attestation date",
                            "measure": "source_time",
                            "value": SOURCES[name]["clock_value"],
                            "literal": SOURCES[name]["clock_value"],
                        }
                    ],
                }
                for name in visual_names
            ],
        }
        append_visual_controls(compiled, transcription)
        self.assertEqual(
            sum(bool(product["tables"]) for product in compiled["products"]),
            len(visual_names),
        )
        transcription["sources"][0]["source_pin"] = {"bytes": 1, "sha256": "0" * 64}
        with self.assertRaises(ValueError):
            append_visual_controls(
                {
                    "products": [
                        {
                            "source": {
                                "id": SOURCES[name]["source_id"],
                                "pin": SOURCES[name]["pin"],
                            },
                            "tables": [],
                        }
                        for name in SOURCES
                    ]
                },
                transcription,
            )


if __name__ == "__main__":
    unittest.main()
