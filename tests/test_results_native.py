import copy
from datetime import datetime, timezone
import gzip
import json

import pytest

from scripts import results_granular as granular, results_native as native, results_intake as intake
from scripts.participation_intake.contract import IntakeError, encoded, observation_id, pin, validate
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
            self.pages = [Page(value) for value in stream.read().decode().split("\f")]
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


def test_unadapted_product_is_not_misreported_as_a_reviewed_numerical_parser_failure(tmp_path, monkeypatch):
    before = baseline(("IN",))
    shard = json.loads(gzip.decompress(before["states/IN.json.gz"]))
    shard["records"][0]["measure"]["literal"] = "Source-specific unsupported measure"
    before["states/IN.json.gz"] = intake.compressed(encoded(shard))
    def acquire(self, url):
        return b"fixture", {"origin": "retained_fixture", **pin(b"fixture")}
    def unsupported(body, url):
        raise ValueError("This product needs a structural adapter")
    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    monkeypatch.setattr(native, "factual_tables", unsupported)
    collector = intake.Collector(tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
                                 datetime(2026, 11, 16, tzinfo=timezone.utc))
    entry, = native.collect_sources(collector, before).values()
    assert entry["adapter"] == "unadapted_primary_product"
    assert entry["error"] == entry["status"] == "unsupported_primary_product"
    assert entry["attempted_source_url"] == "https://in.official.test/2026-general.pdf"
    assert entry["data"] is None


def summary_fixture(layout, value=9):
    url, profile = next((url, profile) for url, profile in native.SUMMARY_PROFILES.items()
                        if profile["layout"] == layout)
    if layout == "repeated_header":
        clock = "2026-11-12 15:10:05"
        facts = {"source_id": profile["identity"], "native_ballots": 7,
                 "native_pdf_clock": clock, "selected_native_parent_literal": "Total Ballots Cast:",
                 "source_role": "native_registration_ballot_reported_turnout_statistics"}
        text = "\n".join(("Statement of Votes Cast by Geography Page: 1 of 1",
            profile["title"] + " 2026-11-13",
            "All Precincts, All Districts, All Counter Groups, All ScanStations, "
            "All Contests, All Boxes 15:10:05",
            f"Total Ballots Cast: {value}, Registered Voters: 10, Overall Turnout: {value * 10:.2f}%",
            "A contest with 999 candidate selections"))
    else:
        clock = "Printed on: 11/04/2026 at 09:09:56 am"
        facts = {"source_administration_id": profile["identity"],
                 "native_values": {"TOTAL TURNOUT": 7},
                 "source_clock_literal": clock,
                 "component_county_fips": profile["component_county_fips"]}
        text = "\n".join((profile["title"] + " Page 1",
            "November 3, 2026 Printed on: 11/05/2026 at 09:09:56 am", "SUMMARY REPORT", "REPORT 3",
            "        TOTAL REGISTRATION      10",
            f"        TOTAL TURNOUT           {value}    {value * 10:.1f}%",
            f"        Mail TURNOUT            {value}    {value * 10:.1f}%",
            "        In-Person TURNOUT       0    0.0%"))
    row = template(profile["state"], profile["name"], profile["level"], facts)
    row["measure"]["literal"] = profile["measure"]
    row["source_clock"]["literal"] = clock
    row["view"]["source_url"] = url
    return text.encode(), row, profile


@pytest.mark.parametrize("layout", ["repeated_header", "column_turnout"])
@pytest.mark.parametrize("value", [0, 9])
def test_summary_collects_changed_parent_and_true_zero_without_rate_promotion(monkeypatch, layout, value):
    pdf_reader(monkeypatch)
    body, row, profile = summary_fixture(layout, value)
    result = native.summary_statistics(body, [row], profile)
    update = result["updates"][0]
    assert update["id"] == row["id"]
    assert update["value"] == value
    assert update["registered"] == 10
    assert update["rate_compatible"] is False
    assert result["analytical_rates_promoted"] is False
    assert result["complete_native_query"][0]["count"] == value
    if layout == "column_turnout":
        assert update["native"]["component_county_fips"] == row["view"]["native_record"]["component_county_fips"]


@pytest.mark.parametrize("layout", ["repeated_header", "column_turnout"])
@pytest.mark.parametrize("field", ["year", "name", "identity", "measure", "count", "qualified"])
def test_summary_rejects_changed_accepted_scope_or_role(monkeypatch, layout, field):
    pdf_reader(monkeypatch)
    body, row, profile = summary_fixture(layout)
    if field == "year":
        row["election"]["year"] = 2024
    elif field == "name":
        row["geography"]["name"] = "A different source geography"
    elif field == "identity":
        row["view"]["native_record"][profile["identity_field"]] = "other"
    elif field == "measure":
        row["measure"]["literal"] = "Candidate votes"
    elif field == "count":
        row["count"]["value"] = 8
    else:
        row["denominator"] = {"qualified": True, "value": 10}
    with pytest.raises(ValueError, match="identity, measure or qualification"):
        native.summary_statistics(body, [row], profile)


def test_repeated_summary_requires_every_page_parent_and_whole_report_scope(monkeypatch):
    pdf_reader(monkeypatch)
    body, row, profile = summary_fixture("repeated_header")
    first = body.replace(b"1 of 1", b"1 of 2")
    second = body.replace(b"1 of 1", b"2 of 2")
    result = native.summary_statistics(first + b"\f" + second, [row], profile)
    assert len(result["complete_native_query"]) == 2
    for changed in (
            second.replace(b"Cast: 9", b"Cast: 8").replace(b"90.00%", b"80.00%"),
            second.replace(b"All Precincts", b"Selected Precincts"),
            second.replace(b"2026-11-13", b"2026-11-14"),
            second.replace(b"Total Ballots Cast: 9", b"Total Candidate Votes: 9")):
        with pytest.raises(ValueError):
            native.summary_statistics(first + b"\f" + changed, [row], profile)


def test_column_summary_finds_later_page_and_holds_missing_misaligned_or_conflicting_cells(monkeypatch):
    pdf_reader(monkeypatch)
    body, row, profile = summary_fixture("column_turnout")
    header = b"\n".join(body.splitlines()[:4])
    later = body.replace(b"Page 1", b"Page 2")
    result = native.summary_statistics(header + b"\f" + later, [row], profile)
    assert result["updates"][0]["native"]["query"]["page"] == 2
    shifted = body.replace(b"        Mail TURNOUT", b"       Mail TURNOUT")
    assert native.summary_statistics(shifted, [row], profile)["updates"][0]["value"] == 9
    contest = body + b"\nShould the Primary Election procedure change?"
    assert native.summary_statistics(contest, [row], profile)["updates"][0]["value"] == 9
    for changed in (
            body.replace(b"TOTAL TURNOUT           9", b"TOTAL TURNOUT           "),
            body.replace(b"        Mail TURNOUT", b"           Mail TURNOUT"),
            body.replace(b"Mail TURNOUT            9", b"Mail TURNOUT            8"),
            body.replace(b"90.0%", b"80.0%"),
            body.replace(b"11/05/2026", b"11/03/2026"),
            body.replace(b"November 3, 2026", b"November 3, 2024")):
        with pytest.raises(ValueError):
            native.summary_statistics(changed, [row], profile)
    changed = copy.deepcopy(row)
    changed["view"]["native_record"]["component_county_fips"] = ["15005", "15009"]
    with pytest.raises(ValueError, match="membership"):
        native.summary_statistics(body, [changed], profile)


def test_summary_final_edition_preserves_native_status_without_promoting_rates(monkeypatch):
    pdf_reader(monkeypatch)
    body, row, profile = summary_fixture("column_turnout")
    result = native.summary_statistics(body.replace(b"REPORT 3", b"FINAL"), [row], profile)
    update = result["updates"][0]
    assert update["value"] == 9
    assert update["native"]["native_report_status_literal"] == "FINAL"
    assert result["complete_native_query"][0]["native_report_status_literal"] == "FINAL"
    assert update["rate_compatible"] is False
    assert result["analytical_rates_promoted"] is False


