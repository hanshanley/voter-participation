import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from scripts import results_granular as granular, results_native as native
from scripts import results_pdf_dunn as dunn
from scripts.participation_intake.contract import digest, encoded, pin


FIXTURE = Path(__file__).with_name("fixtures") / "dunn-accepted.json"


def accepted():
    return json.loads(FIXTURE.read_text())


def pages(count="19,896", registered="27,173", registered_pct="73%",
          eligible="37,812", eligible_pct="53%"):
    return [
        "\n".join(
            (
                "Precinct Reporting Units",
                f"Total Votes Cast = {count} 6 10561 9188",
                f"Total Registered Voters {registered} {registered_pct} Page 1 of 1",
                f"Eligilbe Voters {eligible} {eligible_pct}",
                "DUNN COUNTY, WI UNOFFICIAL RESULTS - November 3, 2026 General Election",
            )
        ),
        "Contest Total 19,790\nReferendum Questions",
    ]


def metadata():
    return {
        "/Title": "Dunn County Unofficial Results 11.03.2026.xlsx",
        "/CreationDate": "D:20261103230017-06'00'",
        "/ModDate": "D:20261103230017-06'00'",
    }


def parsed(row=None, values=None, body=b"synthetic-dunn-pdf"):
    return dunn.parse_pages(
        values or pages(),
        metadata(),
        [row or accepted()],
        {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()},
    )


def baseline(row=None):
    row = copy.deepcopy(row or accepted())
    shard = {"records": [row], "views": {"official": {"counties": [row["id"]]}}}
    body = gzip.compress(encoded(shard), compresslevel=6, mtime=0)
    declaration = {"file": "states/WI.json.gz", **pin(body)}
    return {
        "index.json": encoded({"states": {"WI": declaration}}),
        "states/WI.json.gz": body,
    }


class LocalCollector:
    def __init__(self, body=b"synthetic-dunn-pdf", stop=False):
        self.body = body
        self.stop = stop

    def capture(self, identity, url, parse):
        source = {"url": url, **pin(self.body)}
        if self.stop:
            return {
                "status": "stopped",
                "data": None,
                "error": {"code": "source_stopped", "message": "retained stop"},
                "source": source,
            }
        return {
            "status": "reported",
            "data": parse(self.body),
            "error": None,
            "source": source,
        }


def install_synthetic_parser(monkeypatch, values=None):
    def statistics(body, templates):
        return dunn.parse_pages(
            values or pages(), metadata(), templates,
            {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()},
        )
    monkeypatch.setattr(native, "dunn_statistics", statistics)


def test_fixture_pins_the_complete_accepted_prior_observation():
    row = accepted()
    assert digest(encoded(row)) == dunn.ACCEPTED_ROW_SHA256
    assert digest(encoded(row["view"])) == "25e411e3bea5800bcdd8e2223b6f1f5fb0e159e2e16aff44ff4e81fce94575bd"
    assert dunn.source_url(row) == dunn.URL


def test_source_plan_bridges_only_dunn_and_selects_reviewed_adapter():
    plan = native.source_plan(baseline())
    assert list(plan) == ["WI"]
    assert list(plan["WI"]) == ["WI-registered-4758ec49971e986f"]
    source = plan["WI"]["WI-registered-4758ec49971e986f"]
    assert source["url"] == dunn.URL
    assert source["adapter"] == "reviewed_dunn_unofficial_pdf"
    assert [row["id"] for row in source["templates"]] == [dunn.OBSERVATION_ID]


