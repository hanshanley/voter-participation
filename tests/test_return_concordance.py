from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest

from scripts.return_concordance import bounds, build, encoded, export, pin


def recipe():
    return dict(
        collection="counties", identity=dict(id="fips", state="state", name="name"),
        periods=[dict(key=key, count="v", parties=dict(D="d", R="r"),
                      decimal_places=places, one_party="op")
                 for key, places in (("h24", 1), ("h26", 2))],
        reference_period="h26",
        reference_year=2026,
        reference_contest="U.S. House district contests aggregated within county",
        reporting_fields=["ev", "rem", "eevp"],
        reference=dict(id="geography", state="state_code", name="geography_name",
                       total="total_votes", D="democratic_votes",
                       R="republican_votes", O="other_votes"),
        geographic_holds=dict(AK="statewide hub", CT="planning-region copies"))


def source():
    return dict(count=1, state_fips_to_postal={"01": "AL", "02": "AK", "09": "CT"},
                counties={"01001": dict(fips="01001", state="AL", name="County",
                                       h24=dict(d=40, r=60, v=200, m=-20),
                                       h26=dict(d=60, r=40, v=100, m=20, i=0,
                                                ev=120, rem=20, sp24=-99))})


def reference():
    return [dict(year="2026", contest="U.S. House district contests aggregated within county",
                 geography="01001", state_code="AL", geography_name="County",
                 total_votes="100", democratic_votes="60", republican_votes="40",
                 other_votes="0")]


def candidates():
    return [dict(year="2026", office="U.S. House", state_code="AL", county_fips="01001",
                 district="AL-01", name=name, party=party, votes=votes)
            for name, party, votes in (("A", "Democratic", "60"), ("B", "Republican", "40"))]


