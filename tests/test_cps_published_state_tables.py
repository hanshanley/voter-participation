import io
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
import zipfile

import pytest

from scripts import cps_published_state_tables as cps


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / cps.INPUT_PATH
if not BUNDLE.exists():
    BUNDLE = ROOT.parent / "inputs" / cps.INPUT


def test_published_cells_preserve_native_denominators_and_suppression():
    rows = cps.build(BUNDLE.read_bytes())
    assert len(rows) == 4420
    keyed = {(r["year"], r["source_table"], r["state_code"], r["group"]): r for r in rows}
    assert len(keyed) == len(rows)
    usa = keyed[2020, "4c", "US", "18 to 24"]
    assert (usa["vap_voted_pct"], usa["cvap_voted_pct"], usa["cvap_voted_moe_pp"]) == (48, 51.4, 1.2)
    assert usa["cvap_registered_pct"] == 59.8
    suppressed = keyed[2016, "4b", "WY", "Black alone"]
    assert suppressed["cvap_voted_pct"] is None
    assert suppressed["source_markers"]["cvap_voted_pct"] == "B"
    mature = keyed[2024, "4c", "WY", "65+"]
    assert (mature["native_group"], mature["cvap_voted_pct"], mature["cvap_voted_moe_pp"]) == (
        "65 years and over", 76.1, 3.9)
    assert cps.summary(rows)["states_and_dc"] == 51


def test_changed_workbook_and_incomplete_bundle_are_rejected():
    with zipfile.ZipFile(BUNDLE) as source:
        members = {n: source.read(n) for n in source.namelist()}
    name = "2016-table4b.xlsx"
    for changed, reason in (({**members, name: members[name] + b"changed"}, "checksum differs"),
                            ({k: b for k, b in members.items() if k != name}, "Incomplete")):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            for label, body in changed.items():
                archive.writestr(label, body)
        with pytest.raises(ValueError, match=reason):
            cps.build(out.getvalue())


def test_current_pair_waits_revises_and_retains_without_count_promotion(tmp_path, monkeypatch):
    from openpyxl import load_workbook
    from scripts import results_granular
    from scripts.supported_analytical_release import selected_local_observation_ids

    intake = pytest.importorskip("scripts.results_intake")
    Store = intake.Store
    release = "https://www.census.gov/data/tables/time-series/demo/voting-and-registration/p20-999.html"
    root = "https://www2.census.gov/programs-surveys/cps/tables/p20/999/"
    urls = {table: root + f"vote0{table}_2026.xlsx" for table in ("4b", "4c")}
    headline = "Voting and Registration in the Election of November 2026"
    index = f'<a href="{release}"><span>Table</span> {headline} April 2027</a>'.encode()
    age_link = f'<a href="{urls["4c"]}">Reported Voting and Registration, by Age, for States: November 2026</a>'
    partial_page = (f'<h1>{headline}</h1><a href="{urls["4b"]}">Reported Voting and Registration of the '
                    'Total Voting-Age Population, by Sex, Race and Hispanic Origin, for States: November 2026</a>')
    full_page = (partial_page + age_link).encode()

    def workbook(table, revision=None):
        with zipfile.ZipFile(BUNDLE) as archive:
            original = archive.read(cps.filename(2024, table))
        book = load_workbook(io.BytesIO(original))
        book.active["A2"] = book.active["A2"].value.replace("2024", "2026")
        if revision is not None:
            book.active["M6"] = revision
        out = io.BytesIO()
        book.save(out)
        book.close()
        return out.getvalue()

    sources = {cps.INDEX_URL: index.replace(b"2026", b"2024"), release: partial_page.encode(),
               **{url: workbook(table) for table, url in urls.items()}}
    requests = []

    def acquire(_, spec, *, access_guard):
        url = spec["url"]
        access_guard(url)
        requests.append(url)
        if url not in sources:
            raise intake.IntakeError("source_unavailable", "Controlled missing workbook")
        return sources[url], {"origin": "controlled_test"}

    monkeypatch.setattr(Store, "acquire", acquire)
    now = datetime(2027, 4, 25, tzinfo=timezone.utc)
    stopped = {"urls": [], "prefixes": [], "hosts": []}

    def refresh(prior=None):
        collector = intake.Collector(tmp_path, {cps.CURRENT_FEED: prior} if prior else {}, stopped, now)
        requests.clear()
        return cps.collect_current(collector)

    assert refresh()["status"] == "report_not_linked" and requests == [cps.INDEX_URL]
    sources[cps.INDEX_URL] = index
    assert refresh()["status"] == "report_not_linked" and requests == [cps.INDEX_URL, release]
    sources[release] = full_page
    initial = refresh()
    assert initial["status"] == "reported" and requests == [cps.INDEX_URL, release, *urls.values()]
    assert len(cps.current_rows(initial)) == 884
    baseline = {"index.json": b'{"states":{}}'}
    assert results_granular.project(baseline, {cps.CURRENT_FEED: initial}) == (baseline, [])
    assert selected_local_observation_ids({
        "collection_scope": {"mode": "selected_registered_source_refresh", "source_ids": [cps.CURRENT_FEED]},
        "granular_sources": {cps.CURRENT_FEED: initial},
    }) == set()
    assert refresh(initial) == initial
    sources[cps.INDEX_URL] += b"<!-- unrelated index update -->"
    sources[release] += b"<!-- unrelated page update -->"
    assert refresh(initial) == initial

    sources[urls["4b"]] = workbook("4b", 65.2)
    hold = refresh(initial)
    assert hold["status"] == "retained_after_failure" and "totals differ" in hold["error_detail"]
    assert cps.current_rows(hold) == cps.current_rows(initial)
    sources[urls["4c"]] = workbook("4c", 65.2)
    revised = refresh(hold)
    assert revised["status"] == "reported" and cps.current_rows(revised)[0]["cvap_voted_pct"] == 65.2
    del sources[urls["4c"]]
    hold = refresh(revised)
    assert hold["status"] == "retained_after_failure" and cps.current_rows(hold) == cps.current_rows(revised)


def test_census_index_access_stop_does_not_retry_in_later_runs(tmp_path, monkeypatch):
    intake = pytest.importorskip("scripts.results_intake")
    Store = intake.Store
    requests = []

    def deny(_, spec, *, access_guard):
        url = spec["url"]
        access_guard(url)
        requests.append(url)
        raise intake.IntakeError("source_access", "Forbidden") from HTTPError(url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(Store, "acquire", deny)
    now = datetime(2027, 4, 25, tzinfo=timezone.utc)
    first = intake.Collector(tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []}, now)
    assert cps.collect_current(first)["status"] == "source_stopped"
    second = intake.Collector(tmp_path, {}, intake.read(tmp_path / "source-stops.json"), now)
    assert cps.collect_current(second)["status"] == "source_stopped"
    assert requests == [cps.INDEX_URL]
