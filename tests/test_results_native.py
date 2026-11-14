import copy
from datetime import datetime, timezone
import gzip
import json

import pytest

from scripts import results_granular as granular, results_native as native, results_intake as intake
from scripts.participation_intake.contract import IntakeError, encoded, pin, validate
from test_results_granular import template


def baseline(states):
    bodies, declarations = {}, {}
    for state in states:
        row = template(state, state + " County", "county")
        row["measure"]["literal"] = "Ballots Cast - Total"
        row["view"]["source_url"] = "https://" + state.lower() + ".official.test/2026-general.pdf"
        row["source_clock"]["literal"] = "11/03/2026 10:00PM"
        shard = {"records": [row], "views": {"official": {"counties": [row["id"]]}}}
        name = "states/" + state + ".json.gz"
        bodies[name] = intake.compressed(encoded(shard))
        declarations[state] = {"file": name, **pin(bodies[name])}
    bodies["index.json"] = encoded({"states": declarations})
    return bodies


def pdf_text(state, value=9):
    return ("\n".join(("Summary Results Report", state + " County", "General Election",
        "November 3, 2026", "TOTAL Election Day Absentee", "Registered Voters - Total 100",
        "Ballots Cast - Total " + str(value), "11/04/2026 10:00PM"))).encode()


def pdf_reader(monkeypatch):
    import pypdf
    class Page:
        def __init__(self, value):
            self.value = value
        def extract_text(self, **kwargs):
            return self.value
    class Reader:
        def __init__(self, stream):
            self.is_encrypted = False
            self.pages = [Page(stream.read().decode())]
    monkeypatch.setattr(pypdf, "PdfReader", Reader)


def test_shared_pdf_adapter_collects_and_projects_all51_without_state_branches(tmp_path, monkeypatch):
    pdf_reader(monkeypatch)
    before = baseline(intake.STATES)
    def acquire(self, url):
        self.guard(url)
        state = url.split("//")[1].split(".")[0].upper()
        body = pdf_text(state, 0 if state == "DC" else 9)
        return body, {"url": url, "origin": "fixture_transport", **pin(body)}
    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    collector = intake.Collector(tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
                                 datetime(2026, 11, 14, tzinfo=timezone.utc))
    plan = native.source_plan(before)
    assert set(plan) == set(intake.STATES)
    assert all(len(sources) == 1 for sources in plan.values())
    entries = native.collect_sources(collector, before)
    after, changes = granular.project(before, entries)
    assert len(entries) == len(changes) == 51
    for state in intake.STATES:
        old = json.loads(gzip.decompress(before["states/" + state + ".json.gz"]))
        current = json.loads(gzip.decompress(after["states/" + state + ".json.gz"]))
        assert current["views"] == old["views"]
        row = current["records"][0]
        assert row["id"] == old["records"][0]["id"]
        assert row["geography"] == old["records"][0]["geography"]
        assert row["count"]["value"] == (0 if state == "DC" else 9)
        assert row["measure"] == old["records"][0]["measure"]
        assert row["denominator"] is None
        validate(row)


def test_one_failed_state_does_not_stop_others_or_roll_back_retained_counts(tmp_path, monkeypatch):
    pdf_reader(monkeypatch)
    before = baseline(("NY", "TX", "MI"))
    def acquire(self, url):
        self.guard(url)
        state = url.split("//")[1].split(".")[0].upper()
        if state == "TX":
            raise IntakeError("source_stopped", "Persisted access hold")
        body = pdf_text(state)
        return body, {"url": url, "origin": "fixture_transport", **pin(body)}
    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    collector = intake.Collector(tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
                                 datetime(2026, 11, 14, tzinfo=timezone.utc))
    entries = native.collect_sources(collector, before)
    after, changes = granular.project(before, entries)
    assert {row["state_code"] for row in changes} == {"NY", "MI"}
    assert after["states/TX.json.gz"] == before["states/TX.json.gz"]
    assert next(row for key, row in entries.items() if key.startswith("TX-"))["data"] is None


