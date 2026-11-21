from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from scripts import alaska_cards_history as ak
from scripts.participation_intake.contract import pin

FEED = "AK-2018-general-cards-cast-archive"
DATE, URL, CONTROL_URL = ak.sources(FEED)
CONTROL = ("GEMS ELECTION RESULTS 2018 GENERAL ELECTION November 6, 2018 Official Results 11/26/18 11:20:45 "
           "Registered Voters 4000 - Cards Cast 621 15.53% Num. Report Precinct 442 - Num. Reporting 442 100.00%")


def rows():
    return ([[f"01-{i:03d} Precinct", 0, 1] for i in range(441)]
            + [[f"District {i} - {mode}", 1, 0] for i in range(1, 41) for mode in ak.MODE_NAMES]
            + [[ak.OVERSEAS, 0, 60], [ak.OVERSEAS, 0, 0], ["Total", 120, 501]])


@pytest.mark.parametrize("mutate", [
    lambda table: table.pop(-2),
    lambda table: table[1].__setitem__(0, table[0][0]),
    lambda table: table[441].__setitem__(0, "District 1 - Mail"),
    lambda table: table[-1].__setitem__(1, 121),
])
def test_reject_incomplete_or_ambiguous_unit_frames(mutate):
    table = rows()
    mutate(table)
    with pytest.raises(ValueError):
        ak.reconcile(DATE, table, CONTROL)


def test_collect_control_cache_and_export(monkeypatch):
    report_body = b"synthetic pdf"
    control_body = CONTROL.encode()
    calls = []

    def parse_report(body, election):
        assert body == report_body and election == DATE
        calls.append("parse")
        return rows()

    def capture(feed, url, parser, **kwargs):
        assert (feed, url) == (FEED, URL)
        return {"source": {"url": url, **pin(report_body)}, "status": "reported", "data": parser(report_body)}

    def acquire(url):
        assert url == CONTROL_URL
        return control_body, {}

    collector = SimpleNamespace(prior={}, offline=False, now=datetime(2026, 11, 20, tzinfo=timezone.utc),
                                capture=capture, acquire=acquire)
    monkeypatch.setattr(ak, "parse_report", parse_report)
    entry = ak.collect(collector, FEED)
    collector.prior[FEED] = entry
    assert ak.collect(collector, FEED, reuse_checked_week=True) is entry
    assert ak.collect(collector, FEED) == entry
    assert calls == ["parse"]
    result = list(ak.exports(collector.prior))
    assert len(result) == 564 and result[-1]["cards_cast"] == 621
    assert [row["unit_scope"] for row in result if row["reporting_unit"] == ak.OVERSEAS] == [
        "central_unallocated", "duplicate_zero_overseas_line"]
    bad = deepcopy(entry)
    bad["data"]["native_control"] = CONTROL.replace("621", "620")
    with pytest.raises(ValueError):
        list(ak.exports({FEED: bad}))
