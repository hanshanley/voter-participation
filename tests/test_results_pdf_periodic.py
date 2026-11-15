import copy
from datetime import datetime, timezone
import gzip
import inspect
import json
from pathlib import Path
import re

import pytest

from scripts import results_granular as granular
from scripts import results_intake as intake
from scripts import results_native as native
from scripts import results_pdf_ocr as shared_ocr
from scripts import results_pdf_periodic as periodic
from scripts import results_pdf_periodic_ocr as periodic_ocr
from scripts.participation_intake.contract import encoded, observation_id, pin, validate


FIXTURES = Path(__file__).parent / "fixtures" / "results_pdf_periodic"


def load(name):
    return json.loads(gzip.decompress((FIXTURES / name).read_bytes()))


@pytest.fixture(scope="module")
def products():
    fixture = load("complete-products.json.gz")
    assert fixture["contract"] == "participation.public_nj_periodic_fixture.v1"
    return fixture


@pytest.fixture(scope="module")
def ocr_views():
    return load("sussex-ocr-views.json.gz")


def record(state, name, url, measure, *, native=None, count=7, clock="11/03/26 1:00 PM"):
    source_id = "public-fixture-" + intake.digest(url.encode())[:16]
    geography_id = state + "|fixture|" + name
    row = {
        "contract": "participation.observation.v1",
        "id": observation_id(
            source_id, "general-2026", geography_id, measure["id"], measure["mode"]),
        "election": {"id": "general-2026", "year": 2026, "date": "2026-11-03",
                     "type": "general", "qualification": "native"},
        "geography": {"id": geography_id, "name": name, "state_code": state,
                      "level": "county", "parent_id": None,
                      "join": {"status": "unreviewed", "reference_id": None,
                               "feature_key": None, "evidence": None}},
        "measure": copy.deepcopy(measure),
        "count": {"value": count, "literal": count, "status": "reported"},
        "denominator": None,
        "source_clock": {"literal": clock, "timezone": None},
        "reporting_status": {"literal": "UNOFFICIAL", "reported_units": None,
                             "total_units": None, "complete": None},
        "source": {"id": source_id, "url": url, "input_sha256": "a" * 64,
                   "selector": {}, "classification": "public_aggregate", "fields": {}},
        "quality": {"conflicts": [], "notes": []},
        "view": {"native_record": native or {}, "source_url": url, "ballots": count,
                 "denominator": None, "reported_pct": None,
                 "source_update_label": clock},
    }
    return validate(row)


def product_templates(products):
    result = {}
    for product in products["products"]:
        native_record = {
            "source_record_id": product["source_record_id"],
            "source_query": product["source_query"],
            "selected_native_aggregate_literal":
                product["selected_native_aggregate_literal"],
        }
        result[product["url"]] = record(
            "NJ", product["county"], product["url"], products["measure"],
            native=native_record, count=product["prior_count"],
            clock=product["previous_clock"],
        )
    return result


def install_facts(monkeypatch, products, ocr_views):
    by_url = {product["url"]: product for product in products["products"]}

    def complete_tables(body, profile):
        product = by_url[profile["url"]]
        if product["kind"] != "text":
            raise AssertionError("OCR products do not use text tables")
        return (
            copy.deepcopy(product["facts"]),
            copy.deepcopy(product["tables"]),
            copy.deepcopy(product["table_clocks"]),
            copy.deepcopy(product["headers"]),
        )

    monkeypatch.setattr(periodic, "_complete_tables", complete_tables)
    monkeypatch.setattr(periodic_ocr, "_source_page", lambda body: None)
    monkeypatch.setattr(
        shared_ocr, "first_page_views",
        lambda body, **kwargs: copy.deepcopy(ocr_views),
    )
    return by_url


def baseline(products):
    templates = product_templates(products)
    bodies, declarations = {}, {}
    for state in intake.STATES:
        rows = list(templates.values()) if state == "NJ" else [
            record(
                state, state + " County",
                "https://www.themarginoferror.com/retained/" + state + ".json.gz",
                products["measure"],
            )
        ]
        shard = {
            "contract": "participation.state_counts.v1",
            "state_code": state, "year": 2026, "records": rows,
            "views": {"official": {"counties": [row["id"] for row in rows],
                                   "precincts": [], "nongeographic": []}},
        }
        path = "states/" + state + ".json.gz"
        bodies[path] = intake.compressed(encoded(shard))
        declarations[state] = {"file": path, **pin(bodies[path])}
    bodies["index.json"] = encoded({"states": declarations})
    return bodies, templates


