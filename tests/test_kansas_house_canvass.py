from datetime import datetime, timezone
from io import BytesIO

from openpyxl import Workbook
import pytest

from scripts import kansas_house_canvass as ks, results_granular
from scripts.results_intake import Collector


OLD = b'<a href="24elec/2024-General-Election-Official-Vote-Totals.pdf">2024 Official GeneralElection Results</a>'
CONTROL = b'<a href="26elec/2026-General-Election-Official-Vote-Totals.pdf">2026 Official GeneralElection Results</a>'
DETAIL = b'<a href="26elec/2026-General-Election-US-House-Precinct-Results.xlsx">U.S. House of Representatives2026 General Election</a>'


def test_official_link_pair_and_retention(tmp_path, monkeypatch):
    feed = "KS-2026-official-house-canvass-audit"
    links = ks.discover(OLD + CONTROL + DETAIL, year=2026)
    assert set(links) == {"control", "workbook"}
    assert ks.discover(OLD, year=2026) == {}
    with pytest.raises(ValueError, match="ambiguous"):
        ks.discover(OLD + CONTROL + DETAIL + DETAIL, year=2026)
    with pytest.raises(ValueError, match="unexpected|Unexpected"):
        ks.discover(OLD + DETAIL.replace(b"26elec/", b"https://outside.invalid/26elec/"), year=2026)
    monkeypatch.setattr(ks, "read_control", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ks, "read_workbook", lambda *_args, **_kwargs: {
        "named": [], "uncontrolled": [], "counties": 105, "blank_main_rows": 0,
    })
    c = Collector(tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
                  datetime(2026, 11, 21, tzinfo=timezone.utc), offline=True)
    bodies = {ks.INDEX: OLD + CONTROL, **dict.fromkeys(links.values(), b"fixture")}
    monkeypatch.setattr(c, "acquire", lambda url: (bodies[url], {"origin": "fixture"}))
    partial = ks.collect(c, feed)
    assert list(ks.exports({feed: partial}))[0]["decision"] == "report_pair_incomplete"
    bodies[ks.INDEX] += DETAIL
    pair = ks.collect(c, feed)
    baseline = {"index.json": b'{"states": {}}'}
    assert results_granular.project(baseline, {feed: pair}) == (baseline, [])
    c.prior[feed] = pair
    bodies[ks.INDEX] = OLD
    held = ks.collect(c, feed)
    assert held["status"] == "retained_after_failure" and held["data"] == pair["data"]


def test_supplemental_counts_not_doubled_or_promoted():
    book = Workbook()
    main = book.active
    main.title = "OfficialPrecinctLevelResults"
    main.append(["County", "Precinct", "Race", "Candidate", "Party", "Votes", "VTD"])
    for i in range(104):
        main.append([f"County{i}", "Test", "United States House of Representatives 2",
                     "Smith, Jane", "Democratic", 1, "000001"])
    supplement = book.create_sheet("SHAWNEE")
    supplement.append(["PRECINCT", "United States Representative 2nd District", None])
    supplement.append([None, "DEM Jane Smith", "Write-in"])
    supplement.append(["COUNTY TOTALS", 4, 50])
    control = [{"district": 2, "candidate": "Jane Smith", "party": "D", "statewide_votes": 108}]

    def parse():
        buffer = BytesIO()
        book.save(buffer)
        return ks.read_workbook(buffer.getvalue(), control=control)

    audit = parse()
    entries = {"KS-2024-official-house-canvass-audit": {"status": "reported", "data": {"audit": audit}}}
    named, write_in = list(ks.exports(entries))
    assert named["workbook_votes"] == 108 and named["difference"] == 0
    assert write_in["workbook_votes"] == 50 and "statewide_votes" not in write_in
    assert not named["scope_complete_for_model"] and not write_in["scope_complete_for_model"]
    main.append(["Shawnee", "Test", "United States House of Representatives 2", "Smith, Jane",
                 "Democratic", 4, "000001"])
    with pytest.raises(ValueError, match="overlaps"):
        parse()
