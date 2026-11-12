import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.precinct_source_batch import (collect, collect_products, discover_links, fetch_index,
    is_general_precinct_product, ledger_holds, registry, STATE_CODES)
from scripts.participation_intake.contract import digest, encoded, pin
from scripts.participation_intake.engine import Store


def directory_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["State", "Precinct Boundaries / Maps", "Precinct-Level Election Results"])
    writer.writeheader()
    writer.writerows(rows)
    return b"\xef\xbb\xbf"+stream.getvalue().encode()


def row(state, results="https://example.gov/results/", boundaries="Not available from state"):
    return {"State":state, "Precinct Boundaries / Maps":boundaries, "Precinct-Level Election Results":results}


class DirectoryBatchTests(unittest.TestCase):
    def test_multiline_export_and_wrong_product_do_not_become_result_data(self):
        body = directory_bytes([row("Virginia", "https://www.elections.virginia.gov/casting-a-ballot/redistricting/gis/\n")])
        record = registry(body, False)[0]
        result = record["products"]["results"]
        self.assertEqual(result["url"], "https://www.elections.virginia.gov/casting-a-ballot/redistricting/gis/")
        self.assertEqual(result["status"], "wrong_product_link_requires_review")
        self.assertFalse(result["numerical_counts_available"])

    def test_missing_directory_entry_and_manual_request_are_not_unavailable_observations(self):
        record = registry(directory_bytes([row("Missouri", "Not available from state",
            "County maps can be requested for a small fee")]), False)[0]
        self.assertEqual(record["products"]["results"]["status"], "not_listed_in_directory")
        self.assertEqual(record["products"]["boundaries"]["status"], "manual_request_not_followed")
        self.assertIsNone(record["products"]["boundaries"]["url"])

    def test_duplicates_incomplete_inventory_and_duplicate_headers_rejected(self):
        with self.assertRaises(ValueError):
            registry(directory_bytes([row("Alabama"), row("Alabama")]), False)
        with self.assertRaises(ValueError):
            registry(directory_bytes([row("Alabama")]))
        with self.assertRaises(ValueError):
            registry(b"State,Precinct Boundaries / Maps,Precinct-Level Election Results,State\n")

    def test_discovery_keeps_general_year_and_explicitly_unqualified_downloads(self):
        body = b'<a href="/2026/general-results.csv">2026 General</a><a href="/2026/primary.csv">Primary 2026</a><a href="/2024/general.csv">2024</a>'
        links = discover_links(body, "https://example.gov/results/", 2026)
        self.assertEqual([link["url"] for link in links], ["https://example.gov/2026/general-results.csv"])
        self.assertFalse(links[0]["election_scope_verified"])
        self.assertFalse(links[0]["numerical_data_qualified"])

    def test_cached_original_and_stopped_route_never_make_network_requests(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(Path(temporary)/"cache")
            body = b"public source index"
            store.object(body)
            url = "https://example.gov/results/"
            store.db.execute("INSERT INTO inputs VALUES(?,?,?,?,?)", (url,digest(body),None,None,None))
            store.db.commit()
            with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network not allowed")):
                cached = fetch_index(store,url,set())
                stopped = fetch_index(store,url,{url})
            self.assertEqual(cached["status"],"cached_original")
            self.assertEqual(cached["source_requests"],0)
            self.assertEqual(stopped["status"],"ledger_access_hold_not_followed")
            store.object(body).write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                fetch_index(store,url,set())
            store.db.close()

    def test_ledger_stops_do_not_authorize_an_alternate_product(self):
        text = "Native https://example.gov/denied.csv returned HTTP 403; route stopped."
        holds = ledger_holds(text)
        self.assertIn("https://example.gov/denied.csv",holds)
        self.assertNotIn("https://example.gov/different.csv",holds)

    def test_denied_table_row_does_not_block_independent_held_sources(self):
        text=("| Source | Status |\n|---|---|\n"
            "| [Denied](https://example.gov/denied.csv) | HTTP 403; route stopped |\n"
            "| [Held](https://other.gov/results/) | Acquired; historical results held |\n")
        self.assertEqual(ledger_holds(text),{"https://example.gov/denied.csv"})

    def test_complete_directory_run_is_idempotent_and_fetch_mode_is_not_a_false_noop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/"directory.csv"
            source.write_bytes(directory_bytes([row(state) for state in STATE_CODES]))
            output = root/"output"
            first = collect(source,root/"cache",output,2026)
            self.assertEqual(first["jurisdictions"],51)
            self.assertEqual(first["new_qualified_ballot_observations"],0)
            second = collect(source,root/"cache",output,2026)
            self.assertEqual(second["status"],"unchanged")
            self.assertEqual(second["source_requests"],0)
            with self.assertRaises(ValueError):
                collect(source,root/"cache",output,2026,fetch=True)
            self.assertEqual(json.loads((output/"complete-jurisdiction-query.json").read_bytes())[0]["state_code"],"AK")

    def test_historical_and_midterm_years_share_the_same_source_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/"directory.csv"
            source.write_bytes(directory_bytes([row(state) for state in STATE_CODES]))
            result = collect(source,root/"cache",root/"output",[2016,2018,2020,2022,2024])
            self.assertEqual(result["election_years"],[2024,2022,2020,2018,2016])
            self.assertEqual(result["jurisdictions"],51)
            self.assertEqual(result["source_requests"],0)

    def test_product_filter_uses_election_filename_not_upload_directory_year(self):
        links = discover_links(b"""
            <a href="/2018/2017-Special-General-PrecinctLevel.zip">2017</a>
            <a href="/2019/2018-Official-General-Precinct-Results.zip">General</a>
            <a href="/2018/2018-General-Totals-by-Age.xlsx">General</a>
            <a href="/2018/2018-Primary-Precinct.zip">Primary</a>
        ""","https://example.gov/",2018)
        selected = [link for link in links if is_general_precinct_product(link,2018)]
        self.assertEqual(len(selected),1)
        self.assertIn("2018-Official-General-Precinct-Results",selected[0]["url"])

    def test_real_product_bytes_cached_noop_and_declaration_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root/"indexes";collection.mkdir()
            url = "https://example.gov/2018-General-Precinct-Results.zip"
            body = io.BytesIO()
            with zipfile.ZipFile(body,"w") as archive:
                archive.writestr("source.csv","county,precinct,votes\nA,1,7\n")
            store = Store(root/"cache")
            store.object(body.getvalue())
            store.db.execute("INSERT INTO inputs VALUES(?,?,?,?,?)",(url,digest(body.getvalue()),None,None,None))
            store.db.commit();store.db.close()
            query = encoded([dict(state_code="AL",products=dict(results=dict(
                url="https://example.gov/results/", acquisition=dict(sha256="a"*64),
                linked_candidates_by_year={"2018":[dict(url=url,text="General",role="download_candidate")]})))])
            (collection/"complete-jurisdiction-query.json").write_bytes(query)
            (collection/"manifest.json").write_bytes(encoded(dict(files={"complete-jurisdiction-query.json":pin(query)})))
            with patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("no reacquisition")):
                first = collect_products(collection,root/"cache",root/"products",[2018],["AL"])
                self.assertEqual(first["acquired_products"],1)
                self.assertEqual(first["source_requests"],0)
                second = collect_products(collection,root/"cache",root/"products",[2018],["AL"])
                self.assertEqual(second["status"],"unchanged")
                (collection/"complete-jurisdiction-query.json").write_bytes(b"[]")
                with self.assertRaises(ValueError):
                    collect_products(collection,root/"cache",root/"products-new",[2018],["AL"])


if __name__ == "__main__":
    unittest.main()