@pytest.mark.parametrize("status", ["FINAL REVISION", "PRELIMINARY"])
def test_summary_final_edition_rejects_unreviewed_or_mixed_page_status(monkeypatch, status):
    pdf_reader(monkeypatch)
    body, row, profile = summary_fixture("column_turnout")
    with pytest.raises(ValueError, match="report clock changed"):
        native.summary_statistics(body.replace(b"REPORT 3", status.encode()), [row], profile)
    header = b"\n".join(body.replace(b"REPORT 3", b"FINAL").splitlines()[:4])
    later = body.replace(b"Page 1", b"Page 2")
    with pytest.raises(ValueError):
        native.summary_statistics(header + b"\f" + later, [row], profile)


@pytest.mark.parametrize("legacy_notes", [None, "Earlier report printed 70.0%."])
def test_summary_registered_sources_refresh_actual_projection_without_changing_other_states(
        tmp_path, monkeypatch, legacy_notes):
    pdf_reader(monkeypatch)
    before = baseline(("NY",))
    index = json.loads(before["index.json"])
    originals = {}
    for layout in ("repeated_header", "column_turnout"):
        body, row, profile = summary_fixture(layout)
        body = body.replace(b"REPORT 3", b"FINAL")
        row["view"].update(source_status_literal="REPORT 3", native_printed_pct="70.0%",
                           quality=["Earlier report printed 70.0%.",
                                    "Earlier source clock is not the current report clock."])
        if legacy_notes is not None:
            row["view"]["notes"] = legacy_notes
        originals[row["view"]["source_url"]] = body
        state = profile["state"]
        name = "states/" + state + ".json.gz"
        before[name] = intake.compressed(encoded({"records": [row],
            "views": {"official": {"counties": [row["id"]]}}}))
        index["states"][state] = {"file": name, **pin(before[name])}
    before["index.json"] = encoded(index)
    def acquire(self, url):
        self.guard(url)
        if url not in originals:
            raise IntakeError("source_stopped", "Retained unchanged state")
        return originals[url], {"url": url, "origin": "fixture_transport", **pin(originals[url])}
    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    collector = intake.Collector(tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
                                 datetime(2026, 11, 14, tzinfo=timezone.utc))
    entries = native.collect_sources(collector, before)
    after, changes = granular.project(before, entries)
    assert len(changes) == 2
    assert after["states/NY.json.gz"] == before["states/NY.json.gz"]
    for state in ("WA", "HI"):
        old = json.loads(gzip.decompress(before["states/" + state + ".json.gz"]))
        current = json.loads(gzip.decompress(after["states/" + state + ".json.gz"]))
        assert current["views"] == old["views"]
        assert current["records"][0]["geography"] == old["records"][0]["geography"]
        assert current["records"][0]["id"] == old["records"][0]["id"]
        assert current["records"][0]["quality"] == old["records"][0]["quality"]
        assert current["records"][0]["count"]["value"] == 9
        assert current["records"][0]["denominator"] is None
        view = current["records"][0]["view"]
        assert view["source_status_literal"] == ("FINAL" if state == "HI" else None)
        assert view["native_printed_pct"] == ("90.0%" if state == "HI" else "90.00%")
        assert view["reported_pct"] is None
        assert current["records"][0]["source"]["fields"] == view
        prefix = "Retained earlier-report context (not current report statistics): "
        assert view.get("notes") == (prefix + legacy_notes if legacy_notes is not None else None)
        assert view["quality"] == [
            prefix + "Earlier report printed 70.0%.",
            "Earlier source clock is not the current report clock."]
        if state == "HI":
            assert current["records"][0]["reporting_status"]["literal"] == "FINAL"
        assert current["records"][0]["reporting_status"]["complete"] is None
    assert granular.project(after, entries) == (after, [])
    collector.prior = entries
    for url, body in originals.items():
        originals[url] = (body.replace(b" 9", b" 8").replace(b"90.00%", b"80.00%")
                          .replace(b"90.0%", b"80.0%").replace(b"2026-11-13", b"2026-11-12")
                          .replace(b"11/05/2026", b"11/04/2026"))
    retained = native.collect_sources(collector, before)
    for identity, entry in retained.items():
        if identity.startswith(("HI-", "WA-")):
            assert entry["status"] == "retained_after_failure"
            assert entry["data"] == entries[identity]["data"]
            assert entry["data"]["updates"][0]["value"] == 9


@pytest.mark.parametrize("field,value", [
    ("native_fraction_literal", "80.0%"),
    ("native_fraction_literal", 90),
    ("native_report_status_literal", "REPORT 3"),
])
def test_summary_projection_rejects_display_facts_unbound_to_native_query(monkeypatch, field, value):
    pdf_reader(monkeypatch)
    body, row, profile = summary_fixture("column_turnout")
    facts = native.summary_statistics(body.replace(b"REPORT 3", b"FINAL"), [row], profile)
    facts["updates"][0]["native"][field] = value
    before = baseline(("HI",))
    name = "states/HI.json.gz"
    before[name] = intake.compressed(encoded({"records": [row]}))
    index = json.loads(before["index.json"])
    index["states"]["HI"] = {"file": name, **pin(before[name])}
    before["index.json"] = encoded(index)
    entry = {"status": "reported", "data": facts,
             "source": {"url": row["view"]["source_url"], **pin(body)}}
    with pytest.raises(ValueError, match="display facts disagree"):
        granular.project(before, {"HI-summary": entry})


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


def mapped_pdf_fixture():
    before = baseline(("MO", "TX"))
    shard = json.loads(gzip.decompress(before["states/MO.json.gz"]))
    row = shard["records"][0]
    row["measure"].update(kind="ballots_cast", literal="Ballots Cast")
    row["view"]["native_record"] = {"native_unit": "Ballots Cast - Total"}
    row["view"]["registered"] = 100
    row["source"]["fields"] = {"native_unit": "Ballots Cast - Total"}
    row["source"]["selector"] = {"native_unit": "Ballots Cast - Total"}
    before["states/MO.json.gz"] = intake.compressed(encoded(shard))
    index = json.loads(before["index.json"])
    index["states"]["MO"].update(pin(before["states/MO.json.gz"]))
    before["index.json"] = encoded(index)
    text = (
        "Summary Results Report Final Official\nNovember 3, 2026\nGeneral Election\n"
        "MO County\nStatistics TOTAL Election Absentee Central 1 Central 2 Central 3 Central 4\n"
        "Day\nRegistered Voters - Total 100\n"
        "Ballots Cast - Total 9 4 1 1 1 1 1\nVoter Turnout - Total 9.00%\n"
        "Election Summary - 11/04/2026 10:00PM")
    return before, row, text


def wrapped_pdf_fixture(value=9, clock="11/04/2026"):
    row = granular.selected_records(baseline(("KY",)), "KY")[0]
    components = "4 1 1 3 0" if value else "0 0 0 0 0"
    text = (
        "Summary Results Report UNOFFICIAL RESULTS\nKY County\nGeneral Election\n"
        "November 3, 2026\nStatistics TOTAL Election Mail Walk-in Walk-in Provision\n"
        "Day Excuse Early al\nBallots Cast - Total " + str(value) + " " + components
        + "\nElection Summary - " + clock + " 3:07 PM")
    return row, text


@pytest.mark.parametrize("value", [0, 9])
def test_wrapped_method_header_retains_explicit_total_and_complete_components(value):
    row, text = wrapped_pdf_fixture(value)
    result = native.pdf_text_statistics(text, [row], 53)
    update, = result["updates"]
    query, = result["complete_native_query"]
    assert update["value"] == value and update["registered"] is None
    assert update["rate_compatible"] is False
    assert query["native_statistical_column_header"] == [
        "Statistics TOTAL Election Mail Walk-in Walk-in Provision", "Day Excuse Early al"]
    assert query["native_statistical_line"] == text.splitlines()[6]
    assert query["pdf_report_timezone_literal"] is None
    assert not result["analytical_rates_promoted"] and not result["geographic_joins_changed"]


