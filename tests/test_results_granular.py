import copy
import gzip
import io
import json
import zipfile

import pytest

from scripts import results_granular as granular
from scripts.participation_intake.contract import encoded, observation_id, pin, validate


def template(state="MN", name="UNIT", level="reporting_unit", native=None):
    row = {
        "contract": "participation.observation.v1", "id": "",
        "election": {"id": "general-2026", "year": 2026, "date": "2026-11-03",
                     "type": "general", "qualification": "native"},
        "geography": {"id": state + "-unit", "name": name, "state_code": state,
                      "level": level, "parent_id": None,
                      "join": {"status": "unreviewed", "reference_id": None,
                               "feature_key": None, "evidence": None}},
        "measure": {"id": "native-statistics", "kind": "participation_reported",
                    "literal": "Native statistics", "mode": "source_defined", "unit": "source_units"},
        "count": {"value": 7, "literal": "7", "status": "reported"},
        "denominator": None, "source_clock": {"literal": "OLD CLOCK", "timezone": None},
        "reporting_status": {"literal": "Unofficial", "reported_units": None,
                             "total_units": None, "complete": None},
        "source": {"id": "native-source", "url": "https://example.test/statistics",
                   "input_sha256": "a" * 64, "selector": {}, "classification": "public_aggregate", "fields": {}},
        "quality": {"conflicts": [], "notes": []},
        "view": {"native_record": native or {}, "ballots": 7, "denominator": None,
                 "reported_pct": None, "source_update_label": "OLD CLOCK"}}
    row["id"] = observation_id("native-source", "general-2026", state + "-unit",
                               "native-statistics", "source_defined")
    return validate(row)


def mn_templates():
    unit = template(native={"county_id": "01", "precinct_id": "0001", "precinct_name": "UNIT"})
    parent = template(name="COUNTY", level="county", native={"native_county_id": "01"})
    parent["geography"]["id"] = "MN-county"
    parent["id"] = observation_id("native-source", "general-2026", "MN-county",
                                 "native-statistics", "source_defined")
    return [unit, parent]


def test_native_mn_zeros_unknowns_parent_scope_and_invented_clock_are_separate():
    templates = mn_templates()
    body = b"MN;01;0001;UNIT;1;10;0;0;0;0;0;0\n"
    result = granular.minnesota(body, templates)
    assert [row["value"] for row in result["updates"]] == [0, 0]
    assert all(row["clock"] is None for row in result["updates"])
    missing = granular.minnesota(body.replace(b";UNIT;1;", b";UNIT;0;"), templates)
    assert all(row["value"] is None for row in missing["updates"])
    assert missing["county_queries"][0]["reported_subtotal"] == 0
    for changed in (body + body, body.replace(b";UNIT;", b";RENAMED;"),
                    body.replace(b";10;", b";;"), body.replace(b";10;", b";-1;")):
        with pytest.raises(ValueError):
            granular.minnesota(changed, templates)


def test_successor_preserves_identity_views_holds_and_previous_bodies():
    templates = mn_templates()
    shard = {"records": templates, "views": {"official": {"counties": [templates[1]["id"]],
             "precincts": [templates[0]["id"]]}}}
    body = gzip.compress(encoded(shard), mtime=0)
    index = {"states": {"MN": {"file": "states/MN.json.gz", **pin(body)}}}
    baseline = {"index.json": encoded(index), "states/MN.json.gz": body}
    original = copy.deepcopy(baseline)
    facts = granular.minnesota(b"MN;01;0001;UNIT;1;10;0;0;0;0;0;9\n", templates)
    entries = {"MN-native-local": {"status": "reported", "data": facts,
               "source": {"url": granular.MN_URL, **pin(b"native")}}}
    updated, changes = granular.project(baseline, entries)
    result = json.loads(gzip.decompress(updated["states/MN.json.gz"]))
    assert baseline == original
    assert result["views"] == shard["views"]
    assert [row["id"] for row in result["records"]] == [row["id"] for row in templates]
    assert [row["count"]["value"] for row in result["records"]] == [9, 9]
    assert all(row["denominator"] is None and row["source_clock"]["literal"] is None
               for row in result["records"])
    assert all(row["view"]["automatic_source_refresh"] is True for row in result["records"])
    assert len(changes) == 2
    assert granular.project(updated, entries) == (updated, [])
    for row in result["records"]:
        validate(row)


