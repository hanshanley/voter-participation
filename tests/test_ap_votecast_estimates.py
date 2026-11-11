import csv
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import zipfile
from decimal import Decimal

from scripts import ap_votecast_estimates as ap


class VoteCastEstimatesTests(unittest.TestCase):
    def test_native_windows_quotes_and_partial_utf8_probe(self):
        self.assertEqual(ap.csv_encoding(b"DON\x92T KNOW"), "cp1252")
        self.assertEqual(ap.csv_encoding(b"header,\xe2\x80"), "utf-8-sig")

    def test_native_postal_label_not_numeric_state_code(self):
        self.assertEqual(ap.postal_state("(AK) Alaska"), "AK")
        self.assertEqual(ap.postal_state("(AL) Alabama"), "AL")
        with self.assertRaises(ValueError):
            ap.postal_state("02")

    def test_native_formatted_codes(self):
        self.assertEqual(ap.formatted_code("(1) Likely voter"), "1")
        self.assertEqual(ap.formatted_code("(88) REMOVED FOR DISCLOSURE RISK"), "88")
        self.assertEqual(ap.formatted_code(""), "MISSING")
        with self.assertRaises(ValueError):
            ap.formatted_code("1.0")

    def test_full_frame_includes_nonvoters(self):
        cell = ap.new_cell()
        ap.add(cell, Decimal("2.5"), "1", "5")
        ap.add(cell, Decimal("3.5"), "2", "4")
        self.assertEqual(cell["n"], 2)
        self.assertEqual(cell["weight"], 6)
        self.assertEqual(cell["modeled_nonvoter_weight"], Decimal("3.5"))
        self.assertEqual(cell["already_voted_self_report_weight"], Decimal("2.5"))
        self.assertEqual(cell["unlikely_intent_weight"], Decimal("3.5"))

    def test_zero_weight_remains_raw_accounted(self):
        cell = ap.new_cell()
        ap.add(cell, Decimal(0), "1", "1")
        self.assertEqual(cell["n"], 1)
        self.assertEqual(cell["positive_weight_n"], 0)
        self.assertEqual(cell["weight"], 0)

    def test_no_negative_weight_repair(self):
        with self.assertRaises(ValueError):
            ap.add(ap.new_cell(), Decimal("-1"), "1", "1")

    def test_state_inference_exclusions(self):
        self.assertIn("national_only", ap.state_inference("2022", "DE", "FINALVOTE_STATE_WEIGHT"))
        self.assertIn("national_only", ap.state_inference("2022", "WV", "FINALVOTE_STATE_WEIGHT"))
        self.assertIn("47_state", ap.state_inference("2018", "NC", "FINALVOTE_STATE_WEIGHT"))
        self.assertIn("national_registered", ap.state_inference("2022", "US50_SOURCE", "FINALVOTE_NATIONAL_WEIGHT"))

    def test_documented_but_unreleased_demographics_are_explicit(self):
        body = io.StringIO(newline="")
        writer = csv.writer(body)
        writer.writerow(["P_STATE", "LIKELYVOTER", "LVB", "AGE65", "FINALVOTE_NATIONAL_WEIGHT"])
        writer.writerow(["(AK) Alaska", "(1) Likely voter", "(5) Already voted", "(1) 18-24", "2"])
        writer.writerow(["(AL) Alabama", "(2) Nonvoter", "(4) Definitely not", "(6) 65+", "3"])
        raw = body.getvalue().encode()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "native.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("native.csv", raw)
            rows, result = ap.reduce_wave("2022", {
                "demographics": {"variables": ["AGE65", "RACETH5"]},
                "weights": {"fields": {"FINALVOTE_NATIONAL_WEIGHT": "national"}},
                "archive": {"path": str(path), "selected_members": {"csv": {
                    "name": "native.csv", "sha256": hashlib.sha256(raw).hexdigest()}}},
                "rows": 2,
            })
        self.assertEqual(result["documented_demographics_not_in_released_csv"], ["RACETH5"])
        self.assertEqual({row["dimension"] for row in rows}, {"overall", "AGE65"})
        self.assertEqual(next(row for row in rows if row["dimension"] == "overall")["weight"], 5)
        self.assertEqual({row["weight_field"] for row in rows}, {"FINALVOTE_NATIONAL_WEIGHT"})


if __name__ == "__main__":
    unittest.main()
