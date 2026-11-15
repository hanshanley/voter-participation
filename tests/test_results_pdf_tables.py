import copy
import gzip
import json

import pytest

from scripts import results_granular as granular, results_native as native
from scripts import results_pdf_tables as pdf
from scripts.participation_intake.contract import encoded, observation_id, pin
from test_results_granular import template
from test_results_native import pdf_reader


def source(layout):
    return next((url, profile) for url, profile in pdf.PROFILES.items() if profile["layout"] == layout)


def record(url, profile, name, level, facts=None):
    row = template(profile["state"], name, level, facts)
    row["measure"] = copy.deepcopy(profile["measure"])
    row["geography"]["id"] = profile["state"] + ":" + name
    row["id"] = observation_id(row["source"]["id"], row["election"]["id"],
                               row["geography"]["id"], row["measure"]["id"], row["measure"]["mode"])
    row["source_clock"]["literal"] = "11/03/2026 10:00PM"
    row["source"]["url"] = url
    row["view"]["source_url"] = url
    return row


def county_body(value=9, clock="11/04/2026 10:00PM"):
    header = "\n".join(("Summary Results Report UNOFFICIAL RESULTS", "General Election",
                        "November 3, 2026 Wood County, WV"))
    statistics = "\n".join((
        "Statistics TOTAL", "Election Day Precincts Reporting 69 of 69",
        "Precincts Complete 69 of 69", "Precincts Partially Reported 0 of 69",
        "Absentee/ Early Precincts Reporting 69 of 69", "Registered Voters - Total 10",
        f"Ballots Cast - Total {value}", "Ballots Cast - Blank 0",
        f"Voter Turnout - Total {value * 10:.2f}%",
        "FOR A DIFFERENT CONTEST", "Total Votes Cast 999"))
    return ("\f".join(header + "\n" + (statistics if page == 1 else "FOR ANOTHER CONTEST")
            + f"\nElection Summary - {clock} Page {page} of 2" for page in (1, 2))).encode()


def city_body():
    url, profile = source("ward_columns")
    groups = [["1", "2", "3", "4", "4A"], ["1", "1A", "2", "3", "4"],
              ["1", "2", "3", "4"], ["1", "2", "2A", "3", "4"],
              ["1", "2", "3", "4"], ["1", "2", "3", "3A", "4"],
              ["1", "2", "3", "4"]]
    precincts = "Precinct " + " ".join(" ".join(group + ["TOTAL"]) for group in groups) + " Total"
    registered, ballots, records = [], [], [record(url, profile, "Somerville", "municipality")]
    for ward, group in enumerate(groups, 1):
        for precinct in group:
            registered.append(1)
            ballots.append(2)
            kind = "Subprecinct" if precinct.endswith("A") else "Precinct"
            records.append(record(url, profile, f"Ward {ward}, {kind} {precinct}", "reporting_unit",
                                  {"city": "Somerville", "ward": str(ward), "precinct": precinct}))
        registered.append(len(group))
        ballots.append(2 * len(group))
    registered.append(32)
    ballots.append(64)
    body = "\n".join((
        "Somerville UnOfficial Election Totals - Tuesday November 3, 2026",
        "Ward 1 Ward 2 Ward 3 Ward 4 Ward 5 Ward 6 Ward 7 Grand", precincts,
        "REGISTERED VOTERS - TOTAL", "REGISTERED VOTERS - TOTAL " + " ".join(map(str, registered)),
        "BALLOTS CAST - TOTAL", "BALLOTS CAST - TOTAL " + " ".join(map(str, ballots)),
        "A DIFFERENT CONTEST 999", "Tuesday, November 3, 2026 Page 1 of 1")).encode()
    return url, body, records


@pytest.mark.parametrize("value", [0, 9])
def test_county_pdf_refresh_uses_statistics_not_candidate_votes_and_keeps_counters(monkeypatch, value):
    pdf_reader(monkeypatch)
    url, profile = source("county_summary")
    row = record(url, profile, profile["parent"], "county")
    result = pdf.statistics(county_body(value), [row], url)
    update, = result["updates"]
    assert update["value"] == value and update["registered"] == 10
    assert not update["rate_compatible"]
    assert update["native"]["query"]["reporting_counters"]["Precincts Complete"]["reported"] == 69
    assert update["native"]["native_reporting_complete_qualified"] is False
    assert result["complete_native_query"]["statistics"][0]["blank"] == 0


