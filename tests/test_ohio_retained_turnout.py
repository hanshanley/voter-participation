from pathlib import Path

import pytest

from scripts import results_turnout_history as history, statewide_ballot_totals as totals


def test_ohio_retained_facts_require_the_exact_stopped_route():
    root = Path(__file__).resolve().parents[1]
    evidence_path = root / totals.OH_INPUT
    if not evidence_path.is_file():
        evidence_path = root.parent / "inputs/oh-retained-original.json"
    evidence = evidence_path.read_bytes()
    stopped = {"status": "source_stopped", "error_stage": "acquisition", "source": None, "data": None,
               "attempted_source_url": history.OH_ELECTION}

    def summary(entry, body=evidence):
        return totals.ohio_summary({"granular_sources": {history.OH_FEED: entry}}, body)

    prior, retained = summary(stopped)
    row = totals.observation("OH", prior, retained)
    assert row["count"]["value"] == 4_658_250 and row["denominator"]["value"] == 8_018_054
    assert row["view"]["status"] == "retained_after_failure"
    assert row["reporting_status"]["complete"] is None
    assert row["source_clock"] == {"literal": None, "timezone": None}
    for changed in ({"attempted_source_url": history.OH_BALLOTS}, {"status": "source_unavailable"},
                    {"error_stage": "validation"}, {"data": {}}):
        assert summary({**stopped, **changed}) == (None, False)
    with pytest.raises(ValueError, match="retained aggregate evidence"):
        summary(stopped, evidence + b"\n")
    accepted = {"status": "reported", "source": prior["source"],
                "data": {"report": prior["source"], "complete_native_query": prior["query"]}}
    assert summary(accepted, b"not consulted") == (prior, False)