@pytest.mark.parametrize("old,new", [
    ("TOTAL Election", "Election TOTAL"),
    ("Day Excuse Early al", "Day Early Excuse al"),
    ("Walk-in Walk-in", "Walk-in"),
    ("Provision", "Candidate"),
    ("9 4 1 1 3 0", "9 4 1 1 3"),
    ("9 4 1 1 3 0", "9 4 1 1 3 0 0"),
    ("9 4 1 1 3 0", "9 4 1 1 4 0"),
    ("9 4 1 1 3 0", "? 4 1 1 3 0"),
    ("Day Excuse Early al", "Day Excuse Early al\nStatistics TOTAL Election Mail "
        "Walk-in Walk-in Provision\nDay Excuse Early al"),
])
def test_wrapped_header_rejects_reordered_missing_duplicate_and_unreconciled_columns(old, new):
    row, text = wrapped_pdf_fixture()
    with pytest.raises(ValueError):
        native.pdf_text_statistics(text.replace(old, new), [row], 53)


@pytest.mark.parametrize("status", ["OFFICIAL RESULTS", None])
def test_wrapped_pdf_status_refresh_does_not_reuse_the_initial_result_label(status):
    before = baseline(("KY",))
    row, text = wrapped_pdf_fixture()
    text = text.replace(" UNOFFICIAL RESULTS", " " + status if status else "")
    result = native.pdf_text_statistics(text, [row], 53)
    after, _ = granular.project(before, {"KY-summary": {
        "status": "reported", "source": {"url": row["view"]["source_url"], **pin(text.encode())},
        "data": result}})
    current, = granular.selected_records(after, "KY")
    assert current["view"]["source_status_literal"] == status
    assert current["reporting_status"]["literal"] == status
    assert current["reporting_status"]["complete"] is None


@pytest.mark.parametrize("text_layer", [True, False])
def test_plain_pdf_rejects_clock_rollback_behind_advanced_last_good(monkeypatch, text_layer):
    from scripts import results_pdf_ocr as ocr
    pdf_reader(monkeypatch)
    row = granular.selected_records(baseline(("KY",)), "KY")[0]
    accepted = pdf_text("KY").decode().replace("11/04/2026", "11/06/2026")
    older = accepted.replace("11/06/2026", "11/05/2026")
    def parse(text, prior=None):
        if not text_layer:
            view = {"text": text, "confidence": [1.] * len(text.splitlines()), "receipt": {}}
            monkeypatch.setattr(ocr, "first_page_views", lambda body: [view, copy.deepcopy(view)])
        return native.pdf_parent_statistics(text.encode() if text_layer else b"", [row], prior)
    result = parse(accepted)
    prior = {"source": {"url": row["view"]["source_url"], **pin(accepted.encode())},
             "data": result}
    with pytest.raises(ValueError, match="last-good"):
        parse(older, prior)
    assert parse(accepted, prior)["updates"] == result["updates"]
    broken = copy.deepcopy(prior)
    broken["data"]["updates"][0]["value"] = 9999
    with pytest.raises(ValueError, match="query-bound"):
        parse(accepted, broken)


def retained_parent_fixture(state):
    row = granular.selected_records(baseline((state,)), state)[0]
    if state == "WI":
        row["geography"]["name"] = "Walworth County"
        row["measure"].update(literal="Ballots Cast", kind="ballots_cast")
        row["source_clock"]["literal"] = "11/3/2026 9:36:49 PM"
        return row, (
            "Page: 1 of 8 11/3/2026 9:36:49 PM\n"
            "COMPLETE FINAL UNOFFICIAL ELECTION NIGHT RESULTS\n"
            "GENERAL ELECTION\nNOVEMBER 3, 2026\nWALWORTH COUNTY, WISCONSIN\n"
            "Precincts Reported: 38 of 38 (100.00%)\n"
            "Registered Voters: 46,612 of 0 (N/A)\nBallots Cast: 46,612\n"
            "Governor / Lieutenant Governor (Vote for 1)\n"
            "Candidate Party Total\nTotal Votes 46,261")
    row["geography"]["name"] = "Cape May County"
    row["denominator"] = {
        "qualified": True, "basis": "native_registered_voters",
        "literal": "native_registered_voters", "value": 76899}
    row["source_clock"]["literal"] = "Election Summary - 11/12/2026 03:34PM"
    url = ("https://nj.gov/state/elections/assets/pdf/periodic-report/2026/"
           "2026-1112-capemay-periodic-report.pdf")
    sha = "ad9f416a54062c82b545140f1ac8da201a647d830b06a0c5d89ba766356a98aa"
    row["source"].update(
        id="native-nj-capemay-summary-20261112", url=url, input_sha256=sha,
        selector={"measure": "total", "native_unit": "Ballots Cast - Total",
                  "source_id": "nj-capemay", "source_page": 2,
                  "table_id": "capemay-summary-page-2-section-1"})
    row["view"].update(source_url=url, native_record={
        "native_source_pin": {"sha256": sha, "bytes": 80305},
        "native_summary_statistics": {
            label: {"native_unit": label}
            for label in ("Registered Voters - Total", "Ballots Cast - Total")}})
    return row, (
        "Summary Report UNOFFICIAL RESULTS\n2026 General Election\n"
        "November 3, 2026 Cape May County\n"
        "Statistics TOTAL Early Election Mail-inProvisional Emergenc State/Fed\n"
        "Voting Day y\nElection Day Precincts Reporting 127 of 128 0 127 127 105 0 0\n"
        "Registered Voters - Total 76,899\n"
        "Ballots Cast - Total 42,442 9,678 24,033 8,340 335 0 56\n"
        "Voter Turnout - Total 55.19%\n"
        "Election Summary - 11/12/2026 03:34PM 1 of 10")


@pytest.mark.parametrize("state", ["NJ", "WI"])
def test_retained_statistical_parent_selects_native_count_not_cover_or_candidate_votes(monkeypatch, state):
    pdf_reader(monkeypatch)
    row, text = retained_parent_fixture(state)
    body = ("11/12/2026 3:38 PM\nIntroductory administrative report\f" + text
            if state == "NJ" else text).encode()
    result = native.pdf_parent_statistics(body, [row])
    update, = result["updates"]
    query, = result["complete_native_query"]
    assert update["value"] == (42442 if state == "NJ" else 46612)
    assert query["page"] == (2 if state == "NJ" else 1)
    assert update["registered"] == (76899 if state == "NJ" else None)
    assert update["rate_compatible"] is (state == "NJ")
    assert query["pdf_report_timezone_literal"] is None
    if state == "NJ":
        assert query["pdf_report_clock_literal"] == "11/12/2026 03:34PM"
        assert query["native_fraction_literal"] == "55.19%"
        assert query["native_report_status_literal"] == "UNOFFICIAL RESULTS"
        assert len(query["native_statistical_column_header"]) == 2
    else:
        assert query["native_statistical_line"] == "Ballots Cast: 46,612"
        assert update["value"] != 46261


@pytest.mark.parametrize("state,old,new", [
    ("NJ", "42,442 9,678", "? 9,678"),
    ("NJ", "42,442 9,678", "42,442 9,679"),
    ("NJ", "55.19%", "55.18%"),
    ("NJ", "Cape May County", "Other County"),
    ("NJ", "November 3, 2026", "November 3, 2024"),
    ("NJ", "Ballots Cast - Total", "Candidate Votes"),
    ("NJ", "Voting Day y", "Day Voting y"),
    ("WI", "Ballots Cast: 46,612", "Ballots Cast: ?"),
    ("WI", "Ballots Cast: 46,612", "Ballots Cast: -1"),
    ("WI", "Ballots Cast: 46,612", "Total Votes: 46,612"),
    ("WI", "Ballots Cast: 46,612", "Candidate Party Total\nBallots Cast: 46,612"),
    ("WI", "Precincts Reported:", "Contest Precincts Reported:"),
    ("WI", "WALWORTH COUNTY", "OTHER COUNTY"),
])
def test_retained_parent_rejects_changed_scope_missing_counts_and_candidate_substitution(
        monkeypatch, state, old, new):
    pdf_reader(monkeypatch)
    row, text = retained_parent_fixture(state)
    body = ("\f" if state == "NJ" else "") + text.replace(old, new)
    with pytest.raises(ValueError):
        native.pdf_parent_statistics(body.encode(), [row])