@pytest.mark.parametrize("change", [
    lambda text: text.replace(b"General Election", b"Primary Election"),
    lambda text: text.replace(b"November 3, 2026", b"November 5, 2024"),
    lambda text: text.replace(b"NY County", b"TX County"),
    lambda text: text.replace(b"TOTAL Election Day Absentee", b"Election Day TOTAL Absentee"),
    lambda text: text.replace(b"Ballots Cast - Total 9", b"Candidate Votes 9"),
    lambda text: text.replace(b"Ballots Cast - Total 9", b"Ballots Cast - Total 2.5"),
    lambda text: text.replace(b"11/04/2026 10:00PM", b"11/02/2026 10:00PM"),
])
def test_pdf_scope_column_measure_and_edition_mutations_are_held(monkeypatch, change):
    pdf_reader(monkeypatch)
    row = granular.selected_records(baseline(("NY",)), "NY")[0]
    with pytest.raises(ValueError):
        native.pdf_parent_statistics(change(pdf_text("NY")), [row])


@pytest.mark.parametrize("state", ["NY", "TX", "MI"])
def test_record_family_is_state_agnostic_and_preserves_zeros_and_native_units(state):
    row = template(state, "County A", "county", {"query": {"county_id": "01"}})
    profile = {"state": state, "query_id": "reviewed-statistics", "identity": "code",
               "name": "county", "count": "NativeCount", "registered": "Register",
               "template_identity": ("query", "county_id")}
    body = encoded([{"code": "01", "county": "County A", "NativeCount": 0, "Register": 10}])
    result = native.record_statistics(body, [row], profile)
    assert result["updates"][0]["value"] == 0
    assert result["updates"][0]["clock"] is None
    assert result["updates"][0]["registered"] == 10
    assert result["native_measure_not_relabelled_as_ballots"] is True
    for mutation in (body.replace(b'"NativeCount":0', b'"NativeCount":true'),
                     body.replace(b'"01"', b'"02"'),
                     body.replace(b'"County A"', b'"County B"')):
        with pytest.raises(ValueError):
            native.record_statistics(mutation, [row], profile)
    wrong_state = copy.deepcopy(profile)
    wrong_state["state"] = "AL"
    with pytest.raises(ValueError, match="scope"):
        native.record_statistics(body, [row], wrong_state)


def test_california_family_requires_complete_county_state_closure_and_general_election():
    row = template("CA", "County A", "county", {"query": {"county_id": "1"}})
    profile = native.RECORD_PROFILES[native.CA_URL]
    county = {"county": 1, "countyName": "County A", "voterTurnout": "9",
              "totalRegisteredVoters": "10", "timestamp": "November 4, 2026",
              "precinctsReporting": "1", "precinctsTotal": "1",
              "firstReportTimestamp": "202611032001", "lastReportTimestamp": "202611041200"}
    parent = {**county, "county": 59, "countyName": "Statewide"}
    result = native.record_statistics(encoded([county, parent]), [row], profile)
    assert len(result["complete_native_query"]) == 2
    assert result["updates"][0]["value"] == 9
    for values in ([county], [county, {**parent, "voterTurnout": "10"}],
                   [{**county, "firstReportTimestamp": "202606021200"}, parent],
                   [county, county, parent]):
        with pytest.raises(ValueError):
            native.record_statistics(encoded(values), [row], profile)