class ReturnConcordanceTests(unittest.TestCase):
    def run_build(self, new=None, old=None, ref=None, native=None):
        return build(new or source(), old or source(), ref if ref is not None else reference(),
                     native if native is not None else candidates(), recipe())

    def query(self, **kwargs):
        files, summary = self.run_build(**kwargs)
        return json.loads(files["county-concordance.json"])[0], summary

    def test_rounding_bounds_are_not_recovered_candidate_counts(self):
        low, high = bounds(33.33, 2)
        self.assertTrue(low <= Fraction(100, 3) <= high)
        self.assertEqual(bounds(0, 2)[0], 0)
        self.assertEqual(bounds(100, 2)[1], 100)
        for value, precision in ((True, 2), (-1, 2), (101, 2), ("NaN", 2),
                                 (33.333, 2), (40, True)):
            with self.assertRaises(ValueError):
                bounds(value, precision)

    def test_full_denominator_and_no_endpoint_or_behavior_promotion(self):
        row, summary = self.query()
        self.assertEqual(row["comparison_status"], "arithmetic_compatible_not_independent_validation")
        self.assertFalse(row["independent_validation"])
        self.assertFalse(row["eligible_as_model_endpoint"])
        self.assertIsNone(row["measured_turnout"])
        self.assertEqual(row["native_current_periods"]["h26"]["rem"], 20)
        interval = row["source_descriptive_margin_change_interval_pp"]
        self.assertEqual(interval["lower"], "39.89")
        self.assertEqual(interval["upper"], "40.11")
        self.assertNotEqual(interval["lower"], "-99")
        self.assertEqual(summary["new_exact_candidate_counts_inferred"], 0)
        new = source()
        new["counties"]["01001"]["h26"].update(d=30, r=20, v=200)
        ref = reference()
        ref[0].update(total_votes="200", other_votes="100")
        native = candidates() + [dict(candidates()[0], name="C", party="Independent", votes="100")]
        row, _ = self.query(new=new, ref=ref, native=native)
        self.assertEqual(row["rounded_party_checks"]["D"]["reference_exact_percent_fraction"], "30")

    def test_reporting_updates_do_not_become_contest_count_updates(self):
        new = source()
        new["counties"]["01001"]["h26"].update(ev=150, rem=50)
        row, summary = self.query(new=new)
        self.assertFalse(row["selected_contest_total_changed"])
        self.assertEqual(row["selected_change_kind"], "reporting_fields_only")
        self.assertEqual(summary["changed_selected_records"], 1)
        self.assertEqual(summary["changed_selected_contest_totals"], 0)
        new["counties"]["01001"]["h26"]["v"] = 110
        row, _ = self.query(new=new)
        self.assertEqual(row["comparison_status"], "contest_total_difference")
        self.assertEqual(row["source_minus_reference_contest_votes"], 10)
        new["counties"]["01001"]["h26"].update(v=100, d=59.99)
        row, _ = self.query(new=new)
        self.assertEqual(row["selected_change_kind"], "same_total_nonreporting_fields_changed")

    def test_missing_and_zero_are_distinct_and_reference_only_units_survive(self):
        new = source()
        del new["counties"]["01001"]["h26"]
        row, _ = self.query(new=new)
        self.assertEqual(row["comparison_status"], "secondary_result_missing")
        self.assertIsNone(row["source_minus_reference_contest_votes"])
        new["counties"]["01001"]["h26"] = dict(d=0, r=0, v=0)
        row, _ = self.query(new=new)
        self.assertEqual(row["comparison_status"], "secondary_zero_contest_total")
        new["counties"].clear()
        new["count"] = 0
        row, summary = self.query(new=new, old=new)
        self.assertEqual(summary["complete_union_queries"], 1)
        self.assertIsNotNone(row["reference_native_row"])
        self.assertIsNone(row["native_current_periods"]["h26"])
        ref = reference()
        ref[0].update(total_votes="0", democratic_votes="0", republican_votes="0")
        row, _ = self.query(ref=ref, native=[dict(r, votes="0") for r in candidates()])
        self.assertEqual(row["comparison_status"], "reference_zero_contest_total")

    def test_geographic_and_one_party_holds_are_not_lifted(self):
        new = source()
        new["counties"]["01001"]["h24"]["op"] = 1
        row, _ = self.query(new=new)
        self.assertIsNone(row["source_descriptive_margin_change_interval_pp"])
        self.assertIn("one_major_party_or_zero_reported_share_h24",
                      row["source_descriptive_margin_change_holds"])
        new["counties"]["02020"] = new["counties"].pop("01001")
        new["counties"]["02020"].update(fips="02020", state="AK")
        ref = [dict(reference()[0], geography="02020", state_code="AK")]
        native = [dict(r, county_fips="02020", state_code="AK", district="AK-AL")
                  for r in candidates()]
        row, _ = self.query(new=new, old=new, ref=ref, native=native)
        self.assertEqual(row["comparison_status"], "geography_held")
        self.assertEqual(row["rounded_party_checks"], {})
        self.assertIsNone(row["source_descriptive_margin_change_interval_pp"])

    def test_changed_share_and_invalid_reference_fail_without_repair(self):
        new = source()
        new["counties"]["01001"]["h26"]["d"] = 59.99
        row, _ = self.query(new=new)
        self.assertEqual(row["comparison_status"], "rounded_party_share_difference")
        native = candidates()
        native[0]["votes"] = "61"
        with self.assertRaisesRegex(ValueError, "complete native candidate"):
            self.run_build(native=native)
        with self.assertRaisesRegex(ValueError, "Repeated reference"):
            self.run_build(ref=reference() * 2)
        with self.assertRaisesRegex(ValueError, "Repeated native"):
            self.run_build(native=candidates() * 2)
        with self.assertRaisesRegex(ValueError, "year or contest"):
            self.run_build(ref=[dict(reference()[0], year="2024")])
        with self.assertRaisesRegex(ValueError, "year or contest"):
            self.run_build(ref=[dict(reference()[0], contest="U.S. Senate")])
        new["counties"]["01001"]["state"] = "AK"
        with self.assertRaisesRegex(ValueError, "native state"):
            self.run_build(new=new)

    def test_offline_export_rejects_modified_complete_input_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "inputs").mkdir()
            (root / "inputs/facts.json").write_bytes(b"bad")
            manifest = dict(inputs={"inputs/facts.json": pin(b"old")})
            (root / "source-manifest.json").write_bytes(encoded(manifest))
            with self.assertRaisesRegex(ValueError, "Changed complete-package input"):
                export(root, root / "output")
            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main()