@pytest.mark.parametrize("field", ["page", "source", "identity", "register"])
def test_second_page_requires_its_exact_reviewed_source_and_registered_frame(monkeypatch, field):
    pdf_reader(monkeypatch)
    row, text = retained_parent_fixture("NJ")
    if field == "page":
        row["source"]["selector"]["source_page"] = 1
    elif field == "source":
        row["source"]["input_sha256"] = "0" * 64
    elif field == "identity":
        row["geography"]["name"] = "Other County"
    else:
        row["denominator"]["basis"] = "eligible_population"
    with pytest.raises(ValueError):
        native.pdf_parent_statistics(("\f" + text).encode(), [row])


@pytest.mark.parametrize("state", ["NJ", "WI"])
def test_retained_parent_holds_an_advanced_last_good_clock_and_wrong_physical_page(monkeypatch, state):
    pdf_reader(monkeypatch)
    row, text = retained_parent_fixture(state)
    old_date, new_date = (("11/12/2026", "11/14/2026") if state == "NJ"
                          else ("11/3/2026", "11/5/2026"))
    prefix = "\f" if state == "NJ" else ""
    accepted = native.pdf_parent_statistics((prefix + text.replace(old_date, new_date)).encode(), [row])
    prior = {"source": {"url": row["view"]["source_url"]}, "data": accepted}
    with pytest.raises(ValueError, match="last-good"):
        native.pdf_parent_statistics((prefix + text).encode(), [row], prior)
    if state == "NJ":
        with pytest.raises(ValueError, match="physical page"):
            native.pdf_text_statistics(text, [row], 11)
        with pytest.raises(ValueError, match="page is missing"):
            native.pdf_parent_statistics(text.encode(), [row])


@pytest.mark.parametrize("value", [0, 9])
def test_mapped_pdf_refreshes_native_context_without_promoting_rates(monkeypatch, value):
    pdf_reader(monkeypatch)
    before, row, text = mapped_pdf_fixture()
    if value == 0:
        text = text.replace("9 4 1 1 1 1 1", "0 0 0 0 0 0 0").replace("9.00%", "0.00%")
    result = native.pdf_parent_statistics(text.encode(), [row])
    entry = {"status": "reported", "data": result,
             "source": {"url": row["view"]["source_url"], **pin(text.encode())}}
    after, changes = granular.project(before, {"MO-native": entry})
    current = granular.selected_records(after, "MO")[0]
    query = result["complete_native_query"][0]
    assert current["count"]["value"] == query["count"] == value
    assert query["native_measure_literal"] == "Ballots Cast - Total"
    assert query["template_measure_literal"] == "Ballots Cast"
    assert current["id"] == row["id"] and current["measure"] == row["measure"]
    assert current["geography"] == row["geography"]
    assert current["denominator"] is None and current["view"]["reported_pct"] is None
    assert current["view"]["registered"] == 100
    assert current["view"]["native_printed_pct"] == f"{value}.00%"
    assert current["view"]["source_status_literal"] == "Final Official"
    assert current["reporting_status"]["complete"] is None
    assert current["source_clock"]["timezone"] is None
    assert after["states/TX.json.gz"] == before["states/TX.json.gz"]
    assert len(changes) == 1 and not result["updates"][0]["rate_compatible"]
    validate(current)


@pytest.mark.parametrize("old,new", [
    ("Central 2", "Central 1"), ("Central 2", "Central 3"), ("\nDay\n", "\nOther\n"),
    ("TOTAL Election Absentee", "Election Absentee TOTAL"),
    ("9 4 1 1 1 1 1", "9 4 1 1 1 2"), ("9 4 1 1 1 1 1", "9 4 1 1 1 1 2"),
    ("9 4 1 1 1 1 1", "- 4 1 1 1 1 1"), ("9.00%", "8.00%"),
    ("General Election", "Primary Election"), ("November 3, 2026", "November 3, 2024"),
    ("MO County", "Other County"), ("11/04/2026", "11/02/2026"),
    ("Ballots Cast - Total", "Candidate Votes"), ("Registered Voters - Total", "Other Register"),
])
def test_mapped_pdf_rejects_changed_roles_scope_unknown_count_and_discrepancies(old, new):
    _, row, text = mapped_pdf_fixture()
    with pytest.raises(ValueError):
        native.pdf_text_statistics(text.replace(old, new), [row], 1)


@pytest.mark.parametrize("part", ["fields", "selector"])
def test_mapped_pdf_requires_matching_reviewed_field_and_selector(part):
    _, row, text = mapped_pdf_fixture()
    row["source"][part]["native_unit"] = "Candidate Votes"
    with pytest.raises(ValueError, match="explicit reviewed parent"):
        native.pdf_text_statistics(text, [row], 1)


def test_existing_explicit_pdf_parent_selection_does_not_inherit_the_new_mapping():
    _, row, text = mapped_pdf_fixture()
    row["view"]["native_record"]["selected_native_parent_literal"] = "Total Ballots"
    text = text.replace("Ballots Cast - Total", "Total Ballots")
    result = native.pdf_text_statistics(text, [row], 1)
    assert result["updates"][0]["value"] == 9
    assert result["complete_native_query"][0]["native_measure_literal"] == "Total Ballots"
    assert "template_measure_literal" not in result["complete_native_query"][0]


def test_mapped_pdf_default_collector_holds_last_good_on_rollback_and_source_stop(tmp_path, monkeypatch):
    pdf_reader(monkeypatch)
    before, row, text = mapped_pdf_fixture()
    bodies = {"MO": text.encode(), "TX": pdf_text("TX")}
    calls = []
    def acquire(self, url):
        self.guard(url)
        calls.append(url)
        state = url.split("//")[1].split(".")[0].upper()
        return bodies[state], {"url": url, "origin": "fixture_transport", **pin(bodies[state])}
    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    stops = {"urls": [], "prefixes": [], "hosts": []}
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    first = native.collect_sources(intake.Collector(tmp_path / "first", {}, stops, now), before)
    identity = next(key for key in first if key.startswith("MO-"))
    assert first[identity]["status"] == "reported"
    bodies["MO"] = text.replace("11/04/2026", "11/03/2026").encode()
    second = native.collect_sources(
        intake.Collector(tmp_path / "second", first, stops, now), before)
    assert second[identity]["status"] == "retained_after_failure"
    assert second[identity]["data"] == first[identity]["data"]
    assert second[identity]["source"] == first[identity]["source"]
    assert second[identity]["error"] == "schema_or_source_semantics_changed"
    first_projection, _ = granular.project(before, first)
    second_projection, changes = granular.project(before, second)
    assert second_projection == first_projection
    assert next(item for item in changes if item["state_code"] == "MO")[
        "source_status"] == "retained_after_failure"
    calls.clear()
    held = {"urls": [row["view"]["source_url"]], "prefixes": [], "hosts": []}
    third = native.collect_sources(
        intake.Collector(tmp_path / "third", second, held, now), before)
    assert third[identity]["error"] == "source_stopped"
    assert third[identity]["data"] == first[identity]["data"]
    assert row["view"]["source_url"] not in calls
    assert granular.project(before, third)[0] == first_projection


def test_mapped_pdf_rejects_unbound_last_good_query(monkeypatch):
    pdf_reader(monkeypatch)
    _, row, text = mapped_pdf_fixture()
    result = native.pdf_parent_statistics(text.encode(), [row])
    prior = {"source": {"url": row["view"]["source_url"], **pin(text.encode())},
             "data": copy.deepcopy(result)}
    prior["data"]["complete_native_query"][0]["county"] = "Other County"
    with pytest.raises(ValueError, match="query-bound"):
        native.pdf_parent_statistics(text.encode(), [row], prior=prior)


