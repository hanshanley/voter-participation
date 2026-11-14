import copy
import importlib.util
import io
import os
from pathlib import Path
import re
import zipfile

import pytest

from scripts import results_granular as granular
from scripts.participation_intake.contract import pin


def candidate_module():
    path = Path(__file__).resolve().parents[1] / "scripts/results_native.py"
    spec = importlib.util.spec_from_file_location("candidate_results_native", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


native = candidate_module()
BASELINE = Path(os.environ.get("WORKBOOK_NATIVE_BASELINE", ""))
SOURCES = {
    native.CO_WORKBOOK_URL: Path(os.environ.get("WORKBOOK_NATIVE_CO", "")),
    native.WAYNE_MAIN_URL: Path(os.environ.get("WORKBOOK_NATIVE_WAYNE_MAIN", "")),
    native.WAYNE_SUPPLEMENT_URL: Path(os.environ.get("WORKBOOK_NATIVE_WAYNE_SUPPLEMENT", "")),
}


@pytest.fixture(scope="module")
def baseline():
    if not BASELINE.is_dir() or any(not path.is_file() for path in SOURCES.values()):
        pytest.skip("retained workbook originals and accepted baseline are required")
    return {str(path.relative_to(BASELINE)): path.read_bytes()
            for path in BASELINE.rglob("*") if path.is_file()}


@pytest.fixture(scope="module")
def planned(baseline):
    plan = native.source_plan(baseline)
    return {
        source["url"]: (identity, source)
        for sources in plan.values()
        for identity, source in sources.items()
        if source["url"] in SOURCES
    }


def parsed(planned, url, body=None, templates=None):
    _, source = planned[url]
    return native.workbook_statistics(
        SOURCES[url].read_bytes() if body is None else body,
        source["templates"] if templates is None else templates,
        native.WORKBOOK_PROFILES[url],
    )


def replace_zip_text(body, old, new):
    source, output, replacements = io.BytesIO(body), io.BytesIO(), 0
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(output, "w") as after:
        for item in before.infolist():
            value = before.read(item.filename)
            count = value.count(old)
            replacements += count
            after.writestr(item, value.replace(old, new))
    assert replacements
    return output.getvalue()


def replace_cell_cache(body, sheet, address, replacement):
    from scripts.native_tabular import xlsx

    member = next(table["member"] for table in xlsx(body) if table["name"] == sheet)
    source, output, changed = io.BytesIO(body), io.BytesIO(), False
    pattern = re.compile(
        rb'(<c\b[^>]*\br="' + re.escape(address.encode()) + rb'"[^>]*>.*?<v>)(.*?)(</v>)',
        re.S,
    )
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(output, "w") as after:
        for item in before.infolist():
            value = before.read(item.filename)
            if item.filename == member:
                value, count = pattern.subn(
                    lambda match: match.group(1) + replacement + match.group(3), value, count=1)
                changed = count == 1
            after.writestr(item, value)
    assert changed
    return output.getvalue()


def cells(number, values):
    return [dict(address=column + str(number), value=value, cached_literal=None,
                 storage_type="inlineStr" if isinstance(value, str) else "n",
                 attributes={"r": column + str(number)}, formula=None)
            for column, value in values.items()]


def county_workbook(first=5, zero_index=None, blank_index=None, changed_header=False):
    names = [f"County {number:02d}" for number in range(1, 65)]
    workbook, modes = [], {
        "All_Returned_Ballots_By_County": [first] + [1] * 63,
        "Returned_Mail_Ballots_By_County": [3] + [1] * 63,
        "In_Person_Ballots_By_County": [first - 3] + [0] * 63,
    }
    if zero_index is not None:
        for values in modes.values():
            values[zero_index] = 0
    for sheet in native.WORKBOOK_PROFILES[native.CO_WORKBOOK_URL]["sheets"]:
        if sheet not in native.COUNTY_WORKBOOK_SHEETS:
            workbook.append(dict(name=sheet, rows=[]))
            continue
        headings = {column: label for label, column in native.COUNTY_WORKBOOK_FIELDS.items()}
        headings["A"] = "COUNTY"
        if changed_header and sheet == "All_Returned_Ballots_By_County":
            headings["M"] = "Changed Total"
        rows = [
            dict(row=1, cells=cells(1, {
                "A": native.COUNTY_WORKBOOK_SHEETS[sheet]})),
            dict(row=2, cells=cells(2, headings)),
        ]
        totals = {field: 0 for field in list(native.COUNTY_WORKBOOK_FIELDS)[1:]}
        for index, (name, value) in enumerate(zip(names, modes[sheet]), 3):
            record = {field: 0 for field in list(native.COUNTY_WORKBOOK_FIELDS)[1:-1]}
            record["ACN"] = value
            record["Grand Total"] = value
            totals = {field: totals[field] + record[field] for field in totals}
            values = {"A": name, **{
                native.COUNTY_WORKBOOK_FIELDS[field]: item
                for field, item in record.items()
                if not (blank_index == index - 3 and field == "Grand Total"
                        and sheet == "All_Returned_Ballots_By_County")
            }}
            rows.append(dict(row=index, cells=cells(index, values)))
        rows.append(dict(row=67, cells=cells(67, {"A": "Grand Total", **{
            native.COUNTY_WORKBOOK_FIELDS[field]: value
            for field, value in totals.items()}})))
        rows.append(dict(row=68, cells=cells(68, {"A": "end of worksheet"})))
        workbook.append(dict(name=sheet, rows=rows))
    templates = []
    for index, name in enumerate(names, 3):
        reviewed = {}
        for sheet in native.COUNTY_WORKBOOK_SHEETS:
            reviewed[sheet] = {
                "county": name, "native_excel_row": index, "native_record": {}}
        templates.append({
            "id": f"co-{index}", "count": {"status": "reported", "value": 1},
            "denominator": None,
            "election": {"year": 2026, "type": "general"},
            "geography": {"state_code": "CO", "level": "county", "name": name + " County"},
            "measure": {"literal": "Returned and processed ballots (native all-returned total)"},
            "view": {"native_record": reviewed},
        })
    return workbook, templates


def wayne_workbook_and_templates():
    from scripts.native_products import query, statistical_units

    profile = {
        "state": "MI", "kind": "statistical_mode_blocks", "product": "synthetic-wayne",
        "query_id": "synthetic-wayne-statistics", "sheet": "Stats", "first_row": 8,
        "modes": ["Early Voting", "Election Day", "Absentee"],
        "parents": ["Wayne County - Total", "County - Total"], "expected_units": 2,
    }
    rows = [
        dict(row=1, cells=[dict(address="H1", value="46332.356106122701",
            cached_literal="46332.356106122701", storage_type="n",
            attributes={"r": "H1", "s": "0"}, formula=None)]),
        dict(row=5, cells=cells(5, {
            "A": "Precinct", "B": "Registered\nVoters",
            "D": "Voters Cast", "F": "% Turnout"})),
    ]
    source = [
        (8, "Unit A", None, None, None),
        (9, "Early Voting", 10, 0, 0),
        (10, "Election Day", 10, 2, "0.2"),
        (11, "Absentee", 10, 0, 0),
        (12, "Total", 10, 2, "0.2"),
        (13, "Unit B", None, None, None),
        (14, "Early Voting", 20, 1, "0.05"),
        (15, "Election Day", 20, 3, "0.15"),
        (16, "Absentee", 20, 0, 0),
        (17, "Total", 20, 4, "0.2"),
        (18, "Wayne County - Total", 30, 6, "0.2"),
        (19, "County - Total", 30, 6, "0.2"),
        (20, "Early Voting", 30, 1, "0.0333333333333333"),
        (21, "Election Day", 30, 5, "0.166666666666667"),
        (22, "Absentee", 30, 0, 0),
    ]
    for number, label, registered, cast, fraction in source:
        values = {"A": label}
        if registered is not None:
            values.update(B=registered, D=cast, F=fraction)
        rows.append(dict(row=number, cells=cells(number, values)))
    table = dict(name="Stats", rows=rows, workbook_properties={},
        workbook_cell_formats=[{"numFmtId": "164"}],
        workbook_number_formats={"164": r"[$-10409]m/d/yyyy\ h:mm:ss\ AM/PM"})
    selection = {
        "id": profile["query_id"], "product": profile["product"], "tables": ["Stats"],
        "fields": {
            "column_A": "A", "column_B": "B", "column_C": "C", "column_D": "D",
            "column_E": "E", "column_F": "F", "column_G": "G", "column_H": "H",
            "native_row": "$row", "native_table": "$table",
        },
        "keys": ["native_table", "native_row"],
        "require": {"5": {
            "A": "Precinct", "B": "Registered\nVoters",
            "D": "Voters Cast", "F": "% Turnout"}},
    }
    source_query = query({"tables": [dict(kind="worksheet", **table)]}, selection)
    grouping = statistical_units(source_query, {
        "first_row": 8, "modes": profile["modes"], "parents": profile["parents"],
        "fields": {"row": "native_row", "label": "column_A", "registered": "column_B",
                   "cast": "column_D", "fraction": "column_F"},
    })
    clock = {
        "cached_literal": "46332.356106122701", "cell": "H1", "date_system": "1900",
        "literal": "2026-11-06T08:32:47.569 (decoded Excel cache; timezone not supplied)",
        "number_format": r"[$-10409]m/d/yyyy\ h:mm:ss\ AM/PM",
        "qualification": "decoded_native_worksheet_cache_not_printed_text",
        "timezone": None,
    }
    templates = [{
        "id": "mi-" + unit["unit"], "count": {"status": "reported", "value": unit["cast"]},
        "denominator": None, "election": {"year": 2026, "type": "general"},
        "geography": {"state_code": "MI", "level": "reporting_unit", "name": unit["unit"]},
        "measure": {"literal": "Voters Cast (reported statistical units)"},
        "view": {"native_record": {
            "source_product": profile["product"], "native_clock": clock,
            "native_unit": unit, "native_parent": grouping["parent"],
            "agreeing_native_parent_copies": grouping["agreeing_native_parent_copies"],
        }},
    } for unit in grouping["units"]]
    return [table], templates, profile


def test_portable_count_change_flows_through_complete_mode_and_parent_controls():
    workbook, templates = county_workbook(first=5)
    result = native.county_mode_statistics(
        b"synthetic", templates, native.WORKBOOK_PROFILES[native.CO_WORKBOOK_URL], workbook)
    assert result["updates"][0]["value"] == 5
    parents = {row["mode"]: row["native_record"]["Grand Total"]
               for row in result["complete_native_query"] if row["county"] == "Grand Total"}
    assert parents["All_Returned_Ballots_By_County"] == (
        parents["Returned_Mail_Ballots_By_County"]
        + parents["In_Person_Ballots_By_County"])


def test_portable_true_zero_is_retained_but_blank_count_is_held():
    workbook, templates = county_workbook(zero_index=1)
    result = native.county_mode_statistics(
        b"synthetic", templates, native.WORKBOOK_PROFILES[native.CO_WORKBOOK_URL], workbook)
    assert result["updates"][1]["value"] == 0
    blank, templates = county_workbook(blank_index=1)
    with pytest.raises(ValueError, match="blank"):
        native.county_mode_statistics(
            b"synthetic", templates, native.WORKBOOK_PROFILES[native.CO_WORKBOOK_URL], blank)


def test_portable_changed_header_and_election_scope_are_held():
    workbook, templates = county_workbook(changed_header=True)
    with pytest.raises(ValueError, match="columns"):
        native.county_mode_statistics(
            b"synthetic", templates, native.WORKBOOK_PROFILES[native.CO_WORKBOOK_URL], workbook)
    workbook, templates = county_workbook()
    templates[0]["election"]["type"] = "primary"
    with pytest.raises(ValueError, match="scope"):
        native.county_mode_statistics(
            b"synthetic", templates, native.WORKBOOK_PROFILES[native.CO_WORKBOOK_URL], workbook)


def test_portable_wayne_component_clocks_cannot_be_collapsed():
    workbook, templates, profile = wayne_workbook_and_templates()
    templates[1]["view"]["native_record"]["native_clock"] = {
        **templates[1]["view"]["native_record"]["native_clock"],
        "literal": "2026-11-06T11:57:18.452 (decoded Excel cache; timezone not supplied)",
    }
    with pytest.raises(ValueError, match="distinct component identity"):
        native.statistical_workbook_statistics(b"synthetic", templates, profile, workbook)


def test_actual_plan_assigns_distinct_shared_workbook_roles_and_all_templates(planned):
    expected = {
        native.CO_WORKBOOK_URL: 64,
        native.WAYNE_MAIN_URL: 758,
        native.WAYNE_SUPPLEMENT_URL: 12,
    }
    assert set(planned) == set(expected)
    for url, count in expected.items():
        _, source = planned[url]
        assert source["adapter"] == "reviewed_workbook_statistics"
        assert len(source["templates"]) == count
    assert native.WORKBOOK_PROFILES[native.WAYNE_MAIN_URL]["product"] == "wayne-main"
    assert native.WORKBOOK_PROFILES[native.WAYNE_SUPPLEMENT_URL]["product"] == (
        "wayne-three-localities")


def test_actual_workbooks_preserve_modes_zeros_blanks_and_distinct_clocks(planned):
    colorado = parsed(planned, native.CO_WORKBOOK_URL)
    main = parsed(planned, native.WAYNE_MAIN_URL)
    supplement = parsed(planned, native.WAYNE_SUPPLEMENT_URL)
    assert (len(colorado["updates"]), sum(row["value"] for row in colorado["updates"])) == (
        64, 2761449)
    assert [row["native_statistical_units"]["parent"]["cast"] for row in (main, supplement)] == [
        724872, 22132]
    assert (len(main["updates"]), len(supplement["updates"])) == (758, 12)
    assert sum(row["value"] == 0 for row in main["updates"] + supplement["updates"]) == 3
    assert main["updates"][0]["clock"] == (
        "2026-11-06T08:32:47.569 (decoded Excel cache; timezone not supplied)")
    assert supplement["updates"][0]["clock"] == (
        "2026-11-06T11:57:18.452 (decoded Excel cache; timezone not supplied)")
    assert all(row["registered"] is None and not row["rate_compatible"]
               for row in main["updates"] + supplement["updates"])
    blank = replace_cell_cache(SOURCES[native.WAYNE_MAIN_URL].read_bytes(), "Stats", "D13", b"")
    with pytest.raises(ValueError, match="blank|recorded count"):
        parsed(planned, native.WAYNE_MAIN_URL, blank)


@pytest.mark.parametrize(("url", "old", "new"), [
    (native.CO_WORKBOOK_URL, b"Adams", b"Changed Adams"),
    (native.CO_WORKBOOK_URL, b"Grand Total", b"Changed Total"),
    (native.WAYNE_MAIN_URL, b"Voters Cast", b"Changed Cast"),
])
def test_malformed_reviewed_rows_columns_and_headers_are_held(planned, url, old, new):
    changed = replace_zip_text(SOURCES[url].read_bytes(), old, new)
    with pytest.raises(ValueError):
        parsed(planned, url, changed)


@pytest.mark.parametrize("url", [
    native.CO_WORKBOOK_URL, native.WAYNE_MAIN_URL, native.WAYNE_SUPPLEMENT_URL,
])
def test_election_scope_and_clock_regressions_are_held(planned, url):
    _, source = planned[url]
    templates = copy.deepcopy(source["templates"])
    templates[0]["election"]["type"] = "primary"
    with pytest.raises(ValueError, match="scope"):
        parsed(planned, url, templates=templates)
    if url != native.CO_WORKBOOK_URL:
        body = SOURCES[url].read_bytes()
        sheet = native.WORKBOOK_PROFILES[url]["sheet"]
        changed = replace_cell_cache(body, sheet, "H1", b"46331.000000000000")
        with pytest.raises(ValueError, match="regressed"):
            parsed(planned, url, changed)


def test_actual_retained_plan_projects_all_834_existing_ids_without_network(baseline, planned):
    class RetainedCollector:
        network_acquisitions = 0

        def capture(self, identity, url, parse):
            if url not in SOURCES:
                return {"status": "source_stopped", "data": None,
                        "source": {"url": url, "origin": "offline_hold"}}
            body = SOURCES[url].read_bytes()
            return {"status": "reported", "data": parse(body),
                    "source": {"url": url, "origin": "retained_original", **pin(body)}}

    collector = RetainedCollector()
    entries = native.collect_sources(collector, baseline)
    assert collector.network_acquisitions == 0
    for url, (identity, _) in planned.items():
        assert entries[identity]["status"] == "reported"
        assert entries[identity]["adapter"] == "reviewed_workbook_statistics"
    after, changes = granular.project(baseline, entries)
    assert len(changes) == 834
    assert {row["state_code"] for row in changes} == {"CO", "MI"}
    assert sum(row["previous"] != row["current"] for row in changes) == 0
    assert sum(row["current"] for row in changes if row["state_code"] == "CO") == 2761449
    assert sum(row["current"] for row in changes if row["state_code"] == "MI") == 747004
    assert after["index.json"] != baseline["index.json"]
