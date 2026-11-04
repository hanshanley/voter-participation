import csv
import hashlib
import io
import json
import zipfile
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from scripts.nationwide import (
    ROOT, NoData, parse_demographics, parse_mode, parse_official, refresh,
)


def mode(state="GA", category="inperson", total=10):
    return {"state": state, "category": category, "snapshot_date": "2026-11-03",
            "regions": {"Example": {"DEM": {"votes": 4}, "REP": {"votes": total - 4}}},
            "statewide_total": {"DEM": {"votes": 4}, "REP": {"votes": total - 4}}}


def groups(state="GA", category="inperson", dimension="race", total=10):
    return {"state": state, "category": category, "snapshot_date": "2026-11-03",
            "region": None, "breakdown_by": dimension, "values": {"Group A": 4, "Group B": total - 4},
            "total": total}


def test_mode_sums_party_and_keeps_source_region_counts_without_inventing_precincts():
    result = parse_mode(mode(), "GA", "inperson", date(2026, 11, 4))
    assert result["total"] == 10
    assert result["regions"] == [{"name": "Example", "ballots": 10}]
    assert result["quality"] == []
    assert "DEM" not in json.dumps(result)
    payload = mode()
    payload["regions"]["Example"]["DEM"]["votes"] = 3
    assert parse_mode(payload, "GA", "inperson", date(2026, 11, 4))["quality"] == [
        "region_state_totals_disagree"]
    statewide_only = parse_mode({**mode(), "regions": {}}, "GA", "inperson", date(2026, 11, 4))
    assert statewide_only["total"] == 10
    assert statewide_only["quality"] == ["source_regions_not_reported"]


@pytest.mark.parametrize("change", [
    {"state": "TX"}, {"category": "requested"}, {"snapshot_date": "2024-11-05"},
    {"snapshot_date": "2026-11-05"}, {"statewide_total": {"Other": {"votes": -1}}},
])
def test_wrong_state_election_mode_future_dates_and_negative_counts_are_rejected(change):
    with pytest.raises(ValueError):
        parse_mode({**mode(), **change}, "GA", "inperson", date(2026, 11, 4))


def test_demographic_total_reconciliation_and_undated_zero_responses():
    with pytest.raises(ValueError, match="reconcile"):
        parse_demographics({**groups(), "total": 11}, "GA", "inperson", "race", date(2026, 11, 4))
    with pytest.raises(NoData):
        parse_demographics({**groups(), "snapshot_date": None}, "GA", "inperson", "race", date(2026, 11, 4))


AL = b"""<h1>2026 GENERAL ELECTION</h1>
Total Ballots Cast: 10 Total Registered Voters: 100 Voter Turnout: 10.00%
Counties Reported: 1 of 2 Last Updated: 11/04/2026 12:07:22 AM
GOVERNOR candidate one 7 candidate two 2"""
OR = b"""<input id="hidElectionDate" value="11/3/2026" />
Statewide Voter Turnout (details) <span>10</span><span>.00%</span>
Ballots Counted 10 Active Registered Voters 100
Results last updated: 11/4/2026 | 6:30 AM PT"""
ND = b"""Tuesday, November 3, 2026 - 11:30pm
39.8 percent of eligible North Dakota voters cast 239,057 ballots during the 2026 General Election.
135,098 votes cast on election day, 50,493 ballots by early vote, and 53,466 absentee/vote-by-mail ballots."""


def test_official_ballots_are_not_candidate_totals_and_denominators_stay_distinct():
    al, oregon, nd = (parse_official(body, state) for body, state in [(AL, "AL"), (OR, "OR"), (ND, "ND")])
    assert al["ballots"] == 10
    assert al["validated_pct"] == oregon["validated_pct"] == 10
    assert al["denominator_basis"] != oregon["denominator_basis"]
    assert nd["ballots"] == 239057
    assert nd["denominator"] is None
    assert nd["validated_pct"] is None
    assert nd["published_pct"] == 39.8
    assert nd["denominator_basis"] == "eligible_voters_source_estimate"
    with pytest.raises(ValueError, match="components"):
        parse_official(ND.replace(b"53,466", b"53,467"), "ND")
    with pytest.raises(ValueError, match="administrative"):
        parse_official(OR.replace(b"11/3/2026", b"11/5/2024"), "OR")
    assert parse_official(AL.replace(b"10.00%", b"90.00%"), "AL")["validated_pct"] is None


