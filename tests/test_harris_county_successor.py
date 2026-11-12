import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from harris_county_successor import qualify, SOURCE_SHA


class HarrisTests(unittest.TestCase):
    def fixture(self):
        counts = [
            ("denominator", "registered_voters", 2761770),
            ("voters", "in_person", 1344609), ("voters", "by_mail", 48886), ("voters", "total", 1393495),
            ("rejected_or_pending", "provisional", 3605), ("rejected_or_pending", "mail", 1695),
            ("rejected_or_pending", "total", 5300),
            ("counted_ballots", "in_person", 1345094), ("counted_ballots", "mail", 47186),
            ("counted_ballots", "total", 1392280), ("reconciliation", "difference", -4085),
            ("could_be_added", "mail", 9752), ("could_be_added", "provisional", 3605)]
        return dict(source=dict(sha256=SOURCE_SHA, bytes=29813,
            status_native="Preliminary Election Reconciliation - Unofficial Totals",
            report_date_native="11/4/2026", report_time_native=None, timezone_native=None),
            election=dict(date="2026-11-03"), jurisdiction=dict(state="TX", county="Harris"),
            measures=[dict(category=c, mode=m, count=n) for c, m, n in counts],
            counted_ballots=dict(count=1392280, native_label="I. Total ballots counted (G+H)"),
            primary_participation_observation=dict(count=1393495), denominator=dict(count=2761770))

    def test_counted_not_roster_and_negative_gap_retained(self):
        result = qualify(self.fixture())
        self.assertEqual(result["counted"], 1392280)
        self.assertEqual(result["roster"], 1393495)
        self.assertEqual(result["signed_native_difference"], -4085)
        self.assertFalse(result["denominator_qualified"])
        self.assertIsNone(result["timezone"])

    def test_changed_source_scope_missing_row_and_roster_substitution_fail(self):
        for key in ("county", "source", "missing", "roster", "negative", "duplicate"):
            source = self.fixture()
            if key == "county":
                source["jurisdiction"]["county"] = "Harrisburg"
            elif key == "source":
                source["source"]["sha256"] = "0"*64
            elif key == "missing":
                source["measures"].pop()
            elif key == "roster":
                source["counted_ballots"]["count"] = 1393495
            elif key == "negative":
                source["measures"][7]["count"] = -1
            else:
                source["measures"][-1] = copy.deepcopy(source["measures"][0])
            with self.subTest(key=key), self.assertRaises(ValueError):
                qualify(source)


if __name__ == "__main__":
    unittest.main()