def test_indiana_keeps_false_zero_holds_and_independent_overrides():
    reported = template("IN", "Adams County", "county", {"County": "Adams"})
    unknown = template("IN", "Allen County", "county", {"County": "Allen"})
    unknown["count"] = {"status": "unknown", "value": None, "literal": None}
    for row in (reported, unknown):
        row["source_clock"]["literal"] = (
            "Voter statistics WriteTime: 2026-11-09T15:03:29.353; timezone not supplied. "
            "Separate candidate control WriteTime: 2026-11-09T15:03:39.467.")
    profile = {**native.RECORD_PROFILES[native.IN_URL], "independent_overrides": ["Cass"]}
    def county(name, value, registered=10):
        return {"County": name, "ElectionDateName": "Tuesday, November 3, 2026",
                "VotersVoting": value, "REGISTERED_VOTERS": registered,
                "InPerson": value, "Absentee": 0}
    rows = [county("Adams", 9), county("Allen", 0), county("Cass", 1), county("Total", 10, 30)]
    body = encoded({"root": {"WriteTime": "2026-11-10T12:00:00.000", "CountyTurnout": rows}})
    result = native.record_statistics(body, [reported, unknown], profile)
    assert len(result["complete_native_query"]) == 4
    assert [row["id"] for row in result["updates"]] == [reported["id"]]
    assert result["updates"][0]["rate_compatible"] is False
    for mutation in (body.replace(b"2026-11-10T12:00:00.000", b"2026-11-08T12:00:00.000"),
                     body.replace(b"Tuesday, November 3, 2026", b"Tuesday, May 5, 2026"),
                     body.replace(b'"VotersVoting":9', b'"VotersVoting":0'),
                     encoded({"root": {"WriteTime": "2026-11-10T12:00:00.000",
                                        "CountyTurnout": rows[1:]}})):
        with pytest.raises(ValueError):
            native.record_statistics(mutation, [reported, unknown], profile)


def webforms_fixture():
    text = (
        '<span>GENERAL 2026</span><span>November 3, 2026</span>'
        'Results last updated:</span><span>11/12/2026 11:07 AM MT</span>'
        '<span class="header-ballot-number">9</span><br /><span class="header-voter-text">'
        'Eligible Voters</span><span class="header-voter-number">10</span>'
        '<span class="header-partial-number">0</span><span class="header-total-number">1</span>'
        '<span class="header-totalprecincts-text">1</span>'
        '<div class="col turnout-results-box-a"><h1>County A</h1><a countyid="02"></a>'
        '<div class="odd"><div class="county-precinct">UNIT 0</div>'
        '<div class="county-cast"><span>9</span></div>'
        '<div class="county-counted"><span>10</span></div></div></form>')
    templates = []
    for level, unit in (("county", ""), ("reporting_unit", "UNIT 0")):
        query = {"query_id": "nm-all-turnout", "geography_level": level,
                 "county_id": "02", "county": "County A", "unit": unit,
                 "source_clock": "11/11/2026 11:07 AM MT",
                 "selector": {"county_id": "02", "geography_level": level, "unit": unit}}
        templates.append(template("NM", unit or "County A", level, {"query": query}))
    return text.encode(), templates


def test_webforms_preserves_complete_statistical_queries_and_detects_missing_zero_units():
    body, templates = webforms_fixture()
    result = native.webforms_statistics(body, templates)
    assert len(result["complete_native_query"]) == 3
    assert len(result["updates"]) == 2
    assert [row["value"] for row in result["updates"]] == [9, 9]
    zero = body.replace(b">9</", b">0</")
    assert all(row["value"] == 0 for row in native.webforms_statistics(zero, templates)["updates"])
    for mutation in (body.replace(b"GENERAL 2026", b"PRIMARY 2026"),
                     body.replace(b"UNIT 0", b"UNIT 1"),
                     body.replace(b">9</", b"></"),
                     body.replace(b"11/12/2026", b"11/10/2026"),
                     body.replace(b'header-partial-number">0', b'header-partial-number">1')):
        with pytest.raises(ValueError):
            native.webforms_statistics(mutation, templates)
    with pytest.raises(ValueError, match="identities"):
        native.webforms_statistics(body, templates[:1])


