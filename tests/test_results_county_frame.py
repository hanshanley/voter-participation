import copy
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
import json
import re

import pytest

from scripts import results_county_frame as frame
from scripts import results_intake
from scripts.participation_intake.contract import encoded, pin
from test_results_clarity_congress import capture, facts


def baseline(value):
    profile = frame.IA
    bounds = {"sha256": profile["reference_sha256"], "boundary_year": 2026,
              "review_id": "test-existing-reference"}
    scopes, joins, records = {}, [], []
    for i, name in enumerate(value["status"]["P"]):
        key = f"19{2*i+1:03d}"
        county = name + " County"
        provider_id = f"provider:{key}"
        scopes[key] = {"state_code": "IA", "name": county, "boundary_year": 2026}
        joins.append({"county_id": provider_id, "feature_key": key})
        records.append({
            "id": provider_id, "source": {"id": "early"}, "denominator": None,
            "count": {"status": "reported", "value": 1},
            "view": {"county": county, "county_fips": key, "county_id": provider_id,
                     "reference_geometry": bounds},
        })
    early_ids = [row["id"] for row in records]
    for identity, name in zip(profile["old_selections"], ("Linn", "Marion")):
        records.append({
            "id": identity, "source": {"id": f"dated-{name}"}, "denominator": None,
            "count": {"status": "reported", "value": 2}, "view": {"county": name + " County"},
        })
    modes = {mode: {"qualified": True, "counties": list(profile["old_selections"]),
                    "nongeographic": [], "precincts": [], "holds": []} for mode in frame.MODES}
    modes["in_person_early"] = {"qualified": True, "counties": early_ids}
    modes["mail_returned"] = {"qualified": True, "counties": ["separate-mail-inventory"]}
    shard = {"contract": "participation.count_snapshot.v1", "state_code": "IA", "year": 2026,
             "records": records, "views": modes}
    path = "states/IA.json.gz"
    body = frame.compressed(shard)
    current = frame.compressed({"snapshot": {"reporting": []}})
    index = {"states": {"IA": {"file": path, **pin(body), "records": len(records),
             "views": {mode: {"counties": 2, "dispositions": {}} for mode in frame.MODES}}},
             "current_snapshot": {"file": "current.json.gz", **pin(current)},
             "coverage": {"IA": {"unrelated_field": "preserve"}}}
    native = {"county_bindings": {"IA": {"in_person_early": {
        "sha256": bounds["sha256"], "features": len(scopes), "feature_keys": list(scopes),
        "feature_scopes": scopes, "rows": joins}}}}
    return {path: body, "index.json": encoded(index),
            "current.json.gz": current}, {
                "index.json": encoded(native)}


def snapshot(entry):
    return {"congress": {"official_candidate_evidence": {frame.clarity.IDENTITY: entry}}}


def test_cuyahoga_complete_scope_revision_and_failure(tmp_path, monkeypatch):
    parser = frame.county_pdf
    _, native = baseline(facts())
    counts_root = results_intake.ROOT / "data/results-intake/baseline/counts"
    counts = {name: (counts_root / name).read_bytes() for name in ("index.json", "states/OH.json.gz")}
    shard = frame.decode(counts["states/OH.json.gz"])
    early = next(row["view"] for row in shard["records"]
                 if row["view"].get("county_fips") == frame.CUYAHOGA_FIPS
                 and row["id"] in shard["views"]["in_person_early"]["counties"])
    code = "OH"
    bounds = {"feature_keys": [frame.CUYAHOGA_FIPS], "features": 1,
              "feature_scopes": {frame.CUYAHOGA_FIPS: dict(state_code=code, name=parser.COUNTY, boundary_year=2026)},
              "sha256": early["reference_geometry"]["sha256"],
              "rows": [dict(feature_key=frame.CUYAHOGA_FIPS, county_id=early["county_id"])]}
    native["index.json"] = encoded({"county_bindings": {code: {"in_person_early": bounds}}})
    route = parser.REPORT + "20096519-6ca4-4375-b2f3-d07c61762bfb/"
    report = b"fixture PDF body"
    label = parser.STATUSES[0]
    pages = [dict(title=label, election=parser.TITLE, scope=parser.SCOPE,
                  statistics="Total Ballots Cast: 482011, Registered Voters: 878381, Overall Turnout: 54.87%",
                  clock="2026-11-04 05:29:45", page=f"Page: {number} of 2") for number in (1, 2)]
    monkeypatch.setattr(parser, "parse_report", lambda body: copy.deepcopy(pages))
    def collect(previous=None, body=report):
        collector = results_intake.Collector(tmp_path, {parser.IDENTITY: previous},
            {"urls": [], "hosts": [], "prefixes": []}, datetime(2026, 11, 19, tzinfo=timezone.utc))
        index_body = f'<a href="{route}"> {label} </a>'.encode()
        def acquire(url):
            if url == parser.INDEX_URL:
                return index_body, {"origin": "test"}
            assert url.endswith(route)
            if body is None:
                raise ValueError("Incomplete report transport")
            return body, {"origin": "test"}
        collector.acquire = acquire
        return parser.collect(collector)

    def project(previous_counts, previous_native, entry):
        return frame.project_cuyahoga(previous_counts, previous_native, {"granular_sources": {parser.IDENTITY: entry}})

    initial = collect()
    assert initial["status"] == "reported"
    result, mapped, changes = project(counts, native, initial)
    assert changes[0]["current"] == 482011
    after = frame.decode(result["states/OH.json.gz"])
    assert after["records"][:-1] == shard["records"]
    row = after["records"][-1]
    assert row["denominator"]["value"] == 878381 and row["denominator"]["qualified"]
    assert row["view"]["native_printed_pct"] == "54.87%" and row["source_clock"]["literal"] is None
    for mode in ("available", "in_person_early", "mail_returned"):
        assert after["views"][mode] == shard["views"][mode]
    for mode in ("official", "uf_vap", "uf_vep"):
        assert row["id"] in after["views"][mode]["counties"]
        binding = json.loads(mapped["index.json"])["county_bindings"][code][mode]
        assert binding["rows"][-1]["feature_key"] == frame.CUYAHOGA_FIPS
    assert project(result, mapped, collect(initial)) == (result, mapped, [])
    for value, fraction, clock in [(482111, "54.89", "2026-11-05 05:29:45"),
                                  (481911, "54.86", "2026-11-06 05:29:45")]:
        for page in pages:
            page.update(clock=clock, statistics=f"Total Ballots Cast: {value}, Registered Voters: 878381, Overall Turnout: {fraction}%")
        initial = collect(initial, body=str(value).encode())
        assert initial["status"] == "reported"
        result, mapped, changes = project(result, mapped, initial)
        assert changes[0]["current"] == value
    pages.pop()
    rejected = collect(initial)
    assert rejected["status"] == "retained_after_failure"
    assert "page sequence" in rejected["error_detail"]
    result, mapped, changes = project(result, mapped, rejected)
    assert changes[0]["current"] == 481911 and changes[0]["source_status"] == "retained_after_failure"
    assert project(result, mapped, collect(initial, body=None)) == (result, mapped, [])


