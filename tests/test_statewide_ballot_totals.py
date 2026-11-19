import copy
import gzip
import json
from pathlib import Path

import pytest

from scripts import statewide_ballot_totals as totals
from scripts import automatic_native_refresh as native
from scripts import results_state_statistics as stats
from scripts.results_native_state_family import AZ_COUNTIES
from scripts.participation_intake.contract import encoded, pin
from test_protected_official_wyoming import entry, native as workbook, changed
from scripts import protected_official_wyoming as official


def source(delta=0):
    data = official.parse(workbook(changed(delta)))
    return {"status": "reported", "data": data,
            "source": {"url": official.URL, **data["native_facts"]["original"]}}


def snapshot(value):
    return {"congress": {"official_candidate_evidence": {official.IDENTITY: value}}}


def baseline(monkeypatch):
    shard = {"contract": "participation.count_snapshot.v1", "state_code": "WY",
             "year": 2026, "records": [], "views": {"official": {"counties": [], "precincts": []}}}
    body = totals.compressed(shard)
    monkeypatch.setitem(totals.PROFILES["WY"], "initial_shard", pin(body))
    index = {"contract": "participation.count_index.v1", "year": 2026,
             "states": {"WY": {"file": "states/WY.json.gz", "records": 0, **pin(body)}},
             "coverage": {"WY": {}}}
    current = {"contract": "participation.current_snapshot.v1",
               "reviewed_states": [], "snapshot": {"reporting": []}}
    return {"states/WY.json.gz": body, "index.json": encoded(index),
            "current.json.gz": totals.compressed(current), "other-file": b"unchanged"}


def row(files):
    return json.loads(gzip.decompress(files["states/WY.json.gz"]))["records"][-1]


def test_south_carolina_binds_existing_reader_to_one_count_only_observation(monkeypatch):
    from test_results_state_statistics import document, template

    files = baseline(monkeypatch)
    path = "states/SC.json.gz"
    original = Path(__file__).resolve().parents[1] / "data/results-intake/baseline/counts" / path
    files[path] = original.read_bytes()
    index = json.loads(files["index.json"])
    index["states"]["SC"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)
    current = json.loads(gzip.decompress(files["current.json.gz"]))
    source = {"url": stats.URL, **pin(document())}
    data = stats.statistics(document(), "SC")
    current["snapshot"]["reporting"] = [stats.refresh(
        {**template(), "review_id": "participation-native-declarations-20261113-02"}, data, source)]
    files["current.json.gz"] = totals.compressed(current)
    captured = {"participation_observations": [
        {"channel": "SC-official", "status": "reported", "source": source, "observation": data}]}
    out, changes = totals.project(files, captured)
    assert changes == [{"state_code": "SC", "id": totals.identity("SC"), "previous": None,
                        "current": 2054835, "source_status": "reported"}]
    new = json.loads(gzip.decompress(out[path]))["records"][-1]
    assert new["count"]["value"] == 2054835 and new["denominator"] is None
    assert new["view"]["native_printed_pct"] == "59.8%" and new["view"]["validated_pct"] is None
    assert new["view"]["cast_ballot_count_qualified"] is False
    assert totals.project(out, captured) == (out, [])
    updated = document(early="1,043,811", total="2,054,836")
    captured["participation_observations"][0].update(
        source={"url": stats.URL, **pin(updated)}, observation=stats.statistics(updated, "SC"))
    out, changes = totals.project(out, captured)
    assert changes[0]["current"] == 2054836
    held, changes = totals.project(out, {})
    assert changes[0]["source_status"] == "retained_after_failure"
    assert changes[0]["current"] == 2054836
    assert totals.project(held, {}) == (held, [])


