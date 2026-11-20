import io
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from openpyxl import Workbook

from scripts import results_intake, washington_participation as wa


def workbook(rows):
    book = Workbook(write_only=True)
    notes = book.create_sheet("README")
    for text in ("postcensal estimates", "Registered voter data is estimated from the election period",
                 "Population data is estimated from April 1st"):
        notes.append([text])
    table = book.create_sheet("Table")
    table.append(wa.HEADER)
    for row in rows:
        table.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def rows(year=2025, amendment=0):
    for county in (*wa.COUNTIES, wa.STATE):
        counties = len(wa.COUNTIES) if county == wa.STATE else 1
        for age in wa.AGES:
            multiplier = counties * (6 if age == "0TOTAL" else 1)
            changed = county in (wa.STATE, "Adams") and age in ("0TOTAL", "18-24")
            female_ballots = multiplier * 5 + (amendment if changed else 0)
            yield [county, year, "General", None, None, None, age, 11 * multiplier, 13 * multiplier,
                   24 * multiplier, 10 * multiplier, 12 * multiplier, None, 22 * multiplier, female_ballots,
                   6 * multiplier, None, female_ballots + 6 * multiplier, *([None] * 9)]


@pytest.fixture(scope="module")
def history():
    return [row for year in range(2005, 2025) for row in rows(year)]


def test_workbook_placeholder_age_hold_and_factual_replay(history):
    observed = deepcopy(history) + list(rows())
    altered = next(r for r in observed if r[:3] == ["Adams", 2014, "General"] and r[6] == "45-54")
    altered[6] = "55-64"
    future = [row[:7] + [None] * 20 for row in rows(2026)]
    data = wa.parse(workbook([*observed, *future]))
    entry = {"status": "reported", "source": {"url": wa.URL, "sha256": "a" * 64}, "data": data}
    exported = wa.exports({wa.FEED: entry})
    held = [row for row in exported if row["observation_status"] == "held_ambiguous_age_label"]
    assert len(held) == 6 and all(row["total_ballots_per_registration_estimate"] is None for row in held)
    assert [row["source_occurrence"] for row in held if row["age_group"] == "55-64"] == [1, 2]
    assert sum(row["observation_status"] == "workbook_placeholder" for row in exported) == 280
    regular = next(row for row in exported if row["age_group"] == "18-24"
                   and row["geography"] == "Washington")
    assert regular["total_ballots_per_registration_estimate"] == 0.5
    assert regular["total_ballots_per_april_vap_estimate"] == 11 / 24
    with pytest.raises(ValueError, match="county-age roster"):
        wa.query(observed[:-1])


def test_revisions_noop_and_failed_source_retain_last_good(tmp_path, history):
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    stops = {"urls": [], "prefixes": [], "hosts": []}
    # Treat real XLSX bytes as the source in each collector invocation.
    accepted = {}
    for amendment in (0, 1, -1):
        body = workbook([*history, *rows(amendment=amendment)])
        collector = results_intake.Collector(tmp_path, accepted, stops, now)
        collector.acquire = lambda url: (body, {"origin": "fixture"})
        entry = wa.collect(collector)
        assert entry["status"] == "reported"
        assert next(row for row in entry["data"]["complete_native_query"]
                    if row[0] == wa.STATE and row[1] == 2025 and row[6] == "0TOTAL")[17] == 2574 + amendment
        accepted = {wa.FEED: entry}
    collector = results_intake.Collector(tmp_path, accepted, stops, now)
    collector.acquire = lambda url: pytest.fail("Weekly reuse unexpectedly accessed the source")
    assert wa.collect(collector, reuse_checked_week=True) == entry

    def denied(url):
        raise results_intake.IntakeError("http_403", "source denied")

    collector.acquire = denied
    retained = wa.collect(collector)
    assert retained["status"] == "retained_after_failure"
    assert retained["data"] == entry["data"] and retained["source"] == entry["source"]
