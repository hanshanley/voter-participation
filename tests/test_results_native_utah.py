import copy
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import fitz
import pytest

from scripts import results_native
from scripts import results_native_utah as adapter
from scripts.nationwide import STATES
from scripts.participation_intake.contract import IntakeError, encoded, pin
from scripts.results_granular import project
from scripts.results_intake import Collector


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures/utah-native"
API_BODY = gzip.decompress((FIXTURES / "api-data.json.gz").read_bytes())
SOURCE_DOCUMENT = json.loads(API_BODY)
PDF_BODIES = {
    county: gzip.decompress(
        (FIXTURES / "summaries" / (county.split()[0].lower() + "-summary.pdf.gz"))
        .read_bytes()
    )
    for county in adapter.REPORTS
}
FROZEN_UT = (FIXTURES / "frozen-ut.json.gz").read_bytes()
ROLLING_UT = (FIXTURES / "rolling7416-ut.json.gz").read_bytes()
NOW = datetime(2026, 11, 15, 13, tzinfo=timezone.utc)
EMPTY_STOPS = {"urls": [], "prefixes": [], "hosts": []}


def source_document():
    return copy.deepcopy(SOURCE_DOCUMENT)


def source_body(document=None):
    return API_BODY if document is None else encoded(document)


def selected_templates(shard=FROZEN_UT):
    records = json.loads(gzip.decompress(shard))["records"]
    return [
        row for row in records
        if row.get("source", {}).get("id") in adapter.SOURCE_IDS
    ]


def full_baseline(ut_body=FROZEN_UT, selected_only=False):
    files, states = {}, {}
    for state in STATES:
        if state == "UT":
            if selected_only:
                shard = json.loads(gzip.decompress(ut_body))
                shard["records"] = selected_templates(ut_body)
                selected_ids = {row["id"] for row in shard["records"]}
                for view in shard["views"].values():
                    if not isinstance(view, dict):
                        continue
                    for key, value in view.items():
                        if isinstance(value, list):
                            view[key] = [
                                identity for identity in value
                                if identity in selected_ids
                            ]
                body = gzip.compress(encoded(shard), mtime=0)
            else:
                body = ut_body
        else:
            body = gzip.compress(encoded({
                "contract": "portable.complete.state.v1",
                "state_code": state,
                "year": 2026,
                "records": [],
                "views": {},
            }), mtime=0)
        name = "states/" + state + ".json.gz"
        files[name] = body
        states[state] = {"file": name}
    files["index.json"] = encoded({"states": states})
    return files


def declared_bodies(document, overrides=None):
    declarations = adapter._report_declarations(document)["reports"]
    overrides = overrides or {}
    return {
        row["source_url"]: overrides.get(county, PDF_BODIES[county])
        for county, row in declarations.items()
    }


def collect(
    work_root,
    baseline,
    document=None,
    pdf_overrides=None,
    prior=None,
    name="capture",
    stops=EMPTY_STOPS,
):
    work = work_root / name
    api = source_body(document)
    declared = source_document() if document is None else document
    try:
        bodies = declared_bodies(declared, pdf_overrides)
    except ValueError:
        bodies = declared_bodies(source_document(), pdf_overrides)
    collector = Collector(work, prior or {}, stops, NOW)

    def acquire(url, **_):
        collector.guard(url)
        if url == adapter.API_URL:
            body = api
        elif url in bodies:
            body = bodies[url]
        else:
            raise IntakeError("source_unavailable", "Fixture transport unavailable")
        return body, {"origin": "retained_original", **pin(body)}

    collector.acquire = acquire
    return results_native.collect_sources(collector, baseline), collector


def utah_entry(feeds):
    entries = [
        row for row in feeds.values()
        if row.get("adapter") == adapter.ADAPTER
    ]
    assert len(entries) == 1
    return entries[0]