def test_real_pdf_text_layer_and_fraction_summary_never_use_contest_times_cast():
    fitz = pytest.importorskip("fitz")
    row = granular.selected_records(baseline(("NY",)), "NY")[0]
    row["measure"]["literal"] = "Voters Cast"
    text = ("NY County\nGeneral Election\nNovember 3, 2026\n"
            "Summary for: All Contests, All Districts, All Tabulators\n"
            "Voters Cast: 9 of 10 (90.00%)\nTimes Cast 1\n11/04/2026 10:00PM")
    with fitz.open() as document:
        document.new_page().insert_text((30, 30), text)
        body = document.tobytes()
    result = native.pdf_parent_statistics(body, [row])
    assert result["updates"][0]["value"] == 9
    for changed in (text.replace("90.00%", "99.00%"),
                    text.replace("All Districts", "One District"),
                    text.replace("Voters Cast:", "Times Cast:")):
        with pytest.raises(ValueError):
            native.pdf_text_statistics(changed, [row], 1)


def test_pdf_ocr_agrees_by_clock_instant_and_never_overrides_meaningful_text(monkeypatch):
    from scripts import results_pdf_ocr as ocr
    pdf_reader(monkeypatch)
    row = granular.selected_records(baseline(("NY",)), "NY")[0]
    view = {"text": pdf_text("NY").decode(), "confidence": [1.] * 8,
            "receipt": {"engine": "fixture"}}
    calls = []
    def views(body):
        calls.append(body)
        second = {**view, "text": view["text"].replace("10:00PM", "10:00 PM")}
        return [view, second]
    monkeypatch.setattr(ocr, "first_page_views", views)
    result = native.pdf_parent_statistics(b"", [row])
    assert result["updates"][0]["value"] == 9
    assert result["ocr"]["same_engine_resolution_check_not_independent_validation"]
    assert len(calls) == 1
    with pytest.raises(ValueError):
        native.pdf_parent_statistics(b"Primary Election", [row])
    assert len(calls) == 1
    bad = {**view, "text": view["text"].replace("Total 9", "Total 8")}
    monkeypatch.setattr(ocr, "first_page_views", lambda body: [view, bad])
    with pytest.raises(ValueError, match="disagreement"):
        native.pdf_parent_statistics(b"", [row])
    low_confidence = {**view, "confidence": [0.] * 8}
    monkeypatch.setattr(ocr, "first_page_views", lambda body: [view, low_confidence])
    with pytest.raises(ValueError, match="confidence"):
        native.pdf_parent_statistics(b"", [row])


def test_pdf_total_column_components_and_whitespace_are_checked():
    row = granular.selected_records(baseline(("NY",)), "NY")[0]
    text = pdf_text("NY").decode().replace("TOTAL Election Day Absentee", "Statistics TOTAL")
    text = text.replace("Cast - Total 9", "Cast-Total 9 4 5")
    assert native.pdf_text_statistics(text, [row], 1)["updates"][0]["value"] == 9
    with pytest.raises(ValueError, match="components"):
        native.pdf_text_statistics(text.replace("9 4 5", "9 4 6"), [row], 1)
    other = copy.deepcopy(row)
    other["geography"]["name"] = "Second County"
    with pytest.raises(ValueError, match="multiple counties"):
        native.pdf_text_statistics(text + "\nSecond County", [row, other], 1)


def test_ocr_groups_physical_rows_not_reading_order_and_keeps_numeric_confidence():
    from scripts.results_pdf_ocr import physical_lines
    def box(x, y, width=10):
        return [[x, y], [x + width, y], [x + width, y + 10], [x, y + 10]]
    result = physical_lines([[box(100, 0), "0", .999], [box(0, 0, 90), "Total Ballots", .8],
                             [box(0, 30), "Second line", .95]])
    assert result["text"] == "Total Ballots 0\nSecond line"
    assert result["confidence"] == [.999, .95]