def test_ocr_groups_physical_rows_not_reading_order_and_keeps_numeric_confidence():
    from scripts.results_pdf_ocr import physical_lines, vertical_layout
    def box(x, y, width=10):
        return [[x, y], [x + width, y], [x + width, y + 10], [x, y + 10]]
    result = physical_lines([[box(100, 0), "0", .999], [box(0, 0, 90), "Total Ballots", .8],
                             [box(0, 30), "Second line", .95]])
    assert result["text"] == "Total Ballots 0\nSecond line"
    assert result["confidence"] == [.999, .95]
    def rectangle(x, y, width, height):
        return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]
    ambiguous = [
        [rectangle(460, 549, 97, 69), "123", .999],
        [rectangle(1203, 557, 95, 62), "123", .999],
        [rectangle(600, 564, 60, 21), "voters", .999],
        [rectangle(670, 566, 68, 24), "rejected", .999],
    ]
    with pytest.raises(ValueError, match="Ambiguous physical"):
        physical_lines(ambiguous)
    strict = physical_lines(ambiguous, strict_role_alignment=True)
    assert "voters rejected" in strict["text"]
    assert vertical_layout([
        [rectangle(0, y, 10, 100), "vertical", 1.] for y in (0, 110, 220)])
    assert not vertical_layout([[rectangle(0, 0, 100, 10), "horizontal", 1.]])


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


def test_json_projection_preserves_query_bound_utc_and_clears_obsolete_status():
    before = baseline(("IN", "TX"))
    row = granular.selected_records(before, "IN")[0]
    query = {"native_report_status_literal": None, "source_clock_timezone_literal": "UTC"}
    facts = {"query": query, "native_report_status_literal": None,
             "source_clock_timezone_literal": "UTC",
             "native_reporting_complete_qualified": False}
    update = granular.change(row, 34, facts, clock="2026-11-10T22:08:21.2472948Z")
    entry = {"status": "reported", "data": {"updates": [update]},
             "source": {"url": row["view"]["source_url"], **pin(b"native JSON facts")}}
    after, changes = granular.project(before, {"IN-native": entry})
    current = granular.selected_records(after, "IN")[0]
    assert current["source_clock"]["literal"] == update["clock"]
    assert current["source_clock"]["timezone"] == "UTC"
    assert current["reporting_status"]["literal"] is None
    assert current["view"]["source_status_literal"] is None
    assert current["source"]["fields"] == current["view"]
    assert after["states/TX.json.gz"] == before["states/TX.json.gz"]
    assert len(changes) == 1
    for changed in ("timezone", "query", "clock"):
        broken = copy.deepcopy(entry)
        item = broken["data"]["updates"][0]
        if changed == "clock":
            item["clock"] = item["clock"][:-1]
        elif changed == "query":
            item["native"]["query"]["source_clock_timezone_literal"] = None
        else:
            item["native"]["source_clock_timezone_literal"] = "EST"
        with pytest.raises(ValueError, match="UTC"):
            granular.project(before, {"IN-native": broken})


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


def texas_template(count_value=1262, form="official", county="Example County"):
    source_county = county.removesuffix(" County")
    row = template("TX", county, "county")
    row["count"] = {"value": count_value, "literal": count_value, "status": "reported"}
    row["source_clock"] = {"literal": None, "timezone": None}
    row["measure"]["literal"] = (
        "M. Total ballots counted (I+J+K+L)"
        if form == "official" else "I. Total ballots counted (G+H)")
    row["view"]["source_url"] = "https://tx.example.test/" + source_county.lower() + "-reconciliation.pdf"
    row["view"]["native_record"] = {
        "source_county": source_county, "native_election_date": "11/03/2026",
        "native_status_literal": (
            "Election Reconciliation - Official Totals"
            if form == "official"
            else "Preliminary Election Reconciliation - Unofficial Totals"),
        "ballots": count_value, "registered": 2305, "total_voters": 1265,
        "total_rejected": 3, "difference": 3,
    }
    return validate(row)


def texas_text(form="official"):
    if form == "official":
        return "\n".join((
            "12-2", "Election Reconciliation - Official Totals",
            "County Example Election Name General Election",
            "Registered Voters 2305 Election Date 11/03/2026",
            "E. Total voters 1265 H. Total ballots 3 M. Total ballots 1262",
            "N. Difference between voters and ballots 3 O. Difference as percentage of voters",
            "(E-H-M) (N/(E-H)*100) 0.00%", "5. Attestation", "11/09/2026",
        ))
    return "\n".join((
        "12-1", "Preliminary Election Reconciliation - Unofficial Totals",
        "County Example Election Name General Election",
        "Registered Voters 2305 Election Date 11/03/2026",
        "C. Total voters 1265 F. Total ballots rejected or pending 3 "
        "I. Total ballots counted 1262",
        "J. Difference between voters and ballots 0 K. Difference as percentage of voters",
        "(C-F-I) (J/(C-F)*100) 0.00%", "5. Attestation", "11/03/2026",
    ))


@pytest.mark.parametrize("form", ["official", "preliminary"])
def test_texas_reconciliation_selects_reviewed_physical_parent_without_promoting_register(form):
    row = texas_template(form=form)
    result = native._tx_parse_view(texas_text(form), row, 1)
    facts = result[0]
    assert facts["count"] == 1262
    assert facts["registered_raw"] == 2305
    assert facts["registered_denominator_not_promoted"] is True
    assert facts["source_clock"] is None
    assert facts["attestation_date_is_not_count_update_clock"] is True
    assert facts["selected_physical_role"] == (
        "M. Total ballots counted" if form == "official" else "I. Total ballots counted")
    assert facts["native_total_role_evidence"] == {
        "roles": ["E", "H", "M"] if form == "official" else ["C", "F", "I"],
        "left_to_right": True, "counted_role_explicit": True,
        "binding": "literal_header_line",
    }


def test_texas_reconciliation_retains_signed_native_discrepancy_without_repair():
    row = texas_template()
    facts, _lines = native._tx_parse_view(texas_text(), row, 1)
    assert facts["printed_difference"] == 3
    assert facts["computed_difference"] == 0
    assert facts["discrepancy"] == {
        "code": "native_reconciliation_difference_disagrees",
        "repaired": False, "actual_native": 3, "computed": 0,
        "expression": "E-H-M",
    }


def test_texas_reconciliation_source_plan_is_role_driven_not_county_allowlisted():
    row = texas_template(county="Unlisted County")
    shard = {"records": [row], "views": {"official": {"counties": [row["id"]]}}}
    body = intake.compressed(encoded(shard))
    before = {"index.json": encoded({"states": {"TX": {
        "file": "states/TX.json.gz", **pin(body)}}}), "states/TX.json.gz": body}
    source = next(iter(native.source_plan(before)["TX"].values()))
    assert source["adapter"] == "reviewed_texas_reconciliation_parent"
    assert source["templates"][0]["geography"]["name"] == "Unlisted County"


def test_texas_reconciliation_never_substitutes_candidate_sums():
    row = texas_template()
    text = texas_text().replace(
        "E. Total voters 1265 H. Total ballots 3 M. Total ballots 1262",
        "Candidate A 700 Candidate B 562 Total Votes 1262")
    with pytest.raises(ValueError, match="parent headers|statistical-parent"):
        native._tx_parse_view(text, row, 1)


@pytest.mark.parametrize("changed", [
    "E. Total voters 1265 M. Total ballots 3 H. Total ballots 1262",
    "E. Total voters 1265 Total ballots 3 M. Total ballots 1262",
    "E. Total voters 1265 999 H. Total ballots 3 M. Total ballots 1262",
])
def test_texas_reconciliation_rejects_swapped_missing_or_decoy_parent_headers(changed):
    row = texas_template()
    text = texas_text().replace(
        "E. Total voters 1265 H. Total ballots 3 M. Total ballots 1262", changed)
    with pytest.raises(ValueError, match="headers"):
        native._tx_parse_view(text, row, 1)


def test_texas_reconciliation_geometry_binds_voter_rejected_counted_columns():
    def cell(left, text, start=0):
        return {"left": left, "right": left + 40, "start": start,
                "end": start + len(text), "text": text, "confidence": 1.}
    lines = [
        "1. Voters 2. Rejected ballots 3. Counted ballots",
        "E. Total voters H. Total ballots M. Total ballots",
        "1265 3 1262",
    ]
    geometry = [
        [cell(10, "1. Voters"), cell(110, "2. Rejected ballots"),
         cell(210, "3. Counted ballots")],
        [cell(10, "E. Total voters"), cell(110, "H. Total ballots"),
         cell(210, "M. Total ballots")],
        [cell(10, "1265", 0), cell(110, "3", 5), cell(210, "1262", 7)],
    ]
    role = native.TX_RECONCILIATION_ROLES["m. total ballots counted (i+j+k+l)"]
    position, values, evidence = native._tx_total_row(lines, role, geometry)
    assert position == 2
    assert [value for value, _span in values] == [1265, 3, 1262]
    assert evidence["binding"] == "physical_voter_rejected_counted_columns"
    swapped = copy.deepcopy(geometry)
    swapped[1][1]["left"], swapped[1][2]["left"] = 210, 110
    swapped[1][1]["right"], swapped[1][2]["right"] = 250, 150
    with pytest.raises(ValueError, match="physical columns|left-to-right"):
        native._tx_total_row(lines, role, swapped)