def summary_pdf(county, count, registered, clock, status=None, include_clock=True):
    status = adapter.REPORTS[county]["status"] if status is None else status
    rate = 100 * count / registered
    lines = [
        "Summary Results Report",
        status,
        "General Election",
        "November 3, 2026",
        county + ", Utah",
        "Statistics TOTAL",
        "Election Day Precincts Reporting 1 of 1",
        "Precincts Complete 0 of 1",
        "Precincts Partially Reported 1 of 1",
        "Absentee/ Early Precincts Reporting 1 of 1",
        f"Registered Voters - Total {registered:,}",
        f"Ballots Cast - Total {count:,}",
        "Ballots Cast - Blank 0",
        f"Voter Turnout - Total {rate:.2f}%",
    ]
    if include_clock:
        lines.append("Election Summary - " + clock)
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "\n".join(lines), fontsize=11)
    body = document.tobytes()
    document.close()
    return body


def revise_report(document, county, upload_date, suffix):
    expected = adapter.REPORTS[county]["report_name"]
    report = next(
        report
        for category in document["election"]["publicReportCategories"]
        for report in category.get("reports", [])
        if report.get("reportName") == expected
    )
    blob = county.replace(" ", "_") + "_" + suffix + ".pdf"
    report["blobName"] = blob
    report["versions"] = [{
        "reportName": expected,
        "blobName": blob,
        "versionOrder": 2,
        "uploadDate": upload_date,
        "status": "Updated",
    }]


def set_api_clock(document, value):
    document["election"]["asOf"] = value
    document["election"]["lastUpdated"] = value


def test_default_source_plan_collector_projection_repeat_and_rolling7416_counts(
        tmp_path):
    baseline = full_baseline()
    plan = results_native.source_plan(baseline)
    selected = [
        row for row in plan["UT"].values()
        if row["adapter"] == adapter.ADAPTER
    ]
    assert len(selected) == 1
    assert selected[0]["url"] == adapter.API_URL
    assert len(selected[0]["templates"]) == 4

    feeds, collector = collect(tmp_path, baseline)
    entry = utah_entry(feeds)
    assert entry["status"] == "reported"
    assert entry["reviewed_record_count"] == 4
    assert any(
        attempt["status"] == "retained_original"
        and attempt["url"] == adapter.API_URL
        for attempt in collector.attempts
    )
    query = entry["data"]["complete_native_query"][0]
    assert query["reconciliation"] == {
        "selected_counties": 4,
        "native_total_ballots_sum": 50830,
        "candidate_votes_used_as_ballots": False,
        "denominators_or_rates_promoted": False,
        "state_parent_derived_from_county_sum": False,
        "counting_completion_certified": False,
    }

    projected, changes = project(baseline, feeds)
    assert len([row for row in changes if row["state_code"] == "UT"]) == 4
    projected_rows = {
        row["id"]: row
        for row in json.loads(gzip.decompress(projected["states/UT.json.gz"]))[
            "records"]
    }
    rolling_rows = {
        row["id"]: row
        for row in json.loads(gzip.decompress(ROLLING_UT))["records"]
    }
    selected_ids = {row["id"] for row in selected_templates()}
    assert len(projected_rows) == len(rolling_rows) == 151
    assert {
        identity: row for identity, row in projected_rows.items()
        if identity not in selected_ids
    } == {
        identity: row for identity, row in rolling_rows.items()
        if identity not in selected_ids
    }
    for identity in selected_ids:
        before = rolling_rows[identity]
        current = projected_rows[identity]
        assert current["count"]["value"] == before["count"]["value"]
        for field in ("id", "election", "geography", "measure", "denominator"):
            assert current[field] == before[field]
        assert current["view"]["maps_approved"] is True
        assert current["view"]["reported_pct"] is None
        assert current["source_clock"]["timezone"] is None
        assert current["reporting_status"]["complete"] is None
        assert current["view"]["native_record"]["pdf_report_timezone_literal"] is None
        assert current["view"]["native_record"][
            "candidate_votes_not_used_as_ballots"] is True

    repeated_feeds, _ = collect(
        tmp_path, projected, prior=feeds, name="repeat")
    repeated, repeated_changes = project(projected, repeated_feeds)
    assert repeated == projected
    assert repeated_changes == []


