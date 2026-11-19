import copy
import json
from pathlib import Path

import pytest

from scripts import results_county_frame as county, statewide_ballot_totals as totals


def test_retained_georgia_uses_exact_stop_and_yields_to_fresh_report():
    root = Path(__file__).resolve().parents[1]
    original = root / totals.GA_INPUT
    body = (original if original.is_file() else root.parent / "inputs/ga-retained-original.json").read_bytes()
    h = totals.history
    entry = {"status": "source_stopped", "error_stage": "acquisition",
             "attempted_source_url": h.GA_URL, "source": None, "data": None}
    snapshot = {"granular_sources": {h.GA_FEED: entry}}

    def summary(retained=body):
        return totals.retained_archive_summary(snapshot, "GA", retained, h.GA_URL, totals.GA_RETAINED_SHA256)

    assert summary(None) == (None, False)
    report, retained = summary()
    row = totals.georgia_observation(report, retained)
    assert retained and row["view"]["status"] == "retained_after_failure"
    assert (row["count"]["value"], row["denominator"]["value"]) == (4_218_112, 7_535_442)
    assert len(report["query"]["counties"]) == 159
    assert row["source_clock"] == {"literal": None, "timezone": None}
    with pytest.raises(ValueError, match="Georgia retained aggregate evidence"):
        summary(body + b"\n")
    for changed in ({"attempted_source_url": h.GA_URL + "/other"},
                    {"error_stage": "schema"},
                    {"status": "unavailable"},
                    {"data": {}}):
        snapshot["granular_sources"][h.GA_FEED] = {**entry, **changed}
        assert summary() == (None, False)

    live = copy.deepcopy(json.loads(body))
    live["source"]["sha256"] = live["index"]["sha256"] = "a" * 64
    live["query"]["published"] = "2026-11-19T15:00:00Z"
    live["query"]["counties"][0]["ballots"] -= 1
    snapshot["granular_sources"][h.GA_FEED] = {"status": "reported", "source": live["index"],
        "data": {"report": live["source"], "complete_native_query": live["query"]}}
    report, retained = summary()
    assert not retained and report == live
    assert totals.georgia_observation(report, retained)["count"]["value"] == 4_218_111


@pytest.mark.parametrize(("profile", "validate", "expected"), [
    (county.SUMMIT, county.county_pdf.summit_controls, (20_223, 29_388)),
    (county.SUSSEX, county.county_pdf.sussex_controls, (57_818, 112_512)),
    (county.DOUGLAS, county.county_pdf.douglas_controls, (19_423, 26_599)),
])
def test_retained_county_canvass_requires_an_exact_acquisition_stop(profile, validate, expected):
    root = Path(__file__).resolve().parents[1]
    original = root / county.RETAINED_CANVASSES_INPUT
    body = (original if original.is_file() else root.parent / "inputs/retained-county-canvasses.json").read_bytes()
    stopped = {"status": "source_stopped", "error_stage": "acquisition",
               "attempted_source_url": profile[6], "source": None, "data": None}
    data = county.retained_county_canvass(stopped, profile, body)
    assert validate(data)[1:3] == expected
    with pytest.raises(ValueError, match="Retained county canvass evidence differs"):
        county.retained_county_canvass(stopped, profile, body + b"\n")
    for changed in ({"attempted_source_url": data["report"]["url"]},
                    {"status": "reported"}, {"status": "retained_after_failure"},
                    {"error_stage": "parse"}, {"source": data["report"]}, {"data": data}):
        assert county.retained_county_canvass({**stopped, **changed}, profile, body) is None
