import copy
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import statewide_ballot_totals as totals
from scripts import automatic_native_refresh as native
from scripts import results_state_statistics as stats
from scripts import results_pa_vote_history as pa
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


def test_pennsylvania_vote_history_keeps_age_residual_and_excludes_primary_from_general():
    url = ("https://www.pa.gov/content/dam/copapwp-pagov/en/dos/resources/voting-and-elections/"
           "bulk-data/2026-general-election/voter-registration-vote-history-summary-2026-general.xlsx")
    primary = url.replace("2026-general-election/", "2026-general-primary/").replace(
        "2026-general.xlsx", "2026-primary.xlsx")
    index = f'<a href="{url}">General</a><a href="{primary}">Primary</a>'.encode()
    assert pa.archive_link(index, pa.INDEX, pa.report_pattern(2026)) == url
    assert pa.archive_link(index.replace(url.encode(), b"/elsewhere"), pa.INDEX, pa.report_pattern(2026)) is None
    tables = {name: [list(header)] for name, header in pa.HEADERS.items()}
    for county in [*pa.COUNTIES, "TOTAL"]:
        scale = len(pa.COUNTIES) if county == "TOTAL" else 1
        tables["By county"].append([county, 8 * scale, 16 * scale, 50])
        tables["By vote method"].append([county, scale, 4 * scale, 2 * scale, scale])
        tables["By county & age"].append([county] + [scale] * 7 + [2 * scale] * 7 + [50] * 7)
    data = {"year": 2026, "election_date": "2026-11-03", "tables": tables,
            "report": {"url": url, **pin(b"fixture")}}
    exported, csv_body = pa.exports({pa.FEEDS[2026]: {"status": "reported", "data": data}})
    total = exported["editions"][0]["rows"][-1]
    assert total["age_not_tabulated"] == {"vote_history": 67, "registered": 134}
    assert b",TOTAL,18 to 24,67,134,50.0," in csv_body
    assert len(csv_body.splitlines()) == 1 + 68 * 8
    assert exported["certified_ballots_cast"] is False
    for sheet, column in (("By vote method", 2), ("By county & age", 1), ("By county", 2)):
        corrupt = copy.deepcopy(data)
        corrupt["tables"][sheet][-1][column] += 1
        with pytest.raises(ValueError):
            pa.queries(corrupt)


def test_kansas_waits_for_a_declared_workbook_and_preserves_a_reconciled_count(monkeypatch):
    history = totals.history
    files = baseline(monkeypatch)
    path = "states/KS.json.gz"
    original = Path(__file__).resolve().parents[1] / "data/results-intake/baseline/counts" / path
    files[path] = original.read_bytes()
    index = json.loads(files["index.json"])
    index["states"]["KS"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)
    archive = {"url": history.KS_URL, **pin(b"index")}
    entry = {"status": "reported", "source": archive, "data": {"current_election_status": "workbook_not_linked"}}
    snapshot = {"granular_sources": {history.KS_FEED: entry}}
    assert totals.project(files, snapshot) == (files, [])
    original_url = "/elections/22elec/2022-General-Election-Turnout-Information.xlsx"
    current_url = "/elections/26elec/2026-General-Election-Turnout-Information.xlsx"
    link = lambda url: f'<a href="{url}">Turnout Information</a>'.encode()
    assert history.kansas_link(link(original_url), 2026) is None
    assert history.kansas_link(link("https://example.org" + current_url), 2026) is None
    declared = history.kansas_link(link(original_url) + link(current_url), 2026)
    assert declared == "https://www.sos.ks.gov" + current_url
    names = [f"COUNTY {n:03}" for n in range(105)]
    monkeypatch.setattr(history, "KS_COUNTIES", pin(encoded(names)))
    query = {"counties": [[name, "N/A", 100, 200] for name in names], "total": [0, 10500, 21000]}
    entry["data"] = {"report": {"url": declared, **pin(b"workbook")}, "complete_native_query": query}
    projected, changes = totals.project(files, snapshot)
    assert changes == [{"state_code": "KS", "id": totals.identity("KS"), "previous": None,
                        "current": 10500, "source_status": "reported"}]
    original_shard, next_shard = (json.loads(gzip.decompress(value[path])) for value in (files, projected))
    assert original_shard["views"] == next_shard["views"]
    row = next_shard["records"][-1]
    assert row["view"]["validated_pct"] == 50 and row["source_clock"]["literal"] is None
    assert totals.project(projected, snapshot) == (projected, [])
    retained, changes = totals.project(projected, {})
    assert changes[0]["current"] == 10500 and changes[0]["source_status"] == "retained_after_failure"
    assert totals.project(retained, {}) == (retained, [])
    query["counties"][0][2] += 1
    with pytest.raises(ValueError, match="statewide totals disagree"):
        totals.project(projected, snapshot)