@pytest.mark.parametrize(
    "values, expected",
    [
        (pages("20,101", "27,300", "74%", "38,000", "53%"), (20101, 27300, 38000)),
        (pages("0", "27,300", "0%", "38,000", "0%"), (0, 27300, 38000)),
    ],
)
def test_parser_changes_direct_native_numeric_bodies_and_accepts_true_zero(values, expected):
    result = parsed(values=values)
    update = result["updates"][0]
    assert (update["value"], update["registered"],
            update["replacement"]["source"]["fields"]["eligible_voters"]) == expected
    assert update["replacement"]["denominator"] is None
    assert update["replacement"]["source_clock"] == {"literal": None, "timezone": None}
    assert update["replacement"]["reporting_status"]["literal"] == "UNOFFICIAL RESULTS"
    assert update["rate_compatible"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row.update(id="other-observation"),
        lambda row: row["source"].update(id="other-source"),
        lambda row: row["source"].update(input_sha256="b" * 64),
        lambda row: row["source"].update(url=dunn.URL),
        lambda row: row["view"].update(source_url=dunn.URL),
        lambda row: row["reporting_status"].update(literal="OFFICIAL RESULTS"),
        lambda row: row["measure"].update(literal="Candidate votes"),
        lambda row: row["source_clock"].update(literal="11/03/2026 11:00 PM"),
        lambda row: row.update(denominator={
            "value": 27173, "literal": "Registered voters",
            "basis": "registered", "qualified": True,
        }),
        lambda row: row["source"]["fields"].update(
            official_max_governor_contest_total=19896
        ),
    ],
)
def test_bridge_rejects_wrong_ids_sha_urls_status_measure_clock_denominator_or_control(mutation):
    row = accepted()
    mutation(row)
    with pytest.raises(ValueError):
        dunn.source_url(row)


@pytest.mark.parametrize(
    "changed",
    [
        lambda text: text.replace("General Election", "Primary Election"),
        lambda text: text.replace("UNOFFICIAL RESULTS", "OFFICIAL RESULTS"),
        lambda text: text.replace("Total Votes Cast =", "Contest Total ="),
        lambda text: text + "\nTotal Votes Cast = 19,895",
        lambda text: text + "\nReport Generated 11/03/2026 11:00 PM",
    ],
)
def test_parser_rejects_changed_election_status_parent_scope_ambiguity_or_clock(changed):
    values = pages()
    values[0] = changed(values[0])
    with pytest.raises(ValueError):
        parsed(values=values)


@pytest.mark.parametrize(
    "values",
    [
        pages("27,174", "27,173", "100%", "37,812", "72%"),
        pages("19,896", "27,173", "72%", "37,812", "53%"),
        pages("19,896", "27,173", "73%", "37,812", "52%"),
    ],
)
def test_parser_rejects_unsafe_or_disagreeing_context(values):
    with pytest.raises(ValueError):
        parsed(values=values)


def test_collector_project_applies_only_explicit_bridge_and_repeats_byte_exact(
        monkeypatch):
    install_synthetic_parser(monkeypatch)
    before = baseline()
    entries = native.collect_sources(LocalCollector(), before)
    key = "WI-registered-4758ec49971e986f"
    assert entries[key]["adapter"] == "reviewed_dunn_unofficial_pdf"
    after, changes = granular.project(before, entries)
    assert changes == [{
        "state_code": "WI", "id": dunn.OBSERVATION_ID,
        "previous": 19896, "current": 19896, "source_status": "reported",
    }]
    row = json.loads(gzip.decompress(after["states/WI.json.gz"]))["records"][0]
    expected = accepted()
    expected["source"]["url"] = dunn.URL
    expected["source"]["input_sha256"] = hashlib.sha256(b"synthetic-dunn-pdf").hexdigest()
    expected["view"]["source_url"] = dunn.URL
    assert row == expected
    repeat_entries = native.collect_sources(LocalCollector(), after)
    repeated, repeat_changes = granular.project(after, repeat_entries)
    assert repeat_changes == []
    assert repeated == after


def test_collector_stop_rolls_back_to_exact_baseline(monkeypatch):
    install_synthetic_parser(monkeypatch)
    before = baseline()
    entries = native.collect_sources(LocalCollector(stop=True), before)
    after, changes = granular.project(before, entries)
    assert changes == []
    assert after == before


def test_projector_rejects_replacement_outside_reviewed_scope(monkeypatch):
    install_synthetic_parser(monkeypatch)
    before = baseline()
    entries = native.collect_sources(LocalCollector(), before)
    entry = entries["WI-registered-4758ec49971e986f"]
    entry["data"]["updates"][0]["replacement"]["quality"]["notes"].append("unreviewed")
    with pytest.raises(ValueError, match="exceeded"):
        granular.project(before, entries)
