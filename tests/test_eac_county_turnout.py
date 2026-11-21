import csv
import gzip
import io

import pytest

from scripts.eac_county_turnout import CONTRACT, SOURCES, exports, locality_rows, reconcile
from scripts.participation_intake.contract import encoded


def county(fips="01001", turnout="10", highest="0"):
    return [2, "AL", "Autauga County", fips, "2024", "20", turnout, highest]


def jurisdiction(fips="0100100000", turnout="10", highest="0"):
    return [2, fips, "AL", "AUTAUGA", "2024", "20", turnout, highest]


def test_direct_scope_keeps_zero_and_rejects_county_mismatch_or_candidate_proxy():
    good, = reconcile([county(turnout="0")], [jurisdiction(turnout="0")])
    assert good["direct_reported_turnout"] == good["same_report_registration_fraction_pct"] == 0
    for direct, native, reason in (
        (county(turnout="-99"), [jurisdiction()], "county_turnout_missing_or_noninteger"),
        (county(turnout="9.5"), [jurisdiction()], "county_turnout_missing_or_noninteger"),
        (county(), [jurisdiction(turnout="11")], "direct_and_county_turnout_disagree"),
        (county(), [jurisdiction(highest="1")], "highest_office_source_reported"),
        (county(), [jurisdiction(), jurisdiction("0100100001")], "no_unambiguous_direct_county_report"),
        (county(fips="01000"), [], "not_a_county_scope"),
    ):
        held, = reconcile([direct], native)
        assert held["decision"] == reason
        assert held["direct_reported_turnout"] is held["same_report_registration_fraction_pct"] is None


def test_full_download_preserves_source_fields_and_is_platform_stable(monkeypatch):
    packet = {"contract": CONTRACT, "county": [county(highest="-66")], "jurisdiction": [jurisdiction()],
              "sources": {name: {"url": url} for name, url in SOURCES.items()}}
    data = gzip.compress(encoded(packet), mtime=0)
    files, descriptor = exports(data)
    path = "participation/eac-county-year-decisions.csv.gz"
    row, = csv.DictReader(io.StringIO(gzip.decompress(files[path]).decode()))
    assert row["county_fips"] == "01001" and row["county_highest_office_flag"] == "-66"
    assert row["direct_reported_turnout"] == "10" and row["same_report_registration_fraction_pct"] == ""
    assert descriptor["direct_count_rows"] == 1 and descriptor["same_report_registration_fraction_rows"] == 0
    compress = gzip.compress

    def alternate_platform(*args, **kwargs):
        body = compress(*args, **kwargs)
        return body[:9] + bytes([19 if body[9] != 19 else 3]) + body[10:]

    monkeypatch.setattr(gzip, "compress", alternate_platform)
    assert (files, descriptor) == exports(data)


def test_local_history_keeps_real_zero_and_withholds_proxy_and_county_only_data():
    local = [
        [2, "2302100100", "ME", "ABBOT", "2024", "20", "0", "0", "0", "1", "0", "0"],
        [3, "2303100275", "ME", "ACTON", "2024", "20", "12", "1", "0", "1", "0", "0"],
        [4, None, "ME", "YORK COUNTY", "2006", "300", "180", "0", "0", "1", "0", "0"],
        [5, "2303100275", "ME", "ACTON", "2022", "0", "12", "0", "0", "1", "0", "0"],
        [6, "2303100275", "ME", "ACTON", "2020", "20", "12", "0", "1", "0", "0", "0"],
    ]
    packet = {"localities": local, "jurisdiction": [r[:8] for r in local],
              "sources": {"jurisdiction": {"url": SOURCES["jurisdiction"], "sha256": "a" * 64}}}
    rows = locality_rows(packet)
    assert [r["reported_counted_ballot_participants"] for r in rows] == [0, None, None, 12, None]
    assert [r["same_report_registration_fraction_pct"] for r in rows] == [0, None, None, None, None]
    assert all(not r["geographic_match_claimed"] for r in rows)
    assert rows[1]["count_hold"] == "highest_office_source_reported"
    assert rows[2]["count_hold"] == "no_county_subdivision_identifier"
    assert rows[4]["count_hold"] == "ballot_count_source_not_confirmed"
    local[0][6] = "1"
    with pytest.raises(ValueError, match="differ from reviewed"):
        locality_rows(packet)
