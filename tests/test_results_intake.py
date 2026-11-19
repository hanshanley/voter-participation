import copy
from datetime import datetime, timezone
import gzip
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request
import zipfile

import pytest

from scripts import results_intake as intake
from scripts.participation_intake.contract import IntakeError, encoded, pin
from scripts.participation_intake.engine import AllowedRedirect, Store
from scripts.participation_intake.publisher import GitPublisher
from scripts.results_house import candidate_results, districts, state_totals


NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)
EMPTY_STOPS = {"urls": [], "prefixes": [], "hosts": []}


def declaration():
    regions, count = {}, 0
    for index, state in enumerate(code for code in intake.STATES if code != "DC"):
        for number in range(1, (9 if index < 35 else 8) + 1):
            count += 1
            regions[state.lower() + "-" + str(number).zfill(2)] = {
                "type": "Congressional District", "election_id": count}
    return {"test_data": False, "country": "US", "province": "US",
            "election_date": "2026-11-03", "election_type": "House of Representatives",
            "election_scope": "General", "region_results": regions}


def candidate(declared, votes=0):
    return {"test_data": False, "country": "US", "province": declared["state_code"],
            "district": declared["district"], "election_date": "2026-11-03",
            "election_type": "House of Representatives", "election_scope": "General",
            "last_updated": "2026-11-14T01:00:00Z", "percent_reporting": 100,
            "candidates": [{"name": "A", "party": "D", "votes": votes},
                           {"name": "B", "party": "R", "votes": 3}]}