def test_dc_citywide_scope_projects_without_duplicating_the_count(monkeypatch):
    from scripts.supported_analytical_release import administrative, administrative_coverage

    files = baseline(monkeypatch)
    path = "states/DC.json.gz"
    original = Path(__file__).resolve().parents[1] / "data/results-intake/baseline/counts" / path
    files[path] = original.read_bytes()
    index = json.loads(files["index.json"])
    index["states"]["DC"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)
    projected, changes = totals.project(files, {})
    assert changes == [] and files[path] == projected[path]
    state, = json.loads(gzip.decompress(projected["current.json.gz"]))["snapshot"]["reporting"]
    assert state["state_code"] == "DC" and state["status"] == "retained_after_failure"
    assert (state["ballots"], state["denominator"], state["validated_pct"]) == (
        185086, 457371, 100 * 185086 / 457371)
    admin = administrative(projected)
    count, = [r for r in admin if r["also_covers_full_jurisdiction"]]
    assert count["observation_id"] == state["equivalent_county_observation_id"]
    coverage = next(r for r in administrative_coverage(admin) if r["state_code"] == "DC")
    assert coverage["statewide_election_participation_count_records"] == 1
    assert coverage["county_or_equivalent_election_participation_count_records"] == 1
    assert totals.project(projected, {}) == (projected, [])


def test_arkansas_retained_count_and_checked_successors(monkeypatch):
    files = baseline(monkeypatch)
    path = "states/AR.json.gz"
    original = Path(__file__).resolve().parents[1] / "data/results-intake/baseline/counts" / path
    files[path] = original.read_bytes()
    index = json.loads(files["index.json"])
    index["states"]["AR"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)
    stopping = {"granular_sources": {totals.AR_FEED: {"status": "source_stopped"}}}
    archived, changes = totals.project(files, stopping)
    assert changes == [{"state_code": "AR", "id": totals.identity("AR"), "previous": None,
                        "current": 893026, "source_status": "retained_after_failure"}]
    original_rows = json.loads(gzip.decompress(files[path]))
    shard = json.loads(gzip.decompress(archived[path]))
    assert shard["views"] == original_rows["views"]
    assert shard["records"][:-1] == original_rows["records"]
    row = shard["records"][-1]
    assert row["denominator"] is None
    assert row["reporting_status"] == {"literal": "UNOFFICIAL", "reported_units": 2761,
                                       "total_units": 2768, "complete": False}
    assert row["source_clock"]["literal"] is None
    assert totals.project(archived, stopping) == (archived, [])

    parent = copy.deepcopy(row["view"]["statewide_ballot_parent"])
    data = {key: parent[key] for key in ("statewide", "counties", "election_id", "count_source_clock")}
    previous = archived
    for delta, size in ((120, 10), (-200, 11)):
        data["statewide"][0] += delta
        data["counties"][0][1] += delta
        data["status"] = "OFFICIAL"
        capture = {"granular_sources": {totals.AR_FEED: {
            "status": "reported", "source": {"url": parent["source"]["url"], "bytes": size,
                                             "sha256": str(size % 10) * 64},
            "data": {"statewide_ballot_parent": data},
        }}}
        latest, changed = totals.project(previous, capture)
        assert changed[0]["current"] - changed[0]["previous"] == delta
        assert totals.project(latest, capture) == (latest, [])
        previous = latest
    assert totals.project(previous, stopping)[1][0] == {
        "state_code": "AR", "id": totals.identity("AR"), "previous": 892946,
        "current": 892946, "source_status": "retained_after_failure"}
    data["counties"][0][1] += 1
    with pytest.raises(ValueError, match="statewide and county"):
        totals.project(previous, capture)


