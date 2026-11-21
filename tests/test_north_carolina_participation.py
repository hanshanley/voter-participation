from datetime import datetime, timezone
from copy import deepcopy
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from scripts import north_carolina_participation as nc, results_intake as intake


def archive(member, text):
    buffer = BytesIO()
    with ZipFile(buffer, "w") as zipped:
        zipped.writestr(member, text)
    return buffer.getvalue()


@pytest.mark.parametrize("year,day,kind,header,delimiter,updated", [
    (2002, 5, "history", False, "\t", "2003-01-21 07:52:21.000"),
    (2004, 2, "history", True, ",", "06/06/2008"),
    (2006, 7, "voter", True, "\t", "2007-02-13 09:32:44.540000000"),
])
def test_legacy_frames_validate_dates_and_keep_distinct_native_precinct_spellings(
        monkeypatch, year, day, kind, header, delimiter, updated):
    election = nc.FEEDS[f"NC-{year}-general-participation-statistics"]
    counties = [f"COUNTY{i:03}" for i in range(100)]
    monkeypatch.setattr(nc, "COUNTY_PIN", nc.digest(("\n".join(counties) + "\n").encode()))
    fields = ("county_desc precinct_abbrv age party_cd race_code ethnic_code sex_code "
              "total_voters election_date stats_type update_date").split()
    trailer = {"history": ["IN-PERSON", "DEM"], "voter": []}[kind]
    if kind == "history":
        fields += ["voting_method", "voting_meth_desc", "voted_party_desc"] if year == 2004 else [
            "voting_method", "voted_party_cd"]
        if year == 2004:
            trailer = ["E", "IN-PERSON", "DEM"]

    def row(county, precinct):
        return [county, precinct, "Age 26 - 40", "DEM", "W  ", "NL ", "F", "3",
                f"11/{day:02}/{year}", kind.title(), updated, *trailer]

    lines = ([fields] if header else []) + [row(name, "A") for name in counties] + [row(counties[0], "A ")]
    member = f"{kind}_stats_{year}11{day:02}.txt"

    def parse():
        return nc.extract(archive(member, "\n".join(
            delimiter.join(f'"{cell}"' if delimiter == "," else cell for cell in line)
            for line in lines)), kind, election)

    facts = parse()
    assert facts["counties"][counties[0]] == 6
    assert facts["groups"]["race"] == {"W": 303}
    assert facts["units"][:2] == [[counties[0], "A", 3, []], [counties[0], "A ", 3, []]]
    assert facts["edition"] == ("2008-06-06" if year == 2004 else updated[:10])
    assert facts.get("native_edition_timestamp") == (None if year == 2004 else updated)
    lines[-1][8] = f"11/{day + 1:02}/{year}"
    with pytest.raises(ValueError, match="election, category or count"):
        parse()


def test_linked_2000_notice_is_not_empty_election_data():
    election = nc.FEEDS["NC-2000-general-participation-statistics"]
    with pytest.raises(nc.IntakeError, match="no participation statistics") as error:
        nc.extract(archive("Readme.txt", "Data Unavailable"), "history", election)
    assert error.value.code == "report_data_unavailable"


def test_published_age_control_rejects_a_one_credit_difference_and_wrong_denominator():
    assert nc.reviewed_age_rate(629299, 1841623, [629298, 342]) == (None, "published_history_count_differs")
    assert nc.reviewed_age_rate(233441, 900000, [233441, 241]) == (None, "published_age_rate_differs")
    assert nc.reviewed_age_rate(233441, 968290, [233441, 241]) == (23344100 / 968290, None)
    assert nc.reviewed_age_rate(2796509, 4820870, [2796509, 58, 0]) == (279650900 / 4820870, None)
    assert nc.reviewed_age_rate(45352, 116174, [45352, 391, 1]) == (None, "published_age_rate_differs")


def test_paired_bulk_capture_accepts_both_revision_directions_and_retains_on_failure(tmp_path):
    feed = "NC-2016-general-participation-statistics"
    election = nc.FEEDS[feed]
    endpoints = {kind: nc.report_url(kind, election) for kind in nc.CATALOGS}
    bodies = {catalog: f'<a href="{endpoints[kind]}">Election archive</a>'.encode()
              for kind, catalog in nc.CATALOGS.items()} | {
                  endpoints["history"]: b"100", endpoints["voter"]: b"150"}

    def acquire(_, spec, *, access_guard):
        body = bodies[spec["url"]]
        return body, {"origin": "fixture", **intake.pin(body)}

    def extract(body, kind, day):
        return {"edition": "2016-12-28", "count": int(body)}

    with patch.object(intake.Store, "acquire", acquire), patch.object(nc, "extract", extract):
        def capture(prior=None):
            collector = intake.Collector(tmp_path, {feed: prior} if prior else {},
                                         {"urls": [], "prefixes": [], "hosts": []},
                                         datetime(2026, 11, 21, tzinfo=timezone.utc))
            return nc.collect(collector, feed)

        first = capture()
        assert first["status"] == "reported"
        assert capture(first) == first
        bodies[endpoints["history"]] = b"103"
        up = capture(first)
        assert up["data"]["pair"]["history"]["facts"]["count"] == 103
        bodies[endpoints["history"]] = b"97"
        down = capture(up)
        assert down["data"]["pair"]["history"]["facts"]["count"] == 97
        old = deepcopy(down)
        bodies[nc.CATALOGS["voter"]] = b"<html>No archive link</html>"
        retained = capture(down)
        assert retained["status"] == "retained_after_failure"
        assert retained["error"] == "report_not_linked"
        assert retained["data"] == old["data"]