def test_public_fixtures_are_complete_and_disclosure_safe(products, ocr_views):
    granular.public_facts(products)
    granular.public_facts(ocr_views)
    assert len(products["products"]) == 15
    assert sum(sum(len(table["rows"]) for table in product.get("tables", []))
               for product in products["products"]) == 920
    assert len(ocr_views) == 2
    disclosure = products["disclosure"]
    assert disclosure == {
        "individual_records_included": False,
        "original_document_templates_included": False,
        "public_aggregate_numerical_and_geometry_facts_only": True,
        "publisher_application_code_included": False,
        "raw_pdfs_included": False,
    }
    serialized = json.dumps([products, ocr_views])
    private_markers = ("/" + "Users" + "/", ".copilot" + "/session-state")
    assert all(marker not in serialized for marker in private_markers)
    assert not granular.PRIVATE_HEADERS.search(serialized)
    assert {tuple(path.suffixes) for path in FIXTURES.iterdir()} == {
        (".json", ".gz")}
    package_source = inspect.getsource(intake.collect)
    assert "code/tests/fixtures/results_pdf_periodic/" in package_source
    assert all(name in package_source for name in (
        "complete-products.json.gz", "sussex-ocr-views.json.gz",
        "results_pdf_periodic.py", "results_pdf_periodic_ocr.py",
        "results_pdf_periodic_grids.json", "results_pdf_periodic_sussex.json",
        "test_results_pdf_periodic.py",
    ))


def test_public_text_fixture_changes_count_and_rejects_role_header_and_rollback(
        monkeypatch, products, ocr_views):
    real_complete_tables = periodic._complete_tables
    by_url = install_facts(monkeypatch, products, ocr_views)
    fixture_complete_tables = periodic._complete_tables
    templates = product_templates(products)
    url = periodic.BASE + "atlantic-periodic-report.pdf"
    result = periodic.statistics(b"public synthetic PDF body", [templates[url]], url)
    assert result["updates"][0]["value"] == by_url[url]["expected_count"]
    changed = copy.deepcopy(by_url[url]["tables"])
    table_id, number = by_url[url]["source_record_id"].rsplit(":", 1)
    selected = next(table for table in changed if table["id"] == table_id)[
        "rows"][int(number) - 1]
    selected["cells"]["mail_ballots_tallied"]["value"] += 1
    monkeypatch.setattr(
        periodic, "_complete_tables",
        lambda body, profile: (
            copy.deepcopy(by_url[url]["facts"]), changed,
            copy.deepcopy(by_url[url]["table_clocks"]),
            copy.deepcopy(by_url[url]["headers"]),
        ),
    )
    changed_result = periodic.statistics(b"changed count", [templates[url]], url)
    assert changed_result["updates"][0]["value"] == result["updates"][0]["value"] + 1
    monkeypatch.setattr(periodic, "_complete_tables", fixture_complete_tables)
    newer = copy.deepcopy(templates[url])
    newer["source_clock"]["literal"] = "11/13/26 4:41 PM"
    with pytest.raises(ValueError, match="regressed"):
        periodic.statistics(b"rollback", [newer], url)
    monkeypatch.setattr(periodic, "_complete_tables", real_complete_tables)

    from scripts import native_pdf
    profile = {
        "expected_pages": 1,
        "grids": [{
            "id": "fixture-table", "page": 1, "source_role": periodic.ROLE,
            "fields": [{"id": "native_unit", "kind": "literal", "band": [0, 10]}],
            "rows": [[20, 30]], "numeric_guard_bottom": 31,
            "require": [{"decoded_text": "11/12/26 1:00 PM",
                         "reading_bbox": [0, 0, 10, 10]}],
            "source_annotations": {
                "native_table_clock_literal": "11/12/26 1:00 PM",
                "native_header_clock_literals": ["11/12/2026", "1:01 PM"],
            },
            "require_unofficial_header": True,
            "require_general_election_header": True,
        }],
    }
    facts = {"pages": [{
        "page": 1, "reading_rect": [0, 0, 100, 100], "glyphs": [],
        "native_text_absent_requires_separate_review": False,
    }]}
    table = {
        "id": "fixture-table", "source_page": 1, "source_role": periodic.ROLE,
        "source_annotations": {}, "rows": [],
    }
    monkeypatch.setattr(native_pdf, "read", lambda body: facts)
    monkeypatch.setattr(
        native_pdf, "text",
        lambda page, box: {"decoded_text": "11/12/26 1:00 PM"},
    )
    monkeypatch.setattr(native_pdf, "project", lambda facts, spec: copy.deepcopy(table))
    monkeypatch.setattr(
        periodic, "_page_text",
        lambda body: [["11/12/2026", "1:01 PM", "UNOFFICIAL",
                       "2026 GENERAL ELECTION"]],
    )
    assert periodic._complete_tables(b"layout", profile)[2] == {
        "fixture-table": "11/12/26 1:00 PM"}
    bad_role = copy.deepcopy(profile)
    bad_role["grids"][0]["source_role"] = "candidate_returns"
    with pytest.raises(ValueError, match="source role"):
        periodic._complete_tables(b"layout", bad_role)
    monkeypatch.setattr(
        periodic, "_page_text",
        lambda body: [["11/12/2026", "1:01 PM", "2026 GENERAL ELECTION"]],
    )
    with pytest.raises(ValueError, match="status"):
        periodic._complete_tables(b"layout", profile)