def test_pdf_projection_preserves_only_explicit_native_timezone_and_all_other_states():
    before = baseline(("NY", "TX"))
    row = granular.selected_records(before, "NY")[0]
    text = pdf_text("NY").decode().replace("11/04/2026 10:00PM", (
        "Date: 11/04/2026\nTime: 10:00:00 PM CST"))
    result = native.pdf_text_statistics(text, [row], 1)
    entries = {"NY-native": {"status": "reported", "data": result,
               "source": {"url": row["view"]["source_url"], **pin(text.encode())}}}
    after, changes = granular.project(before, entries)
    current = granular.selected_records(after, "NY")[0]
    assert current["source_clock"]["timezone"] == "CST"
    assert current["source_clock"]["literal"] == "11/04/2026 10:00:00 PM CST"
    assert after["states/TX.json.gz"] == before["states/TX.json.gz"]
    assert len(changes) == 1


def test_pdf_refresh_preserves_existing_qualified_frame_only_with_native_registration():
    from scripts.automatic_native_refresh import observation_identity
    before = baseline(("NY",))
    shard = json.loads(gzip.decompress(before["states/NY.json.gz"]))
    row = shard["records"][0]
    row["denominator"] = {"value": 100, "literal": "Registered Voters - Total",
                          "basis": "native_registered_voters_total_same_report", "qualified": True}
    before["states/NY.json.gz"] = intake.compressed(encoded(shard))
    result = native.pdf_text_statistics(pdf_text("NY").decode(), [row], 1)
    entries = {"NY-native": {"status": "reported", "data": result,
               "source": {"url": row["view"]["source_url"], **pin(pdf_text("NY"))}}}
    after, _ = granular.project(before, entries)
    current = granular.selected_records(after, "NY")[0]
    assert observation_identity(current) == observation_identity(row)
    assert current["denominator"]["value"] == 100
    assert current["view"]["reported_pct"] == 9
    for changed in (pdf_text("NY").decode().replace("Registered Voters - Total", "Other Register"),
                    pdf_text("NY").decode().replace("Total 100", "Total 8")):
        with pytest.raises(ValueError, match="register"):
            native.pdf_text_statistics(changed, [row], 1)


def test_explicit_voters_cast_fraction_does_not_inherit_contest_column_order():
    row = granular.selected_records(baseline(("NY",)), "NY")[0]
    row["measure"]["literal"] = "Voters Cast"
    text = ("NY County\nGeneral Election\nNovember 3, 2026\n"
            "Voters Cast: 9 of 100 (9.00%)\n"
            "Election Day Absentee TOTAL\nCandidate Name 4 5 9\n11/04/2026 10:00PM")
    assert native.pdf_text_statistics(text, [row], 1)["updates"][0]["value"] == 9


def test_pdf_ocr_rejects_disagreement_in_existing_qualified_register(monkeypatch):
    from scripts import results_pdf_ocr as ocr
    pdf_reader(monkeypatch)
    row = granular.selected_records(baseline(("NY",)), "NY")[0]
    row["denominator"] = {"value": 100, "literal": "Registered Voters - Total",
                          "basis": "native_registered_voters_total_same_report", "qualified": True}
    view = {"text": pdf_text("NY").decode(), "confidence": [1.] * 8, "receipt": {}}
    other = {**view, "text": view["text"].replace("Total 100", "Total 101")}
    monkeypatch.setattr(ocr, "first_page_views", lambda body: [view, other])
    with pytest.raises(ValueError, match="disagreement"):
        native.pdf_parent_statistics(b"", [row])


def test_complete_projection_is_identical_after_source_fact_serialization():
    before = baseline(("NY", "TX"))
    entries = {}
    for state in ("TX", "NY"):
        row = granular.selected_records(before, state)[0]
        text = pdf_text(state).decode()
        entries[state + "-native"] = {"status": "reported",
            "data": native.pdf_text_statistics(text, [row], 1),
            "source": {"url": row["view"]["source_url"], **pin(text.encode())}}
    serialized = json.loads(encoded(entries))
    assert granular.project(before, entries) == granular.project(before, serialized)
