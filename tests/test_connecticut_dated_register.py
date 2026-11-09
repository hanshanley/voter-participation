import copy
import gzip
import json
from pathlib import Path
import re
import unittest
import zipfile

from scripts.connecticut_dated_register import active_frame, results_hold


class ConnecticutDatedRegisterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/connecticut-dated-register/20261108-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/connecticut-complete-native-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.first, cls.second = (json.loads(archive.read(name)) for name in ("pymupdf-pages.json", "pypdf-pages.json"))
            cls.lookup = json.loads(gzip.decompress(archive.read("results/Lookupdata.json.gz")))
            cls.headers, cls.turnouts = [], []
            for version in ("52337", "52338"):
                cls.headers.append(json.loads(gzip.decompress(archive.read("results/" + version + "/election_Electiondata.json.gz"))))
                cls.turnouts.append(json.loads(gzip.decompress(archive.read("results/" + version + "/voterTurnout_Electiondata.json.gz"))))

    def frame(self, first=None, second=None):
        return active_frame(self.first if first is None else first,
                            self.second if second is None else second, self.lookup["townIds"])

    def transformed(self, transform):
        return ([transform(page) for page in self.first], [transform(page) for page in self.second])

    def test_selects_dated_native_active_not_inactive_or_combined(self):
        parent, rows, legend, discrepancies = self.frame()
        self.assertEqual((parent["totals_active"], parent["totals_inactive"], parent["totals_total"]),
                         (2255397, 234553, 2489950))
        self.assertEqual((len(rows), len(legend), discrepancies), (170, 11, []))
        self.assertIn(dict(party_name_literal="Independance", party_key_literal="INDA"), legend)

    def test_missing_native_parent_cannot_use_town_or_party_marginals(self):
        first, second = self.transformed(lambda page: re.sub(r"(?m)^\s*Totals\s+\d[^\n]*", "", page))
        with self.assertRaisesRegex(ValueError, "native Totals parent"):
            self.frame(first, second)

    def test_duplicate_native_parent_is_not_added(self):
        first, second = copy.deepcopy(self.first), copy.deepcopy(self.second)
        for pages in (first, second):
            line = next(line for line in pages[-1].splitlines() if re.match(r"^\s*Totals\s+\d", line))
            pages[-1] += "\n" + line + "\n"
        with self.assertRaisesRegex(ValueError, "duplicate native Totals parent"):
            self.frame(first, second)

    def test_missing_town_is_not_treated_as_zero(self):
        first, second = self.transformed(lambda page: re.sub(r"(?m)^\s*Andover\s+[^\n]*", "", page))
        with self.assertRaisesRegex(ValueError, "169-town coverage"):
            self.frame(first, second)

    def test_changed_date_requires_new_review(self):
        first, second = self.transformed(lambda page: page.replace("October 19, 2026", "November 3, 2026"))
        with self.assertRaisesRegex(ValueError, "native date"):
            self.frame(first, second)

    def test_independent_extraction_disagreement_is_not_repaired(self):
        first = copy.deepcopy(self.first)
        first[0] = first[0].replace("2,179", "2,178", 1)
        with self.assertRaisesRegex(ValueError, "extractions disagree"):
            self.frame(first, self.second)

    def test_truncated_count_row_cannot_substitute_other_status(self):
        transform = lambda page: re.sub(r"(?m)^(\s*Totals\s+)\d[\d,]*\s+", r"\1", page)
        first, second = self.transformed(transform)
        with self.assertRaisesRegex(ValueError, "15-column"):
            self.frame(first, second)

    def test_column_reordering_is_not_silently_reinterpreted(self):
        first, second = self.transformed(lambda page: page.replace("Republican Party", "Unreviewed Party"))
        with self.assertRaisesRegex(ValueError, "column order"):
            self.frame(first, second)

    def test_comma_separated_district_is_not_registration_count(self):
        transform = lambda page: re.sub(r"(?m)^(\s*Andover\s+Tolland\s+)2(\s+)", r"\g<1>1,2\2", page)
        first, second = self.transformed(transform)
        parent, rows, _, _ = self.frame(first, second)
        andover = next(row for row in rows if row["town_literal"] == "Andover")
        self.assertEqual((andover["congressional_district_literal"], andover["republican_active"]), ("1,2", 697))
        self.assertEqual(parent["totals_active"], 2255397)

    def test_partial_results_remain_held_not_repaired_by_snapshot(self):
        hold = results_hold(self.lookup, self.headers, self.turnouts)
        self.assertEqual((len(hold["zero_reported_registration_towns"]), len(hold["zero_reported_voted_towns"])), (13, 14))
        self.assertEqual(hold["native_results_header"]["RV"], "2,102,250")
        self.assertFalse(hold["native_zero_is_zero_population"])
        self.assertFalse(hold["native_statewide_ballot_reference_qualified"])
        self.assertTrue(hold["registration_snapshot_not_substituted"])

    def test_changed_results_version_requires_review_not_silent_merge(self):
        headers = copy.deepcopy(self.headers)
        headers[1]["RV"] = "2,255,397"
        with self.assertRaisesRegex(ValueError, "held results versions"):
            results_hold(self.lookup, headers, self.turnouts)


if __name__ == "__main__":
    unittest.main()