def test_florida_projects_only_the_unchanged_retained_statewide_total(monkeypatch):
    baseline_path = Path(__file__).resolve().parents[1] / "data/results-intake/baseline/counts/states/FL.json.gz"
    if not baseline_path.is_file():
        pytest.skip("Retained collector baseline is not part of this runtime-only archive")
    files = baseline(monkeypatch)
    path = "states/FL.json.gz"
    files[path] = baseline_path.read_bytes()
    before = json.loads(gzip.decompress(files[path]))
    index = json.loads(files["index.json"])
    index["states"]["FL"] = {"file": path, **pin(files[path])}
    old_current = files["current.json.gz"]
    index["current_snapshot"] = {"file": "current.json.gz", **pin(old_current)}
    files["index.json"] = encoded(index)
    projected, changes = totals.project(files, {})
    assert changes == [{"state_code": "FL", "id": totals.identity("FL"), "previous": None,
                        "current": 8335497, "source_status": "retained_after_failure"}]
    after = json.loads(gzip.decompress(projected[path]))
    record = after["records"][-1]
    assert after["records"][:-1] == before["records"] and after["views"] == before["views"]
    assert record["denominator"] is record["view"]["validated_pct"] is None
    assert record["view"]["source_capture_date"] == "2026-11-06"
    assert record["source_clock"]["literal"] is record["reporting_status"]["complete"] is None
    assert json.loads(projected["index.json"])["current_snapshot"] == {
        "file": "current.json.gz", **pin(projected["current.json.gz"])}
    reporting, = json.loads(gzip.decompress(projected["current.json.gz"]))["snapshot"]["reporting"]
    assert reporting == record["view"]
    assert totals.project(projected, {}) == (projected, [])
    for candidate in before["records"]:
        if candidate["view"].get("review_id") == totals.FL_REVIEW:
            candidate["view"]["native_record"]["reported_participants"] = "0"
            break
    files[path] = totals.compressed(before)
    index["states"]["FL"].update(pin(files[path]))
    files["index.json"] = encoded(index)
    assert totals.project(files, {}) == (files, [])


def test_alaska_preserves_precinct_inventory_disagreement_and_uses_report_fraction(monkeypatch):
    ak = totals.alaska
    files = baseline(monkeypatch)
    index = json.loads(files["index.json"])
    path = "states/AK.json.gz"
    files[path] = totals.compressed({"contract": "participation.count_snapshot.v1",
                                   "state_code": "AK", "year": 2026, "records": [], "views": {}})
    index["states"]["AK"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)
    pdf = {"statewide_header": ["401", "401", "100.00%", "290,323", "605,433", "47.95%",
                                "UNOFFICIAL RESULTS"],
           "page_clocks_and_ordinals": [["11/18/2026 5:25:35 PM", "1", "1"]]}
    feed = ak.controls(encoded({"name": "Alaska 2026 General Election", "format": "2024",
        "summaryReportUrl": ak.REPORT, "certified": False, "updated": "11/18/2026 5:56 PM",
        "contestNames": list(ak.OFFICES), "totals": [
            {"n": i, "b": 290323, "t": 288207, "v": 605433, "p": 403, "r": 401} for i in range(2)]}))
    entry = {"status": "reported", "source": {"url": ak.URL, **pin(encoded(feed))},
             "data": {"date": "2026-11-18T17:25:35", "report": {"url": ak.REPORT, **pin(encoded(pdf))},
                      "complete_native_query": {"pdf": pdf, "statewide_feed": feed},
                      "reconciliation": ak.reconcile(pdf, feed)}}
    packet = {"granular_sources": {ak.FEED: entry}}
    updated, changes = totals.project(files, packet)
    assert changes[0]["current"] == 290323
    observation, = json.loads(gzip.decompress(updated[path]))["records"]
    assert observation["denominator"]["value"] == 605433 and observation["denominator"]["qualified"]
    assert observation["view"]["native_printed_pct"] == "47.95%"
    assert observation["reporting_status"]["complete"] is observation["reporting_status"]["total_units"] is None
    assert observation["source_clock"]["literal"] is None
    assert totals.project(updated, packet) == (updated, [])
    entry["status"] = "retained_after_failure"
    _, changes = totals.project(updated, packet)
    assert changes[0]["source_status"] == "retained_after_failure" and changes[0]["current"] == 290323
    feed["federal_controls"][1]["b"] -= 1
    with pytest.raises(ValueError, match="controls disagree"):
        ak.reconcile(pdf, feed)


