from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from scripts import results_intake as intake
from scripts.participation_intake.contract import encoded, pin
from scripts.participation_intake.engine import Store
from scripts import results_native_north_dakota as nd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nd_native_fixture_support as fixture_support


FIXTURES = Path(__file__).with_name("fixtures") / "nd-native-automatic"
NOW = datetime(2026, 11, 15, 9, 18, 25, tzinfo=timezone.utc)
EMPTY_STOPS = {"urls": [], "prefixes": [], "hosts": []}


def compressed(value):
    return intake.compressed(encoded(value))


def accepted_house_rows():
    rows = []
    states = [code for code in intake.STATES if code != "DC"]
    for index, state in enumerate(states):
        for number in range(1, (9 if index < 35 else 8) + 1):
            district = state.lower() + "-" + str(number).zfill(2)
            rows.append({
                "state_code": state, "district": district,
                "name": "Accepted fixture candidate", "party": "FIX", "votes": 0,
                "source_updated_at": "2026-11-05T01:30:08Z",
                "source_url": "https://example.invalid/accepted-house/" + district,
            })
    assert len(rows) == 435
    return rows


def registry(tmp_path):
    root = tmp_path / "source"
    accepted = root / "accepted"
    (accepted / "states").mkdir(parents=True)
    templates = fixture_support.load_gzip(
        FIXTURES / "accepted-templates.json.gz")["records"]
    counties = [
        row["id"] for row in templates if row["geography"]["level"] == "county"]
    units = [
        row["id"] for row in templates
        if row["geography"]["level"] == "reporting_unit"]
    files, states = {}, {}
    for state in intake.STATES:
        name = "states/" + state + ".json.gz"
        if state == "ND":
            shard = {
                "contract": "participation.count_snapshot.v1",
                "state_code": "ND", "year": 2026, "records": templates,
                "views": {
                    "official": {
                        "counties": counties, "precincts": units, "nongeographic": []}
                },
            }
        else:
            shard = {
                "contract": "participation.count_snapshot.v1",
                "state_code": state, "year": 2026,
                "records": [{"id": state, "count": {"value": None}}],
                "views": {},
            }
        body = compressed(shard)
        (accepted / name).write_bytes(body)
        files[name] = pin(body)
        states[state] = {"file": name, **pin(body)}
    index_body = encoded({
        "contract": "participation.count_index.v1", "year": 2026,
        "states": states, "coverage": {},
    })
    (accepted / "index.json").write_bytes(index_body)
    files["index.json"] = pin(index_body)
    accepted_queries = {}
    query_values = {
        "accepted-current-candidate-queries.json": accepted_house_rows(),
        "accepted-current-House-controls.json": {"fixture": "complete controls"},
        "accepted-house-state-status-flags.json": {"fixture": "complete flags"},
        "accepted-official-native-scope.json": {"fixture": "complete scope"},
    }
    for number, (name, value) in enumerate(query_values.items()):
        filename = f"accepted-{number}.json"
        body = encoded(value)
        (root / filename).write_bytes(body)
        accepted_queries[name] = {"file": filename, **pin(body)}
    config = {
        "contract": intake.CONTRACT, "election_date": "2026-11-03",
        "baseline": {"root": "accepted", "files": files},
        "jurisdictions": {
            code: {"url": None, "status": "not_listed_in_directory"}
            for code in intake.STATES
        },
        "source_stops": EMPTY_STOPS,
        "accepted_queries": accepted_queries,
    }
    path = root / "registry.json"
    path.write_bytes(encoded(config))
    return path


def seed_nd(work):
    facts = fixture_support.load_gzip(FIXTURES / "nd-complete-facts.json.gz")
    documents = fixture_support.source_documents(facts)
    store = Store(work / "cache")
    for url, body in documents.items():
        store.object(body)
        store.db.execute(
            "INSERT OR REPLACE INTO inputs VALUES(?,?,?,?,NULL)",
            (url, intake.digest(body), None, None),
        )
    store.db.commit()
    store.db.close()


def clean_environment():
    return {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}


def test_collect_emits_self_contained_nd_14_output_packet_and_literal_replay(tmp_path):
    registry_path = registry(tmp_path)
    work = tmp_path / "run"
    seed_nd(work)
    report = intake.collect(registry_path, work, now=NOW, offline=True)
    assert report["passed"] is True
    packet = tmp_path / "packet"
    with zipfile.ZipFile(work / "complete-results.zip") as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        required = {
            "code/scripts/results_native_north_dakota.py",
            "code/tests/test_results_native_north_dakota.py",
            "code/tests/test_results_native_north_dakota_repair.py",
            "code/tests/test_results_intake_north_dakota_package.py",
            "code/tests/nd_native_fixture_support.py",
            "code/tests/fixtures/nd-native-automatic/accepted-templates.json.gz",
            "code/tests/fixtures/nd-native-automatic/nd-complete-facts.json.gz",
        }
        assert required <= names
        archive.extractall(packet)
    granular = json.loads(gzip.decompress(
        (packet / "queries/granular-source-queries.json.gz").read_bytes()))
    nd_entry = next(
        entry for entry in granular.values()
        if entry.get("adapter") == nd.ADAPTER)
    assert nd_entry["status"] == "reported"
    assert nd_entry["reviewed_record_count"] == 411
    assert len(nd_entry["data"]["updates"]) == 411
    assert nd_entry["data"]["complete_native_query"][0]["state_ballots"] == 239057
    replay = subprocess.run(
        [sys.executable, "code/reproduce.py", "replay", "--package", ".",
         "--output", "literal-reproduced"],
        cwd=packet, env=clean_environment(), check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    assert json.loads(replay.stdout) == {
        "complete_outputs": 14, "network_requests": 0, "passed": True}
    subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path[:0]=['code','code/tests']; "
         "from scripts import results_native_north_dakota; "
         "import nd_native_fixture_support; "
         "assert results_native_north_dakota.ADAPTER"],
        cwd=packet, env=clean_environment(), check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q",
         "tests/test_results_native_north_dakota.py",
         "tests/test_results_native_north_dakota_repair.py"],
        cwd=packet / "code", env=clean_environment(), check=True,
    )