def test_texas_reconciliation_ocr_keeps_same_engine_two_resolution_and_point98(monkeypatch):
    from scripts import results_pdf_ocr as ocr

    pdf_reader(monkeypatch)
    row = texas_template()
    text = texas_text()
    lines = text.splitlines()
    view = {"text": text, "confidence": [1.] * len(lines),
            "receipt": {"engine": "fixture", "count_minimum_confidence": .98}}
    monkeypatch.setattr(
        ocr, "first_page_views", lambda body, **kwargs: [view, copy.deepcopy(view)])
    result = native.texas_reconciliation_statistics(b"", [row])
    assert result["updates"][0]["value"] == 1262
    assert result["updates"][0]["registered"] is None
    assert result["updates"][0]["clock"] is None
    assert result["ocr"]["same_engine_resolution_check_not_independent_validation"] is True
    assert [item["roles"] for item in result["ocr"]["native_total_role_evidence"]] == [
        ["E", "H", "M"], ["E", "H", "M"]]
    low = copy.deepcopy(view)
    low["confidence"][4] = .979
    monkeypatch.setattr(ocr, "first_page_views", lambda body, **kwargs: [view, low])
    with pytest.raises(ValueError, match="confidence"):
        native.texas_reconciliation_statistics(b"", [row])


def legacy_webforms_fixture(monkeypatch, url=None):
    url = url or next(iter(native.LEGACY_WEBFORMS_PROFILES))
    profile = native.LEGACY_WEBFORMS_PROFILES[url]
    monkeypatch.setitem(native.LEGACY_WEBFORMS_PROFILES, url, {**profile, "counties": 1})
    body = (
        f'<title>{profile["title"]}</title>'
        '<h1>Unofficial Results</h1><h2>General Election November 3, 2026</h2>'
        '<span class="header-ballot-text">Ballots Cast</span>'
        '<span class="header-ballot-number">100</span>'
        '<span class="header-voter-text">Registered Voters</span>'
        '<span class="header-voter-number">200</span>'
        '<span class="header-partial-number">0</span>'
        '<span class="header-total-number">1</span>'
        '<span class="header-totalprecincts-text">1</span>'
        '<div class="col turnout-results-box-a"><h1>County A</h1><input countyid="02">'
        '<div class="provisional-precinct-header">'
        '<span class="county-precinct">Precinct Results</span>'
        '<span class="county-cast">Ballots Cast</span>'
        '<span class="county-counted">Registered Voters</span></div>'
        '<div class="odd"><div class="county-precinct">UNIT 0</div>'
        '<div class="county-cast"><span>0</span></div>'
        '<div class="county-counted"><span>10</span></div></div></form>').encode()
    rows = []
    for level, unit in (("county", ""), ("reporting_unit", "UNIT 0")):
        row = template(profile["state"], unit or "County A", level, {})
        row["measure"] = copy.deepcopy(native.LEGACY_WEBFORMS_MEASURE)
        row["geography"]["id"] = profile["state"] + "-" + level + "-" + url.rsplit("=", 1)[1]
        row["id"] = observation_id(*granular.identity_fields(row))
        row["view"].update(source_url=url, county_id="02", county="County A", unit=unit)
        rows.append(row)
    return url, body, rows


def test_legacy_webforms_native_rows_do_not_invent_parent_or_clock(monkeypatch):
    url, body, rows = legacy_webforms_fixture(monkeypatch)
    result = native.legacy_webforms_statistics(body, rows, url)
    assert len(result["updates"]) == 1
    update = result["updates"][0]
    assert update["value"] == 0 and update["clock"] is None
    assert update["native"]["query"]["native_measure_literal"] == "Ballots Cast"
    assert result["template_decisions"][0]["status"] == "held_county_parent_not_supplied"
    assert result["native_unit_count_sum"] == 0 and result["native_state_count"] == 100
    changed = body.replace(b"<span>0</span>", b"<span>7</span>")
    assert native.legacy_webforms_statistics(changed, rows, url)["updates"][0]["value"] == 7


def test_legacy_webforms_ambiguous_and_renamed_labels_never_join_by_position(monkeypatch):
    url, body, rows = legacy_webforms_fixture(monkeypatch)
    block = body[body.index(b'<div class="odd">'):body.index(b"</form>")]
    duplicated = body.replace(b"</form>", block + b"</form>")
    result = native.legacy_webforms_statistics(duplicated, rows, url)
    assert result["updates"] == []
    assert len(result["complete_native_query"]) == 3
    assert result["template_decisions"][1]["status"] == "held_ambiguous_literal_unit"
    renamed = native.legacy_webforms_statistics(body.replace(b"UNIT 0", b"RENAMED"), rows, url)
    assert renamed["updates"] == []
    assert renamed["template_decisions"][1]["status"] == "held_literal_unit_not_supplied"


def test_legacy_webforms_rendered_whitespace_preserves_original_labels(monkeypatch):
    url, body, rows = legacy_webforms_fixture(monkeypatch)
    body = body.replace(b"<h1>County A</h1>", b"<h1>County<br />A</h1>")
    body = body.replace(b"UNIT 0", b"UNIT  0")
    result = native.legacy_webforms_statistics(body, rows, url)
    query = result["updates"][0]["native"]["query"]
    assert query["county"] == "County A" and query["county_literal"] == "County\nA"
    assert query["unit"] == "UNIT 0" and query["unit_literal"] == "UNIT  0"


def test_legacy_webforms_scope_column_roles_and_clock_rollback_fail_closed(monkeypatch):
    url, body, rows = legacy_webforms_fixture(monkeypatch)
    for old, new in ((b"Unofficial Results", b"Official Results"),
                     (b"November 3, 2026", b"May 5, 2026"),
                     (b"Registered Voters", b"Eligible Voters"),
                     (b'class="county-cast">Ballots Cast',
                      b'class="county-cast">Candidate Votes'),
                     (b"Precinct Results", b"Candidate Results"),
                     (b"<span>0</span>", b"<span></span>"),
                     (b'countyid="02"', b'countyid="03"')):
        with pytest.raises(ValueError):
            native.legacy_webforms_statistics(body.replace(old, new), rows, url)
    rows[1]["source_clock"]["literal"] = "11/12/2026 10:00 AM"
    dated = body + b"Results last updated:</span><span>11/11/2026 10:00 AM</span>"
    with pytest.raises(ValueError, match="regressed"):
        native.legacy_webforms_statistics(dated, rows, url)
    missing = native.legacy_webforms_statistics(body, rows, url)["updates"][0]
    assert missing["clock"] is None
    assert missing["native"]["prior_accepted_source_clock"] == "11/12/2026 10:00 AM"
    assert missing["native"]["current_native_count_clock_not_supplied"] is True
    for field, value in (("kind", "candidate_votes"), ("literal", "Candidate votes"),
                         ("mode", "early")):
        changed = copy.deepcopy(rows)
        changed[1]["measure"][field] = value
        with pytest.raises(ValueError, match="scope changed"):
            native.legacy_webforms_statistics(body, changed, url)


