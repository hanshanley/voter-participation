import csv
import gzip
import io

from scripts.eac_county_turnout import CONTRACT, SOURCES, exports, reconcile
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


def test_full_download_preserves_source_fields_when_rate_flag_is_unavailable():
    packet = {"contract": CONTRACT, "county": [county(highest="-66")], "jurisdiction": [jurisdiction()],
              "sources": {name: {"url": url} for name, url in SOURCES.items()}}
    data = gzip.compress(encoded(packet), mtime=0)
    files, descriptor = exports(data)
    path = "participation/eac-county-year-decisions.csv.gz"
    row, = csv.DictReader(io.StringIO(gzip.decompress(files[path]).decode()))
    assert row["county_fips"] == "01001" and row["county_highest_office_flag"] == "-66"
    assert row["direct_reported_turnout"] == "10" and row["same_report_registration_fraction_pct"] == ""
    assert descriptor["direct_count_rows"] == 1 and descriptor["same_report_registration_fraction_rows"] == 0
    assert files == exports(data)[0]
