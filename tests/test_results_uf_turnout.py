import copy
import csv
from datetime import datetime, timezone
import gzip
import io
import json
from urllib.error import HTTPError

import pytest

from scripts import results_intake, results_uf_turnout as uf
from scripts.participation_intake.contract import encoded, pin


def original(count=500, status="", version="0.3"):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=sorted(uf.FIELDS), lineterminator="\n")
    writer.writeheader()
    for code, name in sorted(uf.NAMES.items()):
        row = dict.fromkeys(uf.FIELDS, "")
        row.update(STATE=name, STATE_ABV=code, SOURCE="https://official.test/2026/turnout",
                   STATUS=status, TOTAL_BALLOTS_COUNTED=str(count), VAP="2000", VEP="1000",
                   VEP_TURNOUT_RATE=f"{count / 10:.2f}%", VAP_TURNOUT_RATE=f"{count / 20:.2f}%")
        writer.writerow(row)
    documentation = (
        "DOCUMENTATION FOR 2026 GENERAL ELECTION TURNOUT RATES\nVersion: " + version
        + "\nDate: 11/2/2026\nCreative Commons 4.0 Attribution License\n"
        + "\n\n".join(key + "\n=======\n"
                      + ("Where li" if key == "TOTAL_BALLOTS_COUNTED" else "Native definition.")
                      for key in sorted(uf.FIELDS))
        + "\nIf blank, STATUS indicates TOTAL_BALLOTS_COUNTED is estimated from available source data.\n"
        + "Pre-election forecast v0.2\n")
    return stream.getvalue().encode(), documentation.encode()


def source_bodies(count=500, status="", version="0.3"):
    dataset = "https://election.lab.ufl.edu/dataset/2026-general-election-turnout-rates-v" \
        + version.replace(".", "-") + "/"
    csv_url = "https://election.lab.ufl.edu/data-downloads/turnoutdata/Turnout_2026G_v" + version + ".csv"
    doc_url = csv_url[:-4] + "_doc.txt"
    raw, doc = original(count, status, version)
    return {
        uf.LANDING: ('<a href="' + dataset + '">2026</a>').encode(),
        dataset: ('<a href="' + csv_url + '">CSV</a><a href="' + doc_url + '">docs</a>').encode(),
        csv_url: raw, doc_url: doc,
    }