def test_ct_native_parent_checks_every_town_and_keeps_vv_not_ballot_alias():
    fields = ("EV", "VV", "ABR", "ABC", "EBR", "EBC", "EDR", "EDC")
    turnout = {str(i): dict.fromkeys(fields, "1") for i in range(1, 170)}
    for i, row in turnout.items():
        row["NM"] = "Town " + i
    turnout["170"] = {**dict.fromkeys(fields, "169"), "NM": "Total"}
    status = {str(i): {"TS": "Unofficial", "PR": ""} for i in range(1, 170)}
    town = template("CT", "Town 1", "municipality")
    town["view"]["source_town_id"] = "1"
    elections = [{"ID": "108", "Name": "11/03/2026 -- November 2026 State Election"}]
    result = granular.connecticut(turnout, {"ID": "108", "BC": "169", "RV": "169"},
                                  elections, status, [town])
    assert result["updates"][0]["value"] == 1
    assert result["updates"][0]["registered"] is None
    assert result["updates"][0]["native"]["town_status"]["PR"] == ""
    turnout["2"]["ABC"] = "2"
    with pytest.raises(ValueError, match="Total"):
        granular.connecticut(turnout, {"ID": "108", "BC": "169", "RV": "169"},
                             elections, status, [town])


def test_failed_capture_with_older_retained_facts_never_rolls_back_last_good_website_counts():
    templates = mn_templates()
    body = gzip.compress(encoded({"records": templates}), mtime=0)
    baseline = {"states/MN.json.gz": body, "index.json": encoded({
        "states": {"MN": {"file": "states/MN.json.gz", **pin(body)}}})}
    facts = granular.minnesota(b"MN;01;0001;UNIT;1;10;0;0;0;0;0;6\n", templates)
    entry = {"status": "retained_after_failure", "data": facts,
             "source": {"url": granular.MN_URL, **pin(b"older-native-facts")},
             "error": "blocked_403"}
    assert granular.project(baseline, {"MN-native-local": entry}) == (baseline, [])
    assert entry["data"] == facts


def test_discovery_uses_anchor_scope_not_only_filename_and_rejects_person_files():
    assert granular.eligible_product({"url": "https://official.test/2026/general/export.csv", "text": ""})
    assert granular.eligible_product({"url": "https://official.test/export.csv",
                                     "text": "November 3 2026 general county results"})
    for text in ("2026 general CVR", "2026 general voter file", "2026 general primary",
                 "2026 general sample ballots", "2024 general precinct results",
                 "VoterGuide_2026_General_English.pdf"):
        assert not granular.eligible_product({"url": "https://official.test/data.csv", "text": text})
    with pytest.raises(ValueError, match="Individual"):
        granular.factual_tables(b"VoterID,StreetAddress\n1,private\n", "general.csv")
    result = granular.factual_tables(b"County,Precinct,Party,Votes\nA,01,D,0\nA,01,R,2\n", "general.csv")
    assert len(result["tables"][0]["rows"]) == 2
    assert result["numerical_data_qualified"] is False
    assert result["candidate_votes_are_ballots"] is False


def test_declared_zip_keeps_complete_tabular_queries_without_extracting_paths():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("results.csv", "County,Precinct,Votes\nA,1,0\n")
        archive.writestr("../escape.csv", "A,B\n1,2\n")
        archive.writestr("cvr.csv", "VoterID,Vote\n1,secret\n")
    result = granular.factual_tables(buffer.getvalue(), "2026-general.zip")
    assert set(result["members"]) == {"results.csv"}
    assert result["members"]["results.csv"]["tables"][0]["rows"][0]["values"][-1] == "0"


def test_native_space_urls_and_utf16_statistical_files_are_not_rejected_as_schema_errors():
    url = "https://official.test/2026 General/summary.txt"
    assert granular.transport_url(url) == "https://official.test/2026%20General/summary.txt"
    assert granular.transport_url(granular.transport_url(url)) == granular.transport_url(url)
    body = "County\tPrecinct\tVotes\nA\t1\t0\n".encode("utf-16")
    result = granular.factual_tables(body, "summary.txt")
    assert result["tables"][0]["rows"][0]["values"][-1] == "0"