def fixture(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    baseline = root / "accepted"
    (baseline / "states").mkdir(parents=True)
    index = {"states": {}}
    files = {}
    for state in intake.STATES:
        name = "states/" + state + ".json.gz"
        body = intake.compressed(encoded({"records": [{"id": state, "count": {"value": None}}]}))
        (baseline / name).write_bytes(body)
        files[name] = pin(body)
        index["states"][state] = {"file": name, **pin(body)}
    body = encoded(index)
    (baseline / "index.json").write_bytes(body)
    files["index.json"] = pin(body)
    config = {"contract": intake.CONTRACT, "election_date": "2026-11-03",
              "baseline": {"root": "accepted", "files": files},
              "jurisdictions": {code: {"url": None, "status": "not_listed_in_directory"}
                                for code in intake.STATES}, "source_stops": EMPTY_STOPS}
    (root / "registry.json").write_bytes(encoded(config))
    return root / "registry.json"


def unavailable(self, url):
    self.guard(url)
    raise IntakeError("source_unavailable", "Fixture transport unavailable")


def test_district_identity_and_missing_counts_are_not_completion_or_zero():
    native = declaration()
    declared = districts(native)
    assert len(declared) == 435
    row = next(iter(declared.values()))
    parsed = candidate_results(candidate(row), row)
    assert parsed["candidates"][0]["votes"] == 0
    assert parsed["certification_qualified"] is False
    assert parsed["candidate_votes_are_ballots"] is False
    for change in (None, True, -1):
        body = candidate(row)
        body["candidates"][0]["votes"] = change
        with pytest.raises(ValueError):
            candidate_results(body, row)
    body = candidate(row)
    body["election_scope"] = "Primary"
    with pytest.raises(ValueError):
        candidate_results(body, row)
    native["region_results"].pop(next(iter(native["region_results"])))
    with pytest.raises(ValueError):
        districts(native)
    aggregate = state_totals({row["district"]: {"status": "reported", "data": parsed}}, declared)
    assert next(item for item in aggregate if item["state_code"] == row["state_code"])["party_votes"] is None


@pytest.mark.parametrize("http_status", [403, 429])
def test_new_denial_survives_fresh_store_and_429_stops_host(tmp_path, monkeypatch, http_status):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            raise HTTPError(request.full_url, http_status, "Denied", {}, io.BytesIO(b""))
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    first = intake.Collector(tmp_path / "first", {}, EMPTY_STOPS, NOW)
    result = first.capture("source", "https://example.test/one", lambda body: {})
    assert result["data"] is None and len(calls) == 1
    second = intake.Collector(tmp_path / "new-cache", {}, intake.read(tmp_path / "first/source-stops.json"), NOW)
    second.capture("source", "https://example.test/one", lambda body: {})
    assert len(calls) == 1
    if http_status == 429:
        second.capture("other", "https://example.test/two", lambda body: {})
        assert len(calls) == 1


def test_redirect_target_is_checked_before_following_it(tmp_path):
    collector = intake.Collector(tmp_path, {},
                                {"urls": ["https://example.test/held"], "prefixes": [], "hosts": []}, NOW)
    handler = AllowedRedirect(["example.test"], collector.guard)
    with pytest.raises(IntakeError, match="Persisted"):
        handler.redirect_request(Request("https://example.test/allowed"), None, 302, "",
                                 {}, "https://example.test/held")


def test_source_failure_keeps_prior_counts_and_clocks(tmp_path, monkeypatch):
    prior = {"source": {"status": "reported", "data": {"total": 12, "date": "2026-11-12"},
                        "source": {"url": "https://example.test/data", "bytes": 1, "sha256": "a" * 64},
                        "first_observed_at": "old", "error": None}}
    monkeypatch.setattr(intake.Collector, "acquire", unavailable)
    collector = intake.Collector(tmp_path, prior, EMPTY_STOPS, NOW)
    result = collector.capture("source", "https://example.test/data", lambda body: {})
    assert result["data"] == prior["source"]["data"]
    assert result["source"] == prior["source"]["source"]
    assert result["status"] == "retained_after_failure"


def test_failed_capture_preserves_attempt_url_input_pin_and_specific_parser_reason(tmp_path, monkeypatch):
    body = b"permitted public aggregate fixture"
    monkeypatch.setattr(intake.Collector, "acquire", lambda self, url: (
        body, {"origin": "retained_fixture", **pin(body)}))
    collector = intake.Collector(tmp_path, {}, EMPTY_STOPS, NOW)
    def parse(body):
        raise ValueError("Native precinct/county totals disagree")
    result = collector.capture("WI-registered-fixture", "https://official.test/report", parse)
    assert result["source"] is None
    assert result["attempted_source_url"] == "https://official.test/report"
    assert result["attempted_source_pin"] == pin(body)
    assert result["error_stage"] == "parsing"
    assert result["error_detail"] == "Native precinct/county totals disagree"
    assert result["error"] == "schema_or_source_semantics_changed"
    collector.prior["WI-registered-fixture"] = result
    recovered = collector.capture(
        "WI-registered-fixture", "https://official.test/report", lambda body: {"total": 0})
    assert recovered["status"] == "reported" and recovered["data"]["total"] == 0
    assert recovered["error_detail"] is None and recovered["error_stage"] is None


def test_selected_refresh_reuses_every_other_capture_and_rejects_unknown_sources(tmp_path, monkeypatch):
    from scripts import results_native
    registry = fixture(tmp_path)
    identity = "WI-registered-87e0d6c3aa94b8a6"
    previous = {
        "feeds": {"unchanged-feed": {"status": "reported", "data": {"total": 12}}},
        "granular": {"unchanged": {"status": "reported", "data": {"updates": []}}},
        "districts": {str(index): {} for index in range(435)},
        "house": {str(index): {"status": "reported", "data": {"count": index}} for index in range(435)},
        "directories": {state: {} for state in intake.STATES}, "source_stops": EMPTY_STOPS,
    }
    original = copy.deepcopy(previous)
    calls = []
    monkeypatch.setattr(results_native, "source_plan", lambda baseline: {
        "WI": {identity: {"adapter": "reviewed_pdf_county_parent"}}})
    def selected(collector, baseline, source_ids=None):
        calls.append(source_ids)
        return {identity: {"status": "reported", "data": {"updates": []}}}
    monkeypatch.setattr(results_native, "collect_sources", selected)
    monkeypatch.setattr(intake, "export_collection",
                        lambda work, config, baseline, inputs, extras, now, attempts: inputs)
    result = intake.refresh_selected(registry, tmp_path / "scoped", previous, [identity], NOW)
    assert calls == [{identity}] and previous == original
    assert result["house"] == original["house"]
    assert result["feeds"]["unchanged-feed"] == original["feeds"]["unchanged-feed"]
    assert result["granular"]["unchanged"] == original["granular"]["unchanged"]
    assert result["collection_scope"]["source_ids"] == [identity]
    with pytest.raises(ValueError, match="dispatch plan"):
        intake.refresh_selected(registry, tmp_path / "wrong", previous, ["WI-registered-" + "0" * 16], NOW)
    assert len(calls) == 1
    monkeypatch.setattr(results_native, "collect_sources", lambda *args, **kwargs: {
        identity: {"status": "schema_or_source_semantics_changed", "data": None}})
    monkeypatch.setattr(intake, "export_collection",
                        lambda *args: pytest.fail("A failed selected capture must not be published"))
    with pytest.raises(ValueError, match="no replacement publication"):
        intake.refresh_selected(registry, tmp_path / "failed", previous, [identity], NOW)
    assert previous == original


def test_uf_only_dispatch_preserves_congress_counties_and_every_other_source(tmp_path, monkeypatch):
    from scripts import results_native, results_uf_turnout as uf
    registry = fixture(tmp_path)
    intake.write(registry.parent / "uf-turnout.json", uf.CONFIG)
    previous = {
        "feeds": {"unchanged-feed": {"status": "reported", "data": {"total": 12}}},
        "granular": {"unchanged": {"status": "reported", "data": {"updates": []}}},
        "districts": {str(index): {} for index in range(435)},
        "house": {str(index): {"status": "reported", "data": {"count": index}} for index in range(435)},
        "congress": {"native_clock": "must stay unchanged"},
        "directories": {state: {} for state in intake.STATES}, "source_stops": EMPTY_STOPS,
    }
    original, calls = copy.deepcopy(previous), []
    monkeypatch.setattr(results_native, "source_plan", lambda baseline: {})
    monkeypatch.setattr(results_native, "collect_sources",
                        lambda *args, **kwargs: pytest.fail("UF refresh must not acquire local sources"))
    def collect(collector, config):
        calls.append(config)
        return {"status": "reported", "data": {"rows": []}}
    monkeypatch.setattr(uf, "collect", collect)
    monkeypatch.setattr(intake, "export_collection",
                        lambda work, config, baseline, inputs, extras, now, attempts: inputs)
    result = intake.refresh_selected(registry, tmp_path / "selected", previous, [uf.IDENTITY], NOW)
    assert calls == [uf.CONFIG] and previous == original
    for key in ("granular", "districts", "house", "congress", "directories", "source_stops"):
        assert result[key] == original[key]
    assert result["feeds"]["unchanged-feed"] == original["feeds"]["unchanged-feed"]
    assert result["collection_scope"]["source_ids"] == [uf.IDENTITY]


@pytest.mark.parametrize("ohio_status", ["reported", "source_stopped", "retained_after_failure"])
def test_selected_administrative_refresh_does_not_reacquire_congress(tmp_path, monkeypatch, ohio_status):
    from scripts import philadelphia_divisions, results_native, results_pdf_county_parent, results_turnout_history

    registry = fixture(tmp_path)
    previous = {
        "feeds": {"unchanged": {"status": "reported", "data": {"total": 12}}},
        "granular": {},
        "districts": {str(index): {} for index in range(435)},
        "house": {str(index): {"status": "reported", "data": {"count": index}} for index in range(435)},
        "congress": {"native_clock": "must stay unchanged"},
        "directories": {state: {} for state in intake.STATES}, "source_stops": EMPTY_STOPS,
    }
    calls = []

    def adapter(identity):
        def capture(_):
            calls.append(identity)
            status = ohio_status if identity == selected[0] else "reported"
            return {"status": status, "data": None if status == "source_stopped" else {"identity": identity}}
        return capture

    selected = [results_turnout_history.OH_FEED, results_pdf_county_parent.PHILADELPHIA_FEED,
                philadelphia_divisions.FEED]
    monkeypatch.setattr(results_turnout_history, "collect_ohio", adapter(selected[0]))
    monkeypatch.setattr(results_pdf_county_parent, "collect_philadelphia", adapter(selected[1]))
    monkeypatch.setattr(philadelphia_divisions, "collect", adapter(selected[2]))
    monkeypatch.setattr(results_native, "collect_sources",
                        lambda *args, **kwargs: pytest.fail("Scoped refresh must not acquire unrelated sources"))
    monkeypatch.setattr(intake, "export_collection",
                        lambda work, config, baseline, inputs, extras, now, attempts: inputs)

    result = intake.refresh_selected(registry, tmp_path / "scoped", previous, selected, NOW)
    assert calls == selected and set(result["granular"]) == set(selected)
    assert result["granular"][selected[0]]["status"] == ohio_status
    assert result["granular"][selected[1]]["status"] == result["granular"][selected[2]]["status"] == "reported"
    for key in ("feeds", "districts", "house", "congress", "directories", "source_stops"):
        assert result[key] == previous[key]


def test_accepted_candidate_strings_survive_a_blocked_live_declaration(tmp_path, monkeypatch):
    registry = fixture(tmp_path)
    rows = [{"state_code": row["state_code"], "district": row["district"],
             "name": "A", "party": "D", "votes": "12", "source_updated_at": "old",
             "source_url": row["url"]} for row in districts(declaration()).values()]
    body = encoded(rows)
    (registry.parent / "candidates.json").write_bytes(body)
    config = intake.read(registry)
    config["accepted_queries"] = {
        "accepted-current-candidate-queries.json": {"file": "candidates.json", **pin(body)}}
    intake.write(registry, config)
    monkeypatch.setattr(intake.Collector, "acquire", unavailable)
    report = intake.collect(registry, tmp_path / "run", now=NOW)
    assert report["house_districts_available"] == 435
    state = intake.read(tmp_path / "run/state.json")
    assert all(row["data"]["candidates"][0]["votes"] == 12 for row in state["house"].values())
    assert all(row["url"] is None for row in state["districts"].values())
    assert all(row["retained_districts"] == row["available_districts"]
               for row in state_totals(state["house"], state["districts"]))
    rows[0]["votes"] = None
    with pytest.raises(ValueError, match="accepted candidate"):
        intake.house_baseline(rows)


def test_cached_resume_keeps_new_stops_and_never_opens_transport(tmp_path, monkeypatch):
    work = tmp_path / "run"
    store = Store(work / "cache")
    body = b'{"value":12}'
    sha = intake.digest(body)
    store.object(body)
    store.db.execute("INSERT INTO inputs VALUES(?,?,?,?,?)",
                     ("https://example.test/allowed", sha, None, None, None))
    store.db.commit()
    monkeypatch.setattr("urllib.request.build_opener",
                        lambda *args: pytest.fail("Offline resume opened transport"))
    collector = intake.Collector(work, {}, EMPTY_STOPS, NOW, offline=True)
    assert collector.acquire("https://example.test/allowed")[0] == body
    registry = fixture(tmp_path)
    intake.write(work / "source-stops.json",
                 {"urls": [intake.API + "/AL/capabilities"], "prefixes": [], "hosts": []})
    intake.collect(registry, work, now=NOW, offline=True)
    assert intake.API + "/AL/capabilities" in intake.read(work / "source-stops.json")["urls"]


def test_all51_full_queries_and_extracted_packet_replay_without_network(tmp_path, monkeypatch):
    registry = fixture(tmp_path)
    monkeypatch.setattr(intake.Collector, "acquire", unavailable)
    report = intake.collect(registry, tmp_path / "run", now=NOW)
    assert report["jurisdictions"] == 51 and report["house_districts_available"] == 0
    snapshot = json.loads(gzip.decompress((tmp_path / "run/snapshot.json.gz").read_bytes()))
    assert len(snapshot["jurisdictions"]) == 51
    assert len(snapshot["participation_observations"]) == 51
    assert all(row["observation"]["count"]["value"] is None
               for row in snapshot["participation_observations"])
    packet = tmp_path / "packet"
    with zipfile.ZipFile(tmp_path / "run/complete-results.zip") as archive:
        assert archive.testzip() is None
        archive.extractall(packet)
    replayed = intake.replay(packet, tmp_path / "reproduced")
    assert replayed["complete_outputs"] == 10
    subprocess.run([sys.executable, "-c",
        "import sys; sys.path[:0]=['code']; "
        "from scripts import results_pdf_tables as pdf; "
        "from scripts import results_pdf_boston, results_json_statistics, results_pdf_periodic; "
        "from scripts import results_pdf_periodic_ocr, automatic_native_refresh; "
        "from scripts import results_pdf_affiliations, results_pdf_jefferson, results_pdf_cass, results_pdf_dunn; "
        "from scripts import results_native_state_family, results_native_virginia; "
        "from scripts import results_native_delaware, results_native_dc, results_native_idaho; "
        "from scripts import results_native_north_carolina; "
        "from scripts import results_native_utah; "
        "from scripts import results_state_statistics; "
        "from scripts import native_pdf, pdf_group_queries; "
        "import json; "
        "assert pdf.Path('code/scripts/results_pdf_cass.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_pdf_cass.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_cass.py').is_file(); "
        "assert pdf.Path('code/scripts/results_pdf_dunn.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_pdf_dunn.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_state_family.py').is_file(); "
        "assert pdf.Path('code/scripts/results_native_virginia.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_virginia.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_virginia_repair.py').is_file(); "
        "assert pdf.Path('code/scripts/results_native_delaware.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_delaware.py').is_file(); "
        "assert pdf.Path('code/tests/fixtures/delaware-native/accepted-de-shard.json').is_file(); "
        "assert pdf.Path('code/tests/fixtures/delaware-native/complete-turnout.json').is_file(); "
        "assert pdf.Path('code/scripts/results_native_dc.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_dc.py').is_file(); "
        "assert pdf.Path('code/tests/fixtures/dc-native-accepted.json').is_file(); "
        "assert pdf.Path('code/scripts/results_native_idaho.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_idaho.py').is_file(); "
        "assert pdf.Path('code/tests/fixtures/idaho-native/accepted-data.json.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/idaho-native/accepted-ballots.xlsx.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/idaho-native/accepted-templates.json.gz').is_file(); "
        "assert pdf.Path('code/scripts/results_native_north_carolina.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_north_carolina.py').is_file(); "
        "assert pdf.Path('code/tests/fixtures/north-carolina-native/accepted-reporting.json.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/north-carolina-native/accepted-templates.json.gz').is_file(); "
        "assert pdf.Path('code/scripts/results_native_utah.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_utah.py').is_file(); "
        "assert pdf.Path('code/tests/fixtures/utah-native/api-data.json.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/utah-native/frozen-ut.json.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/utah-native/rolling7416-ut.json.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/utah-native/summaries/cache-summary.pdf.gz').is_file(); "
        "assert pdf.Path('code/scripts/results_state_statistics.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_state_statistics.py').is_file(); "
        "assert pdf.Path('code/scripts/results_native_louisiana_runtime.py').is_file(); "
        "assert pdf.Path('code/scripts/louisiana_bootstrap.py').is_file(); "
        "assert pdf.Path('code/tests/test_louisiana_onboarding.py').is_file(); "
        "assert pdf.Path('code/tests/LOUISIANA_ONBOARDING_TESTS.txt').is_file(); "
        "assert pdf.Path('code/tests/fixtures/louisiana-native/authority-resolution.json').is_file(); "
        "assert pdf.Path('code/tests/fixtures/louisiana-native/route-authority.json').is_file(); "
        "assert pdf.Path('code/tests/fixtures/louisiana-native/source-baseline/index.json').is_file(); "
        "assert pdf.Path('code/tests/fixtures/dunn-accepted.json').is_file(); "
        "assert (pdf.Path('code/tests/fixtures/results_pdf_periodic') / "
        "'complete-products.json.gz').is_file(); "
        "assert (pdf.Path('code/tests/fixtures/results_pdf_periodic') / "
        "'sussex-ocr-views.json.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/results_pdf_jefferson/"
        "complete-pages.json.gz').is_file(); "
        "p=json.loads(pdf.Path(pdf.__file__).with_name('results_pdf_grids.json').read_bytes()); "
        "assert len(p['source']['grids']) == 14; "
        "import pytest; "
        "assert pytest.main(['-q', '-p', 'no:cacheprovider', "
        "'code/tests/test_results_pdf_cass.py', "
        "'code/tests/test_results_native_cass.py', "
        "'code/tests/test_results_pdf_dunn.py', "
        "'code/tests/test_results_native_state_family.py', "
        "'code/tests/test_results_native_virginia.py', "
        "'code/tests/test_results_native_virginia_repair.py', "
        "'code/tests/test_results_native_delaware.py', "
        "'code/tests/test_results_native_dc.py', "
        "'code/tests/test_results_native_idaho.py', "
        "'code/tests/test_results_native_north_carolina.py', "
        "'code/tests/test_results_native_utah.py', "
        "'code/tests/test_results_state_statistics.py']) == 0"],
        cwd=packet, check=True, capture_output=True)
    assert (tmp_path / "reproduced/granular-source-queries.json.gz").is_file()
    assert (tmp_path / "reproduced/declared-numerical-queries.json.gz").is_file()
    (packet / "queries/coverage.csv").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Changed"):
        intake.replay(packet, tmp_path / "second")


def test_same_data_is_a_numerical_noop_despite_new_check_time(tmp_path, monkeypatch):
    registry = fixture(tmp_path)
    def fetch(self, url):
        self.guard(url)
        if url.endswith("/capabilities"):
            state = url.split("/")[-2]
            body = encoded({"state": state, "categories": {"inperson": {"race": False}}})
        elif url == intake.NATIONAL_URL:
            body = encoded(declaration())
        else:
            raise IntakeError("source_unavailable", "Fixture unavailable")
        return body, {"origin": "new_source_response", **pin(body)}
    monkeypatch.setattr(intake.Collector, "acquire", fetch)
    first = intake.collect(registry, tmp_path / "first", now=NOW)
    second = intake.collect(registry, tmp_path / "second", intake.read(tmp_path / "first/state.json"),
                            now=NOW.replace(hour=1))
    assert first["version"] == second["version"]
    assert first["files"] == second["files"]


def test_complete_factual_products_are_not_duplicated_as_participation_observations(tmp_path):
    registry = fixture(tmp_path)
    config = intake.read(registry)
    baseline = intake.baseline_inputs(registry.parent / "accepted", config["baseline"])
    facts = {"status": "reported", "source": {"url": "https://example.test/workbook"},
             "data": {"numerical_data_qualified": False,
                      "tables": [{"rows": [["label", "count"], ["native", 0], ["missing", None]]}]},
             "error": None, "first_observed_at": NOW.isoformat()}
    native = {"status": "reported", "source": {"url": "https://example.test/statistics"},
              "data": {"ballots": 0, "source_update_label": None}}
    inputs = {"feeds": {"CA-product": facts, "CA-official": native},
              "house": {}, "districts": {},
              "directories": {state: {"status": "not_listed"} for state in intake.STATES},
              "granular": {}, "products": {"CA-product": facts}}
    before = copy.deepcopy(inputs)
    outputs = intake.project(inputs, baseline)
    snapshot = json.loads(gzip.decompress(outputs["snapshot.json.gz"]))
    observations = snapshot["participation_observations"]
    assert len(observations) == 52
    assert observations[-1]["observation"] == native["data"]
    assert all(row["channel"] != "CA-product" for row in observations)
    query = outputs["declared-numerical-queries.json.gz"]
    assert json.loads(gzip.decompress(query)) == inputs["products"]
    reference = snapshot["declared_numerical_products_query"]
    assert reference == {"file": "declared-numerical-queries.json.gz", **pin(query)}
    indexed = snapshot["declared_numerical_products"]["CA-product"]
    assert indexed["complete_factual_query"] == {**reference, "key": "CA-product"}
    assert indexed["factual_data_available"] is True and "data" not in indexed
    assert inputs == before


def test_invalid_stop_seed_is_fail_closed_before_transport(tmp_path):
    with pytest.raises(ValueError, match="ledger"):
        intake.Collector(tmp_path, {}, {"urls": None, "prefixes": [], "hosts": []}, NOW)


def test_partial_clone_publisher_does_not_fetch_unchanged_blobs(tmp_path):
    remote = tmp_path / "remote"
    local = tmp_path / "publisher"
    subprocess.run(["git", "init", str(remote)], check=True, capture_output=True)
    original = GitPublisher(remote, ref="results-data")
    original.git("config", "uploadpack.allowFilter", "true")
    parent = original.commit(original.tree(None, {"archive.txt": b"unchanged"}), None, "Original")
    original.git("update-ref", original.ref_path, parent)
    old_blob = original.git("rev-parse", parent + ":archive.txt")
    subprocess.run(["git", "clone", "--no-checkout", "--filter=blob:none", remote.as_uri(), str(local)],
                   check=True, capture_output=True)
    publisher = GitPublisher(local, ref="results-data")
    assert "?" + old_blob in publisher.git("rev-list", "--objects", "--missing=print", parent)
    staged = publisher.commit(publisher.tree(parent, {"latest.json": b"new"}), parent, "Successor")
    assert "?" + old_blob in publisher.git("rev-list", "--objects", "--missing=print", staged)
    publisher.promote(staged, parent)
    assert original.git("rev-parse", staged + ":archive.txt") == old_blob
    assert original.git("show", staged + ":latest.json") == "new"


@pytest.mark.parametrize("interrupt_staging", [False, True, "successor"])
def test_real_git_publication_keeps_main_and_persists_last_good_results(
        tmp_path, monkeypatch, interrupt_staging):
    registry = fixture(tmp_path)
    monkeypatch.setattr(intake.Collector, "acquire", unavailable)
    work = tmp_path / "run"
    report = intake.collect(registry, work, now=NOW)
    collected = intake.read(work / "state.json")
    full_entry = {
        "status": "reported",
        "source": {"url": "https://official.example/native"},
        "data": {"updates": [{"id": "one", "value": 0}],
                 "complete_native_query": [0, None, 7]},
    }
    collected.setdefault("feeds", {})["LA-native"] = copy.deepcopy(full_entry)
    collected.setdefault("granular", {})["LA-native"] = copy.deepcopy(full_entry)
    collected = intake.compact_collector_state(collected)
    intake.write(work / "state.json", collected)
    repo = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    interrupted_once = False

    def verify(self, commit, files):
        nonlocal interrupted_once
        if interrupt_staging and not interrupted_once and any(
                name.startswith("snapshots/" + report["version"]) for name in files):
            interrupted_once = True
            raise OSError("Temporary verification outage")
        for name, expected in files.items():
            assert pin(subprocess.check_output(
                ["git", "-C", str(self.repository), "show", commit + ":" + name])) == expected
    monkeypatch.setattr(GitPublisher, "verify_files", verify)
    intake.write(work / "publication-parent.json", {"parent": None})
    git = GitPublisher(repo, ref="results-data")
    previous_head = None
    before_latest = before_state = ""
    if interrupt_staging == "successor":
        prior = tmp_path / "prior"
        shutil.copytree(work, prior)
        intake.write(prior / "report.json", {**report, "version": "a" * 64})
        previous_head = intake.publish(repo, "results-data", "fixture/results", prior)["data_commit"]
        before_latest = git.git("show", previous_head + ":latest.json")
        before_state = git.git("show", previous_head + ":state.json")
        intake.write(work / "publication-parent.json", {"parent": previous_head})
        collected["source_stops"]["urls"].append("https://example.test/newly-stopped")
        intake.write(work / "state.json", collected)
        intake.write(work / "source-stops.json", collected["source_stops"])
    if interrupt_staging:
        with pytest.raises(OSError, match="Temporary verification outage"):
            intake.publish(repo, "results-data", "fixture/results", work)
        stage = git.remote_head()
        assert git.git("show", stage + ":latest.json", check=False) == before_latest
        assert git.git("show", stage + ":state.json", check=False) == before_state
        if previous_head is not None:
            assert "https://example.test/newly-stopped" in json.loads(
                git.git("show", stage + ":source-stops.json"))["urls"]
        with pytest.raises(ValueError, match="staged collection must be activated"):
            intake.publisher_state(repo, "results-data", "fixture/results", tmp_path / "next")
        intake_checkout = tmp_path / "next-runner"
        subprocess.run(["git", "init", "-b", "main", str(intake_checkout)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(intake_checkout), "remote", "add", "origin", str(remote)], check=True)
        monkeypatch.setattr(intake.Collector, "acquire", lambda *args: pytest.fail("Recollected after staging"))
        result = intake.resume_publication(intake_checkout, "results-data", "fixture/results")
        assert result["results_commit"] == stage
        assert intake.resume_publication(intake_checkout, "results-data", "fixture/results")["status"] == (
            "no_pending_publication")
        git.fetch_parent(result["data_commit"])
    else:
        result = intake.publish(repo, "results-data", "fixture/results", work)
    assert result["status"] == "published"
    assert result["version"] == report["version"]
    published = json.loads(subprocess.check_output(
        ["git", "-C", str(repo), "show", result["data_commit"] + ":state.json"]))
    assert published["contract"] == intake.STATE_CONTRACT
    assert intake.unpack_state(published) == intake.read(work / "state.json")
    _, restored = intake.publisher_state(repo, "results-data", "fixture/results", tmp_path / "next")
    assert restored == intake.read(work / "state.json")
    hydrated = intake.hydrate_collector_state(restored)
    assert hydrated["feeds"]["LA-native"]["data"] == full_entry["data"]
    assert subprocess.check_output(["git", "-C", str(repo), "symbolic-ref", "HEAD"]).strip() == b"refs/heads/main"
    intake.write(work / "publication-parent.json", {"parent": result["data_commit"]})
    assert intake.publish(repo, "results-data", "fixture/results", work)["status"] == "unchanged"
    failed = tmp_path / "failed"
    intake.write(failed / "publication-parent.json", {"parent": result["data_commit"]})
    intake.write(failed / "source-stops.json",
                 {"urls": ["https://example.test/stopped"], "prefixes": [], "hosts": []})
    with pytest.raises(ValueError, match="durable stops preserved"):
        intake.publish(repo, "results-data", "fixture/results", failed)
    head = GitPublisher(repo, ref="results-data").remote_head()
    assert json.loads(subprocess.check_output(["git", "-C", str(repo), "show", head + ":latest.json"]))["version"] == report["version"]
    assert "https://example.test/stopped" in json.loads(
        subprocess.check_output(["git", "-C", str(repo), "show", head + ":state.json"]))["source_stops"]["urls"]
    interrupted = intake.unpack_state(json.loads(subprocess.check_output(
        ["git", "-C", str(repo), "show", head + ":state.json"])))
    assert interrupted["feeds"] == restored["feeds"]
    assert subprocess.check_output(
        ["git", "-C", str(repo), "ls-remote", "--heads", "origin"]) == b""
    assert subprocess.check_output(
        ["git", "-C", str(repo), "ls-remote", "--tags", "origin", "refs/tags/results-data"]
    ).decode().split()[0] == head


def test_data_tag_updates_preserve_main_and_reject_stale_or_backward_publication(tmp_path):
    repo, remote = tmp_path / "repository", tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    code = GitPublisher(repo, ref="main")
    main = code.commit(code.tree(None, {"README": b"Retained website source\n"}), None, "Source")
    code.promote(main, None)
    data = GitPublisher(repo)
    first = data.commit(data.tree(None, {"catalog.json": b'{"value":0}\n'}), None, "First data")
    data.promote(first, None)
    data.fetch_parent(first)
    second = data.commit(
        data.tree(first, {"catalog.json": b'{"value":1}\n'}), first, "Next data")
    data.promote(second, first)
    assert data.remote_head() == second
    with pytest.raises(IntakeError, match="advanced"):
        data.promote(first, first)
    with pytest.raises(IntakeError, match="discarding history"):
        data.promote(first, second)
    assert data.remote_head() == second
    assert code.remote_head() == main
    assert subprocess.check_output(
        ["git", "-C", str(repo), "ls-remote", "--heads", "origin"]
    ).decode().splitlines() == [main + "\trefs/heads/main"]



def test_granular_alias_compaction_is_idempotent_strict_and_publishable():
    full_entry = {
        "status": "reported",
        "source": {"url": "https://official.example/native"},
        "data": {"updates": [{"id": "one", "value": 0}],
                 "complete_native_query": [0, None, 7]},
    }
    state = {
        "source_stops": copy.deepcopy(EMPTY_STOPS),
        "feeds": {"LA-native": copy.deepcopy(full_entry)},
        "granular": {"LA-native": copy.deepcopy(full_entry)},
        "house": {}, "districts": {}, "directories": {}, "products": {},
    }
    compact = intake.compact_collector_state(state)
    assert intake.compact_collector_state(compact) == compact
    assert intake.pack_state(state) == intake.pack_state(compact)
    unpacked = intake.unpack_state(json.loads(intake.pack_state(compact)))
    assert unpacked == compact
    assert intake.hydrate_collector_state(unpacked) == state
    legacy = {"source_stops": copy.deepcopy(EMPTY_STOPS),
              "feeds": {"old": {"data": 0}}}
    assert intake.hydrate_collector_state(
        intake.compact_collector_state(legacy)) == legacy
    for mutation in ("contract", "key", "pin", "missing_pin", "extra"):
        broken = copy.deepcopy(compact)
        alias = broken["feeds"]["LA-native"]["data"]
        if mutation == "contract":
            alias["contract"] = "changed"
        elif mutation == "key":
            alias["granular_key"] = "different"
        elif mutation == "pin":
            alias["data_pin"]["sha256"] = "0" * 64
        elif mutation == "missing_pin":
            alias.pop("data_pin")
        else:
            alias["extra"] = True
        with pytest.raises(ValueError):
            intake.compact_collector_state(broken)
        with pytest.raises(ValueError):
            intake.hydrate_collector_state(broken)
        with pytest.raises(ValueError):
            intake.pack_state(broken)
    missing = copy.deepcopy(compact)
    del missing["granular"]["LA-native"]
    with pytest.raises(ValueError, match="target is missing"):
        intake.pack_state(missing)
    null_full = copy.deepcopy(compact)
    null_full["granular"]["LA-native"]["data"] = None
    with pytest.raises(ValueError, match="no full data"):
        intake.pack_state(null_full)
    alias_full = copy.deepcopy(compact)
    alias_full["granular"]["LA-native"]["data"] = copy.deepcopy(
        alias_full["feeds"]["LA-native"]["data"])
    with pytest.raises(ValueError, match="full data is an alias"):
        intake.pack_state(alias_full)


def test_complete_state_storage_preserves_legacy_unknown_zero_and_full_native_facts(monkeypatch):
    state = {"source_stops": EMPTY_STOPS,
             "feeds": {"zero": {"data": {"count": 0, "native": ["literal", None, 17]}},
                       "unknown": {"data": {"count": None, "clock": None}}},
             "facts": "complete numerical cells " * 1000}
    envelope = json.loads(intake.pack_state(state))
    assert len(intake.pack_state(state)) < len(encoded(state))
    assert intake.unpack_state(envelope) == state
    assert intake.unpack_state(copy.deepcopy(state)) == state
    mutations = [
        {**envelope, "contract": "unrecognized"},
        {**envelope, "decoded": {**envelope["decoded"], "sha256": "0" * 64}},
        {**envelope, "decoded": {**envelope["decoded"], "bytes": 1}},
        {**envelope, "gzip_base64": "!invalid"},
        {**envelope, "source_stops": {**EMPTY_STOPS, "hosts": ["stopped.test"]}},
    ]
    for changed in mutations:
        with pytest.raises((ValueError, EOFError, OSError)):
            intake.unpack_state(changed)
    monkeypatch.setattr(intake, "MAX_STATE_BYTES", 10)
    with pytest.raises(ValueError, match="size"):
        intake.unpack_state(envelope)


def test_completed_collection_restores_without_transport_and_rejects_lost_stops(tmp_path, monkeypatch):
    registry = fixture(tmp_path)
    monkeypatch.setattr(intake.Collector, "acquire", unavailable)
    original = tmp_path / "original"
    report = intake.collect(registry, original, now=NOW)
    def forbidden(*args, **kwargs):
        raise AssertionError("Recovery must never acquire a source")
    monkeypatch.setattr(intake.Collector, "acquire", forbidden)
    packet, report_path = original / "complete-results.zip", original / "report.json"
    with pytest.raises(ValueError, match="refusing recovery rollback"):
        intake.restore(packet, report_path, tmp_path / "older",
                       latest={"checked_at": NOW.replace(hour=1).isoformat()})
    assert not (tmp_path / "older").exists()
    lost_stop = {"source_stops": {**EMPTY_STOPS, "hosts": ["new-stop.test"]}}
    with pytest.raises(ValueError, match="drop current durable"):
        intake.restore(packet, report_path, tmp_path / "rejected", lost_stop)
    assert not (tmp_path / "rejected").exists()
    destination = tmp_path / "restored"
    result = intake.restore(packet, report_path, destination)
    assert result["network_requests"] == 0 and result["original_packet_and_queries_unchanged"]
    assert result["version"] == report["version"]
    for name in (*report["files"], "state.json", "report.json", "source-stops.json"):
        assert (destination / name).read_bytes() == (original / name).read_bytes()
    with pytest.raises(ValueError, match="fresh publication"):
        intake.restore(packet, report_path, destination)
    changed = {**report, "files": {**report["files"],
               "complete-results.zip": {**report["files"]["complete-results.zip"], "sha256": "0" * 64}}}
    intake.write(tmp_path / "changed-report.json", changed)
    with pytest.raises(ValueError, match="Changed or unvalidated"):
        intake.restore(packet, tmp_path / "changed-report.json", tmp_path / "changed")
    assert not (tmp_path / "changed").exists()