@pytest.mark.parametrize("code", ["VA", "WA"])
def test_history_activates_only_on_a_published_general_election_row(monkeypatch, code):
    history = totals.history
    va = code == "VA"
    parser = history.parse_virginia if va else history.parse_washington
    feed, url = (history.VA_FEED, history.VA_URL) if va else (history.WA_FEED, history.WA_URL)
    files = baseline(monkeypatch)
    index = json.loads(files["index.json"])
    path = f"states/{code}.json.gz"
    files[path] = totals.compressed({"contract": "participation.count_snapshot.v1",
                                   "state_code": code, "year": 2026, "records": [], "views": {}})
    index["states"][code] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)
    header = "<tr>" + "".join(f"<th>{cell}</th>" for cell in (history.VA_HEADER if va else history.WA_HEADER)) + "</tr>"
    notes = ""
    if va:
        header = f"<tr><td>{history.VA_TITLE}</td></tr>" + header
        notes = f"<p>{history.VA_CERTIFICATION}</p><p>* NVRA</p><p>** Roll purges</p><p>*** Absentee unavailable</p>"

    def row_markup(year, value, rate):
        lead = f"<td>{year}</td><td>1000</td>"
        measure = f"<td>{value}</td><td>{rate}</td>"
        return "<tr>" + lead + ("<td>0.00%</td>" if va else "") + measure + ("<td>***</td>" if va else "") + "</tr>"

    old = "".join(row_markup("1996*" if va and y == 1996 else y, 500, "50.00%")
                  for y in range(2025, 1975 if va else 1979, -1))
    def snapshot(current="", status="reported"):
        body = f"{notes}<table>{header}{current}{old}</table>".encode()
        return {"granular_sources": {feed: {
            "status": status, "source": {"url": url, **pin(body)}, "data": parser(body)}}}

    unavailable = snapshot()
    assert totals.project(files, unavailable) == (files, [])
    dated = unavailable["granular_sources"][feed]
    assert dated["data"]["current_election_status"] == "not_yet_published"
    assert len(history.history_csv(dated, virginia=va).splitlines()) == (51 if va else 47)
    if va:
        assert b"1996*,0.00%,***" in history.history_csv(dated, virginia=True)
    row_html = row_markup(2026, 550, "55.00%")
    present = snapshot(row_html)
    current, changes = totals.project(files, present)
    assert changes[0]["current"] == 550
    observation, = json.loads(gzip.decompress(current[path]))["records"]
    assert observation["denominator"]["qualified"] and observation["view"]["validated_pct"] == 55
    assert observation["source_clock"]["literal"] is None
    if va:
        assert observation["measure"]["literal"] == "Total Voting"
        assert observation["view"]["source_status_literal"] == "Published after certification"
        assert not observation["view"]["cast_ballot_count_qualified"]
    assert totals.project(current, present) == (current, [])
    inconsistent = snapshot(row_html.replace("55.00%", "54.00%"))
    conflict, _ = totals.project(current, inconsistent)
    observation, = json.loads(gzip.decompress(conflict[path]))["records"]
    assert observation["count"]["value"] == 550 and observation["view"]["validated_pct"] is None
    assert observation["view"]["native_printed_pct"] == "54.00%"
    retained, changes = totals.project(current, snapshot(row_html, status="retained_after_failure"))
    assert changes[0]["current"] == 550 and changes[0]["source_status"] == "retained_after_failure"
    assert totals.project(retained, unavailable) == (retained, [])