def test_workbook_inventory_retains_native_shapes_without_promoting_unknown_measure(monkeypatch):
    from scripts import native_tabular
    monkeypatch.setattr(native_tabular, "xls", lambda body: [
        {"name": "Statistics", "nrows": 4, "ncols": 9, "rows": []},
        {"name": "Native results", "nrows": 30, "ncols": 8, "rows": []}])
    result = granular.factual_tables(b"held bytes", "general.xls")
    assert result["native_inventory"] == [
        {"name": "Statistics", "rows": 4, "columns": 9},
        {"name": "Native results", "rows": 30, "columns": 8}]
    assert result["numerical_data_qualified"] is False


def test_complete_workbook_cells_survive_nested_zip_with_formula_cache_zero_and_blank(monkeypatch):
    from scripts import native_tabular
    tables = [{"name": "Statistics", "nrows": 3, "ncols": 2, "rows": [
        {"row": 1, "cells": [{"address": "A1", "value": "Native count"}]},
        {"row": 2, "cells": [{"address": "B2", "value": 0, "cached_value": "0",
                              "formula": {"text": "SUM(B3:B3)"}}]},
        {"row": 3, "cells": [{"address": "B3", "value": None}]}]}]
    monkeypatch.setattr(native_tabular, "xls", lambda body: tables)
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr("statistics.xls", b"native workbook")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr("county.zip", inner.getvalue())
    result = granular.factual_tables(outer.getvalue(), "2026-general.zip")
    workbook = result["members"]["county.zip"]["members"]["statistics.xls"]
    assert workbook["tables"] == tables
    assert workbook["complete_native_cells_retained"] is True
    assert workbook["numerical_data_qualified"] is False


def test_private_workbook_header_is_checked_beyond_sheet_inventory(monkeypatch):
    from scripts import native_tabular
    monkeypatch.setattr(native_tabular, "xls", lambda body: [
        {"name": "Records", "nrows": 1, "ncols": 1,
         "rows": [{"row": 1, "cells": [{"address": "A1", "value": "VoterID"}]}]}])
    with pytest.raises(ValueError, match="Individual"):
        granular.factual_tables(b"private workbook", "general.xls")


def test_nested_json_retains_full_native_values_but_rejects_private_or_duplicate_keys():
    body = {"election": {"year": 2026}, "counties": {
        "A": {"precincts": [{"count": 0}, {"count": None}]}}}
    result = granular.factual_tables(encoded(body), "general.json")
    assert result["native_json"] == body
    assert result["numerical_data_qualified"] is False
    body["counties"]["A"]["precincts"][0]["VoterID"] = "excluded"
    with pytest.raises(ValueError, match="Individual"):
        granular.factual_tables(encoded(body), "general.json")
    with pytest.raises(ValueError, match="Duplicate"):
        granular.factual_tables(b'{"counties":{"A":0,"A":1}}', "general.json")


def test_html_tables_keep_source_spans_and_zero_without_copying_application_code():
    body = (b'<script>excluded application</script><table id="statistics" onclick="excluded()">'
            b'<tr><th colspan="2">Native statistics</th></tr>'
            b'<tr><td>County A</td><td>0</td></tr></table>')
    result = granular.factual_tables(body, "general.aspx")
    table = result["tables"][0]
    assert table["rows"][0]["cells"][0]["attributes"] == {"colspan": "2"}
    assert table["rows"][1]["cells"][1]["value"] == "0"
    assert "excluded" not in json.dumps(result)
    with pytest.raises(ValueError, match="nested"):
        granular.factual_tables(b"<table><tr><td><table></table></td></tr></table>", "general.html")


def test_nested_archive_budget_and_duplicate_members_fail_without_partial_queries():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("one.csv", "COUNT\n0\n")
    with pytest.raises(ValueError, match="size/inventory"):
        granular.factual_tables(buffer.getvalue(), "general.zip",
                                _budget={"bytes": 1, "members": 1000})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("one.csv", "COUNT\n0\n")
        with pytest.warns(UserWarning):
            archive.writestr("one.csv", "COUNT\n1\n")
    with pytest.raises(ValueError, match="size/inventory"):
        granular.factual_tables(buffer.getvalue(), "general.zip")