def test_north_carolina_exports_retained_report_without_stale_baseline_double_count(monkeypatch):
    from scripts.supported_analytical_release import administrative, administrative_coverage

    root = Path(__file__).resolve().parents[1]
    original = (root / totals.NC_INPUT).read_bytes()
    files = baseline(monkeypatch)
    path = "states/NC.json.gz"
    files[path] = (root / "data/results-intake/baseline/counts" / path).read_bytes()
    index = json.loads(files["index.json"])
    index["states"]["NC"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)
    projected, [change] = totals.project(files, {}, original)
    assert change["current"] == 4242662 and change["source_status"] == "retained_after_failure"
    assert totals.project(projected, {}, original) == (projected, [])
    admin = administrative(projected)
    superseded = next(x for x in admin if x["observation_id"] == totals.NC_BASELINE_ID)
    current = next(x for x in admin if x["observation_id"] == totals.identity("NC"))
    assert superseded["superseded_by_observation_id"] == current["observation_id"]
    assert current["registered_or_other_denominator"] == 7885046
    assert current["source_timezone"] is None
    coverage = next(x for x in administrative_coverage(admin) if x["state_code"] == "NC")
    assert coverage["statewide_election_participation_count_records"] == 1
    with pytest.raises(ValueError, match="retained original hash changed"):
        totals.project(files, {}, original + b" ")


def test_oregon_projects_same_report_statewide_rate_without_changing_county_views(monkeypatch):
    files = baseline(monkeypatch)
    path = "states/OR.json.gz"
    original_path = Path(__file__).resolve().parents[1] / "data/results-intake/baseline/counts" / path
    shard = json.loads(gzip.decompress(original_path.read_bytes()))
    original_statewide = next(row for row in shard["records"] if row["id"] == totals.OR_BASELINE_ID)
    files[path] = totals.compressed(shard)
    index = json.loads(files["index.json"])
    index["states"]["OR"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)
    current = json.loads(gzip.decompress(files["current.json.gz"]))
    clock = "11/18/2026 | 10:45 PM PT"
    current["snapshot"]["reporting"].append({
        "state_code": "OR", "source_url": totals.OR_DISPLAY_URL,
        "source_update_label": clock, "ballots": 360, "denominator": 720,
        "denominator_basis": "active_registered_voters",
    })
    files["current.json.gz"] = totals.compressed(current)
    counties = {str(i): f"County {i}" for i in range(36)}
    monkeypatch.setattr(totals, "OR_COUNTIES", pin(encoded(counties)))
    header = {"election_date": "11/3/2026", "election_type": "General", "status": "Unofficial",
              "statewide_clock_zone_literal": "PT", "source_update_label": clock, "counties": counties,
              "ballots_counted": 360, "active_registered_voters": 720, "source_pin": pin(b"header")}
    query = {"independent_official_header": header, "source_pin": pin(b"counties"), "county_records": [
        {"CountyID": key, "CountyName": name, "PrecinctName": "Countywide",
         "calcVoterTurnout": 10, "Voters": 20} for key, name in counties.items()
    ]}
    entry = {"status": "reported", "adapter": totals.oregon.ADAPTER,
             "source": {"url": totals.oregon.API_URL, **query["source_pin"]},
             "data": {"complete_native_query": [query], "updates": []}}
    snapshot = {"granular_sources": {totals.OR_FEED: entry}}
    projected, [change] = totals.project(files, snapshot)
    state = json.loads(gzip.decompress(projected[path]))
    original = state["records"][-1]
    assert state["records"][:-1] == shard["records"]
    assert state["views"] == shard["views"]
    assert change["current"] == 360 and original["view"]["validated_pct"] == 50
    assert original["source_clock"] == {"literal": clock, "timezone": "PT"}
    assert totals.project(projected, snapshot) == (projected, [])
    assert b"OR,2026,360,reported,720,50.0" in totals.exports(projected)[
        "participation/native-statewide-ballot-totals.csv"]
    snapshot["collection_scope"] = {"mode": "selected_registered_source_refresh",
                                    "source_ids": [totals.OR_FEED]}
    from scripts.supported_analytical_release import administrative, administrative_coverage, selected_local_observation_ids
    assert selected_local_observation_ids(snapshot, projected) == {original["id"]}
    admin = administrative(projected)
    audit = next(row for row in admin if row["observation_id"] == totals.OR_BASELINE_ID)
    assert audit["source_count"] == original_statewide["count"]["value"]
    assert audit["superseded_by_observation_id"] == original["id"]
    coverage = next(row for row in administrative_coverage(admin) if row["state_code"] == "OR")
    assert coverage["statewide_superseded_records"] == 1
    assert coverage["statewide_election_participation_count_records"] == 1
    revised = copy.deepcopy(snapshot)
    new_query, = revised["granular_sources"][totals.OR_FEED]["data"]["complete_native_query"]
    new_query["county_records"][0]["calcVoterTurnout"] -= 1
    with pytest.raises(ValueError, match="do not reconcile"):
        totals.project(projected, revised)
    new_query["independent_official_header"].update(ballots_counted=359, source_pin=pin(b"new"))
    new_query["source_pin"] = pin(b"new counties")
    revised["granular_sources"][totals.OR_FEED]["source"].update(new_query["source_pin"])
    revised_files, [change] = totals.project(projected, revised)
    assert change["previous"] == 360 and change["current"] == 359
    assert totals.project(revised_files, revised) == (revised_files, [])
    new_query["independent_official_header"].update(
        source_update_label="11/17/2026 | 10:45 PM PT", source_pin=pin(b"older header"))
    retained, [change] = totals.project(revised_files, revised)
    assert change["current"] == 359 and change["source_status"] == "retained_after_failure"
    assert totals.project(retained, {}) == (retained, [])