def capture(tmp_path, bodies, prior=None, modified="Tue, 17 Nov 2026 10:00:00 GMT", stopped=None):
    collector = results_intake.Collector(
        tmp_path, {uf.IDENTITY: prior} if prior else {},
        stopped or {"urls": [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 17, 12, tzinfo=timezone.utc))
    requested = []

    def acquire(url):
        collector.guard(url)
        requested.append(url)
        if url not in bodies:
            raise ValueError("Unavailable declared original")
        body = bodies[url]
        return body, {"origin": "supplied_original", **pin(body)}

    collector.acquire = acquire
    collector.public_edition = lambda url: {
        "body_sha256": pin(bodies[url])["sha256"], "http_etag": '"edition"',
        "http_last_modified": modified,
        "qualification": "HTTP representation edition, not a native count-update clock"}
    return uf.collect(collector, uf.CONFIG), requested, collector


def test_native_status_not_source_link_controls_classification():
    for literal, expected in (
        ("", "estimate"), ("Official", "source_reported_not_independently_certified"),
        ("Final", "source_reported_not_independently_certified"),
        ("Offiical", "unrecognized_source_status"),
    ):
        rows = uf.parse(original(status=literal)[0])
        assert len(rows) == 52
        assert all(row["ballots_status"] == expected for row in rows)
        assert all(row["source_status_literal"] == literal for row in rows)
        assert all(row["independently_certified"] is False
                   and row["local_allocation_qualified"] is False for row in rows)
        assert rows[0]["native"]["SOURCE"].startswith("https://official.test/")


def test_count_revisions_downward_and_true_zero_need_source_edition(tmp_path):
    first, _, _ = capture(tmp_path / "first", source_bodies())
    assert first["status"] == "reported"
    for count in (507, 493, 0):
        revised, _, _ = capture(tmp_path / str(count), source_bodies(count), first,
                                "Tue, 17 Nov 2026 11:00:00 GMT")
        assert revised["status"] == "reported"
        assert all(row["ballots"] == count for row in uf.view(revised)["rows"])
        held, _, _ = capture(tmp_path / ("held-" + str(count)), source_bodies(count), first)
        assert held["status"] == "retained_after_failure"
        assert held["data"] == first["data"] and held["source"] == first["source"]
        assert held["first_observed_at"] == first["first_observed_at"]


def test_unchanged_response_is_exact_and_new_advertised_version_is_discovered(tmp_path):
    first, _, _ = capture(tmp_path / "first", source_bodies())
    same, requested, _ = capture(tmp_path / "same", source_bodies(), first)
    assert same == first and len(requested) == 4
    bodies = source_bodies(499, version="0.4")
    bodies[uf.LANDING] += source_bodies()[uf.LANDING]
    new, requested, _ = capture(tmp_path / "new", bodies, first, modified=None)
    assert new["status"] == "reported" and new["data"]["version"] == "0.4"
    assert all("v0.3" not in url and "v0-3" not in url for url in requested)
    older, _, _ = capture(tmp_path / "older", source_bodies(), new)
    assert older["status"] == "retained_after_failure" and older["data"] == new["data"]


def test_new_edition_cannot_silently_drop_a_state_map_value(tmp_path):
    first, _, _ = capture(tmp_path / "first", source_bodies())
    successor = source_bodies(493, version="0.4")
    url = next(url for url in successor if url.endswith(".csv"))
    rows = list(csv.DictReader(io.StringIO(successor[url].decode())))
    row = next(row for row in rows if row["STATE_ABV"] == "ME")
    row["VEP_TURNOUT_RATE"] = ""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=sorted(uf.FIELDS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    successor[url] = output.getvalue().encode()
    held, _, _ = capture(tmp_path / "incomplete", successor, first)
    assert held["status"] == "retained_after_failure" and "ME:vep_rate" in held["error_detail"]
    assert held["data"] == first["data"] and len(uf.view(held)["rows"]) == 52
    recovered, _, _ = capture(tmp_path / "recovered", source_bodies(493, version="0.4"), held)
    assert recovered["status"] == "reported" and recovered["data"]["version"] == "0.4"


def test_outage_and_stopped_child_preserve_last_good_without_transport(tmp_path):
    bodies = source_bodies()
    first, _, _ = capture(tmp_path / "first", bodies)
    csv_url = first["data"]["declarations"]["csv"]
    missing = {key: value for key, value in bodies.items() if key != csv_url}
    held, _, _ = capture(tmp_path / "outage", missing, first)
    assert held["status"] == "retained_after_failure" and held["data"] == first["data"]
    held, requested, collector = capture(tmp_path / "stopped", bodies, first,
        stopped={"urls": [csv_url], "prefixes": [], "hosts": []})
    assert csv_url not in requested and held["status"] == "retained_after_failure"
    assert held["data"] == first["data"] and collector.stopped["urls"] == [csv_url]


def test_invalid_inventory_counts_rates_and_wrong_election_refuse():
    raw, _ = original()
    for invalid in (
        raw.replace(b"Alabama", b"Another state"),
        raw.replace(b",AL,", b",XX,"),
        raw.replace(b"500,", b"-1,", 1),
        raw.replace(b"50.00%", b"49.00%", 1),
        b"\n".join(raw.splitlines()[:-1]) + b"\n",
        raw.replace(b"STATUS", b"NEW_STATUS"),
    ):
        with pytest.raises(ValueError):
            uf.parse(invalid)
    with pytest.raises(ValueError, match="2026"):
        uf.discover(b'<a href="/dataset/2024-general-election-turnout-rates-v0-4/">2024</a>')
    with pytest.raises(ValueError, match="origin"):
        uf.discover(b'<a href="https://wrong.test/dataset/2026-general-election-turnout-rates-v0-4/">bad</a>')


def test_documentation_anomalies_are_retained_not_native_clocks():
    _, raw = original()
    declaration = uf.documentation(raw, "0.3")
    assert set(declaration["anomalies"]) == {
        "documentation_date_predates_election_not_a_count_clock",
        "documentation_retains_forecast_or_prior_version_language",
        "total_ballots_definition_truncated"}
    for body, version in ((raw.replace(b"2026 GENERAL", b"2024 GENERAL"), "0.3"),
                          (raw, "0.4"), (raw.replace(b"If blank, STATUS", b"Removed rule"), "0.3")):
        with pytest.raises(ValueError):
            uf.documentation(body, version)


def test_current_snapshot_exports_and_noop_preserve_other_counts(tmp_path):
    automatic_runtime = pytest.importorskip(
        "scripts.automatic_runtime", reason="The source-only packet excludes the separate runtime engine")
    entry, _, _ = capture(tmp_path, source_bodies())
    current = {"contract": "participation.current_snapshot.v1",
               "snapshot": {"reporting": [], "early_voting": [{"ballots": 9}]},
               "reviewed_states": [{"untouched": True}]}
    body = gzip.compress(encoded(current), mtime=0)
    files = {"current.json.gz": body, "states/AL.json.gz": b"unchanged local counts",
             "index.json": encoded({"current_snapshot": {"file": "current.json.gz", **pin(body)}})}
    original_files = dict(files)
    snapshot = {"jurisdictions": [], "source_status": [], "uf_turnout": entry}
    result = automatic_runtime.refresh_current(files, snapshot)
    visible = json.loads(gzip.decompress(result["current.json.gz"]))
    assert visible["uf_turnout"] == uf.view(entry)
    assert visible["snapshot"] == current["snapshot"]
    assert visible["reviewed_states"] == current["reviewed_states"]
    assert files == original_files
    assert result["states/AL.json.gz"] == files["states/AL.json.gz"]
    assert automatic_runtime.refresh_current(result, snapshot) == result
    exports = uf.exports(entry)
    rows = list(csv.DictReader(io.StringIO(exports["uf-turnout.csv"].decode())))
    assert len(rows) == 52 and all(row["ballots"] == "500" for row in rows)
    assert json.loads(exports["uf-turnout-queries.json"]) == entry
    bad = copy.deepcopy(entry)
    bad["data"]["rows"][0]["ballots"] = 999
    with pytest.raises(ValueError, match="query changed"):
        automatic_runtime.refresh_current(files, dict(snapshot, uf_turnout=bad))


def test_original_bom_is_preserved_in_query_pins(tmp_path):
    bodies = source_bodies()
    csv_url = next(url for url in bodies if url.endswith(".csv"))
    bodies[csv_url] = b"\xef\xbb\xbf" + bodies[csv_url]
    entry, _, _ = capture(tmp_path, bodies)
    assert entry["status"] == "reported"
    assert uf.view(entry)["rows"][0]["ballots"] == 500
    assert entry["data"]["originals"]["csv"].encode() == bodies[csv_url]


def test_offline_query_rejects_retargeted_discovery_or_invalid_edition(tmp_path):
    entry, _, _ = capture(tmp_path, source_bodies())
    for key in ("landing", "dataset", "csv", "documentation"):
        changed = copy.deepcopy(entry)
        changed["data"]["declarations"][key] += "?unreviewed=true"
        changed["data"]["sources"][key]["url"] += "?unreviewed=true"
        with pytest.raises(ValueError, match="UF"):
            uf.validate(changed)
    changed = copy.deepcopy(entry)
    changed["data"]["csv_edition"]["http_last_modified"] = "not a date"
    with pytest.raises(ValueError, match="UF"):
        uf.validate(changed)


def test_real_collector_cache_conditional_revision_outage_and_recovery(tmp_path, monkeypatch):
    bodies, calls = source_bodies(), []
    modified = "Tue, 17 Nov 2026 10:00:00 GMT"
    unavailable = set()

    class Response(io.BytesIO):
        status = 200

        def __init__(self, body):
            super().__init__(body)
            self.headers = {"ETag": pin(body)["sha256"], "Last-Modified": modified}

    class Opener:
        def open(self, request, timeout):
            url = request.full_url
            calls.append(url)
            if url in unavailable:
                raise HTTPError(url, 503, "Unavailable", {}, io.BytesIO())
            body = bodies[url]
            headers = dict((key.lower(), value) for key, value in request.header_items())
            if headers.get("if-none-match") == pin(body)["sha256"]:
                raise HTTPError(url, 304, "Unchanged", {}, io.BytesIO())
            return Response(body)

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())

    def run(prior=None):
        collector = results_intake.Collector(
            tmp_path, {uf.IDENTITY: prior} if prior else {},
            {"urls": [], "prefixes": [], "hosts": []},
            datetime(2026, 11, 17, 12, tzinfo=timezone.utc))
        return uf.collect(collector, uf.CONFIG), collector

    first, collector = run()
    assert first["status"] == "reported" and len(calls) == 4
    same, collector = run(first)
    assert same == first and len(calls) == 8
    assert collector.attempts[0]["status"] == "unchanged_conditional_response"
    bodies = source_bodies(493)
    modified = "Tue, 17 Nov 2026 11:00:00 GMT"
    revised, _ = run(first)
    assert revised["status"] == "reported" and revised["data"]["rows"][0]["ballots"] == 493
    csv_url = revised["data"]["declarations"]["csv"]
    unavailable.add(csv_url)
    held, _ = run(revised)
    assert held["status"] == "retained_after_failure" and held["data"] == revised["data"]
    unavailable.clear()
    recovered, _ = run(held)
    assert recovered["status"] == "reported" and recovered["data"] == revised["data"]
    assert recovered["first_observed_at"] == revised["first_observed_at"]


def test_real_denial_stops_child_in_a_new_collector_without_a_second_request(tmp_path, monkeypatch):
    bodies, calls = source_bodies(), []
    csv_url = next(url for url in bodies if url.endswith(".csv"))
    first, _, _ = capture(tmp_path / "accepted", bodies)

    class Response(io.BytesIO):
        status = 200
        headers = {}

    class Opener:
        def open(self, request, timeout):
            url = request.full_url
            calls.append(url)
            if url == csv_url:
                raise HTTPError(url, 403, "Denied", {}, io.BytesIO())
            return Response(bodies[url])

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    collector = results_intake.Collector(
        tmp_path / "denied", {uf.IDENTITY: first}, {"urls": [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 17, tzinfo=timezone.utc))
    held = uf.collect(collector, uf.CONFIG)
    assert held["status"] == "retained_after_failure" and held["data"] == first["data"]
    assert csv_url in collector.stopped["urls"] and calls.count(csv_url) == 1
    fresh = results_intake.Collector(
        tmp_path / "new-cache", {uf.IDENTITY: held}, collector.stopped,
        datetime(2026, 11, 17, tzinfo=timezone.utc))
    retained = uf.collect(fresh, uf.CONFIG)
    assert retained["data"] == first["data"] and calls.count(csv_url) == 1


def test_unknown_counts_stay_unknown_and_known_zero_is_not_missing():
    raw, _ = original(count=0)
    rows = uf.parse(raw)
    assert all(row["ballots"] == 0 and row["vep_rate"] == 0 for row in rows)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=sorted(uf.FIELDS), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        native = dict(row["native"])
        if native["STATE_ABV"] == "AL":
            native.update(TOTAL_BALLOTS_COUNTED="", VEP_TURNOUT_RATE="", VAP_TURNOUT_RATE="")
        writer.writerow(native)
    parsed = {row["state_code"]: row for row in uf.parse(stream.getvalue().encode())}
    assert parsed["AL"]["ballots"] is None and parsed["AL"]["vep_rate"] is None
    assert parsed["AK"]["ballots"] == 0 and parsed["AK"]["vep_rate"] == 0