def revised_ballots(value, delta):
    value = copy.deepcopy(value)
    value["version"] = str(int(value["version"]) + 1)
    county = "Linn"
    index = value["status"]["P"].index(county)
    value["status"]["B"][index] += delta
    for table in (value["sum"]["Contests"], value["summary"]):
        next(row for row in table if row["K"] == "1000")["BC"] += delta
    lines = value["text_report"].splitlines()
    for i, line in enumerate(lines):
        cells = re.split(r"\s{2,}", line.strip())
        if len(cells) == 4 and cells[0] in (county, "Total:") and cells[-1].endswith("%"):
            cells[2] = str(int(cells[2]) + delta)
            rate = (Decimal(cells[2]) * 100 / Decimal(cells[1])).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP)
            cells[3] = f"{rate}%"
            lines[i] = "  ".join(cells)
    value["text_report"] = "\n".join(lines)
    return value


def test_county_frame_replaces_selections_not_observations_and_has_no_rate(tmp_path):
    value = facts()
    original, maps = baseline(value)
    entry, _ = capture(tmp_path, value)
    assert entry["status"] == "reported"
    counts, native, changes = frame.project(original, maps, snapshot(entry))
    before = frame.decode(original["states/IA.json.gz"])
    after = frame.decode(counts["states/IA.json.gz"])
    assert len(changes) == 100
    assert after["records"][:len(before["records"])] == before["records"]
    new = {row["id"]: row for row in after["records"][len(before["records"]):]}
    selected = after["views"]["official"]["counties"]
    assert len(selected) == 99 and sum(new[key]["count"]["value"] for key in selected) == 1382511
    assert all(new[key]["denominator"] is None and new[key]["view"]["reported_pct"] is None
               for key in selected)
    assert {new[key]["view"]["county"]: new[key]["count"]["value"] for key in selected
            if new[key]["view"]["county"] in ("Linn County", "Marion County")} == {
                "Linn County": 107512, "Marion County": 16379}
    bindings = json.loads(native["index.json"])["county_bindings"]["IA"]
    for mode in frame.MODES:
        assert after["views"][mode]["counties"] == selected
        assert {item["feature_key"] for item in bindings[mode]["rows"]} == set(bindings[mode]["feature_keys"])
    for mode in ("in_person_early", "mail_returned"):
        assert after["views"][mode] == before["views"][mode]
    state, = frame.decode(counts["current.json.gz"])["snapshot"]["reporting"]
    assert json.loads(counts["index.json"])["current_snapshot"] == {
        "file": "current.json.gz", **pin(counts["current.json.gz"])}
    assert state["ballots"] == 1382511 and state["registered"] == 2178374
    assert state["source_update_label"] is None and state["source_publication_label"]
    assert frame.project(counts, native, snapshot(entry)) == (counts, native, [])