def test_minnesota_requires_complete_matching_dual_sources(monkeypatch):
    from scripts.results_granular import MN_URL

    mn = totals.mn
    files = baseline(monkeypatch)
    index = json.loads(files["index.json"])
    path = "states/MN.json.gz"
    files[path] = totals.compressed({"contract": "participation.count_snapshot.v1",
                                   "state_code": "MN", "year": 2026, "records": [], "views": {}})
    index["states"]["MN"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)
    fields = {"Eligible Population": "8,700", "Estimated Voters": "4,350",
              "Estimated Turnout": "50.00%", "Counties Reporting": "87 of 87",
              "Counties Complete": "87", "Precincts Reporting in State": "100% 87 of 87",
              "Last Updated": "11/13/26 1:38 PM", "Voters Registered at 7AM": "6,960"}
    header = "<tr>" + "".join(f"<th>{cell}</th>" for cell in mn.HEADER) + "</tr>"
    county_rows = "".join(
        f'<tr><td><a href="/Results/CountyPrecinctStatisticsStatewide/Index?ersElectionId=201&amp;countyid={i}">'
        f'County {i}</a></td><td>1</td><td>1</td><td>100%</td><td>date</td><td>80</td><td>50</td></tr>'
        for i in range(1, 88))
    summary = "".join(f"<td>{key}: {value}</td>" for key, value in fields.items())
    body = (f"<div>Unofficial Results {mn.ELECTION}</div><table><tr><td>{mn.TITLE}</td></tr>"
            f"<tr>{summary}</tr></table><table>{header}{county_rows}</table>").encode()
    report = mn.parse(body)
    units = [dict(state="MN", county_id=f"{i:02}", precinct_id="001", has_reported_statistics="1",
                  registered_7am=80, total_number_voted=50) for i in range(1, 88)]
    txt = {"url": MN_URL, **pin(encoded(units))}
    result = mn.reconcile(report, units)
    entries = {
        mn.IDENTITY: {"status": "reported", "source": {"url": mn.URL, **pin(body)},
                      "data": {**report, "statistical_txt": txt, "reconciliation": result}},
        "MN-native-local": {"status": "reported", "source": txt,
                            "data": {"complete_native_query": units}},
    }
    def project(previous):
        return totals.project(previous, {"granular_sources": entries})

    fresh, changes = project(files)
    assert changes[0]["current"] == 4350
    observation, = json.loads(gzip.decompress(fresh[path]))["records"]
    assert observation["denominator"] is None and observation["view"]["reported_pct"] is None
    assert observation["view"]["statewide_ballot_parent"]["fields"] == fields
    assert project(fresh) == (fresh, [])
    entries[mn.IDENTITY]["status"] = "retained_after_failure"
    stale, changes = project(fresh)
    assert changes[0]["source_status"] == "retained_after_failure" and changes[0]["current"] == 4350
    assert project(stale) == (stale, [])
    units[0]["total_number_voted"] -= 1
    units[1]["total_number_voted"] += 1
    with pytest.raises(ValueError, match="disagree by county"):
        mn.reconcile(report, units)


def arizona_root():
    def label(value):
        return [{"languageId": "en", "text": value}]

    edition = "2026-11-18T15:42:00.028255Z"
    base = {"electionDate": "2026-11-03", "name": label("2026 General Election"),
            "asOf": edition, "isOfficialResults": False}
    return {
        "election": {**base, "id": "01000000-3e48-04ed-11b1-08df1107098b",
                     "isPrimary": False, "isProduction": True,
                     "ballotsCast": 0.0, "totalVoters": 1500.0},
        "jurisdiction": {"id": "01000000-0496-9e5d-0291-08dbda35db79",
                         "name": label("Arizona"), "shortName": "Arizona",
                         "childLocalities": [{"id": uid, "name": label(name), "shortName": slug}
                                             for name, slug, uid in AZ_COUNTIES.values()]},
        "localityElections": [{**base, "jurisdictionId": uid, "totalVoters": 100.0,
                               "ballotsCast": 50.0}
                              for _, _, uid in AZ_COUNTIES.values()],
        "voterRegistration": [{"id": uid, "total": 100} for _, _, uid in AZ_COUNTIES.values()],
    }