def test_frozen_registration_prior_rejects_full_partial_and_status_rollback(
        tmp_path):
    baseline = full_baseline()
    revised = source_document()
    set_api_clock(revised, "2026-11-15T18:00:00Z")
    revise_report(
        revised, "Cache County", "2026-11-15T12:05:00.0000000", "nov15")
    cache_pdf = summary_pdf(
        "Cache County", 42550, 70653, "11/15/2026 12:00PM")
    first, _ = collect(
        tmp_path,
        baseline,
        revised,
        {"Cache County": cache_pdf},
        name="nov15-first",
    )
    first_entry = utah_entry(first)
    assert first_entry["status"] == "reported"
    cache_update = next(
        row for row in first_entry["data"]["updates"]
        if row["native"]["county"] == "Cache County"
    )
    assert cache_update["value"] == 42550
    assert cache_update["clock"] == "11/15/2026 12:00PM"

    rollback = source_document()
    set_api_clock(rollback, "2026-11-14T18:00:00Z")
    revise_report(
        rollback, "Cache County", "2026-11-14T12:05:00.0000000", "nov14")
    failed, _ = collect(
        tmp_path,
        baseline,
        rollback,
        {"Cache County": summary_pdf(
            "Cache County", 42549, 70653, "11/14/2026 12:00PM")},
        prior=first,
        name="full-rollback",
    )
    failed_entry = utah_entry(failed)
    assert failed_entry["status"] == "retained_after_failure"
    assert failed_entry["data"] == first_entry["data"]
    assert failed_entry["source"] == first_entry["source"]

    partial = copy.deepcopy(revised)
    set_api_clock(partial, "2026-11-16T18:00:00Z")
    revise_report(
        partial, "Cache County", "2026-11-14T12:05:00.0000000",
        "partial-cache-rollback")
    revise_report(
        partial, "Kane County", "2026-11-16T12:05:00.0000000",
        "partial-kane-forward")
    partial_failed, _ = collect(
        tmp_path,
        baseline,
        partial,
        {
            "Cache County": summary_pdf(
                "Cache County", 42549, 70653, "11/14/2026 12:00PM"),
            "Kane County": summary_pdf(
                "Kane County", 3396, 5112, "11/16/2026 12:00PM"),
        },
        prior=first,
        name="partial-rollback",
    )
    assert utah_entry(partial_failed)["status"] == "retained_after_failure"
    assert utah_entry(partial_failed)["data"] == first_entry["data"]

    regressed_status = copy.deepcopy(revised)
    revise_report(
        regressed_status, "Cache County",
        "2026-11-16T12:05:00.0000000", "status-regression")
    status_failed, _ = collect(
        tmp_path,
        baseline,
        regressed_status,
        {"Cache County": summary_pdf(
            "Cache County", 42551, 70653, "11/16/2026 12:00PM",
            status="UNOFFICIAL RESULTS")},
        prior=first,
        name="status-rollback",
    )
    assert utah_entry(status_failed)["status"] == "retained_after_failure"
    assert utah_entry(status_failed)["data"] == first_entry["data"]


def test_malformed_duplicate_identity_and_missing_clock_retain_complete_prior(
        tmp_path):
    baseline = full_baseline()
    first, _ = collect(tmp_path, baseline, name="valid-prior")
    prior_entry = utah_entry(first)

    collector = Collector(
        tmp_path / "malformed", copy.deepcopy(first), EMPTY_STOPS, NOW)
    plan = results_native.source_plan(baseline)
    api_identity = next(
        identity for identity, row in plan["UT"].items()
        if row.get("adapter") == adapter.ADAPTER
    )
    assert api_identity in collector.prior
    collector.acquire = lambda url, **_: (
        b"{", {"origin": "retained_original", **pin(b"{")}
    )
    malformed = results_native.collect_sources(collector, baseline)
    malformed_entry = utah_entry(malformed)
    assert malformed_entry["status"] == "retained_after_failure"
    assert malformed_entry["data"] == prior_entry["data"]

    duplicate = source_document()
    category = next(
        row for row in duplicate["election"]["publicReportCategories"]
        if row.get("categoryName") == "Official Summary Results"
    )
    category["reports"].append(copy.deepcopy(category["reports"][0]))
    duplicate_failed, _ = collect(
        tmp_path, baseline, duplicate, prior=first, name="duplicate")
    assert utah_entry(duplicate_failed)["status"] == "retained_after_failure"
    assert utah_entry(duplicate_failed)["data"] == prior_entry["data"]

    drift = source_document()
    category = next(
        row for row in drift["election"]["publicReportCategories"]
        if row.get("categoryName") == "Official Summary Results"
    )
    target = next(
        row for row in category["reports"]
        if row.get("reportName") == adapter.REPORTS["Cache County"]["report_name"]
    )
    target["county"] = "Changed County"
    drift_failed, _ = collect(
        tmp_path, baseline, drift, prior=first, name="identity-drift")
    assert utah_entry(drift_failed)["status"] == "retained_after_failure"
    assert utah_entry(drift_failed)["data"] == prior_entry["data"]

    missing = source_document()
    set_api_clock(missing, "2026-11-16T18:00:00Z")
    revise_report(
        missing, "Cache County", "2026-11-16T12:05:00.0000000",
        "missing-clock")
    missing_failed, _ = collect(
        tmp_path,
        baseline,
        missing,
        {"Cache County": summary_pdf(
            "Cache County", 42551, 70653, "11/16/2026 12:00PM",
            include_clock=False)},
        prior=first,
        name="missing-clock",
    )
    assert utah_entry(missing_failed)["status"] == "retained_after_failure"
    assert utah_entry(missing_failed)["data"] == prior_entry["data"]