def test_georgia_reconciles_county_ballots_and_retains_a_bad_revision(tmp_path, monkeypatch):
    from scripts.results_intake import Collector

    h = totals.history
    files = baseline(monkeypatch)
    path = "states/GA.json.gz"
    shard = {"contract": "participation.count_snapshot.v1", "state_code": "GA", "year": 2026,
             "records": [], "views": {}}
    files[path] = totals.compressed(shard)
    index = json.loads(files["index.json"])
    index["states"]["GA"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)
    counties = {f"{i:036x}": f"County {i}" for i in range(159)}
    monkeypatch.setattr(h, "GA_COUNTIES", pin(encoded(counties)))
    name = lambda text: [{"languageId": "en", "text": text}]
    election = {"id": h.GA_ELECTION, "jurisdictionId": h.GA_JURISDICTION,
                "electionDate": "2026-11-03", "isPrimary": False, "isProduction": True,
                "name": name("November 3, 2026 - General & Special Elections"),
                "publishDate": "2026-11-18T21:00:00.1234567Z", "isOfficialResults": False,
                "ballotsCast": 0.0, "totalVoters": 1590.0}
    body = {"election": election, "jurisdiction": {"id": h.GA_JURISDICTION, "name": name("Georgia"),
            "childLocalities": [{"id": key.upper(), "name": name(label)} for key, label in counties.items()]},
            "localityElections": [{**election, "id": f"{i + 159:036x}", "jurisdictionId": key,
                "ballotsCast": 5.0, "totalVoters": 10.0, "lastUpdated": "2026-11-17T00:00:00Z",
                "precinctsReporting": 1.0} for i, key in enumerate(counties)],
            "voterRegistration": [{"id": key, "localityName": name(label), "total": 10}
                                  for key, label in counties.items()]}

    def acquire(self, _url):
        blob = encoded(body)
        return blob, {"origin": "fixture_transport", **pin(blob)}

    monkeypatch.setattr(Collector, "acquire", acquire)

    def collect(prior=None):
        collector = Collector(tmp_path, prior or {}, {"urls": [], "prefixes": [], "hosts": []},
                              datetime(2026, 11, 19, tzinfo=timezone.utc))
        return {h.GA_FEED: h.collect_georgia(collector)}

    accepted = collect()
    assert collect(accepted) == accepted
    projected, [change] = totals.project(files, {"granular_sources": accepted})
    assert change["current"] == 795
    body["localityElections"][0]["ballotsCast"] -= 1
    revised = collect(accepted)
    projected, [change] = totals.project(projected, {"granular_sources": revised})
    assert change["current"] == 794 and totals.project(projected, {"granular_sources": revised}) == (projected, [])
    body["voterRegistration"][0]["total"] = 9
    failed = collect(revised)
    assert failed[h.GA_FEED]["status"] == "retained_after_failure"
    _, [change] = totals.project(projected, {"granular_sources": failed})
    assert change["current"] == 794 and change["source_status"] == "retained_after_failure"


