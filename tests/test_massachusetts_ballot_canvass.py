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


def test_2022_municipal_only_rows_cannot_overlap_detailed_rows():
    original = precinct_csv().replace(b"Pct,A,B,All", b"Pct,A,B,C,All").replace(
        b",,,Democratic,Republican\n", b",,,Democratic,Republican,Unenrolled\n")
    lines = original.decode().splitlines()
    lines[2:] = [",".join(row.split(",")[:5] + ["0"] + row.split(",")[5:]) for row in lines[2:]]
    lines[2] = lines[2].replace("Lawrence,A,2A", "Lawrence,,")
    data = ("\n".join(lines) + "\n").encode()
    assert ma.precincts(data, contest="154341", year=2022)["units"][0] == ["Lawrence", "", "", 7]
    data = data.replace(b"TOTALS", b"Lawrence,A,1,0,0,0,0,0,0\nTOTALS")
    with pytest.raises(ValueError, match="export control"):
        ma.precincts(data, contest="154341", year=2022)


def test_2022_county_page_shortfall_retains_state_and_native_counts():
    reports = {}
    for contest in ma.PAIRS[2022]:
        export = ma.BASE + f"download/{contest}/precincts_include:1/"
        reports[contest] = {
            "page": {"counties": {"Essex": 7}, "columns_total": [10]},
            "csv": {"units": [["Lawrence", "", "", 10]], "columns_total": [10]},
            "page_source": {"url": ma.BASE + f"view/{contest}/", **pin(b"page")},
            "csv_source": {"url": export, **pin(b"csv")},
        }
    entry = {"status": "reported", "data": {"reports": reports}}
    rows = list(ma.history_exports({ma.FEEDS[2022]: entry}))
    assert [(row["geography_level"], row["ballots_including_blanks"]) for row in rows] == [
        ("statewide", 10), ("county_page_with_statewide_shortfall", 7),
        ("municipality", 10), ("municipality_only_source_row", 10)]
    assert all(row["county_ballot_shortfall"] == 3 for row in rows)


def test_2022_rollup_preserves_original_county_and_requires_one_to_one_names(monkeypatch):
    body = (b"USPS\tGEOID\tNAME\tALAND\nMA\t2500103690\tBarnstable Town city\t1\n"
            b"MA\t2500100000\tCounty subdivisions not defined\t0\n")
    monkeypatch.setattr(ma, "CROSSWALK_PIN", pin(body))
    monkeypatch.setattr(ma, "COUNTY_FIPS", {"25001": "Barnstable"})
    # Exercise the rollup with a single member of the roster; the real original
    # is also replayed with all 351 municipalities.
    reports = {contest: {"page": {"counties": {"Barnstable": 7}, "columns_total": [10]},
                         "csv": {"units": [["Barnstable", "-", "1", 10]], "columns_total": [10]}}
               for contest in ma.PAIRS[2022]}
    entries = {
        ma.FEEDS[2022]: {"status": "reported", "data": {"reports": reports}},
        ma.CROSSWALK_FEED: {"status": "reported", "source": {"url": ma.CROSSWALK_URL, **pin(body)},
                            "data": {"municipalities": {"barnstable": ["Barnstable Town city", "2500103690"]}}},
    }
    state, county, municipality = ma.rollup_exports(entries)
    assert state["ballots_including_blanks"] == 10
    assert county["original_county_page_ballots"] == 7 and county["difference_from_original_county_pages"] == 3
    assert municipality["census_geoid"] == "2500103690"
    entries[ma.CROSSWALK_FEED]["data"]["municipalities"]["not reported"] = ["Not reported town", "2500101234"]
    assert list(ma.rollup_exports(entries)) == []


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