def fake_fetch(failed_ga=False, co_total=10):
    def fetch(url, **kwargs):
        body, status = {"error": "not reported"}, 404
        if "/early-vote/" in url:
            parts = url.split("/early-vote/")[1].split("/")
            state, category = parts[:2]
            if state in {"GA", "CO"}:
                status = 200
                if category == "capabilities":
                    body = {"state": state, "categories": {"inperson": {"race": True, "age": False}}}
                elif len(parts) == 2:
                    body = mode(state=state, total=co_total if state == "CO" else 10)
                    if failed_ga and state == "GA":
                        body["state"] = "TX"
                else:
                    body = groups(state=state, total=co_total if state == "CO" else 10)
        if "alabamavotes" in url:
            return SimpleNamespace(status_code=200, content=AL, headers={})
        return SimpleNamespace(status_code=status, content=json.dumps(body).encode(), headers={})
    return fetch


def test_all_jurisdictions_complete_downloads_and_independent_source_failure(tmp_path):
    first = refresh(root=tmp_path, fetch=fake_fetch(), now=datetime(2026, 11, 4, 2, tzinfo=timezone.utc))
    assert first["audit"]["jurisdictions_assessed"] == 51
    assert first["audit"]["jurisdictions_with_data"] == 3
    assert first["audit"]["jurisdictions_with_demographic_counts"] == 2
    assert len({row["state_code"] for row in first["coverage"]}) == 51
    assert all(row["turnout_pct"] is None for row in first["demographics"])
    assert all(row["mode"] != "requested" for row in first["early_voting"])
    second = refresh(root=tmp_path, fetch=fake_fetch(failed_ga=True, co_total=20),
                     now=datetime(2026, 11, 4, 3, tzinfo=timezone.utc))
    retained = second["datasets"]["GA-inperson"]
    assert retained["status"] == "retained_after_failure"
    assert retained["source"]["snapshot_id"] == first["snapshot_id"]
    assert second["datasets"]["CO-inperson"]["data"]["total"] == 20
    public = tmp_path / "public/data/nationwide" / second["snapshot_id"]
    with zipfile.ZipFile(public / "complete-snapshot.zip") as archive:
        assert json.loads(archive.read("snapshot.json")) == second
        rows = list(csv.DictReader(io.StringIO(archive.read("early_voting.csv").decode())))
        assert len(rows) == len(second["early_voting"])
        for entry in second["datasets"].values():
            if entry.get("data") is not None:
                source = entry["source"]
                raw = archive.read(f'sources/{source["snapshot_id"]}/{source["file"]}')
                assert hashlib.sha256(raw).hexdigest() == source["sha256"]
        rejected = f'sources/{second["snapshot_id"]}/GA-inperson.json'
        assert json.loads(archive.read(rejected))["state"] == "TX"
    latest = json.loads((public.parent / "latest.json").read_text())
    for file in latest["files"]:
        content = (tmp_path / "public/data" / file["path"]).read_bytes()
        assert len(content) == file["bytes"]
        assert hashlib.sha256(content).hexdigest() == file["sha256"]


def test_failed_initial_collection_preserves_evidence_without_promoting_empty_data(tmp_path):
    def unavailable(url, **kwargs):
        return SimpleNamespace(status_code=503, content=b"temporarily unavailable", headers={})
    with pytest.raises(ValueError, match="No valid"):
        refresh(root=tmp_path, fetch=unavailable, now=datetime(2026, 11, 4, tzinfo=timezone.utc))
    assert not (tmp_path / "public/data/nationwide/latest.json").exists()
    manifest = json.loads((tmp_path / "data/raw/nationwide/20261104T000000Z/manifest.json").read_text())
    assert manifest["status"] == "rejected"
    assert len(manifest["sources"]) == 55


def test_saved_nationwide_snapshot_has_all_sources_and_no_demographic_rates():
    public = ROOT / "public/data/nationwide"
    if not (public / "latest.json").exists():
        pytest.skip("Collect nationwide observations before validating saved downloads")
    pointer = json.loads((public / "latest.json").read_text())
    output = public / pointer["snapshot_id"]
    snapshot = json.loads((output / "snapshot.json").read_text())
    assert snapshot["audit"]["jurisdictions_assessed"] == 51
    assert all(row["turnout_pct"] is None for row in snapshot["demographics"])
    with zipfile.ZipFile(output / "complete-snapshot.zip") as archive:
        for field in ["early_voting", "demographics", "reporting", "coverage"]:
            if snapshot[field]:
                rows = list(csv.DictReader(io.StringIO(archive.read(field + ".csv").decode())))
                assert len(rows) == len(snapshot[field])
        for source in snapshot["sources"]:
            content = archive.read(f'sources/{source["snapshot_id"]}/{source["file"]}')
            assert hashlib.sha256(content).hexdigest() == source["sha256"]
