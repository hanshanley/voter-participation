import copy
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import unittest

from scripts.house_native_controls import qualify_pa


FIXTURES = Path(__file__).resolve().parents[1] / "data/pa-house-native-controls/20261112-01/inputs"


class NativeHouseControlTests(unittest.TestCase):
    def setUp(self):
        self.body = (FIXTURES / "native-district-candidates.csv.gz").read_bytes()
        self.audit = json.loads((FIXTURES / "native-district-audit.json").read_bytes())
        self.control = json.loads((FIXTURES / "held-pa-control.json").read_bytes())
        self.districts = json.loads((FIXTURES / "expected-house-districts.json").read_bytes())

    def rewrite(self, mutate):
        rows = list(csv.DictReader(io.StringIO(gzip.decompress(self.body).decode())))
        mutate(rows)
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        body = gzip.compress(stream.getvalue().encode(), mtime=0)
        audit = copy.deepcopy(self.audit)
        audit["files"]["district-candidate-totals.csv.gz"] = dict(
            rows=len(rows), bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
        return body, audit

    def test_complete_native_counts_are_not_blocked_by_county_only_join_rows(self):
        result = qualify_pa(self.body, self.audit, self.control, self.districts)
        self.assertEqual(result["current_reported_candidate_counts"], self.control["current"])
        self.assertEqual(result["county_validation_only_exceptions"],
            [dict(control_index=i, **r) for i, r in enumerate(self.control["full_candidate_control_rows"])
             if r["reported_district_votes"] == ""])
        self.assertTrue(all(r["reported_district_votes"] == ""
                            for r in result["county_validation_only_exceptions"]))
        self.assertFalse(result["candidate_aliases_joined"])
        self.assertFalse(result["county_votes_summed_into_state"])

    def test_missing_native_district_is_not_promoted_to_a_state_total(self):
        body, audit = self.rewrite(lambda rows: rows.__setitem__(
            slice(None), [r for r in rows if r["district"] != "PA-01"]))
        with self.assertRaisesRegex(ValueError, "missing native district"):
            qualify_pa(body, audit, self.control, self.districts)

    def test_missing_native_count_is_not_filled_by_a_county_row(self):
        body, audit = self.rewrite(lambda rows: next(
            r for r in rows if r["state_code"] == "PA").update(votes=""))
        with self.assertRaisesRegex(ValueError, "explicit nonnegative integer"):
            qualify_pa(body, audit, self.control, self.districts)
        control = copy.deepcopy(self.control)
        next(r for r in control["full_candidate_control_rows"]
             if r["reported_district_votes"] != "")["reported_district_votes"] = ""
        with self.assertRaises(ValueError):
            qualify_pa(self.body, self.audit, control, self.districts)

    def test_duplicate_native_candidate_cannot_be_double_counted(self):
        body, audit = self.rewrite(lambda rows: rows.append(copy.deepcopy(
            next(r for r in rows if r["state_code"] == "PA"))))
        with self.assertRaisesRegex(ValueError, "counted twice"):
            qualify_pa(body, audit, self.control, self.districts)

    def test_changed_native_votes_cannot_silently_replace_frozen_controls(self):
        def mutate(rows):
            row = next(r for r in rows if r["state_code"] == "PA")
            row["votes"] = str(int(row["votes"])+1)
        body, audit = self.rewrite(mutate)
        with self.assertRaisesRegex(ValueError, "without aliases"):
            qualify_pa(body, audit, self.control, self.districts)


if __name__ == "__main__":
    unittest.main()