def test_source_stop_never_opens_transport_and_unknown_timezone_rate_stay_held(
        tmp_path, monkeypatch):
    baseline = full_baseline(selected_only=True)
    monkeypatch.setattr(
        "urllib.request.build_opener",
        lambda *_args, **_kwargs: pytest.fail("Stopped Utah source opened transport"),
    )
    collector = Collector(
        tmp_path / "stopped",
        {},
        {"urls": [adapter.API_URL], "prefixes": [], "hosts": []},
        NOW,
    )
    feeds = results_native.collect_sources(collector, baseline)
    entry = utah_entry(feeds)
    assert entry["status"] == "source_stopped"
    assert entry["data"] is None
    assert collector.attempts == [{
        "id": next(
            identity for identity, row in feeds.items()
            if row.get("adapter") == adapter.ADAPTER),
        "url": adapter.API_URL,
        "status": "source_stopped",
    }]

    reported, _ = collect(
        tmp_path, baseline, name="unknown-timezone-rate")
    entry = utah_entry(reported)
    assert entry["status"] == "reported"
    assert all(update["registered"] is None for update in entry["data"]["updates"])
    assert all(update["rate_compatible"] is False for update in entry["data"]["updates"])
    assert all(
        update["native"]["pdf_report_timezone_literal"] is None
        for update in entry["data"]["updates"]
    )
    projected, _ = project(baseline, reported)
    rows = json.loads(gzip.decompress(projected["states/UT.json.gz"]))["records"]
    assert all(row["denominator"] is None for row in rows)
    assert all(row["view"]["reported_pct"] is None for row in rows)
    assert all(row["source_clock"]["timezone"] is None for row in rows)


def test_corrupt_prior_pin_query_or_update_vector_is_not_used_for_clocks(tmp_path):
    baseline = full_baseline(selected_only=True)
    first, _ = collect(tmp_path, baseline, name="prior-coherence")
    entry = utah_entry(first)
    templates = selected_templates()
    bodies = declared_bodies(source_document())
    cases = []
    bad_pin = copy.deepcopy(entry)
    bad_pin["source"]["sha256"] = "0" * 64
    cases.append(bad_pin)
    bad_query = copy.deepcopy(entry)
    bad_query["data"]["complete_native_query"][0][
        "report_records"][0]["ballots_cast"] += 1
    cases.append(bad_query)
    bad_update = copy.deepcopy(entry)
    bad_update["data"]["updates"][0]["clock"] = "11/15/2026 12:00PM"
    cases.append(bad_update)
    for prior in cases:
        calls = []

        def acquire(url):
            calls.append(url)
            return bodies[url], {"origin": "retained_original", **pin(bodies[url])}

        with pytest.raises(ValueError, match="Prior Utah"):
            adapter.statistics(
                API_BODY,
                copy.deepcopy(templates),
                adapter.API_URL,
                acquire=acquire,
                prior=prior,
            )
        assert calls == []