def test_legacy_webforms_plans_collects_projects_all_three_products_and_is_repeat_stable(
        tmp_path, monkeypatch):
    before = baseline(("NE", "SD", "NY"))
    originals, rows_by_state = {}, {"NE": [], "SD": []}
    for url in native.LEGACY_WEBFORMS_PROFILES:
        url, body, rows = legacy_webforms_fixture(monkeypatch, url)
        originals[url] = body
        rows[1]["source_clock"]["literal"] = "11/12/2026 10:00 AM"
        rows_by_state[rows[0]["geography"]["state_code"]].extend(rows)
    index = json.loads(before["index.json"])
    for state, rows in rows_by_state.items():
        shard = {"records": rows, "views": {"official": {
            "counties": [row["id"] for row in rows if row["geography"]["level"] == "county"],
            "precincts": [row["id"] for row in rows if row["geography"]["level"] == "reporting_unit"]}}}
        name = "states/" + state + ".json.gz"
        before[name] = intake.compressed(encoded(shard))
        index["states"][state].update(pin(before[name]))
    before["index.json"] = encoded(index)
    plan = native.source_plan(before)
    selected = [source for state in ("NE", "SD") for source in plan[state].values()]
    assert {source["url"] for source in selected} == set(originals)
    assert all(source["adapter"] == "reviewed_legacy_webforms_statistics" for source in selected)

    def acquire(self, url):
        self.guard(url)
        if url not in originals:
            raise IntakeError("source_stopped", "Persisted access hold")
        body = originals[url]
        return body, {"url": url, "origin": "fixture_transport", **pin(body)}

    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    collector = intake.Collector(tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
                                 datetime(2026, 11, 14, tzinfo=timezone.utc))
    entries = native.collect_sources(collector, before)
    reported = [entry for entry in entries.values() if entry["status"] == "reported"]
    assert len(reported) == 3
    assert all(entry["data"]["native_unit_row_count"] == 1 for entry in reported)
    after, changes = granular.project(before, entries)
    assert len(changes) == 3
    assert after["states/NY.json.gz"] == before["states/NY.json.gz"]
    for state in ("NE", "SD"):
        old, current = (json.loads(gzip.decompress(item["states/" + state + ".json.gz"]))
                        for item in (before, after))
        assert current["views"] == old["views"]
        for prior, row in zip(old["records"], current["records"]):
            assert row["id"] == prior["id"] and row["geography"] == prior["geography"]
            if row["geography"]["level"] == "county":
                assert row == prior
            else:
                assert row["count"]["value"] == 0 and row["denominator"] is None
                assert row["source_clock"]["literal"] is None
                assert row["view"]["native_record"]["prior_accepted_source_clock"] == "11/12/2026 10:00 AM"
    repeated = native.collect_sources(collector, after)
    assert granular.project(after, repeated) == (after, [])
    dated = originals[next(iter(originals))] + (
        b"Results last updated:</span><span>11/11/2026 10:00 AM</span>")
    first_source = next(iter(plan["NE"].values()))
    templates = [row for row in granular.selected_records(after, "NE")
                 if row["view"]["source_url"] == first_source["url"]]
    with pytest.raises(ValueError, match="regressed"):
        native.legacy_webforms_statistics(dated, templates, first_source["url"])
    originals[first_source["url"]] = originals[first_source["url"]].replace(
        b"November 3, 2026", b"May 5, 2026")
    retained = intake.Collector(tmp_path / "retained", repeated,
                               {"urls": [], "prefixes": [], "hosts": []},
                               datetime(2026, 11, 14, tzinfo=timezone.utc))
    failed = native.collect_sources(retained, after)
    held = [entry for entry in failed.values() if entry["status"] == "retained_after_failure"]
    assert len(held) == 1 and held[0]["data"]["updates"][0]["value"] == 0
    assert granular.project(after, failed) == (after, [])


def statistical_html_fixture(monkeypatch, state):
    url, profile = next((url, value) for url, value in native.HTML_STATISTICS_PROFILES.items()
                        if value["state"] == state)
    if state == "NV":
        rows = [("Early Vote Turnout", 0), ("Early Vote Provisional Turnout", 0),
                ("Mail Turnout", 9), ("Election Day Provisional Turnout", 0),
                ("Election Day Turnout", 0), ("Total", 9)]
        text = ("<title>Election Night Results</title>2026 General Election Official Results "
                "Updated 11/13/26 01:39 PM REGISTRATION &amp; TURNOUT 15 Registered Voters"
                "<table><tr><th>Voting Method</th><th>Total</th><th>% / Reg</th>"
                "<th>Grand Total / Total</th></tr>" + "".join(
                    f"<tr><td>{name}</td><td>{value}</td><td>60%</td><td></td></tr>"
                    for name, value in rows) + "</table>")
        old_clock = "Updated 11/09/26 06:46 PM; native_page_update; timezone not supplied."
    elif state == "WI":
        monkeypatch.setitem(profile, "units", 2)
        text = ("<title>Election Results for 11032026</title>"
                "Fall General Election Jefferson County WI Official Results "
                "Number of votes reflect Jefferson County only "
                "Results saying 100% may be only of one machine "
                "Results are unofficial until after the County Canvass is complete. "
                "AS OF 11-06-2026 01:13 pm BALLOT TOTALS Votes "
                "REGISTERED VOTERS TOTAL 15 BALLOTS CAST TOTAL 9 "
                "Precincts Reporting 2 of 2 for 100% Precinct Detail Top "
                "<table><tr><th></th><th>Registered Voters</th><th>Ballots Cast</th>"
                "<th>Ballots Cast %</th></tr>"
                "<tr><td>WARD A</td><td>0</td><td>0</td><td>0%</td></tr>"
                "<tr><td>WARD B</td><td>15</td><td>9</td><td>60%</td></tr></table>"
                "Another Contest Precincts Reporting 1 of 1 for 100%")
        old_clock = "11-06-2026 01:13 pm"
    else:
        text = ("<html><table><tr><td>"
                "Summary Results Report General Election November 3, 2026 UNOFFICIAL RESULTS "
                "Monongalia County, WV Statistics TOTAL "
                "Election Day Precincts Reporting 43 of 43 Precincts Complete 0 of 43 "
                "Precincts Partially Reported 43 of 43 Absentee/ Early Precincts Reporting 43 of 43 "
                "Registered Voters - Total 15 Ballots Cast - Total 9 Ballots Cast - Blank 0 "
                "Voter Turnout - Total 60% Election Summary - 11/03/2026 8:36 PM 1 of 1"
                "</td></tr></table></html>")
        old_clock = "11/03/2026 8:36 PM; timezone not supplied."
    templates = []
    levels = (("county", profile["names"][0]),)
    if state == "WI":
        levels += (("reporting_unit", "WARD A"), ("reporting_unit", "WARD B"))
    for level, name in levels:
        row = template(state, name, level)
        row["measure"] = copy.deepcopy(profile["measure"])
        row["source_clock"]["literal"] = old_clock
        row["source"]["url"] = url
        row["geography"]["id"] = state + "-" + name
        row["id"] = observation_id(*granular.identity_fields(row))
        row["view"].update(source_url=url, county=profile["names"][0], unit=name,
                           registered=14, quality=["Earlier report context"])
        if state == "WI":
            row["denominator"] = {"value": 15, "literal": "Registered Voters",
                                  "basis": "native_registered_voters_same_report_snapshot",
                                  "qualified": level == "county"}
        templates.append(row)
    return url, text.encode(), templates


@pytest.mark.parametrize("state", ("NV", "WI", "WV"))
def test_statistical_html_native_parent_roles_zeros_and_partial_reporting(monkeypatch, state):
    url, body, rows = statistical_html_fixture(monkeypatch, state)
    result = native.statistical_html(body, rows, url)
    assert len(result["updates"]) == len(rows)
    assert result["updates"][0]["value"] == 9
    assert all(row["registered"] == (0 if row["value"] == 0 else 15)
               for row in result["updates"])
    assert all(row["native"]["native_reporting_complete_qualified"] is False
               for row in result["updates"])
    assert all(row["native"]["private_original_pin"] == pin(body) for row in result["updates"])
    if state == "WI":
        assert [row["value"] for row in result["updates"]] == [9, 0, 9]
        assert result["updates"][0]["reported_units"] == 2
        assert result["updates"][0]["total_units"] == 2
        assert result["updates"][1]["rate_compatible"] is False
    elif state == "WV":
        query = result["complete_native_query"][0]
        assert query["reporting_counters"]["Precincts Complete"]["reported"] == 0
        assert query["reporting_counters"]["Precincts Partially Reported"]["reported"] == 43
        assert result["updates"][0]["reported_units"] is None