def test_arizona_rollup_preserves_source_zero_without_replacing_positive_ballots(monkeypatch):
    files = baseline(monkeypatch)
    index = json.loads(files["index.json"])
    az = {"contract": "participation.count_snapshot.v1", "state_code": "AZ",
          "year": 2026, "records": [], "views": {}}
    path = "states/AZ.json.gz"
    files[path] = totals.compressed(az)
    index["states"]["AZ"] = {"file": path, **pin(files[path])}
    index["current_snapshot"] = {"file": "current.json.gz", **pin(files["current.json.gz"])}
    files["index.json"] = encoded(index)
    root = arizona_root()

    def packet():
        body = encoded(root)
        return {"participation_observations": [{
            "channel": "AZ-official", "status": "reported",
            "source": {"url": stats.AZ_URL, **pin(body)}, "observation": stats.statistics(body, "AZ"),
        }]}

    newest, changes = totals.project(files, packet())
    item, = json.loads(gzip.decompress(newest[path]))["records"]
    assert changes[0]["current"] == item["count"]["value"] == 750
    assert item["view"]["statewide_ballot_parent"]["backend_statewide_ballots"] == 0
    assert item["denominator"] is item["view"]["validated_pct"] is None
    assert json.loads(newest["index.json"])["current_snapshot"] == {
        "file": "current.json.gz", **pin(newest["current.json.gz"])}
    assert totals.reviewed_addition("AZ", {}, {item["id"]: item}, pin(files[path]))
    assert totals.project(newest, packet()) == (newest, [])
    for revised_value in (55, 47):
        root["localityElections"][0]["ballotsCast"] = revised_value
        newest, changes = totals.project(newest, packet())
        assert changes[0]["current"] == 700 + revised_value
    retained, changes = totals.project(newest, {})
    assert changes[0]["source_status"] == "retained_after_failure"
    assert changes[0]["current"] == 747
    assert totals.project(retained, {}) == (retained, [])
    assert totals.project(retained, packet())[0] == newest


@pytest.mark.parametrize("change", ["missing_county", "registration_conflict", "backend_conflict"])
def test_arizona_rollup_withholds_incompatible_editions(change):
    root = arizona_root()
    if change == "missing_county":
        root["localityElections"].pop()
    elif change == "registration_conflict":
        root["voterRegistration"][0]["total"] = 101
    else:
        root["election"]["ballotsCast"] = 1
    with pytest.raises(ValueError):
        stats.statistics(encoded(root), "AZ")


def test_vermont_uses_only_the_reconciled_same_report_denominator(monkeypatch):
    files = baseline(monkeypatch)
    index = json.loads(files["index.json"])
    path = "states/VT.json.gz"
    files[path] = totals.compressed({"contract": "participation.count_snapshot.v1",
                                   "state_code": "VT", "year": 2026, "records": [], "views": {}})
    index["states"]["VT"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)
    counties = [
        {"native_unit": name, "total_votes_cast_includes_absentee": 50,
         "registered_voters": 100, "absentee_votes_cast": 10}
        for name in totals.VT_COUNTIES]
    parent = {"native_unit": "State Total", "parent": "State Total",
              "total_votes_cast_includes_absentee": 700, "registered_voters": 1400,
              "absentee_votes_cast": 140, "native_turnout_percent": "50.00%",
              "source_ref": {"page": 13, "row": 15}}
    data = {"source_clock": "11/09/2026", "complete_native_query": {
        "groups": {"queries": {"summary_total": {"rows": [parent]},
                              "summary_parents": {"rows": counties}}}}}
    entry = {"source": {"url": totals.VT_URL, **pin(encoded(data))}, "status": "reported", "data": data}
    snapshot = {"granular_sources": {totals.PROFILES["VT"]["feed"]: entry}}
    active, changes = totals.project(files, snapshot)
    assert changes[0]["current"] == 700
    expected, = json.loads(gzip.decompress(active[path]))["records"]
    assert expected["view"]["validated_pct"] == 50.0
    assert expected["view"]["cast_ballot_count_qualified"] is False
    assert expected["source_clock"]["literal"] is None
    assert totals.project(active, snapshot) == (active, [])
    held, changes = totals.project(active, {})
    assert changes[0]["source_status"] == "retained_after_failure"
    assert totals.project(held, snapshot)[0] == active
    parent["registered_voters"] = 1399
    with pytest.raises(ValueError, match="county and statewide totals disagree"):
        totals.project(files, snapshot)


