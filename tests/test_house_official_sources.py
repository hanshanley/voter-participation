import copy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import house_official_sources as official
from scripts.house_comparability import district_rows
from scripts.native_products import encoded, pin


class OfficialHouseSourcesTests(unittest.TestCase):
    def setUp(self):
        catalog = json.loads(official.CATALOG.read_bytes())
        rows = [dict(contest=contest, title=binding["title"], candidate_id=identity,
                     candidate=f"({party}) Candidate {identity}", total=0 if party == "G" else 10)
            for contest, binding in catalog["sources"][0]["districts"].items()
            for identity, party in zip(binding["candidate_ids"],
                ("D", "R", "G", "N") if contest == "30" else ("D", "R"))]
        self.body = encoded(dict(queries={
            "hi-summary-candidates": dict(rows=rows),
            "wy-state-house": dict(rows=[dict(county="Total", R=20, D=10, L=2, C=1)])}))
        catalog["query_pin"] = pin(self.body)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        path = Path(self.directory.name) / "review.json"
        path.write_bytes(encoded(catalog))
        self.override = patch.object(official, "CATALOG", path)
        self.override.start()
        self.addCleanup(self.override.stop)
        self.current = official.qualified(self.body)["candidates"]
        self.previous = [dict(district=row["district"], candidate=row["name"],
            counted_as="D" if row["party"] == "Democratic" else (
                "R" if row["party"] == "Republican" else "O"),
            votes=10, literal_affiliations=[row["party"]],
            source_lines=[dict(role="named_candidate")]) for row in self.current]

    def test_pinned_shared_file_has_explicit_district_selectors_and_no_fabricated_clock(self):
        rows = district_rows(self.previous, self.current, self.body)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["current"]["reported_counts"]["O"], 10)
        for row in rows:
            for candidate in row["current"]["source_candidate_rows"]:
                self.assertIsNone(candidate["source_updated_at"])
                self.assertTrue(candidate["native_contest_selector"])
        self.assertNotEqual(
            rows[0]["current"]["source_candidate_rows"][0]["native_contest_selector"],
            rows[1]["current"]["source_candidate_rows"][0]["native_contest_selector"])

    def test_altered_count_missing_candidate_and_retrieval_as_clock_are_rejected(self):
        for mutate in ("count", "missing", "clock"):
            rows = copy.deepcopy(self.current)
            if mutate == "count":
                rows[0]["votes"] = "999"
            elif mutate == "missing":
                rows.pop()
            else:
                rows[0]["source_updated_at"] = "2026-11-12T23:06:26Z"
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                district_rows(self.previous, rows, self.body)

    def test_official_url_without_pinned_review_or_arbitrary_gov_url_is_rejected(self):
        with self.assertRaises(ValueError):
            district_rows(self.previous, self.current)
        with self.assertRaises(ValueError):
            official.qualified(self.body + b"\n")
        rows = copy.deepcopy(self.current)
        rows[0]["source_url"] = "https://elections.hawaii.gov/unreviewed.txt"
        with self.assertRaises(ValueError):
            district_rows(self.previous, rows, self.body)


if __name__ == "__main__":
    unittest.main()