@pytest.mark.parametrize("change", ["clock", "pages", "election", "label", "fraction", "duplicate", "counters"])
def test_county_pdf_rejects_mixed_pages_scope_statistics_and_rollback(monkeypatch, change):
    pdf_reader(monkeypatch)
    url, profile = source("county_summary")
    row = record(url, profile, profile["parent"], "county")
    body = county_body()
    if change == "clock":
        body = body.replace(b"11/04/2026", b"11/02/2026")
    elif change == "pages":
        body = body.replace(b"Page 2 of 2", b"Page 1 of 2")
    elif change == "election":
        body = body.replace(b"November 3, 2026", b"November 3, 2024")
    elif change == "label":
        body = body.replace(b"Ballots Cast - Total", b"Total Votes Cast")
    elif change == "fraction":
        body = body.replace(b"90.00%", b"91.00%")
    elif change == "duplicate":
        body = body.replace(b"Ballots Cast - Blank", b"Ballots Cast - Total 9\nBallots Cast - Blank")
    else:
        body = body.replace(b"Partially Reported 0 of 69", b"Partially Reported 1 of 69")
    with pytest.raises(ValueError):
        pdf.statistics(body, [row], url)


def test_city_precinct_columns_keep_split_identities_and_native_above_registration(monkeypatch):
    pdf_reader(monkeypatch)
    url, body, records = city_body()
    result = pdf.statistics(body, records, url)
    assert len(result["updates"]) == 33 and result["source_clock"] is None
    assert result["updates"][0]["value"] == 64
    assert result["updates"][0]["registered"] == 32
    assert all(not update["rate_compatible"] for update in result["updates"])
    assert {update["id"] for update in result["updates"]} == {row["id"] for row in records}
    assert next(update for update in result["updates"] if update["native"]["query"].get(
        "precinct") == "4A")["native"]["query"]["ward"] == "1"


@pytest.mark.parametrize("changed", ["1 1A 2 3 4", "BALLOTS CAST - TOTAL 2", "Page 1 of 1"])
def test_city_rejects_changed_native_header_count_or_page(monkeypatch, changed):
    pdf_reader(monkeypatch)
    url, body, records = city_body()
    body = body.replace(changed.encode(), (changed + " 0").encode(), 1)
    with pytest.raises(ValueError):
        pdf.statistics(body, records, url)