def test_direct_native_parent_is_count_only_and_congressional_contract_stays_separate(monkeypatch):
    initial = baseline(monkeypatch)
    value = entry()
    output, changes = totals.project(initial, snapshot(value))
    item = row(output)
    assert item["count"]["value"] == 191713
    assert item["count"]["value"] != value["data"]["races"][0]["contest_total"]
    assert item["denominator"] is item["view"]["validated_pct"] is None
    assert item["source_clock"] == {"literal": None, "timezone": None}
    assert item["reporting_status"]["complete"] is None
    assert item["view"]["unique_voter_count_qualified"] is False
    assert item["view"]["maps_approved"] is False
    assert value["data"]["participation_observation_qualified"] is False
    assert changes == [{"state_code": "WY", "id": item["id"], "previous": None,
                        "current": 191713, "source_status": "reported"}]
    current = json.loads(gzip.decompress(output["current.json.gz"]))
    assert current["snapshot"]["reporting"] == [item["view"]]
    assert output["other-file"] == initial["other-file"]
    assert totals.project(output, snapshot(value)) == (output, [])
    assert b"WY,2026,191713,reported,,," in totals.exports(output)[
        "participation/native-statewide-ballot-totals.csv"]


@pytest.mark.parametrize("delta", [7, -13])
def test_both_native_revision_directions_propagate_to_canonical_mirror_and_download(monkeypatch, delta):
    output, _ = totals.project(baseline(monkeypatch), snapshot(source()))
    revised, changes = totals.project(output, snapshot(source(delta)))
    item = row(revised)
    assert item["id"] == row(output)["id"]
    assert item["count"]["value"] == 191713 + delta
    assert changes[0]["previous"] == 191713
    assert item["source"]["input_sha256"] != row(output)["source"]["input_sha256"]
    assert native.observation_identity(item) == native.observation_identity(row(output))
    current = json.loads(gzip.decompress(revised["current.json.gz"]))
    assert current["snapshot"]["reporting"][0] == item["view"]
    exported = json.loads(gzip.decompress(totals.exports(revised)[
        "participation/native-statewide-ballot-totals.json.gz"]))
    assert exported["rows"][0]["ballots"] == 191713 + delta


def test_failure_retains_last_good_without_inventing_an_initial_observation_and_recovers(monkeypatch):
    initial = baseline(monkeypatch)
    failed = {"status": "source_stopped", "data": None}
    assert totals.project(initial, snapshot(failed)) == (initial, [])
    good, _ = totals.project(initial, snapshot(source()))
    held, changes = totals.project(good, snapshot(failed))
    assert row(held)["count"] == row(good)["count"]
    assert row(held)["source"]["input_sha256"] == row(good)["source"]["input_sha256"]
    assert row(held)["view"]["status"] == changes[0]["source_status"] == "retained_after_failure"
    assert totals.project(held, snapshot(failed)) == (held, [])
    recovered, _ = totals.project(held, snapshot(source()))
    assert recovered == good


def test_missing_display_mirror_is_restored_without_changing_canonical_observation(monkeypatch):
    good, _ = totals.project(baseline(monkeypatch), snapshot(source()))
    incomplete = dict(good)
    current = json.loads(gzip.decompress(incomplete["current.json.gz"]))
    current["snapshot"]["reporting"] = []
    incomplete["current.json.gz"] = totals.compressed(current)
    repaired, changes = totals.project(incomplete, snapshot(source()))
    assert changes == []
    assert repaired == good
    assert totals.project(repaired, snapshot(source())) == (good, [])


