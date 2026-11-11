import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.house_panel import HISTORICAL, build, district, export, integer


def historical(**changes):
    return dict(dict(year="2024", office="house", state_po="AL", county_fips="01001",
                     district="01", stage="general", candidate="A", party="Democratic",
                     party_group="DEM", votes="60"), **changes)


def current(**changes):
    return dict(dict(year="2026", office="U.S. House", state_code="AL", county_fips="01001",
                     district="AL-01", name="A", party="Democratic", votes="30"), **changes)


def review(**changes):
    return dict(dict(year="2024", office="house", state_code="AL", county_fips="01001",
                     accepted_for_scoped_export="True", withheld_reasons=""), **changes)


def parse(content):
    return list(csv.DictReader(io.StringIO(content.decode())))


class HousePanelTests(unittest.TestCase):
    def run_build(self, old=None, new=None, reviews=None, no_ballot=None, controls=None):
        old = old if old is not None else [
            historical(), historical(candidate="B", party="Republican", party_group="REP", votes="40")]
        new = new if new is not None else [
            current(), current(name="B", party="Republican", votes="50")]
        return build(old, new, reviews if reviews is not None else [review()],
                     no_ballot or [], controls if controls is not None else new, {"AL": "01"})

    def test_exact_counts_and_full_denominators(self):
        files, summary = self.run_build(
            old=[historical(), historical(candidate="B", party="Republican", party_group="REP", votes="40"),
                 historical(candidate="C", party="Independent", party_group="OTHER", votes="100")])
        row = parse(files["county-panel.csv"])[0]
        self.assertEqual(row["2024_contest_votes"], "200")
        self.assertEqual(row["contest_vote_count_change"], "-120")
        self.assertEqual(row["2024_d_minus_r_margin_pct"], "10")
        self.assertEqual(row["2026_d_minus_r_margin_pct"], "-25")
        self.assertEqual(row["unadjusted_literal_d_minus_r_margin_change_pp"], "-35")
        self.assertEqual(summary["known_screen_passes"], 1)
        self.assertEqual(row["measured_turnout_change"], "")
        self.assertEqual(row["district_boundaries_matched"], "")

    def test_missing_is_null_but_reported_zero_is_zero(self):
        files, _ = self.run_build(new=[current(votes="0")])
        row = parse(files["county-panel.csv"])[0]
        self.assertEqual(row["2026_contest_votes"], "0")
        self.assertEqual(row["contest_vote_count_change"], "")
        files, _ = self.run_build(new=[])
        row = parse(files["county-panel.csv"])[0]
        self.assertEqual(row["2026_contest_votes"], "")
        self.assertIn("missing_2026", row["screen_reasons"])

    def test_withheld_historical_rows_not_summed_or_lost(self):
        files, summary = self.run_build(
            old=[historical(votes="*")],
            reviews=[review(accepted_for_scoped_export="False", withheld_reasons="suppression")])
        self.assertEqual(summary["historical_withheld_candidate_rows"], 1)
        self.assertEqual(parse(files["county-panel.csv"])[0]["2024_contest_votes"], "")
        row = parse(files["historical-source-dispositions.csv"])[0]
        self.assertEqual(row["votes"], "*")
        self.assertEqual(row["selection_reason"], "suppression")

    def test_party_group_not_silently_substituted(self):
        files, _ = self.run_build(old=[
            historical(party="Libertarian", party_group="DEM"),
            historical(candidate="B", party="Republican", party_group="REP", votes="40")])
        row = parse(files["county-panel.csv"])[0]
        self.assertEqual(row["2024_d_literal_votes"], "0")
        self.assertEqual(row["2024_other_literal_votes"], "60")
        self.assertIn("historical_party_group_differs", row["screen_reasons"])
        self.assertEqual(row["passes_known_descriptive_screens"], "False")

    def test_fusion_no_ballot_and_partial_uncontested_counties_screened(self):
        files, _ = self.run_build(old=[
            historical(), historical(candidate="B", party="Republican/Conservative",
                                     party_group="REP", votes="40")],
            no_ballot=[dict(year="2024", office="house", state_po="AL", county_fips="01001")])
        row = parse(files["county-panel.csv"])[0]
        self.assertIn("fusion_or_composite", row["screen_reasons"])
        self.assertIn("unopposed_not_on_ballot", row["screen_reasons"])
        self.assertIn("one_major_party", row["screen_reasons"])

    def test_district_labels_do_not_claim_matched_boundaries(self):
        self.assertEqual(district("DE", "00"), "AL")
        self.assertEqual(district("AL", "AL-1"), "01")
        self.assertEqual(district("AL", "00"), "")
        files, _ = self.run_build()
        rows = parse(files["county-district-panel.csv"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["same_label_is_not_matched_boundaries"], "True")

    def test_controls_preserve_unlocated_and_different_scopes(self):
        files, _ = self.run_build(controls=[
            current(votes="32"), current(name="Unlocated", party="Independent", votes="4")])
        statuses = {r["candidate"]: r for r in parse(files["current-candidate-controls.csv"])}
        self.assertEqual(statuses["A"]["located_minus_reported"], "-2")
        self.assertEqual(statuses["Unlocated"]["located_county_votes"], "")
        self.assertEqual(statuses["Unlocated"]["status"], "no_located_county_rows")
        self.assertEqual(statuses["B"]["reported_district_votes"], "")
        row = parse(files["county-panel.csv"])[0]
        self.assertIn("current_district_control", row["screen_reasons"])
        self.assertEqual(row["passes_known_descriptive_screens"], "False")

    def test_invalid_integer_and_duplicate_control_fail(self):
        for value in ("*", "-1", "1.5", "1,000"):
            with self.assertRaises(ValueError):
                integer(value)
        with self.assertRaises(ValueError):
            self.run_build(controls=[current(), current()])
        with self.assertRaises(ValueError):
            self.run_build(new=[current(county_fips="02013")])

    def test_offline_reproduction_rejects_changed_pinned_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "inputs").mkdir()
            (root / "inputs/historical.csv.gz").write_bytes(b"bad")
            receipt = dict(path=HISTORICAL + "/source-candidate-party-lines.csv.gz",
                           bytes=3, sha256=hashlib.sha256(b"old").hexdigest())
            (root / "source-manifest.json").write_text(json.dumps(dict(
                website_repository="hanshanley/margin_of_error", source_commit="a" * 40,
                inputs={"historical": receipt})))
            with self.assertRaisesRegex(ValueError, "Changed complete-package"):
                export(None, root / "output", root)
            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main()
