import json
import hashlib
import zipfile

import pytest

from scripts.current import ROOT, absentee_counts, normalize, reporting_counts, source_specs, update_downloads


def counts(county=False, value=4):
    prefix = "county_name," if county else ""
    place = "WAKE," if county else ""
    return (prefix + "abs_request_type,party_cd,gender,race,ethnicity,0\n"
            + place + f"EARLY VOTING,DEM,FEMALE,WHITE,UNDESIGNATED,{value}\n"
            + place + "EARLY VOTING,REP,FEMALE,WHITE,UNDESIGNATED,6\n").encode()


def reporting(ballots="10", registered="100", published="10.00%", reported="1"):
    row = {"cid": "0", "cnm": "STATE", "tle": "11/03/2026 UNOFFICIAL RESULTS",
           "bct": ballots, "rtl": registered, "bpt": published,
           "prt": reported, "ptl": "2", "imp": "November 3, 2026 9:00 pm"}
    return [row, {**row, "cid": "92", "cnm": "WAKE"}]


def test_current_aggregates_sum_out_party_without_inventing_demographic_rates():
    raw = {"absentee-state.csv": counts(), "absentee-counties.csv": counts(True),
           "reporting.json": json.dumps(reporting()).encode(), "history-catalog.html": b"no archive"}
    snapshot = normalize(raw, [], "snapshot", "2026-11-04T02:00:00Z")
    female = next(row for row in snapshot["demographics"] if row["county"] == "STATEWIDE"
                  and row["request_type"] == "All methods" and row["dimension"] == "sex")
    assert female["ballots"] == 10
    assert female["turnout_pct"] is None
    assert all("party" not in row for row in snapshot["demographics"])
    assert snapshot["audit"]["county_minus_state_ballots_cast"] == 0
    assert snapshot["audit"]["absentee_state_county_cells_match"]


def test_absentee_state_county_disagreement_cannot_be_published():
    raw = {"absentee-state.csv": counts(), "absentee-counties.csv": counts(True, 5),
           "reporting.json": json.dumps(reporting()).encode(), "history-catalog.html": b""}
    with pytest.raises(ValueError, match="State/county absentee cells disagree"):
        normalize(raw, [], "snapshot", "now")


@pytest.mark.parametrize("content", [
    counts(value=-1),
    counts() + counts().split(b"\n")[1] + b"\n",
    counts().replace(b"party_cd", b"voter_name"),
    counts().replace(b"EARLY VOTING", b"UNKNOWN"),
])
def test_changed_schema_negative_counts_and_duplicate_cells_are_rejected(content):
    with pytest.raises(ValueError):
        absentee_counts(content)


def test_zero_unreported_county_is_not_zero_turnout():
    rows, _ = reporting_counts(reporting(ballots="0", published="0.00%", reported="0"))
    assert all(row["ballots_cast"] == 0 for row in rows)
    assert all(row["reported_ballot_fraction_pct"] is None for row in rows)
    assert all("no_ballots_reported_yet" in row["quality"] for row in rows)


def test_inconsistent_percentage_is_preserved_but_not_validated():
    rows, _ = reporting_counts(reporting(published="80.00%"))
    assert rows[0]["source_published_pct"] == 80
    assert rows[0]["reported_ballot_fraction_pct"] is None
    assert "published_percentage_disagrees_with_counts" in rows[0]["quality"]


def test_reporting_requires_same_election_and_reconciled_counties():
    payload = reporting()
    payload[1]["bct"] = "9"
    with pytest.raises(ValueError, match="reconciliation"):
        reporting_counts(payload)
    payload = reporting()
    payload[1]["tle"] = "11/05/2024 RESULTS"
    with pytest.raises(ValueError, match="wrong election"):
        reporting_counts(payload)


def test_observed_zero_demographic_cells_are_retained():
    joint, groups, rows = absentee_counts(counts(value=0).replace(b",6\n", b",0\n"))
    assert rows == 2
    assert sum(joint.values()) == 0
    assert groups[("STATEWIDE", "All methods", "sex", "FEMALE")] == 0


def test_saved_snapshot_preserves_complete_observations_and_original_sources():
    current = ROOT / "public/data/current"
    if not (current / "latest.json").exists():
        pytest.skip("Collect a preliminary snapshot before validating saved downloads")
    latest = json.loads((current / "latest.json").read_text())
    directory = current / latest["snapshot_id"]
    snapshot = json.loads((directory / "snapshot.json").read_text())
    assert snapshot["audit"]["county_count"] == 100
    assert len(snapshot["reporting"]) == 101
    assert all(row["turnout_pct"] is None for row in snapshot["demographics"])
    for file in latest["files"]:
        content = (ROOT / "public/data" / file["path"]).read_bytes()
        assert len(content) == file["bytes"]
        assert hashlib.sha256(content).hexdigest() == file["sha256"]
    with zipfile.ZipFile(directory / "complete-snapshot.zip") as archive:
        for name in ["snapshot.json", "demographics.csv", "reporting.csv"]:
            assert archive.read(name) == (directory / name).read_bytes()
        raw = ROOT / "data/raw/current" / latest["snapshot_id"]
        for source in snapshot["sources"]:
            content = archive.read("sources/" + source["file"])
            assert content == (raw / source["file"]).read_bytes()
            assert hashlib.sha256(content).hexdigest() == source["sha256"]
        assert json.loads(archive.read("sources/manifest.json"))["status"] == "validated"


def test_daily_aggregate_urls_follow_the_official_election_catalog():
    catalog = (
        b"https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2026_11_03/absentee_counts_state_20261104.csv "
        b"https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2026_11_03/absentee_counts_county_20261104.csv "
        b"https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2024_11_05/absentee_counts_state_20241105.csv"
    )
    specs = source_specs(catalog)
    assert specs["absentee-state.csv"].endswith("state_20261104.csv")
    assert specs["absentee-counties.csv"].endswith("county_20261104.csv")
    with pytest.raises(ValueError, match="matching"):
        source_specs(catalog.replace(b"county_20261104", b"county_20261103"))


def test_current_rebundle_keeps_all_observations_without_rebuilding_history(tmp_path):
    data = tmp_path / "public/data"
    data.mkdir(parents=True)
    (data / "analysis.json").write_text('{"national_years":[2024]}')
    (data / "national.csv").write_bytes(b"unchanged historical observations")
    for identifier in ["old", "new"]:
        directory = data / "current" / identifier
        directory.mkdir(parents=True)
        (directory / "demographics.csv").write_text(identifier + " complete demographic rows")
        (directory / "reporting.csv").write_text(identifier + " complete reporting rows")
        (directory / "complete-snapshot.zip").write_bytes(identifier.encode())
    (data / "current/latest.json").write_text('{"snapshot_id":"new"}')
    (data / "incomplete.part").write_text("unfinished")
    update_downloads(tmp_path)
    assert (data / "national.csv").read_bytes() == b"unchanged historical observations"
    assert json.loads((data / "analysis.json").read_text())["current_snapshot"]["snapshot_id"] == "new"
    with zipfile.ZipFile(data / "complete-analysis.zip") as archive:
        names = archive.namelist()
        for identifier in ["old", "new"]:
            assert archive.read(f"current/{identifier}/demographics.csv") == (identifier + " complete demographic rows").encode()
            assert archive.read(f"current/{identifier}/reporting.csv") == (identifier + " complete reporting rows").encode()
        assert "current/new/complete-snapshot.zip" in names
        assert "current/old/complete-snapshot.zip" not in names
        assert not any(name.endswith(".part") for name in names)
    assert (data / "current/old/complete-snapshot.zip").exists()
