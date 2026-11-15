import copy
from datetime import datetime, timezone
import gzip
import io
import json
from pathlib import Path

from openpyxl import load_workbook
import pytest

from scripts.participation_intake.contract import encoded, pin
from scripts.results_granular import project
from scripts.results_intake import Collector
from scripts import results_native
from scripts import results_native_idaho as adapter


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures/idaho-native"


def fixture_bodies():
    data = gzip.decompress((FIXTURES / "accepted-data.json.gz").read_bytes())
    workbook = gzip.decompress((FIXTURES / "accepted-ballots.xlsx.gz").read_bytes())
    url = adapter._declared_workbook(json.loads(data))
    return {adapter.DATA_URL: data, url: workbook}


def fixture_templates():
    return json.loads(gzip.decompress(
        (FIXTURES / "accepted-templates.json.gz").read_bytes()))


def baseline(templates=None):
    templates = fixture_templates() if templates is None else copy.deepcopy(templates)
    counties = [
        row["id"] for row in templates
        if row["source"]["id"] == adapter.COUNTY_SOURCE_ID
    ]
    units = [
        row["id"] for row in templates
        if row["source"]["id"] == adapter.UNIT_SOURCE_ID
    ]
    frame = {"counties": counties, "precincts": units, "nongeographic": []}
    shard = {
        "contract": "portable.complete.state.v1",
        "state_code": "ID",
        "year": 2026,
        "records": templates,
        "views": {
            "available": copy.deepcopy(frame),
            "official": copy.deepcopy(frame),
        },
    }
    return {
        "index.json": encoded({"states": {"ID": {"file": "states/ID.json.gz"}}}),
        "states/ID.json.gz": gzip.compress(encoded(shard), mtime=0),
    }