def test_revised_ballots_flow_through_shared_collector_and_outage_keeps_last_good(tmp_path):
    value = facts()
    counts, native = baseline(value)
    entry, _ = capture(tmp_path / "first", value)
    counts, native, _ = frame.project(counts, native, snapshot(entry))
    for delta in (7, -13):
        value = revised_ballots(value, delta)
        entry, _ = capture(tmp_path / value["version"], value, entry)
        assert entry["status"] == "reported", entry.get("error")
        counts, next_native, changes = frame.project(counts, native, snapshot(entry))
        assert next_native == native
        assert sorted(row["current"] - row["previous"] for row in changes
                      if row["current"] != row["previous"]) == [delta, delta]
    failure, _ = capture(tmp_path / "outage", None, entry)
    assert failure["status"] == "retained_after_failure"
    retained, retained_native, changes = frame.project(counts, native, snapshot(failure))
    assert retained_native == native and len(changes) == 100
    assert all(row["current"] == row["previous"] and row["source_status"] == "retained_after_failure"
               for row in changes)
    assert frame.project(retained, native, snapshot(failure)) == (retained, native, [])
    assert frame.project(retained, native, snapshot(entry))[:2] == (counts, native)


def test_binding_does_not_accept_unreviewed_county_selection(tmp_path):
    value = facts()
    counts, native = baseline(value)
    index = json.loads(native["index.json"])
    index["county_bindings"]["IA"]["in_person_early"]["rows"][0]["feature_key"] = "19003"
    entry, _ = capture(tmp_path, value)
    with pytest.raises(ValueError, match="County reference"):
        frame.project(counts, {"index.json": encoded(index)}, snapshot(entry))


@pytest.mark.parametrize("missing", [{}, {"status": "source_stopped"}])
def test_missing_source_data_marks_only_existing_iowa_frame_retained(tmp_path, missing):
    value = facts()
    initial, initial_native = baseline(value)
    unavailable = snapshot(missing) if missing else {}
    assert frame.project(initial, initial_native, unavailable) == (initial, initial_native, [])
    entry, _ = capture(tmp_path, value)
    counts, native, _ = frame.project(initial, initial_native, snapshot(entry))

    kept, kept_native, changes = frame.project(counts, native, unavailable)
    assert kept_native == native and len(changes) == 100
    before = frame.decode(counts["states/IA.json.gz"])
    after = frame.decode(kept["states/IA.json.gz"])
    for row in before["records"]:
        if row["source"]["id"] == frame.clarity.IDENTITY:
            row["source"]["fields"]["status"] = row["view"]["status"] = "retained_after_failure"
    assert after == before
    state, = frame.decode(kept["current.json.gz"])["snapshot"]["reporting"]
    assert state["status"] == "retained_after_failure"
    assert state["source_version"] == entry["data"]["source_version"]
    assert frame.project(kept, kept_native, unavailable) == (kept, kept_native, [])
    assert frame.project(kept, kept_native, snapshot(entry))[:2] == (counts, native)


def test_reported_source_without_facts_is_an_integrity_failure():
    with pytest.raises(ValueError, match="missing its facts"):
        frame.project({}, {}, snapshot({"status": "reported"}))


def test_reviewed_retained_capture_bootstraps_only_a_dated_count_frame(tmp_path, monkeypatch):
    from scripts import results_intake
    from scripts.participation_intake.contract import IntakeError

    source = frame.clarity
    path = results_intake.ROOT / source.RETAINED_CAPTURE
    if not path.is_file():
        pytest.skip("Retained collector bootstrap input is not part of this runtime-only archive")
    saved = source.document(path.read_bytes())
    counts, native = baseline(saved["data"]["native_facts"])
    collector = results_intake.Collector(
        tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
        source.datetime.fromisoformat(saved["first_observed_at"]))

    def incomplete(url):
        collector.guard(url)
        assert url == source.URL
        raise IntakeError("source_access", "Source did not return a complete successful original")

    monkeypatch.setattr(collector, "acquire", incomplete)
    held = source.collect(collector)
    assert held["reviewed_retained_capture"] is True
    assert held["first_observed_at"] == saved["first_observed_at"]
    assert held["status"] == "retained_after_failure"
    projected, mapping, changes = frame.project(counts, native, snapshot(held))
    state, = frame.decode(projected["current.json.gz"])["snapshot"]["reporting"]
    assert len(changes) == 100
    assert len(json.loads(mapping["index.json"])["county_bindings"]["IA"]["official"]["rows"]) == 99
    assert state["ballots"] == 1382511 and state["validated_pct"] is None
    assert state["status"] == "retained_after_failure"
    assert frame.project(projected, mapping, snapshot(held)) == (projected, mapping, [])
    held["first_observed_at"] = "2026-11-19T00:00:00+00:00"
    with pytest.raises(ValueError, match="retained capture pin"):
        frame.project(counts, native, snapshot(held))
    collector.stopped["urls"].append(source.report_url(saved["data"]["source_version"]))
    assert source.collect(collector)["data"] is None
    collector.stopped["urls"].append(source.URL)
    stopped = source.collect(collector)
    assert stopped["status"] == "source_stopped" and stopped["data"] is None