def test_new_jersey_future_archive_publication_retains_last_good(tmp_path, monkeypatch):
    import pypdf
    from scripts.results_intake import Collector

    def pdf_reader(stream):
        body = stream.read().removeprefix(b"%PDF- ").decode()
        return SimpleNamespace(is_encrypted=False, pages=[
            SimpleNamespace(extract_text=lambda **_: body),
        ])

    monkeypatch.setattr(pypdf, "PdfReader", pdf_reader)
    history = totals.history
    files = baseline(monkeypatch)
    path = "states/NJ.json.gz"
    original = Path(__file__).resolve().parents[1] / "data/results-intake/baseline/counts" / path
    files[path] = original.read_bytes()
    ndx = json.loads(files["index.json"])
    ndx["states"]["NJ"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(ndx)
    url = history.NJ_URL.rsplit("/", 1)[0] + "/assets/pdf/election-results/2026/2026-official-general-voter-turnout.pdf"
    links = b'<a href="2026-official-primary-voter-turnout.pdf">Primary turnout</a>'
    report = "\n".join((
        *history.NJ_HEADER[:2], "General Election November 3, 2026", *history.NJ_HEADER[2:],
        *[f"{name} 2,000 1,000 2 50% 8" for name in history.NJ_COUNTIES],
        "TOTAL 42,000 21,000 42 50% 168", "NJDOE-11/30/2026",
    ))

    def acquire(self, source):
        assert source in (history.NJ_URL, url)
        body = links if source == history.NJ_URL else b"%PDF- " + report.encode()
        return body, {"origin": "fixture_transport", **pin(body)}

    monkeypatch.setattr(Collector, "acquire", acquire)
    feed = history.NJ_FEED
    def collect(prior=None):
        collector = Collector(tmp_path, prior or {}, {"urls": [], "prefixes": [], "hosts": []},
                              datetime(2026, 12, 1, tzinfo=timezone.utc))
        return {feed: history.collect_new_jersey(collector)}

    missing = collect()
    assert missing[feed]["data"]["current_election_status"] == "report_not_linked"
    assert totals.project(files, {"granular_sources": missing}) == (files, [])
    links += f'<a href="{url}">General turnout</a>'.encode()
    accepted = collect(missing)
    assert accepted[feed]["status"] == "reported"
    projected, changes = totals.project(files, {"granular_sources": accepted})
    assert changes == [{"state_code": "NJ", "id": totals.identity("NJ"), "previous": None,
                        "current": 21000, "source_status": "reported"}]
    original_shard, next_shard = (json.loads(gzip.decompress(value[path])) for value in (files, projected))
    assert original_shard["views"] == next_shard["views"]
    assert original_shard["records"] == next_shard["records"][:-1]
    row = next_shard["records"][-1]
    assert row["source"]["url"] == url and row["denominator"]["value"] == 42000
    assert row["view"]["validated_pct"] == 50 and row["source_clock"]["literal"] is None
    assert collect(accepted) == accepted
    assert totals.project(projected, {"granular_sources": accepted}) == (projected, [])
    report = report.replace("21,000 42", "21,001 42")
    failed = collect(accepted)
    assert failed[feed]["status"] == "retained_after_failure"
    assert failed[feed]["error_detail"] == "New Jersey turnout report county and statewide totals disagree"
    retained, changes = totals.project(projected, {"granular_sources": failed})
    assert changes[0]["current"] == 21000 and changes[0]["source_status"] == "retained_after_failure"
    assert totals.project(retained, {"granular_sources": failed}) == (retained, [])


def test_ohio_accepts_reconciled_unofficial_statewide_turnout_and_retains_conflicts(tmp_path, monkeypatch):
    from scripts import results_county_frame as frame
    from scripts.results_intake import Collector
    from scripts.participation_intake.contract import observation_id

    history = totals.history
    files = baseline(monkeypatch)
    path = "states/OH.json.gz"
    original = Path(__file__).resolve().parents[1] / "data/results-intake/baseline/counts" / path
    shard = frame.decode(original.read_bytes())
    by_id = {row["id"]: row for row in shard["records"]}
    early = [by_id[key]["view"] for key in shard["views"]["in_person_early"]["counties"]]
    cuyahoga = observation_id(frame.CUYAHOGA[5], frame.CUYAHOGA_ELECTION, frame.CUYAHOGA_GEO,
                               "countywide-ballots-cast", "all_methods")
    shard["records"].append({"id": cuyahoga, "source": {"id": frame.CUYAHOGA[5]}, "denominator": None,
                            "count": {"status": "reported", "value": 21}, "view": {}})
    modes = ("official", "uf_vap", "uf_vep")
    for mode in modes:
        shard["views"][mode]["counties"] = [cuyahoga]
    files[path] = totals.compressed(shard)
    ndx = json.loads(files["index.json"])
    ndx["states"]["OH"] = {"file": path, **pin(files[path]),
                          "views": {mode: {"dispositions": {}} for mode in modes}}
    ndx["coverage"]["OH"] = {}
    files["index.json"] = encoded(ndx)
    scopes = {view["county_fips"]: {"state_code": "OH", "name": view["county"], "boundary_year": 2026}
              for view in early}
    bounds = {"feature_scopes": scopes, "features": len(scopes), "feature_keys": list(scopes),
              "sha256": frame.CUYAHOGA_REFERENCE}
    native = {"index.json": encoded({"county_bindings": {"OH": {
        "in_person_early": {**bounds, "rows": [{"feature_key": view["county_fips"], "county_id": view["county_id"]}
                                            for view in early]},
        **{mode: {**bounds, "rows": [{"feature_key": frame.CUYAHOGA_FIPS}]} for mode in modes},
    }}})}
    county = ["20", "40", "1", "1", "2", "3"]
    control = [str(88 * int(value)) for value in county]
    parent = dict(zip(history.OH_FIELDS, control), objectId=None, name="Totals", ballotCastPercent="50.00")
    names = [view["county"].removesuffix(" County") for view in early]
    rows = [dict(zip(history.OH_FIELDS, county), objectId=f"_{i}", name=name,
                 ballotCastPercent="50.00") for i, name in enumerate(names)]
    xml = (f'<ElectionReport xmlns="{history.OH_NS["n"]}" IssuerAbbreviation="OH" '
           'Status="UnofficialComplete" GeneratedDate="2026-11-13T09:43:04Z">'
           '<Election Date="2026-11-03" Type="General"><Name><LanguageString>'
           'November 3, 2026 General Unofficial Canvass</LanguageString></Name></Election><GpUnitCollection>'
           + "".join(f'<GpUnit ObjectId="_{i}" Name="{name}" Type="County" IsElectoralDistrict="false" '
                     'VotersParticipated="20" VotersRegistered="40" SubUnitsReported="1" TotalSubUnits="1"/>'
                     for i, name in enumerate(names))
           + '</GpUnitCollection></ElectionReport>').encode()

    def acquire(self, url):
        self.guard(url)
        body = xml if url == history.OH_ELECTION else encoded([parent, *rows, parent])
        return body, {"origin": "fixture_transport", **pin(body)}

    monkeypatch.setattr(Collector, "acquire", acquire)
    feed = history.OH_FEED

    def collect(prior=None, stopped=()):
        collector = Collector(tmp_path, prior or {}, {"urls": list(stopped), "prefixes": [], "hosts": []},
                              datetime(2026, 11, 19, tzinfo=timezone.utc))
        return {feed: history.collect_ohio(collector)}

    accepted = collect()
    assert accepted[feed]["status"] == "reported"
    assert collect(accepted) == accepted
    updated, changes = totals.project(files, {"granular_sources": accepted})
    assert [(r["state_code"], r["current"]) for r in changes] == [("OH", 1760)]
    before, after = [json.loads(gzip.decompress(value[path])) for value in (files, updated)]
    assert before["views"] == after["views"]
    row = after["records"][-1]
    assert row["denominator"]["value"] == 3520 and row["reporting_status"]["complete"] is None
    assert row["view"]["validated_pct"] == 50
    assert totals.project(updated, {"granular_sources": accepted}) == (updated, [])
    counties, bindings, additions = frame.project_ohio(updated, native)
    assert len(additions) == 87
    after_counties = frame.decode(counties[path])
    assert all(after_counties["views"][mode] == shard["views"][mode]
               for mode in ("available", "in_person_early", "mail_returned"))
    assert all(len(after_counties["views"][mode]["counties"]) == 88
               and after_counties["views"][mode]["counties"][0] == cuyahoga for mode in modes)
    assert frame.project_ohio(counties, bindings) == (counties, bindings, [])

    xml_only = collect(stopped=[history.OH_BALLOTS])
    assert xml_only[feed]["status"] == "reported"
    assert xml_only[feed]["source"]["url"] == history.OH_ELECTION
    assert collect(xml_only, [history.OH_BALLOTS]) == xml_only
    assert collect(accepted, [history.OH_BALLOTS])[feed]["status"] == "retained_after_failure"
    derived, changes = totals.project(files, {"granular_sources": xml_only})
    assert [r["current"] for r in changes] == [1760]
    source_view = frame.decode(derived[path])["records"][-1]["view"]
    assert source_view["validated_pct"] == 50
    assert "sums VotersParticipated" in " ".join(source_view["quality"])
    mapped, _, additions = frame.project_ohio(derived, native)
    assert len(additions) == 87
    county_view = frame.decode(mapped[path])["records"][-1]["view"]
    assert county_view["native_printed_pct"] is None
    assert county_view["native_record"]["outstanding_provisional"] is None

    xml = xml.replace(b'VotersParticipated="20"', b'VotersParticipated="19"', 1)
    revised = collect(xml_only, [history.OH_BALLOTS])
    revised_files, changes = totals.project(derived, {"granular_sources": revised})
    assert [r["current"] for r in changes] == [1759]
    assert revised_files[path] != derived[path]
    assert collect(revised, [history.OH_BALLOTS]) == revised
    failed = collect(accepted)
    assert failed[feed]["status"] == "retained_after_failure"
    assert "not reconciled" in failed[feed]["error_detail"]
    xml = xml.replace(f'Name="{names[0]}"'.encode(), b'Name="Unknown County"', 1)
    rejected = collect(revised, [history.OH_BALLOTS])[feed]
    assert rejected["status"] == "retained_after_failure"
    assert rejected["source"] == revised[feed]["source"]
    retained, changes = totals.project(updated, {"granular_sources": failed})
    assert changes[0]["current"] == 1760 and changes[0]["source_status"] == "retained_after_failure"
    assert totals.project(retained, {"granular_sources": failed}) == (retained, [])
    retained_state, _ = totals.project(counties, {"granular_sources": failed})
    retained_counties, retained_bindings, held = frame.project_ohio(retained_state, bindings)
    assert len(held) == 87 and all(item["previous"] == item["current"] == 20
                                   and item["source_status"] == "retained_after_failure" for item in held)
    assert frame.project_ohio(retained_counties, retained_bindings) == (retained_counties, retained_bindings, [])


def test_montana_heading_rate_and_reporting_must_reconcile(tmp_path, monkeypatch):
    from scripts.results_intake import Collector

    history = totals.history
    html = (
        "<h2>General Election - November 3, 2026</h2>"
        "Results last updated: 11/19/2026 12:20:20 AM MT"
        "<h2>Total Turnout <span>300</span><br />Registered Voters <span>1,000</span></h2>"
        """<canvas id="voter-turnout" voterturnout='300' votertotal='700'></canvas>"""
        '<div class="dough-percent"><span class="int">30</span><span class="dec">.00%</span></div>'
        """<canvas id="precinct-reported" precinctsreported='9' precinctspartial='1' """
        """precinctsnotreported='0'></canvas>"""
        '<div class="dough-percent"><span class="int">90</span><span class="dec">.00%</span></div>'
        "Partially <span>1</span><br/><div></div>Fully <span>9</span>"
    ).encode()

    def acquire(self, url):
        assert url == history.MT_URL
        return html, {"origin": "fixture_transport", **pin(html)}

    monkeypatch.setattr(Collector, "acquire", acquire)

    def collect(prior=None):
        collector = Collector(tmp_path, prior or {}, {"urls": [], "prefixes": [], "hosts": []},
                              datetime(2026, 11, 19, tzinfo=timezone.utc))
        return {history.MT_FEED: history.collect_montana(collector)}

    accepted = collect()
    snapshot = {"granular_sources": accepted}
    summary = totals.archive_report_summary(snapshot, "MT")
    row = totals.observation("MT", summary)
    assert row["count"]["value"] == 300 and row["view"]["validated_pct"] == 30
    assert row["measure"]["kind"] == "participation_reported"
    assert row["reporting_status"]["complete"] is False
    assert row["reporting_status"]["reported_units"] == 9
    html += b"<!-- changed page footer -->"
    assert collect(accepted) == accepted
    for wrong in (html.replace(b"11/19/2026", b"11/18/2026"),
                  html.replace(b"votertotal='700'", b"votertotal='701'"),
                  html.replace(b"General Election - November", b"Primary Election - November")):
        html = wrong
        held = collect(accepted)[history.MT_FEED]
        assert held["status"] == "retained_after_failure"
        assert held["data"] == accepted[history.MT_FEED]["data"]

def test_connecticut_retained_control_and_versioned_successor(monkeypatch):
    files = baseline(monkeypatch)
    path = "states/CT.json.gz"
    original = Path(__file__).resolve().parents[1] / "data/results-intake/baseline/counts" / path
    files[path] = original.read_bytes()
    index = json.loads(files["index.json"])
    index["states"]["CT"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)
    retained, changes = totals.project(files, {})
    assert changes == [{"state_code": "CT", "id": totals.identity("CT"), "previous": None,
                        "current": 1150127, "source_status": "retained_after_failure"}]
    original_shard = json.loads(gzip.decompress(files[path]))
    shard = json.loads(gzip.decompress(retained[path]))
    assert shard["views"] == original_shard["views"] and shard["records"][:-1] == original_shard["records"]
    row = shard["records"][-1]
    assert row["denominator"] is None and totals.project(retained, {}) == (retained, [])
    archive = row["view"]["statewide_ballot_parent"]
    query = {key: {"NM": name, **dict(zip(totals.CT_FIELDS, values))}
             for key, name, *values in archive["towns"]}
    query["1"]["VV"] = str(int(query["1"]["VV"]) + 10)
    query["170"] = {"NM": "Total", **dict(zip(totals.CT_FIELDS, archive["total"])), "VV": "1150137"}
    entry = {"status": "reported", "data": {
        "complete_native_query": query, "source_version": 52338,
        "source_url": totals.CT_ROOT + "52338/voterTurnout_Electiondata.json",
        "numerical_input_pins": {"voterTurnout_Electiondata": pin(encoded(query))},
        "election_parent": {**archive["parent"], "BC": "1,150,137"}}}
    snapshot = {"granular_sources": {totals.CT_FEED: entry}}
    changed, changes = totals.project(retained, snapshot)
    assert changes[0]["current"] == 1150137 and changes[0]["source_status"] == "reported"
    assert totals.project(changed, snapshot) == (changed, [])
    assert totals.project(changed, {})[1][0]["source_status"] == "retained_after_failure"
    query["1"]["VV"] = "0"
    with pytest.raises(ValueError, match="controls and direct statewide parent disagree"):
        totals.project(retained, snapshot)


def test_hawaii_direct_parent_preserves_known_cross_scope_difference(monkeypatch):
    from decimal import Decimal

    def report(name, registered, mail, in_person):
        counts = dict(zip(stats.HI_FIELDS, (registered, mail + in_person, mail, in_person)))
        fractions = {key: f"{Decimal(counts[key]) * 100 / registered:.1f}"
                     for key in stats.HI_FIELDS[1:]}
        return {"source": {"url": stats.HI_ROOT + name + ".pdf", "bytes": 1000, "sha256": "a" * 64},
                "pages": [{"page": 1, "source_clock": "Printed on: 11/10/2026 at 08:00:08 pm",
                           "native_report_status_literal": "FINAL", "count": mail + in_person,
                           "registered": registered, "native_values": counts,
                           "native_fraction_literal": fractions["TOTAL TURNOUT"] + "%",
                           "statistical_cells": {key: {"value": value, "fraction": fractions.get(key)}
                                                 for key, value in counts.items()}}]}

    reports = {name: report(name, *values) for name, values in zip(stats.HI_REPORTS, (
        (853399, 374918, 17510), (550792, 244938, 9548), (135544, 59040, 3517),
        (49337, 23244, 1485), (117726, 47696, 2962)))}
    facts = stats.hawaii_controls(reports)
    assert facts["administration_minus_statewide"]["In-Person TURNOUT"] == 2
    files = baseline(monkeypatch)
    path = "states/HI.json.gz"
    original = Path(__file__).resolve().parents[1] / "data/results-intake/baseline/counts" / path
    files[path] = original.read_bytes()
    index = json.loads(files["index.json"])
    index["states"]["HI"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)
    snapshot = {"granular_sources": {stats.HI_FEED: {
        "status": "reported", "source": reports["histatewide"]["source"],
        "data": {"complete_native_query": reports, "reconciliation": facts}}}}
    projected, changes = totals.project(files, snapshot)
    assert len(changes) == 1 and changes[0]["current"] == 392428
    after = json.loads(gzip.decompress(projected[path]))
    before = json.loads(gzip.decompress(files[path]))
    assert before["records"] == after["records"][:-1] and before["views"] == after["views"]
    assert after["records"][-1]["denominator"] is None
    assert totals.project(projected, snapshot) == (projected, [])
    held, changes = totals.project(projected, {})
    assert changes[0]["current"] == 392428 and changes[0]["source_status"] == "retained_after_failure"
    assert totals.project(held, {}) == (held, [])
    reports["com"] = report("com", 117726, 47696, 2963)
    with pytest.raises(ValueError, match="new cross-scope discrepancy"):
        stats.hawaii_controls(reports)


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


def test_texas_retained_archive_never_qualifies_2026_or_displaces_accepted_source():
    h = totals.history
    archive = (Path(__file__).resolve().parents[1] / h.TX_ARCHIVE_INPUT).read_bytes()
    unavailable = {"status": "source_access"}
    fallback = h.texas_history_entry(unavailable, archive)
    assert fallback["status"] == "retained_after_failure"
    assert fallback["data"]["latest_attempt_status"] == "source_access"
    assert fallback["data"]["current_election_status"] == "not_yet_published"
    assert fallback["data"]["complete_native_query"][0]["total_voting"] == 11388674
    assert b",retained_after_failure," in h.history_csv(fallback, texas=True)
    accepted = {"status": "reported", "data": {"current_election_status": "row_published"}}
    assert h.texas_history_entry(accepted, archive) == accepted
    with pytest.raises(ValueError, match="checksum"):
        h.texas_history_entry(unavailable, archive + b"\n")


def test_texas_archive_ignores_primaries_and_activates_only_on_a_general_row(tmp_path, monkeypatch):
    from scripts.results_intake import Collector

    h = totals.history
    files = baseline(monkeypatch)
    path = "states/TX.json.gz"
    original = Path(__file__).resolve().parents[1] / "data/results-intake/baseline/counts" / path
    files[path] = original.read_bytes()
    index = json.loads(files["index.json"])
    index["states"]["TX"] = {"file": path, **pin(files[path])}
    files["index.json"] = encoded(index)

    def section(heading, turnout, rate):
        fields = (
            ("Registered Voters", "1,000"), ("Voting Age Population (VAP)", "2,000"),
            ("Percentage of VAP Registered", "50%"), ("Turnout", turnout),
            ("Percent of Turnout to Registered Voters", rate),
            ("Percent of Turnout to VAP", "25%"),
        )
        return f"<tr><th>{heading}</th></tr>" + "".join(
            f"<tr><td>{label}</td><td>{value}</td></tr>" for label, value in fields)

    past = section("2026 - Primary, March (Gubernatorial) Republican", 500, "50%") + "".join(
        section(f"{year} - General Election, November", 500, "50")
        for year in range(2024, 1969, -2))
    data = f"<table>{past}</table>".encode()

    def acquire(self, url):
        assert url == h.TX_URL
        return data, {"origin": "fixture_transport", **pin(data)}

    monkeypatch.setattr(Collector, "acquire", acquire)

    def collect(prior=None):
        collector = Collector(tmp_path, prior or {}, {"urls": [], "prefixes": [], "hosts": []},
                              datetime(2026, 11, 19, tzinfo=timezone.utc))
        return {h.TX_FEED: h.collect_texas(collector)}

    history = collect()
    result = history[h.TX_FEED]
    assert result["data"]["current_election_status"] == "not_yet_published"
    assert len(h.history_csv(result, texas=True).splitlines()) == 29
    assert totals.project(files, {"granular_sources": history}) == (files, [])
    data = f"<table>{section('2026 - November (Gubernatorial)', 501, '50.1%')}{past}</table>".encode()
    published = collect(history)
    projected, [change] = totals.project(files, {"granular_sources": published})
    assert change["current"] == 501
    row = json.loads(gzip.decompress(projected[path]))["records"][-1]
    assert row["view"]["validated_pct"] == 50.1
    assert row["measure"]["literal"] == "Turnout" and row["measure"]["kind"] == "participation_reported"
    assert not row["view"]["cast_ballot_count_qualified"]
    assert collect(published) == published
    assert totals.project(projected, {"granular_sources": published}) == (projected, [])
    data = f"<table>{section('2026 - November (Gubernatorial)', 499, '50.0%')}{past}</table>".encode()
    revised = collect(published)
    changed, [change] = totals.project(projected, {"granular_sources": revised})
    assert change["current"] == 499
    withdrawn = json.loads(gzip.decompress(changed[path]))["records"][-1]
    assert withdrawn["view"]["validated_pct"] is None
    assert native.compatible_refresh_identity(row, withdrawn)
    data = f"<table>{section('2026 - November (Gubernatorial)', 499, '49.9%')}{past}</table>".encode()
    corrected = collect(revised)
    recovered, [change] = totals.project(changed, {"granular_sources": corrected})
    restored = json.loads(gzip.decompress(recovered[path]))["records"][-1]
    assert change["previous"] == change["current"] == 499
    assert restored["view"]["validated_pct"] == 49.9
    assert native.compatible_refresh_identity(withdrawn, restored)
    bad = copy.deepcopy(restored)
    bad["view"]["statewide_ballot_parent"]["native_row"]["published_turnout"] = "51.0%"
    assert not native.compatible_refresh_identity(withdrawn, bad)
    bad = copy.deepcopy(restored)
    bad["denominator"]["basis"] = "different_population"
    assert not native.compatible_refresh_identity(withdrawn, bad)
    data = f"<table>{past}</table>".encode()
    failed = collect(corrected)
    assert failed[h.TX_FEED]["status"] == "retained_after_failure"
    assert totals.project(recovered, {"granular_sources": failed})[1][0]["current"] == 499


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