def test_collector_projection_repeat_and_last_good_failure_preserve_all51(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from scripts import results_intake as intake

    pdf_reader(monkeypatch)
    url, body, records = city_body()
    states, declarations = {}, {}
    for state in intake.STATES:
        rows = records if state == "MA" else [template(state)]
        shard = {"records": rows, "views": {"official": {"counties": [rows[0]["id"]],
                 "precincts": [row["id"] for row in rows[1:]], "nongeographic": []}}}
        name = "states/" + state + ".json.gz"
        states[name] = intake.compressed(encoded(shard))
        declarations[state] = {"file": name, **pin(states[name])}
    states["index.json"] = encoded({"states": declarations})
    def acquire(self, target):
        self.guard(target)
        if target != url:
            raise ValueError("No undeclared source acquisition")
        return body, {"url": url, "origin": "fixture_transport", **pin(body)}
    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    collector = intake.Collector(tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
                                 datetime(2026, 11, 14, tzinfo=timezone.utc))
    entries = native.collect_sources(collector, states)
    entry, = [value for value in entries.values() if value.get("adapter") == "reviewed_statistical_pdf"]
    assert entry["status"] == "reported" and len(entry["data"]["updates"]) == 33
    after, changed = granular.project(states, entries)
    assert len(changed) == 33
    assert all(states["states/" + state + ".json.gz"] == after["states/" + state + ".json.gz"]
               for state in intake.STATES if state != "MA")
    shard = json.loads(gzip.decompress(after["states/MA.json.gz"]))
    assert shard["views"] == json.loads(gzip.decompress(states["states/MA.json.gz"]))["views"]
    assert all(row["denominator"] is None and row["source_clock"]["literal"] is None
               for row in shard["records"])
    assert all(row["view"]["source_status_literal"] == "UnOfficial" for row in shard["records"])
    assert granular.project(after, entries) == (after, [])
    for value in entries.values():
        value["status"], value["data"] = "retained_after_failure", None
    assert granular.project(after, entries) == (after, [])


@pytest.mark.parametrize("change", ["source", "measure", "ward", "year"])
def test_pdf_template_guards_do_not_broaden_legacy_source_aliases(monkeypatch, change):
    pdf_reader(monkeypatch)
    url, body, records = city_body()
    if change == "source":
        records[0]["source"]["url"] = "https://unrelated.test/export.json"
    elif change == "measure":
        records[0]["measure"]["mode"] = "early_in_person"
    elif change == "ward":
        records[1]["view"]["native_record"]["ward"] = "2"
    else:
        records[0]["election"]["year"] = 2024
    with pytest.raises(ValueError):
        pdf.statistics(body, records, url)


def dover_fixture(monkeypatch):
    import fitz
    header = (
        "REGISTERED VOTERS/TURNOUT\nNOVEMBER 3, 2026 GENERAL ELECTION\n"
        "City of Dover, New Hampshire\nVOTER TURNOUT\n60.0%\n"
        "Ward\nPolling Place\nBallots\nAbsentee\nBallots\nTotal Ballots\nCast\n"
        "All Registered\nVoters\nTurnout\n")
    ballot_rows = [[str(ward), "2", "1", "3", "5", "60.0%"] for ward in range(1, 7)]
    ballot_rows.append(["TOTAL", "12", "6", "18", "30", "60.0%"])
    register_header = (
        "Ward\nChecklist\nRegistered\nRepublicans\nNew Republican\nRegistrations\n"
        "Checklist\nRegistered\nDemocratic\nNew Democratic\nRegistrations\n"
        "Checklist\nRegistered\nUndeclared\nNew Undeclared\nRegistrations\n"
        "All Checklist\nRegistered\nVoters\nTotal New\nVoters\nRegistrations\n"
        "Checklist and\nElection\nRegistered\nVoters\n")
    register_rows = [[str(ward), "1", "0", "1", "0", "1", "2", "3", "2", "5"]
                     for ward in range(1, 7)]
    register_rows.append(["TOTAL", "6", "0", "6", "0", "6", "12", "18", "12", "30"])
    state = {"text": header + "\n".join("\n".join(row) for row in ballot_rows)
             + "\n* Turnout is total ballots cast divided by total checklist and election day registered voters\n"
             + register_header + "\n".join("\n".join(row) for row in register_rows),
             "words": []}
    for top, boundaries, rows in (
            (208, (140, 180, 250, 305, 362, 425, 480), ballot_rows),
            (442, (30, 65, 130, 195, 245, 305, 360, 420, 475, 535, 590), register_rows)):
        for index, row in enumerate(rows):
            for value, left, right in zip(row, boundaries, boundaries[1:]):
                middle = (left + right) / 2
                state["words"].append((middle - 1, top + index * 11,
                                       middle + 1, top + index * 11 + 10, value, 0, 0, 0))
    class Page:
        def get_text(self, kind):
            return state[kind]
    class Document:
        def __len__(self):
            return 1
        def __getitem__(self, number):
            return Page()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    monkeypatch.setattr(fitz, "open", lambda **kwargs: Document())
    return state


def test_ward_rows_read_both_tables_without_candidate_or_registration_choice_inference(monkeypatch):
    dover_fixture(monkeypatch)
    _, profile = source("ward_rows")
    rows, query, clock = pdf.ward_rows(b"fixture", profile)
    assert len(rows) == len(query["registrations"]) == 7
    assert rows["Dover"]["count"] == 18 and rows["Dover"]["registered"] == 30
    assert query["registration_affiliation_is_not_vote_choice"] and clock is None


@pytest.mark.parametrize("change", ["header", "physical_column", "parent"])
def test_ward_rows_reject_reordered_physical_cells_and_bad_registers(monkeypatch, change):
    state = dover_fixture(monkeypatch)
    _, profile = source("ward_rows")
    if change == "header":
        state["text"] = state["text"].replace("Absentee\nBallots", "Candidate\nVotes")
    elif change == "physical_column":
        word = list(state["words"][1])
        word[0], word[2] = 270, 272
        state["words"][1] = tuple(word)
    else:
        state["text"] = state["text"].replace("\n30\n60.0%", "\n31\n60.0%")
    with pytest.raises(ValueError):
        pdf.ward_rows(b"fixture", profile)


def test_reporting_parts_accept_new_date_but_refuse_mixed_page_dates(monkeypatch):
    from scripts import native_pdf, pdf_group_queries
    profile = json.loads(pdf.Path(pdf.__file__).with_name("results_pdf_grids.json").read_bytes())
    pages = [{"page": number, "glyphs": []} for number in range(1, 14)]
    dates = {number: "11/12/2026" for number in range(1, 14)}
    monkeypatch.setattr(native_pdf, "read", lambda body: {"pages": pages})
    monkeypatch.setattr(native_pdf, "text", lambda page, box: {"decoded_text": dates[page["page"]]})
    monkeypatch.setattr(native_pdf, "project", lambda facts, grid: {
        "id": grid["id"], "source_page": grid["page"], "rows": [],
        "source_annotations": grid["source_annotations"]})
    row = {"parent": "COUNTY", "native_unit": "TOWN", "registered_voters": 10,
           "total_votes_cast_includes_absentee": 7, "absentee_votes_cast": 3,
           "rep_district": "PART\nA", "senate_district": "S"}
    grouped = {"queries": {name: {"rows": [row]} for name in profile["grouping"]["expected_rows"]},
               "native_rate_checks": []}
    monkeypatch.setattr(pdf_group_queries, "build", lambda *args: grouped)
    rows, queries, date = pdf.reporting_parts(b"fixture")
    assert date == "11/12/2026" and rows["TOWN"]["count"] == 7
    assert rows["TOWN"]["source_parts"][0]["rep_district"] == "PART\nA"
    dates[13] = "11/09/2026"
    with pytest.raises(ValueError, match="page clocks"):
        pdf.reporting_parts(b"fixture")
    dates[13] = "11/12/2026"
    pages[0]["glyphs"] = [{"id": [999, 0, 0, 0], "text": "0",
                            "reading_bbox": [260, 745, 265, 749]}]
    with pytest.raises(ValueError, match="unselected native numerical"):
        pdf.reporting_parts(b"fixture")
