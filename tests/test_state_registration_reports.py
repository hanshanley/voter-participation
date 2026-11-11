import copy
import json
from pathlib import Path
import re
import unittest
import zipfile

from scripts.state_registration_reports import REPORTS, registration_frame


class StateRegistrationReportsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/state-registration-reports/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-native-registration-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.sources = {state: [json.loads(archive.read(state + "/" + name))
                                  for name in ("pymupdf-pages.json", "pypdf-pages.json")] for state in REPORTS}

    def frame(self, state, sources=None):
        return registration_frame(state, *(self.sources[state] if sources is None else sources))

    def transformed(self, state, transform):
        return [[transform(page) for page in pages] for pages in self.sources[state]]

    def test_selects_two_explicit_native_parents_not_party_components(self):
        for state, total, length in (("OK", 2455735, 78), ("PA", 9052695, 68)):
            with self.subTest(state=state):
                parent, rows, discrepancies = self.frame(state)
                self.assertEqual((parent["counts"][-1], len(rows), discrepancies), (total, length, []))

    def test_missing_native_parent_cannot_use_county_or_party_fallback(self):
        for state in REPORTS:
            letters = "".join(REPORTS[state]["parent"].split())
            pattern = "[ \t]*".join(letters)
            sources = self.transformed(state, lambda page: re.sub(r"(?m)^[ \t]*" + pattern + r"[ \t]+\d[^\n]*", "", page))
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "native state parent"):
                self.frame(state, sources)

    def test_duplicate_parent_is_not_added(self):
        for state in REPORTS:
            sources = copy.deepcopy(self.sources[state])
            parent_key = "".join(REPORTS[state]["parent"].split())
            for pages in sources:
                line = next(line for page in pages for line in page.splitlines()
                            if "".join(re.split(r"\d", line, maxsplit=1)[0].split()) == parent_key)
                pages[-1] += "\n" + line + "\n"
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "duplicate native state parent"):
                self.frame(state, sources)

    def test_missing_county_is_not_treated_as_zero(self):
        sources = self.transformed("OK", lambda page: re.sub(r"(?m)^[ \t]*01[ \t]+[^\n]*", "", page))
        with self.assertRaisesRegex(ValueError, "county coverage"):
            self.frame("OK", sources)

    def test_duplicate_native_county_code_is_not_a_name_based_repair(self):
        sources = self.transformed("OK", lambda page: re.sub(r"(?m)^([ \t]*)01([ \t]+)", r"\g<1>02\2", page))
        with self.assertRaisesRegex(ValueError, "county code inventory"):
            self.frame("OK", sources)

    def test_changed_printed_clock_requires_review(self):
        sources = self.transformed("OK", lambda page: page.replace("3:05 AM", "3:06 AM"))
        with self.assertRaisesRegex(ValueError, "report clock"):
            self.frame("OK", sources)

    def test_changed_election_label_is_not_ignored_as_a_registry_date(self):
        sources = self.transformed("PA", lambda page: page.replace("November 3, 2026", "November 3, 2024"))
        with self.assertRaisesRegex(ValueError, "election label"):
            self.frame("PA", sources)

    def test_independent_numeric_disagreement_is_not_repaired(self):
        sources = copy.deepcopy(self.sources["OK"])
        sources[0][0] = sources[0][0].replace("6,888", "6,887", 1)
        with self.assertRaisesRegex(ValueError, "extractions disagree"):
            self.frame("OK", sources)

    def test_changed_column_order_is_not_reinterpreted(self):
        sources = self.transformed("PA", lambda page: page.replace("Democratic", "Unreviewed"))
        with self.assertRaisesRegex(ValueError, "column order"):
            self.frame("PA", sources)

    def test_source_discrepancies_are_reported_without_repairing_parent(self):
        sources = self.transformed("OK", lambda page: page.replace("6,888", "6,887", 1))
        parent, _, discrepancies = self.frame("OK", sources)
        self.assertEqual(parent["counts"][-1], 2455735)
        self.assertEqual(len(discrepancies), 2)


if __name__ == "__main__":
    unittest.main()
