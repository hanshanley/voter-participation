import unittest

from scripts.native_products import pin, query, unpack


class NativeCountFormatTests(unittest.TestCase):
    def setUp(self):
        self.body = b"unit,ballots,reporting\nA,10,0\nB,0,1\n"
        self.spec = dict(id="test", path="native.csv", kind="delimited",
            pin=pin(self.body), reader={}, expected_rows=2,
            url="https://example.test/public-aggregate.csv", state_code="WA",
            election_year=2026, retrieved_at_utc=None, native_updated_at=None,
            redistribution="factual_tables")
        self.selection = dict(id="units", product="test",
            fields=dict(unit="unit", ballots="ballots", reporting="reporting"),
            counts=["ballots"], keys=["unit"], deduplicate=False)

    def test_explicit_grouped_counts_preserve_native_text_and_true_zero(self):
        body = b'unit,ballots,reporting\nA,"935,956",0\nB,0,1\n'
        product = unpack(dict(self.spec, pin=pin(body)), body)
        with self.assertRaises(ValueError):
            query(product, self.selection)
        selection = dict(self.selection, count_formats=dict(ballots="comma_grouped_integer"))
        result = query(product, selection)
        self.assertEqual([row["ballots"] for row in result["rows"]], [935956, 0])
        self.assertEqual(product["tables"][0]["rows"][0]["values"][1], "935,956")
        self.assertEqual(result["rows"][0]["source_rows"][0]["row"], 2)

    def test_grouped_format_rejects_malformed_values_and_noncount_fields(self):
        for value in ("1,20", "12,34,567", "1.234", "-1", "", " 1,234", "1,234 "):
            with self.subTest(value=value):
                body = ('unit,ballots,reporting\nA,"'+value+'",0\n').encode()
                product = unpack(dict(self.spec, pin=pin(body), expected_rows=1), body)
                selection = dict(self.selection, count_formats=dict(ballots="comma_grouped_integer"))
                with self.assertRaisesRegex(ValueError, "malformed grouped count"):
                    query(product, selection)
        product = unpack(self.spec, self.body)
        for declaration in (dict(unit="comma_grouped_integer"), dict(ballots="decimal"), []):
            with self.subTest(declaration=declaration), self.assertRaisesRegex(ValueError, "supported format"):
                query(product, dict(self.selection, count_formats=declaration))
