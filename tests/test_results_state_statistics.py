import gzip
import json
import zipfile

import pytest

from scripts import results_intake as intake
from scripts import results_state_statistics as state
from scripts.participation_intake.contract import IntakeError


def document(early="1,043,810", total="2,054,835"):
    return (
        "<h1>" + state.TITLE + "</h1><p>" + state.HEADING + "</p>"
        "<p><strong>Early Voting Turnout:</strong> " + early + " (50.8%)</p>"
        "<p><strong>Absentee Voting</strong>: 44,167 (2.1%)</p>"
        "<p><strong>Election Day Turnout</strong>: 966,858 (47.0%)</p>"
        "<p><strong>Total Voter Turnout</strong>: " + total + "</p>"
        "<p><strong>Turnout of Active Registered Voters</strong>: 59.8%</p>"
    ).encode()


def template():
    return {
        "state_code": "SC", "source_url": state.URL, "county_id": "native:SC:statewide",
        "geography_level": "statewide", "mode": "official",
        "participation_measure_kind": "source_defined_participation_count",
        "cast_ballot_count_qualified": False, "unique_voter_count_qualified": False,
        "maps_approved": False, "denominator": None, "denominator_basis": state.BASIS,
        "ballots": 2054835, "source_sha256": "a" * 64, "source_update_label": None,
        "native_statistics": {"retained_original": True}, "quality": ["old count 2054835"],
    }


def test_changed_counts_and_true_zero_are_parsed_not_looked_up():
    result = state.statistics(document(), "SC")
    assert result["ballots"] == 2054835
    assert result["denominator"] is result["validated_pct"] is result["source_update_label"] is None
    assert result["native_state_statistics"]["fields"]["active_registered_pct"]["literal"] == "59.8%"
    assert result["native_state_statistics"]["percentage_diagnostics"][-1] == {
        "field": "election_day", "native": "47.0%", "count_implied_one_decimal": "47.1%",
        "native_value_repaired": False}
    assert state.statistics(document(early="1,043,811", total="2,054,836"), "SC")["ballots"] == 2054836
    zero = state.statistics(document(early="0", total="1,011,025"), "SC")
    assert zero["native_state_statistics"]["fields"]["early"]["value"] == 0


@pytest.mark.parametrize("old,new", [
    ("2026", "2024"),
    ("Statewide General Election", "Statewide Primary Election"),
    ("2,054,835", "2,054,834"),
    ("44,167", ""),
    ("44,167", "44,16"),
    ("47.0%", "101.0%"),
    ("<p><strong>Total Voter Turnout</strong>: 2,054,835</p>", ""),
    ("</p><p><strong>Turnout of Active", "</p><p>Total Voter Turnout: 2,054,835</p><p><strong>Turnout of Active"),
])
def test_wrong_scope_missing_counts_and_conflicting_columns_fail_closed(old, new):
    with pytest.raises(ValueError):
        state.statistics(document().decode().replace(old, new).encode(), "SC")


def test_refresh_replaces_stale_native_vectors_preserves_holds_and_repeats():
    before = template()
    data = state.statistics(document(early="1,043,811", total="2,054,836"), "SC")
    provenance = {"url": state.URL, "sha256": "b" * 64}
    row = state.refresh(before, data, provenance)
    assert before == template()
    assert row["ballots"] == row["native_statistics"]["fields"]["total"]["value"] == 2054836
    assert row["native_statistics"] == data["native_state_statistics"]
    assert row["accepted_source_provenance"]["native_statistics"] == {"retained_original": True}
    assert row["denominator"] is row["reported_pct"] is row["source_update_label"] is None
    assert row["maps_approved"] is row["unique_voter_count_qualified"] is False
    assert state.refresh(row, data, provenance) == row
    data["native_state_statistics"]["fields"]["early"]["value"] += 1
    with pytest.raises(ValueError, match="native values"):
        state.refresh(before, data, provenance)


def test_state_only_qualifications_cannot_be_promoted_or_relabelled():
    data = state.statistics(document(), "SC")
    for key, value in (("geography_level", "county"), ("maps_approved", True),
                       ("cast_ballot_count_qualified", True), ("denominator", 3470220)):
        row = template()
        row[key] = value
        with pytest.raises(ValueError, match="qualification"):
            state.refresh(row, data, {"url": state.URL, "sha256": "b" * 64})


def test_default_collector_and_actual_source_package_include_state_parser(tmp_path, monkeypatch):
    from test_results_intake import NOW, fixture

    registry = fixture(tmp_path)
    calls = []

    def acquire(self, url):
        self.guard(url)
        calls.append(url)
        if url == state.URL:
            return document(), {"origin": "retained-fixture"}
        raise IntakeError("source_unavailable", "Unrelated fixture source")

    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    intake.collect(registry, tmp_path / "work", now=NOW)
    assert calls.count(state.URL) == 1
    with zipfile.ZipFile(tmp_path / "work/complete-results.zip") as archive:
        assert archive.read("code/scripts/results_state_statistics.py") == (
            intake.ROOT / "scripts/results_state_statistics.py").read_bytes()
        assert "code/tests/test_results_state_statistics.py" in archive.namelist()
        report = json.loads(gzip.decompress(archive.read("queries/snapshot.json.gz")))
        decision = next(row for row in report["jurisdictions"] if row["state_code"] == "SC")
        assert decision["statewide_administrative_status"] == "reported"
        assert decision["statewide_administrative_observation"]["ballots"] == 2054835
        assert len(report["jurisdictions"]) == 51