def collect(tmp_path, source, prior=None, baseline_files=None):
    collector = Collector(
        tmp_path,
        prior or {},
        {"urls": [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 15, tzinfo=timezone.utc),
    )

    def acquire(url, **_):
        body = source[url]
        return body, {"origin": "retained_official_original", **pin(body)}

    collector.acquire = acquire
    return results_native.collect_sources(
        collector, baseline() if baseline_files is None else baseline_files), collector


def parsed_rows(files):
    return json.loads(gzip.decompress(files["states/ID.json.gz"]))["records"]


def rewrite_workbook(body, county, precinct, ballots):
    book = load_workbook(io.BytesIO(body))
    sheet = book["Ballots Cast by Precinct"]
    for row in range(2, sheet.max_row + 1):
        if sheet.cell(row, 1).value == county and sheet.cell(row, 2).value == precinct:
            registered = sheet.cell(row, 5).value
            sheet.cell(row, 6).value = ballots
            sheet.cell(row, 7).value = (
                f"{round(100 * ballots / registered):,} %" if registered else "0 %"
            )
            break
    else:
        raise AssertionError("fixture unit not found")
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def revised_source(
        ballots, *, as_of="2026-11-15T10:00:00.1234567Z",
        last_updated="2026-11-15T09:59:59.7654321Z",
        official=False):
    source = fixture_bodies()
    document = json.loads(source[adapter.DATA_URL])
    registration = next(
        row for row in document["voterRegistration"]
        if adapter._english(row["localityName"], "county") == "Ada County"
    )
    locality = next(
        row for row in document["localityElections"]
        if row["jurisdictionId"] == registration["id"]
    )
    original = 2729
    locality["ballotsCast"] += ballots - original
    locality["asOf"] = as_of
    locality["lastUpdated"] = last_updated
    locality["isOfficialResults"] = official
    document["election"]["asOf"] = as_of
    document["election"]["lastUpdated"] = last_updated
    workbook_url = adapter._declared_workbook(document)
    workbook = rewrite_workbook(
        source[next(key for key in source if key != adapter.DATA_URL)],
        "Ada County",
        "1001",
        ballots,
    )
    return {adapter.DATA_URL: encoded(document), workbook_url: workbook}


def replace_document(source, document):
    workbook = source[next(key for key in source if key != adapter.DATA_URL)]
    return {
        adapter.DATA_URL: encoded(document),
        adapter._declared_workbook(document): workbook,
    }


def parse_direct(source=None, templates=None, prior=None):
    source = fixture_bodies() if source is None else source
    templates = fixture_templates() if templates is None else templates
    data = source[adapter.DATA_URL]
    workbook_url = adapter._declared_workbook(json.loads(data))

    def acquire(url, **_):
        body = source[url]
        return body, {"origin": "retained_official_original", **pin(body)}

    return adapter.statistics(
        data, templates, adapter.DATA_URL, acquire=acquire, prior=prior)


def test_default_source_plan_collector_projection_repeat_and_complete_query(tmp_path):
    plan = results_native.source_plan(baseline())
    sources = list(plan["ID"].values())
    assert len(sources) == 1
    assert sources[0]["adapter"] == adapter.ADAPTER
    assert sources[0]["url"] == adapter.DATA_URL
    assert len(sources[0]["templates"]) == 1030

    feeds, collector = collect(tmp_path / "first", fixture_bodies())
    assert len(feeds) == 1
    entry = next(iter(feeds.values()))
    assert entry["status"] == "reported"
    assert entry["adapter"] == adapter.ADAPTER
    assert collector.attempts[0]["status"] == "retained_official_original"
    query = entry["data"]["complete_native_query"][0]
    assert len(query["county_records"]) == 44
    assert len(query["reporting_unit_records"]) == 986
    assert query["reconciliation"]["county_ballots"] == 731980
    assert query["reconciliation"]["reporting_unit_ballots"] == 731980
    assert query["reconciliation"]["registration_differences"] == [{
        "county": "Twin Falls County",
        "workbook_registered_voters": 41878,
        "api_registered_voters": 42990,
    }]
    assert query["reconciliation"]["candidate_votes_used_as_ballots"] is False
    assert query["reconciliation"][
        "state_registration_stock_used_as_ballot_denominator"] is False
    assert len(encoded(query)) < 300_000_000

    initial = baseline()
    after, changes = project(initial, feeds)
    assert len(changes) == 1030
    rows = parsed_rows(after)
    assert len(rows) == 1030
    assert sum(row["count"]["value"] for row in rows
               if row["source"]["id"] == adapter.UNIT_SOURCE_ID) == 731980
    assert sum(row["count"]["value"] for row in rows
               if row["source"]["id"] == adapter.COUNTY_SOURCE_ID) == 731980
    assert sum(bool(row["denominator"]["qualified"]) for row in rows) == 858
    assert all(row["view"]["automatic_source_refresh"] is True for row in rows)
    assert all(row["reporting_status"]["complete"] is None for row in rows)
    assert {row["view"]["maps_approved"] for row in rows
            if row["source"]["id"] == adapter.COUNTY_SOURCE_ID} == {True}
    assert {row["view"]["maps_approved"] for row in rows
            if row["source"]["id"] == adapter.UNIT_SOURCE_ID} == {False}
    county_rows = [
        row for row in rows if row["source"]["id"] == adapter.COUNTY_SOURCE_ID]
    unit_rows = [
        row for row in rows if row["source"]["id"] == adapter.UNIT_SOURCE_ID]
    assert all(row["source_clock"]["timezone"] == "UTC" for row in county_rows)
    assert all(row["source_clock"]["literal"] for row in county_rows)
    assert all(row["source_clock"]["literal"] is None for row in unit_rows)
    assert all(row["source_clock"]["timezone"] is None for row in unit_rows)
    assert all(
        row["view"]["native_record"]["source_clock_scope"]
        == "parent_api_context_not_workbook_clock"
        for row in unit_rows)
    assert all(
        row["view"]["native_record"]["parent_api_context"][
            "source_clock_timezone_literal"] == "UTC"
        for row in unit_rows)

    repeat_feeds, _ = collect(tmp_path / "repeat", fixture_bodies(), prior=feeds)
    repeated, repeated_changes = project(after, repeat_feeds)
    assert repeated == after
    assert repeated_changes == []


@pytest.mark.parametrize("ballots", [2730, 0])
def test_frozen_registration_revised_count_and_genuine_zero_workflow(
        tmp_path, ballots):
    frozen = baseline()
    first, _ = collect(tmp_path / "first", fixture_bodies())
    source = revised_source(ballots)
    revised, _ = collect(
        tmp_path / "revised", source, prior=first, baseline_files=frozen)
    entry = next(iter(revised.values()))
    assert entry["status"] == "reported"
    unit_update = next(
        row for row in entry["data"]["updates"]
        if row["native"].get("unit_key") == "ID|Ada County|1001")
    county_update = next(
        row for row in entry["data"]["updates"]
        if row["native"].get("native_kind") == "county"
        and row["native"].get("county") == "Ada County"
    )
    assert unit_update["value"] == ballots
    assert unit_update["clock"] is None
    assert unit_update["native"]["workbook_source_clock"] is None
    assert "source_clock_timezone_literal" not in unit_update["native"]
    assert county_update["value"] == 232003 + ballots - 2729
    assert county_update["clock"] == "2026-11-15T10:00:00.1234567Z"
    projected, _ = project(frozen, revised)
    before = {row["id"]: row for row in parsed_rows(frozen)}
    after = {row["id"]: row for row in parsed_rows(projected)}
    assert set(after) == set(before)
    for identity in before:
        for field in ("id", "election", "geography", "measure"):
            assert after[identity][field] == before[identity][field]
        assert after[identity]["view"]["maps_approved"] == before[identity]["view"]["maps_approved"]
        assert after[identity]["denominator"]["qualified"] == before[identity]["denominator"]["qualified"]
    selected = next(
        row for row in after.values()
        if row["view"].get("unit_key") == "ID|Ada County|1001")
    assert selected["count"]["value"] == ballots
    assert selected["source_clock"]["literal"] is None
    assert selected["source_clock"]["timezone"] is None
    repeated, _ = collect(
        tmp_path / "repeat", source, prior=revised, baseline_files=frozen)
    repeated_entry = next(iter(repeated.values()))
    assert repeated_entry["status"] == "reported"
    assert repeated_entry["data"] == entry["data"]
    assert repeated_entry["source"] == entry["source"]


def test_frozen_registration_prior_rejects_full_partial_last_updated_and_official_rollback(
        tmp_path):
    frozen = baseline()
    first, _ = collect(tmp_path / "first", fixture_bodies())
    revised_source_body = revised_source(2730)
    revised, _ = collect(
        tmp_path / "revised", revised_source_body,
        prior=first, baseline_files=frozen)
    revised_entry = next(iter(revised.values()))
    assert revised_entry["status"] == "reported"

    def retained(label, source, prior=revised):
        feeds, _ = collect(
            tmp_path / label, source, prior=prior, baseline_files=frozen)
        entry = next(iter(feeds.values()))
        assert entry["status"] == "retained_after_failure"
        assert entry["error"] == "schema_or_source_semantics_changed"
        assert entry["data"] == next(iter(prior.values()))["data"]
        assert entry["source"] == next(iter(prior.values()))["source"]
        return entry

    retained("full-rollback", fixture_bodies())

    partial_document = json.loads(revised_source_body[adapter.DATA_URL])
    registration_names = {
        row["id"]: adapter._english(row["localityName"], "county")
        for row in partial_document["voterRegistration"]
    }
    ada = next(
        row for row in partial_document["localityElections"]
        if registration_names[row["jurisdictionId"]] == "Ada County")
    other = next(
        row for row in partial_document["localityElections"]
        if registration_names[row["jurisdictionId"]] != "Ada County")
    ada["asOf"] = "2026-11-14T10:00:00Z"
    ada["lastUpdated"] = "2026-11-14T09:00:00Z"
    other["asOf"] = "2026-11-16T10:00:00Z"
    other["lastUpdated"] = "2026-11-16T09:00:00Z"
    partial_document["election"]["asOf"] = "2026-11-16T10:00:00Z"
    partial_document["election"]["lastUpdated"] = "2026-11-16T09:00:00Z"
    retained(
        "partial-rollback",
        replace_document(revised_source_body, partial_document))

    last_updated_document = json.loads(
        revised_source_body[adapter.DATA_URL])
    ada = next(
        row for row in last_updated_document["localityElections"]
        if registration_names[row["jurisdictionId"]] == "Ada County")
    ada["asOf"] = "2026-11-16T10:00:00Z"
    ada["lastUpdated"] = "2026-11-14T09:00:00Z"
    last_updated_document["election"]["asOf"] = "2026-11-16T10:00:00Z"
    last_updated_document["election"]["lastUpdated"] = "2026-11-16T09:00:00Z"
    retained(
        "last-updated-rollback",
        replace_document(revised_source_body, last_updated_document))

    official_source = revised_source(
        2730,
        as_of="2026-11-16T10:00:00Z",
        last_updated="2026-11-16T09:00:00Z",
        official=True,
    )
    official, _ = collect(
        tmp_path / "official", official_source,
        prior=revised, baseline_files=frozen)
    assert next(iter(official.values()))["status"] == "reported"
    unofficial_source = revised_source(
        2730,
        as_of="2026-11-17T10:00:00Z",
        last_updated="2026-11-17T09:00:00Z",
        official=False,
    )
    retained("official-rollback", unofficial_source, prior=official)


def test_missing_semantic_source_clock_and_identity_corruption_refuse():
    source = fixture_bodies()
    workbook_url = next(key for key in source if key != adapter.DATA_URL)
    book = load_workbook(io.BytesIO(source[workbook_url]))
    book["Ballots Cast by Precinct"].cell(2, 6).value = None
    output = io.BytesIO()
    book.save(output)
    book.close()
    with pytest.raises(ValueError, match="not zero"):
        parse_direct({adapter.DATA_URL: source[adapter.DATA_URL], workbook_url: output.getvalue()})

    bad = json.loads(source[adapter.DATA_URL])
    bad["election"]["isPrimary"] = True
    with pytest.raises(ValueError, match="general-election authority"):
        parse_direct({**source, adapter.DATA_URL: encoded(bad)})

    bad = json.loads(source[adapter.DATA_URL])
    bad["election"]["publicReportCategories"][0]["reports"][0]["blobName"] = (
        "Candidate Votes_00000000-0000-0000-0000-000000000000.xlsx"
    )
    with pytest.raises(ValueError, match="report role"):
        parse_direct({**source, adapter.DATA_URL: encoded(bad)})

    with pytest.raises(ValueError, match="Unreviewed Idaho"):
        adapter.statistics(
            source[adapter.DATA_URL],
            fixture_templates(),
            "https://example.test/data",
            acquire=lambda url, **_: (source[url], {"origin": "fixture"}),
        )

    templates = fixture_templates()
    templates[0]["geography"]["id"] += ":forged"
    with pytest.raises(ValueError, match="identities changed"):
        parse_direct(templates=templates)

    first_data = parse_direct()
    projected, _ = project(baseline(), {"ID-native": {
        "status": "reported",
        "source": {"url": adapter.DATA_URL, **pin(source[adapter.DATA_URL])},
        "data": first_data,
    }})
    templates = parsed_rows(projected)
    bad = json.loads(source[adapter.DATA_URL])
    for locality in bad["localityElections"]:
        locality["asOf"] = "2026-11-04T22:15:30Z"
    with pytest.raises(ValueError, match="clock regressed"):
        parse_direct({**source, adapter.DATA_URL: encoded(bad)}, templates)

    compact = encoded(json.loads(source[adapter.DATA_URL]))
    duplicate = b'{"duplicate":1,"duplicate":2,' + compact[1:]
    with pytest.raises(ValueError, match="Duplicate Idaho"):
        adapter.statistics(
            duplicate,
            fixture_templates(),
            adapter.DATA_URL,
            acquire=lambda url, **_: (
                source[url], {"origin": "retained_official_original", **pin(source[url])}),
        )


def test_prior_vector_and_projected_clock_status_pin_and_hold_corruption_refuse(tmp_path):
    feeds, _ = collect(tmp_path / "first", fixture_bodies())
    entry = next(iter(feeds.values()))
    corrupt_prior = copy.deepcopy(entry)
    corrupt_prior["data"]["complete_native_query"][0][
        "numerical_input_pins"]["data_api"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source pins"):
        parse_direct(prior=corrupt_prior)

    projected, _ = project(baseline(), feeds)
    rows = parsed_rows(projected)
    unit_index = next(
        index for index, row in enumerate(rows)
        if row["source"]["id"] == adapter.UNIT_SOURCE_ID)
    county_index = next(
        index for index, row in enumerate(rows)
        if row["source"]["id"] == adapter.COUNTY_SOURCE_ID)

    fabricated_clock = copy.deepcopy(rows)
    unit = fabricated_clock[unit_index]
    parent_clock = unit["view"]["native_record"][
        "parent_api_context"]["source_as_of"]
    unit["source_clock"] = {
        "literal": parent_clock,
        "timezone": "UTC",
        "qualification": "native_clock_or_explicitly_not_supplied",
    }
    with pytest.raises(ValueError, match="unit clock"):
        adapter.validate_templates(fabricated_clock)

    bad_context = copy.deepcopy(rows)
    unit = bad_context[unit_index]
    unit["view"]["native_record"]["parent_api_context"][
        "source_last_updated"] = "2026-11-18T00:00:00Z"
    unit["source"]["fields"] = copy.deepcopy(unit["view"])
    with pytest.raises(ValueError, match="source vector|parent context"):
        adapter.validate_templates(bad_context)

    bad_pin = copy.deepcopy(rows)
    county = bad_pin[county_index]
    county["view"]["native_record"]["source_original_pin"]["sha256"] = "0" * 64
    county["source"]["fields"] = copy.deepcopy(county["view"])
    with pytest.raises(ValueError, match="source vector"):
        adapter.validate_templates(bad_pin)

    bad_status = copy.deepcopy(rows)
    county = bad_status[county_index]
    county["view"]["native_record"]["query"][
        "native_report_status_literal"] = "isOfficialResults=true"
    county["source"]["fields"] = copy.deepcopy(county["view"])
    with pytest.raises(ValueError, match="source vector"):
        adapter.validate_templates(bad_status)

    bad_complete = copy.deepcopy(rows)
    bad_complete[county_index]["reporting_status"]["complete"] = True
    with pytest.raises(ValueError, match="coherence|masks"):
        adapter.validate_templates(bad_complete)

    bad_mask = copy.deepcopy(rows)
    qualified_index = next(
        index for index, row in enumerate(bad_mask)
        if row["denominator"]["qualified"])
    bad_mask[qualified_index]["denominator"]["qualified"] = False
    bad_mask[qualified_index]["view"]["reported_pct"] = None
    bad_mask[qualified_index]["source"]["fields"] = copy.deepcopy(
        bad_mask[qualified_index]["view"])
    with pytest.raises(ValueError, match="masks"):
        adapter.validate_templates(bad_mask)


def test_collector_failure_retains_last_good_and_stop_policy(tmp_path):
    source = fixture_bodies()
    feeds, _ = collect(tmp_path / "first", source)
    after, _ = project(baseline(), feeds)
    collector = Collector(
        tmp_path / "failed",
        feeds,
        {"urls": [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 15, tzinfo=timezone.utc),
    )

    def acquire(url, **_):
        if url == adapter.DATA_URL:
            body = source[url]
            return body, {"origin": "retained_official_original", **pin(body)}
        raise ValueError("retained workbook unavailable")

    collector.acquire = acquire
    failed = results_native.collect_sources(collector, after)
    entry = next(iter(failed.values()))
    assert entry["status"] == "retained_after_failure"
    assert entry["error"] == "schema_or_source_semantics_changed"
    retained, changes = project(after, failed)
    assert retained == after
    assert changes == []
    assert collector.stopped == {"urls": [], "prefixes": [], "hosts": []}


def test_default_collector_honors_exact_required_source_stop(tmp_path):
    stopped = {"urls": [adapter.DATA_URL], "prefixes": [], "hosts": []}
    collector = Collector(
        tmp_path / "blocked",
        {},
        stopped,
        datetime(2026, 11, 15, tzinfo=timezone.utc),
    )
    blocked = results_native.collect_sources(collector, baseline())
    entry = next(iter(blocked.values()))
    assert entry["status"] == "source_stopped"
    assert entry["error"] == "source_stopped"
    assert entry["data"] is None
    assert collector.attempts == [{
        "id": next(iter(blocked)),
        "url": adapter.DATA_URL,
        "status": "source_stopped",
    }]
    assert collector.stopped == stopped