def test_public_sussex_ocr_facts_reject_disagreement_confidence_and_header(
        products, ocr_views):
    templates = product_templates(products)
    product = next(item for item in products["products"] if item["kind"] == "ocr")
    profile = periodic.PROFILES[product["url"]]
    result = periodic_ocr.parse_views(
        copy.deepcopy(ocr_views), templates[product["url"]], product["url"], profile,
        product["source_pin"],
    )
    query = result["complete_native_query"]
    assert result["updates"][0]["value"] == product["expected_count"] == 57580
    assert query["complete_numerical_cell_positions"] == 348
    assert query["ocr"]["full_numeric_cell_vectors_equal"] is True
    assert query["old_visual_transcription_values_used_as_numeric_inputs"] is False
    assert result["updates"][0]["native"]["ocr_selected_count_minimum_confidence"] >= .98

    disagreement = copy.deepcopy(ocr_views)
    next(cell for line in disagreement[1]["role_cells"] for cell in line
         if cell["text"] == "11298")["text"] = "11299"
    with pytest.raises(ValueError, match="disagree"):
        periodic_ocr.parse_views(
            disagreement, templates[product["url"]], product["url"], profile,
            product["source_pin"])
    low = copy.deepcopy(ocr_views)
    next(cell for line in low[1]["role_cells"] for cell in line
         if cell["text"] == "11298")["confidence"] = .979
    with pytest.raises(ValueError, match="confidence"):
        periodic_ocr.parse_views(
            low, templates[product["url"]], product["url"], profile,
            product["source_pin"])
    header = copy.deepcopy(ocr_views)
    header[1]["text"] = header[1]["text"].replace("UNOFFICIAL", "CERTIFIED")
    with pytest.raises(ValueError, match="header"):
        periodic_ocr.parse_views(
            header, templates[product["url"]], product["url"], profile,
            product["source_pin"])


def test_public_source_plan_collector_and_projector_are_all_51_stable(
        monkeypatch, tmp_path, products, ocr_views):
    by_url = install_facts(monkeypatch, products, ocr_views)
    before, templates = baseline(products)
    plan = native.source_plan(before)
    assert set(plan["NJ"]) == {
        "NJ-registered-" + intake.digest(url.encode())[:16] for url in templates}
    assert all(source["adapter"] == "reviewed_nj_periodic_pdf"
               for source in plan["NJ"].values())
    assert all(not plan[state] for state in intake.STATES if state != "NJ")

    def acquire(self, url, *, refresh=False):
        self.guard(url)
        body = ("public-fixture:" + url).encode()
        return body, {"url": url, "origin": "public_fixture", **pin(body)}

    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    collector = intake.Collector(
        tmp_path / "collector", {}, {"urls": [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 14, tzinfo=timezone.utc),
    )
    entries = native.collect_sources(collector, before)
    assert len(entries) == 15
    assert all(entry["status"] == "reported"
               and entry["adapter"] == "reviewed_nj_periodic_pdf" for entry in entries.values())
    after, changed = granular.project(before, entries)
    assert len(changed) == 15
    for state in intake.STATES:
        old = json.loads(gzip.decompress(before[f"states/{state}.json.gz"]))
        current = json.loads(gzip.decompress(after[f"states/{state}.json.gz"]))
        assert current["views"] == old["views"]
        assert [row["id"] for row in current["records"]] == [
            row["id"] for row in old["records"]]
        assert [row["geography"] for row in current["records"]] == [
            row["geography"] for row in old["records"]]
        if state != "NJ":
            assert after[f"states/{state}.json.gz"] == before[f"states/{state}.json.gz"]
    current = {
        row["view"]["source_url"]: row for row in
        json.loads(gzip.decompress(after["states/NJ.json.gz"]))["records"]
    }
    assert {url: row["count"]["value"] for url, row in current.items()} == {
        url: product["expected_count"] for url, product in by_url.items()}
    assert all(row["denominator"] is None
               and row["reporting_status"]["complete"] is None
               and row["view"]["automatic_source_refresh"] is True
               for row in current.values())
    assert granular.project(after, entries) == (after, [])
