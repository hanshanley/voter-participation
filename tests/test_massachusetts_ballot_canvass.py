import gzip
import json

import pytest

from scripts import massachusetts_ballot_canvass as ma, statewide_ballot_totals as totals
from scripts.participation_intake.contract import encoded, pin
from scripts.supported_analytical_release import selected_local_observation_ids


def precinct_csv():
    rows = ["City/Town,Ward,Pct,A,B,All Others,Blanks,Total Votes Cast",
            ",,,Democratic,Republican", "Lawrence,A,2A,2,3,1,1,7"]
    rows.extend(f"Town {i},-,1,0,0,0,0,0" for i in range(350))
    return ("\n".join([*rows, "TOTALS,,,2,3,1,1,7"]) + "\n").encode()


def test_precinct_parser_preserves_blanks_and_lettered_ward():
    original = precinct_csv()
    parsed = ma.precincts(original, contest="173530")
    assert parsed["units"][0] == ["Lawrence", "A", "2A", 7]
    assert len(parsed["units"]) == 351
    with pytest.raises(ValueError, match="ballot columns"):
        ma.precincts(original.replace(b"A,2A,2,3,1,1,7", b"A,2A,2,3,1,1,6"), contest="173530")
    with pytest.raises(ValueError, match="export control"):
        ma.precincts(original.replace(b"TOTALS,,,2,3,1,1,7", b"TOTALS,,,2,3,1,2,8"), contest="173530")


def test_reconciliation_checks_both_parent_totals_and_exact_unit_counts():
    def report(units):
        return {"page": {"columns_total": [7, 7], "counties": {"Essex": 7}},
                "csv": {"columns_total": [7, 7], "units": units}}

    units = [["Lawrence", "A", "1", 3], ["Lawrence", "A", "2", 4]]
    reports = {"173530": report(units), "173526": report(units)}
    assert ma.reconcile(reports) == ({"Essex": 7}, units)
    reports["173526"] = report([["Lawrence", "A", "1", 4], ["Lawrence", "A", "2", 3]])
    with pytest.raises(ValueError, match="all-ballot reporting counts"):
        ma.reconcile(reports)
    reports["173526"]["csv"]["columns_total"] = [8, 8]
    with pytest.raises(ValueError, match="pages and exports disagree"):
        ma.reconcile(reports)


def test_statewide_projection_is_count_only_and_retains_last_good():
    def snapshot(ballots):
        counties = dict.fromkeys(ma.COUNTIES, 0)
        counties["Essex"] = ballots
        reports = {}
        for contest in ma.CONTESTS:
            reports[contest] = {
                "page": {"counties": counties, "columns_total": [ballots]},
                "csv": {"units": [["Lawrence", "A", "1", ballots]], "columns_total": [ballots]},
                "page_source": {"url": ma.BASE + f"view/{contest}/", **pin(str(ballots).encode())},
                "csv_source": {"url": ma.BASE + f"download/{contest}/precincts_include:1/", **pin(str(ballots).encode())},
            }
        source = reports["173530"]["page_source"]
        return {"granular_sources": {ma.FEED: {"status": "reported", "source": source, "data": {"reports": reports}}},
                "collection_scope": {"mode": "selected_registered_source_refresh", "source_ids": [ma.FEED]}}

    path = "states/MA.json.gz"
    shard = {"contract": "participation.count_snapshot.v1", "state_code": "MA", "year": 2026,
             "records": [], "views": {"official": {"counties": [], "precincts": []}}}
    body = totals.compressed(shard)
    index = {"contract": "participation.count_index.v1", "year": 2026,
             "states": {"MA": {"file": path, "records": 0, **pin(body)}}, "coverage": {"MA": {}}}
    current = {"contract": "participation.current_snapshot.v1", "reviewed_states": [], "snapshot": {"reporting": []}}
    files = {path: body, "index.json": encoded(index), "current.json.gz": totals.compressed(current)}
    out, changes = totals.project(files, snapshot(10))
    assert changes[0]["current"] == 10
    observation, = json.loads(gzip.decompress(out[path]))["records"]
    assert observation["count"]["value"] == 10
    assert observation["denominator"] is None
    assert observation["view"]["cast_ballot_count_qualified"] is True
    assert selected_local_observation_ids(snapshot(10), out) == {observation["id"]}
    assert totals.project(out, snapshot(10)) == (out, [])
    for revised in (9, 11):
        _, changes = totals.project(out, snapshot(revised))
        assert changes[0]["current"] == revised
    _, changes = totals.project(out, {})
    assert changes[0]["current"] == 10 and changes[0]["source_status"] == "retained_after_failure"