def test_statistical_html_rejects_candidate_columns_missing_counts_and_incomplete_inventories(monkeypatch):
    for state, mutations in (
        ("NV", ((b"<th>Total</th>", b"<th>Candidate Votes</th>"),
                (b"<td>0</td>", b"<td></td>"),
                (b"<td>Total</td><td>9</td>", b"<td>Total</td><td>10</td>"),
                (b"2026 General Election", b"2024 General Election"))),
        ("WI", ((b"<th>Ballots Cast</th>", b"<th>Candidate Votes</th>"),
                (b"WARD B", b"RENAMED"),
                (b"WARD B", b"WARD A"),
                (b"<td>WARD B</td><td>15</td>", b"<td>WARD B</td><td>14</td>"),
                (b"only of one machine", b"all machines"),
                (b"11032026", b"11032024"))),
        ("WV", ((b"Ballots Cast - Total", b"Total Votes Cast"),
                (b"Precincts Complete 0", b"Precincts Complete 1"),
                (b"November 3, 2026", b"May 5, 2026"),
                (b"Monongalia County, WV", b"Another County, WV"))),
    ):
        url, body, rows = statistical_html_fixture(monkeypatch, state)
        for old, new in mutations:
            assert old in body
            with pytest.raises(ValueError):
                native.statistical_html(body.replace(old, new), rows, url)


@pytest.mark.parametrize("state", ("NV", "WI", "WV"))
def test_statistical_html_rejects_clock_rollback_and_changed_template_semantics(monkeypatch, state):
    url, body, rows = statistical_html_fixture(monkeypatch, state)
    for field, value in (("mode", "early"), ("kind", "candidate_votes"),
                         ("literal", "Candidate votes")):
        changed = copy.deepcopy(rows)
        changed[0]["measure"][field] = value
        with pytest.raises(ValueError, match="scope changed"):
            native.statistical_html(body, changed, url)
    for path in ("source_url", "county"):
        changed = copy.deepcopy(rows)
        changed[0]["view"][path] = "Unreviewed source"
        with pytest.raises(ValueError, match="scope changed"):
            native.statistical_html(body, changed, url)
    changed = copy.deepcopy(rows)
    changed[0]["geography"]["name"] = "Another County"
    with pytest.raises(ValueError, match="scope changed"):
        native.statistical_html(body, changed, url)
    token = {"NV": b"11/13/26 01:39 PM", "WI": b"11-06-2026 01:13 pm",
             "WV": b"11/03/2026 8:36 PM"}[state]
    with pytest.raises(ValueError):
        native.statistical_html(body.replace(token, b"Not supplied"), rows, url)
    rows[0]["source_clock"]["literal"] = "11/14/2026 10:00 AM"
    with pytest.raises(ValueError, match="regressed"):
        native.statistical_html(body, rows, url)


def test_statistical_html_printed_pages_require_consistent_headers_and_clocks(monkeypatch):
    url, body, rows = statistical_html_fixture(monkeypatch, "WV")
    second = (b"Summary Results Report General Election November 3, 2026 UNOFFICIAL RESULTS "
              b"Monongalia County, WV Contest totals Election Summary - 11/03/2026 8:36 PM")
    assert native.statistical_html(body + second, rows, url)["complete_native_query"][0][
        "printed_html_report_pages"] == 2
    for old, new in ((b"8:36", b"8:37"), (b"UNOFFICIAL RESULTS", b"OFFICIAL RESULTS"),
                     (b"2026", b"2024")):
        with pytest.raises(ValueError):
            native.statistical_html(body + second.replace(old, new), rows, url)


def test_statistical_html_changed_registration_withholds_existing_rate_and_refreshes_mirror(monkeypatch):
    url, body, rows = statistical_html_fixture(monkeypatch, "WI")
    baseline_files = baseline(("WI",))
    name = "states/WI.json.gz"
    baseline_files[name] = intake.compressed(encoded({"records": rows, "views": {}}))
    body = body.replace(b"VOTERS TOTAL 15", b"VOTERS TOTAL 16").replace(
        b"<td>WARD B</td><td>15</td>", b"<td>WARD B</td><td>16</td>")
    result = native.statistical_html(body, rows, url)
    assert result["updates"][0]["rate_compatible"] is False
    after, _ = granular.project(baseline_files, {"WI-fixture": {
        "status": "reported", "source": {"url": url, **pin(body)}, "data": result}})
    current = json.loads(gzip.decompress(after[name]))["records"]
    assert rows[0]["denominator"]["qualified"] is True
    assert current[0]["denominator"]["qualified"] is False
    assert current[0]["denominator"]["value"] == current[0]["view"]["registered"] == 16
    assert all(row["view"]["reported_pct"] is None for row in current)
    assert current[1]["count"]["value"] == current[1]["view"]["registered"] == 0


def test_statistical_html_preserves_distinct_accepted_appearances(monkeypatch):
    url, body, rows = statistical_html_fixture(monkeypatch, "NV")
    duplicate = copy.deepcopy(rows[0])
    duplicate["source"]["id"] = "another-reviewed-source-appearance"
    duplicate["id"] = observation_id(*granular.identity_fields(duplicate))
    result = native.statistical_html(body, [rows[0], duplicate], url)
    assert [row["id"] for row in result["updates"]] == [rows[0]["id"], duplicate["id"]]
    assert result["updates"][0]["value"] == result["updates"][1]["value"] == 9


def test_statistical_html_collects_all_products_preserves_holds_and_repeats_byte_stably(
        tmp_path, monkeypatch):
    before = baseline(("NV", "WI", "WV", "NY"))
    originals = {}
    index = json.loads(before["index.json"])
    for state in ("NV", "WI", "WV"):
        url, body, rows = statistical_html_fixture(monkeypatch, state)
        originals[url] = body
        shard = {"records": rows, "views": {"official": {
            "counties": [row["id"] for row in rows if row["geography"]["level"] == "county"],
            "precincts": [row["id"] for row in rows if row["geography"]["level"] == "reporting_unit"]}}}
        name = "states/" + state + ".json.gz"
        before[name] = intake.compressed(encoded(shard))
        index["states"][state].update(pin(before[name]))
    before["index.json"] = encoded(index)
    plan = native.source_plan(before)
    assert all(next(iter(plan[state].values()))["adapter"] == "reviewed_statistical_html"
               for state in ("NV", "WI", "WV"))

    def acquire(self, url):
        self.guard(url)
        if url not in originals:
            raise IntakeError("source_stopped", "Persisted access hold")
        body = originals[url]
        return body, {"url": url, "origin": "fixture_transport", **pin(body)}

    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    collector = intake.Collector(tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
                                 datetime(2026, 11, 14, tzinfo=timezone.utc))
    entries = native.collect_sources(collector, before)
    assert sum(entry["status"] == "reported" for entry in entries.values()) == 3
    after, changes = granular.project(before, entries)
    assert len(changes) == 5
    assert after["states/NY.json.gz"] == before["states/NY.json.gz"]
    for state in ("NV", "WI", "WV"):
        old, current = (json.loads(gzip.decompress(item["states/" + state + ".json.gz"]))
                        for item in (before, after))
        assert current["views"] == old["views"]
        for previous, row in zip(old["records"], current["records"]):
            assert row["id"] == previous["id"] and row["geography"] == previous["geography"]
            assert row["reporting_status"]["complete"] is None
            assert row["view"]["registered"] == row["view"]["native_record"]["query"]["registered"]
            if not previous["denominator"] or not previous["denominator"]["qualified"]:
                assert row["view"]["reported_pct"] is None
    repeated = native.collect_sources(collector, after)
    assert granular.project(after, repeated) == (after, [])
    nv_url = next(url for url in originals if "clarkcountynv" in url)
    originals[nv_url] = originals[nv_url].replace(b"2026 General Election", b"2024 General Election")
    retained = intake.Collector(tmp_path / "retained", repeated,
                               {"urls": [], "prefixes": [], "hosts": []},
                               datetime(2026, 11, 14, tzinfo=timezone.utc))
    held = native.collect_sources(retained, after)
    assert sum(entry["status"] == "retained_after_failure" for entry in held.values()) == 1
    assert granular.project(after, held) == (after, [])