def test_complete_native_zero_is_not_missing_or_a_turnout_rate(monkeypatch):
    good, _ = totals.project(baseline(monkeypatch), snapshot(source()))
    facts = changed()
    for table in facts["tables"]:
        for selected in table["rows"]:
            for cell in selected["cells"]:
                if selected["row"] >= 5 and type(cell["value"]) is int:
                    cell["value"] = 0
                    cell["cached_literal"] = "0"
    data = official.parse(workbook(facts))
    empty = {"status": "reported", "data": data,
             "source": {"url": official.URL, **data["native_facts"]["original"]}}
    revised, changes = totals.project(good, snapshot(empty))
    assert row(revised)["count"] == {"value": 0, "literal": 0, "status": "reported"}
    assert row(revised)["view"]["ballots"] == changes[0]["current"] == 0
    assert row(revised)["denominator"] is row(revised)["view"]["validated_pct"] is None
    assert totals.project(revised, snapshot(empty)) == (revised, [])


@pytest.mark.parametrize("mutation", ["count", "denominator", "clock", "map", "source"])
def test_corrupt_prior_or_promoted_qualifications_are_refused(monkeypatch, mutation):
    good, _ = totals.project(baseline(monkeypatch), snapshot(source()))
    shard = json.loads(gzip.decompress(good["states/WY.json.gz"]))
    item = shard["records"][0]
    if mutation == "count":
        item["count"]["value"] += 1
    elif mutation == "denominator":
        item["denominator"] = {"value": 200000, "qualified": True}
    elif mutation == "clock":
        item["source_clock"]["literal"] = "retrieval time"
    elif mutation == "map":
        item["view"]["maps_approved"] = True
    else:
        item["source"]["input_sha256"] = "f" * 64
    good["states/WY.json.gz"] = totals.compressed(shard)
    index = json.loads(good["index.json"])
    index["states"]["WY"].update(pin(good["states/WY.json.gz"]))
    good["index.json"] = encoded(index)
    with pytest.raises(ValueError, match="Existing statewide ballot"):
        totals.project(good, snapshot(source()))


def test_native_inventory_and_display_preimages_remain_fail_closed(monkeypatch):
    initial = baseline(monkeypatch)
    edited = dict(initial)
    shard = json.loads(gzip.decompress(edited["states/WY.json.gz"]))
    shard["views"]["official"]["counties"] = ["unexpected"]
    edited["states/WY.json.gz"] = totals.compressed(shard)
    index = json.loads(edited["index.json"])
    index["states"]["WY"].update(pin(edited["states/WY.json.gz"]))
    edited["index.json"] = encoded(index)
    with pytest.raises(ValueError, match="Unreviewed initial"):
        totals.project(edited, snapshot(source()))
    current = json.loads(gzip.decompress(initial["current.json.gz"]))
    current["snapshot"]["reporting"] = [{"state_code": "WY", "ballots": 1}]
    initial["current.json.gz"] = totals.compressed(current)
    with pytest.raises(ValueError, match="display preimage"):
        totals.project(initial, snapshot(source()))


def test_only_the_reviewed_single_append_passes_native_inventory_guard(monkeypatch):
    initial = baseline(monkeypatch)
    good, _ = totals.project(initial, snapshot(source()))
    before, after, states = native.changed_records(initial, good)
    assert before == after == {} and states == {"WY"}
    shard = json.loads(gzip.decompress(good["states/WY.json.gz"]))
    shard["records"].append(copy.deepcopy(shard["records"][0]))
    shard["records"][-1]["id"] = "unexpected"
    good["states/WY.json.gz"] = totals.compressed(shard)
    index = json.loads(good["index.json"])
    index["states"]["WY"].update(pin(good["states/WY.json.gz"]))
    good["index.json"] = encoded(index)
    with pytest.raises(ValueError, match="only existing count IDs"):
        native.changed_records(initial, good)
