import pytest

from scripts import new_mexico_turnout_history as nm
from scripts.participation_intake.contract import pin
from scripts.results_intake import Collector, late_archive_sources


FEED = "NM-2022-general-native-turnout-archive"


@pytest.fixture
def page(monkeypatch):
    monkeypatch.setitem(nm.ELECTIONS, 2022, ("2838", "November 8, 2022", 33))
    sections = []
    for i in range(33):
        ballots, eligible = ((0, -3) if i == 0 else (25, 22) if i == 1 else (1, 10))
        sections.append(f'''<div class="col turnout-results-box-a"><h1>County {i}</h1>
          <input countyid="{i:02}"><div class="county-precinct">PCT 01</div>
          <div class="county-cast"><span>{ballots}</span></div>
          <div class="county-counted"><span>{eligible}</span></div>''')
    return ('''<form><a href="Default.aspx?eid=2838"><h1>Official Results</h1><h2>2022 General<br />November 8, 2022</h2></a>
        <span>Results last updated:</span><span>11/29/2022 4:39 PM MT</span>
        <span class="header-ballot-number">56</span><br /><span class="header-voter-text">Eligible Voters</span><span class="header-voter-number">329</span>
        <span class="header-partial-number">0</span><span class="header-total-number">33</span><span class="header-totalprecincts-text">33</span>
        ''' + "".join(sections) + "</form>").encode()


def test_native_invalid_denominators_are_preserved_but_rates_are_held(page):
    data = nm.parse(page, FEED)
    rows = list(nm.exports({FEED: {"data": data, "source": {"url": nm.URLS[FEED], **pin(page)},
                                  "status": "reported"}}))
    assert len(rows) == 67 and rows[0]["source_eligible_rate_pct"] == pytest.approx(100 * 56 / 329)
    assert rows[2]["source_eligible_voters"] == -3 and rows[2]["rate_hold"] == "negative_source_denominator"
    assert rows[4]["source_reported_count"] == 25 and rows[4]["rate_hold"] == "count_exceeds_source_denominator"
    assert all(row["source_eligible_rate_pct"] is None for row in rows[1:5])
    assert rows[6]["source_eligible_rate_pct"] == 10
    with pytest.raises(ValueError, match="statewide controls"):
        nm.parse(page.replace(b"<span>-3</span>", b"<span>0</span>"), FEED)


def test_revision_noop_weekly_and_last_good(page, tmp_path, monkeypatch):
    from datetime import datetime, timezone

    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    collector = Collector(tmp_path, {}, {"urls": [], "hosts": [], "prefixes": []}, now)
    monkeypatch.setattr(collector, "acquire", lambda _: (page, {"origin": "fixture"}))
    before = nm.collect(collector, FEED)
    assert before["status"] == "reported" and FEED in late_archive_sources()
    collector.prior[FEED] = before
    monkeypatch.setattr(collector, "acquire", lambda _: pytest.fail("Weekly reuse should not fetch"))
    assert nm.collect(collector, FEED, reuse_checked_week=True) == before
    monkeypatch.setattr(collector, "acquire", lambda _: (page + b"\n", {"origin": "fixture"}))
    assert nm.collect(collector, FEED)["source"] == before["source"]
    monkeypatch.setattr(collector, "acquire", lambda _: (page.replace(b"Official Results", b"Unofficial Results"), {"origin": "fixture"}))
    after = nm.collect(collector, FEED)
    assert after["status"] == "retained_after_failure" and after["data"] == before["data"]


@pytest.mark.parametrize("delta", [-1, 1])
def test_newer_matching_revision_can_move_counts_either_direction(page, tmp_path, monkeypatch, delta):
    from datetime import datetime, timezone

    collector = Collector(tmp_path, {}, {"urls": [], "hosts": [], "prefixes": []},
                          datetime(2026, 11, 22, tzinfo=timezone.utc))
    monkeypatch.setattr(collector, "acquire", lambda _: (page, {"origin": "fixture"}))
    previous = nm.collect(collector, FEED)
    collector.prior[FEED] = previous
    revision = (page.replace(b"11/29/2022 4:39", b"11/30/2022 4:39")
                .replace(b'<span class="header-ballot-number">56', f'<span class="header-ballot-number">{56 + delta}'.encode())
                .replace(b'<span>1</span></div>', f'<span>{1 + delta}</span></div>'.encode(), 1))
    monkeypatch.setattr(collector, "acquire", lambda _: (revision, {"origin": "fixture"}))
    accepted = nm.collect(collector, FEED)
    assert accepted["status"] == "reported" and accepted["data"]["state"] == [56 + delta, 329]
    collector.prior[FEED] = accepted
    monkeypatch.setattr(collector, "acquire", lambda _: (page, {"origin": "fixture"}))
    retained = nm.collect(collector, FEED)
    assert retained["status"] == "retained_after_failure" and retained["data"] == accepted["data"]
