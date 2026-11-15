import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from scripts.participation_intake.contract import pin
from scripts import louisiana_bootstrap
from scripts import results_granular
from scripts import results_native_louisiana as source
from scripts import results_native_louisiana_runtime as runtime


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures/louisiana-native"
BASELINE = FIXTURES / "source-baseline"
FILES = {
    source.ELECTION_DATES_URL: "election-dates.json",
    source.STATE_INDEX_URL: "state-source-declaration.json",
    source.PARISH_INDEX_URL: "parish-source-declaration.json",
    source.STATE_XLSX_URL: "2026_1103_sta.xlsx",
    source.PARISH_XLSX_URL: "2026_1103_par.xlsx",
}


def baseline_files():
    index = json.loads((BASELINE / "index.json").read_bytes())
    result = {
        "index.json": (BASELINE / "index.json").read_bytes(),
        "current.json.gz": (BASELINE / "current.json.gz").read_bytes(),
        "dataset.json": (BASELINE / "dataset.json").read_bytes(),
    }
    for declaration in index["states"].values():
        result[declaration["file"]] = (BASELINE / declaration["file"]).read_bytes()
    return result


def bodies():
    return {url: (FIXTURES / name).read_bytes() for url, name in FILES.items()}


class LouisianaOnboardingTests(unittest.TestCase):
    def temporary(self):
        return tempfile.TemporaryDirectory(dir=HERE)

    def test_authority_and_full_native_candidate(self):
        authority = json.loads((FIXTURES / "authority-resolution.json").read_bytes())
        self.assertEqual(
            authority["status"],
            "verified_exact_publisher_executed_production_mapping",
        )
        route = json.loads((FIXTURES / "route-authority.json").read_bytes())
        self.assertEqual(route, louisiana_bootstrap.EXPECTED_AUTHORITY)
        rows = runtime.canonical_rows(bodies())
        self.assertEqual(len(rows), 3783)
        self.assertEqual(
            [sum(row["geography"]["level"] == level for row in rows)
             for level in ("state", "county_equivalent", "precinct")],
            [1, 64, 3718],
        )
        self.assertTrue(
            all(
                row["reporting_status"]["reported_units"] is None
                and row["reporting_status"]["total_units"] is None
                and row["view"]["reported_units"] is None
                and row["view"]["total_units"] is None
                for row in rows
            )
        )
        self.assertEqual(sum(row["count"]["value"] == 0 for row in rows), 1)
        self.assertTrue(all(row["denominator"] is None for row in rows))
        self.assertTrue(all(row["source_clock"]["literal"] is None for row in rows))

    def test_reviewed_addition_preserves_full_registration_baseline(self):
        before = baseline_files()
        payload = louisiana_bootstrap.addition_payload(before, bodies())
        entry = {
            "status": "reported",
            "source": {
                "url": source.STATE_XLSX_URL,
                **pin(bodies()[source.STATE_XLSX_URL]),
            },
            "data": {"reviewed_count_addition": payload, "updates": []},
        }
        after, changes = results_granular.project(
            before, {louisiana_bootstrap.IDENTITY: entry}
        )
        self.assertEqual(len(changes), 3783)
        before_index = json.loads(before["index.json"])
        for code, declaration in before_index["states"].items():
            if code != "LA":
                self.assertEqual(
                    after[declaration["file"]], before[declaration["file"]]
                )
        old = json.loads(gzip.decompress(before["states/LA.json.gz"]))
        new = json.loads(gzip.decompress(after["states/LA.json.gz"]))
        self.assertEqual(new["records"][:258], old["records"])
        self.assertEqual(len(new["records"]), 4041)
        self.assertEqual(len(new["views"]["official"]["counties"]), 64)
        self.assertEqual(len(new["views"]["official"]["precincts"]), 3718)
        state, = [
            row for row in new["records"][258:]
            if row["geography"]["level"] == "state"
        ]
        selected = {
            identity
            for frame in new["views"].values()
            for partition in ("counties", "precincts", "nongeographic")
            for identity in frame[partition]
        }
        self.assertNotIn(state["id"], selected)


    def test_exact_authority_repeat_changed_missing_and_last_good(self):
        authority = copy.deepcopy(louisiana_bootstrap.EXPECTED_AUTHORITY)
        self.assertEqual(
            louisiana_bootstrap.authority_decision(authority)["status"], "verified"
        )
        for key in ("state_index_url", "publisher_script_url",
                    "authority_receipt_pin"):
            changed = copy.deepcopy(authority)
            if isinstance(changed[key], str):
                changed[key] += "?changed"
            else:
                changed[key]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "differs from review"):
                louisiana_bootstrap.authority_decision(changed)

        before = baseline_files()
        payload = louisiana_bootstrap.addition_payload(before, bodies())
        addition_entry = {
            "status": "reported",
            "source": {"url": source.STATE_XLSX_URL,
                       **pin(bodies()[source.STATE_XLSX_URL])},
            "data": {"reviewed_count_addition": payload, "updates": []},
        }
        added, changes = results_granular.project(
            before, {louisiana_bootstrap.IDENTITY: addition_entry})
        self.assertEqual(len(changes), 3783)
        repeated, repeat_changes = results_granular.project(
            added, {louisiana_bootstrap.IDENTITY: addition_entry})
        self.assertEqual(repeated, added)
        self.assertEqual(repeat_changes, [])

        templates = [
            row for row in runtime.extend_templates(
                added, results_granular.selected_records(added, "LA"))
            if row["source"]["id"] == runtime.SOURCE_ID
        ]

        def acquire(url):
            value = bodies()[url]
            return value, {"url": url, **pin(value)}

        data = runtime.statistics(
            bodies()[source.STATE_XLSX_URL], templates,
            source.STATE_XLSX_URL, acquire=acquire)
        entry = {
            "status": "reported",
            "source": {"url": source.STATE_XLSX_URL,
                       **pin(bodies()[source.STATE_XLSX_URL])},
            "data": data,
        }
        unchanged, unchanged_changes = results_granular.project(
            added, {"LA-native": entry})
        self.assertEqual(unchanged, added)
        self.assertEqual(unchanged_changes, [])

        revised = copy.deepcopy(entry)
        changed_update = revised["data"]["updates"][0]
        changed_update["value"] += 1
        changed_update["native"]["voters_participating"] += 1
        changed_update["native"]["query"]["voters_participating"] += 1
        changed_update["native"]["native_vectors"][
            "voters_participating"]["total"] += 1
        successor, successor_changes = results_granular.project(
            added, {"LA-native": revised})
        self.assertEqual(len(successor_changes), 1)
        self.assertNotEqual(successor, added)

        missing_bodies = bodies()
        del missing_bodies[source.PARISH_XLSX_URL]

        def acquire_missing(url):
            value = missing_bodies[url]
            return value, {"url": url, **pin(value)}

        with self.assertRaises(KeyError):
            runtime.statistics(
                missing_bodies[source.STATE_XLSX_URL], templates,
                source.STATE_XLSX_URL, acquire=acquire_missing)

        failed = copy.deepcopy(entry)
        failed["status"] = "retained_after_failure"
        failed["data"] = None
        last_good, failure_changes = results_granular.project(
            successor, {"LA-native": failed})
        self.assertEqual(last_good, successor)
        self.assertEqual(failure_changes, [])

    def test_safe_declarations_and_typed_source_pin(self):
        for name in ("state-source-declaration.json", "parish-source-declaration.json"):
            declaration = json.loads((FIXTURES / name).read_bytes())
            self.assertEqual(
                declaration["authority_status"],
                "verified_exact_publisher_executed_production_mapping",
            )
            self.assertNotIn("<html", (FIXTURES / name).read_text().lower())
        before = baseline_files()
        after = louisiana_bootstrap.apply_addition(
            before, louisiana_bootstrap.addition_payload(before, bodies())
        )
        templates = [
            row
            for row in runtime.extend_templates(
                after, results_granular.selected_records(after, "LA")
            )
            if row["source"]["id"] == runtime.SOURCE_ID
        ]

        def acquire(url):
            value = bodies()[url]
            return value, {"url": url, **pin(value)}

        data = runtime.statistics(
            bodies()[source.STATE_XLSX_URL],
            templates,
            source.STATE_XLSX_URL,
            acquire=acquire,
        )
        data["updates"][0]["native"].pop("source_original_pin")
        entry = {
            "status": "reported",
            "source": {
                "url": source.STATE_XLSX_URL,
                **pin(bodies()[source.STATE_XLSX_URL]),
            },
            "data": data,
        }
        with self.temporary(), self.assertRaisesRegex(
            ValueError, "per-update numerical input"
        ):
            results_granular.project(after, {"LA-native": entry})


if __name__ == "__main__":
    unittest.main()
