import copy
import gzip
import io
import json
import zipfile

import pytest

from scripts import automatic_runtime as runtime
from scripts.participation_intake.contract import encoded, pin


def test_current_only_updates_matching_fresh_native_measure_and_preserves_every_other_frame():
    rows = [
        {"state_code": "OR", "ballots": 10, "denominator": 20,
         "denominator_basis": "active_registered_voters",
         "source_url": "https://official.test/native", "source_update_label": "old",
         "source_date": "2026-11-04", "source_retrieved_at": "old-retrieval",
         "source_sha256": "a" * 64},
        {"state_code": "NC", "ballots": 7, "source_update_label": "retained"},
    ]
    current = {"snapshot": {"reporting": rows, "demographics": [{"count": 4}], "early_voting": [5]},
               "reviewed_states": [{"untouched": True}]}
    body = gzip.compress(encoded(current), mtime=0)
    files = {"current.json.gz": body, "index.json": encoded({
        "current_snapshot": {"file": "current.json.gz", **pin(body)}})}
    original = copy.deepcopy(files)
    source = {"ballots": 11, "denominator": 20, "denominator_basis": "active_registered_voters",
              "source_update_label": "new native clock"}
    snapshot = {"jurisdictions": [
        {"state_code": "OR", "statewide_administrative_status": "reported",
         "statewide_administrative_observation": source},
        {"state_code": "NC", "statewide_administrative_status": "retained_after_failure",
         "statewide_administrative_observation": {"ballots": 999}}],
        "source_status": [{"source": "OR-official", "source_url": "https://official.test/native"}],
        "participation_observations": [{
            "channel": "OR-official", "status": "reported", "observation": source,
            "source": {"url": "https://official.test/native", "sha256": "b" * 64}}]}
    result = runtime.refresh_current(files, snapshot)
    updated = json.loads(gzip.decompress(result["current.json.gz"]))
    assert files == original
    assert updated["snapshot"]["reporting"][0]["ballots"] == 11
    assert updated["snapshot"]["reporting"][0]["source_update_label"] == "new native clock"
    assert updated["snapshot"]["reporting"][0]["source_sha256"] == "b" * 64
    assert updated["snapshot"]["reporting"][0]["source_retrieved_at"] is None
    assert updated["snapshot"]["reporting"][0]["source_date"] is None
    assert updated["snapshot"]["reporting"][0]["accepted_source_provenance"][
        "source_retrieved_at"] == "old-retrieval"
    assert updated["snapshot"]["reporting"][1] == rows[1]
    assert updated["snapshot"]["early_voting"] == current["snapshot"]["early_voting"]
    assert updated["snapshot"]["demographics"] == current["snapshot"]["demographics"]
    assert updated["reviewed_states"] == current["reviewed_states"]
    assert runtime.refresh_current(result, snapshot) == result
    snapshot["jurisdictions"][0]["statewide_administrative_observation"]["denominator_basis"] = "different_stock"
    assert runtime.refresh_current(files, snapshot) == files


def test_full_archive_is_deterministic_and_never_just_a_pointer():
    members = {"inputs/native-query.csv": b"county,count\nA,0\n",
               "queries/result.json": b'{"value":0}\n', "code/reproduce.py": b"print(0)\n"}
    body = runtime.archive_bytes(members)
    assert body == runtime.archive_bytes(dict(reversed(list(members.items()))))
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("checksums.json"))
        assert manifest == {name: pin(value) for name, value in members.items()}
        assert all(archive.read(name) == value for name, value in members.items())
    with pytest.raises(ValueError, match="Unsafe"):
        runtime.archive_bytes({"../outside": b"not allowed"})


def test_successor_descriptor_does_not_inherit_the_previous_publication_origin():
    before = {"contract": "participation.dataset.v1", "record_contract": "count-contract",
              "id": "test", "version": "old", "base_url": "https://old.test/",
              "staged_commit": "old", "status": "loaded"}
    descriptor = runtime.descriptor(before, {"index.json": b"{}\n"})
    assert all(key not in descriptor for key in ("base_url", "staged_commit", "status"))
    assert descriptor["version"] != "old"
    assert before["staged_commit"] == "old"


def test_untrusted_or_changed_public_body_is_refused_before_any_source_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Untrusted transport was opened")
    monkeypatch.setattr(runtime.urllib.request, "urlopen", forbidden)
    for url in ("http://raw.githubusercontent.com/hanshanley/voter-participation/a",
                "https://official.test/data", "https://raw.githubusercontent.com/other/repo/a"):
        with pytest.raises(ValueError, match="two public"):
            runtime.fetch(url)
    with pytest.raises(ValueError, match="declaration"):
        runtime.fetch(runtime.RESULTS_POINTER, {"bytes": True, "sha256": "a" * 64})


def test_result_pointer_cannot_redirect_pinned_queries_to_another_commit(monkeypatch):
    pointer = {"contract": "participation.automatic_results_latest.v1", "version": "a" * 64,
               "results_commit": "b" * 40,
               "base_url": "https://raw.githubusercontent.com/hanshanley/voter-participation/main/"}
    monkeypatch.setattr(runtime, "fetch", lambda *args, **kwargs: encoded(pointer))
    with pytest.raises(ValueError, match="exact immutable"):
        runtime.results(runtime.RESULTS_POINTER)


def test_safe_seed_inventory_never_packages_unlisted_local_files(tmp_path):
    source = runtime.ROOT / "data/results-intake/model-seed"
    for name, body in runtime.seed_files(source).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    (tmp_path / "private-unlisted.json").write_text('{"do_not_publish":true}')
    members = runtime.seed_files(tmp_path)
    assert len(members) == 25
    assert "private-unlisted.json" not in members
    manifest = json.loads(members["manifest.json"])
    manifest["accepted_candidates"]["path"] = "../outside.json"
    (tmp_path / "manifest.json").write_bytes(encoded(manifest))
    with pytest.raises(ValueError, match="Unsafe"):
        runtime.seed_files(tmp_path)


def test_missing_or_unpinned_rolling_seed_never_falls_back_to_original(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("A previous publication must never reset to bootstrap")
    monkeypatch.setattr(runtime, "seed_files", forbidden)
    monkeypatch.setattr(runtime, "fetch", forbidden)
    for previous in (
        {}, {"contract": runtime.CONTRACT},
        {"contract": runtime.CONTRACT, "version": "a" * 64, "house_sources": {"next_seed": {
            "path": "rolling/next-seed.json.gz", "url": runtime.RESULTS_POINTER}}},
    ):
        with pytest.raises(ValueError):
            runtime.select_seed(previous, "not-used")


def test_verified_rolling_seed_is_the_exact_input_retained_for_replay(monkeypatch):
    from scripts import automatic_estimates
    body = gzip.compress(b'{"newest_accepted":true}\n', mtime=0)
    version = "a" * 64
    item = {"path": "rolling/next-seed.json.gz", **pin(body),
            "url": ("https://raw.githubusercontent.com/" + runtime.WEBSITE_REPOSITORY
                    + "/" + "b" * 40 + "/automatic/versions/" + version
                    + "/rolling/next-seed.json.gz")}
    previous = {"contract": runtime.CONTRACT, "version": version,
                "house_sources": {"next_seed": item}}
    monkeypatch.setattr(runtime, "fetch", lambda *args, **kwargs: body)
    marker = {"last_good_not_original": True}
    monkeypatch.setattr(automatic_estimates, "load_rolling_seed_bytes",
                        lambda value, declaration: marker if value == body and declaration == item else None)
    selected, members = runtime.select_seed(previous, "not-used")
    assert selected is marker
    assert members == {"rolling-seed.json.gz": body, "rolling-seed-descriptor.json": encoded(item)}
    monkeypatch.setattr(runtime, "fetch", lambda *args, **kwargs: body + b"changed")
    with pytest.raises(ValueError, match="Changed rolling"):
        runtime.select_seed(previous, "not-used")


def test_unchanged_dataset_keeps_its_values_but_shares_the_atomic_publication_origin():
    identities = ("participation-counts-2026", "participation-native-bindings-2026")
    catalog = {"datasets": {identity: {
        "id": identity, "version": "a" * 64, "files": {"index.json": pin(b"{}\n")},
        "base_url": "old-origin", "complete_download": {"old_complete": True},
    } for identity in identities}, "unrelated": {"preserved": True}}
    original = copy.deepcopy(catalog)
    changed = {**catalog["datasets"][identities[0]], "version": "c" * 64}
    result, checks = runtime.bind_datasets(catalog, {identities[0]: changed},
                                         "b" * 40, runtime.WEBSITE_REPOSITORY)
    assert catalog == original
    assert result["unrelated"] == original["unrelated"]
    for identity in identities:
        row = result["datasets"][identity]
        assert "/" + "b" * 40 + "/" in row["base_url"]
        assert row["staged_commit"] == "b" * 40
        assert row["complete_download"] == {"old_complete": True}
        assert "datasets/" + identity + "/" + row["version"] + "/index.json" in checks
    assert result["datasets"][identities[1]]["version"] == "a" * 64


def test_complete_packet_includes_accepted_numerical_engine_and_only_selected_seed_bytes():
    seed = {"rolling-seed.json.gz": b"full-public-aggregate-seed"}
    compiled = {"counts": {"index.json": b"count-query"}, "native": {"index.json": b"native-query"},
                "model_files": {"all-nine-results.json.gz": b"complete-model-queries"}}
    packet = runtime.scientific_package({}, b"full-source-packet", {}, {}, seed, compiled)
    with zipfile.ZipFile(io.BytesIO(packet)) as archive:
        runtime.packet_manifest(archive)
        assert archive.read("code/scripts/norc_house_model.py") == (
            runtime.ROOT / "scripts/norc_house_model.py").read_bytes()
        assert {name for name in archive.namelist() if name.startswith("inputs/model-seed/")} == {
            "inputs/model-seed/rolling-seed.json.gz"}
        assert archive.read("queries/model-queries/all-nine-results.json.gz") == b"complete-model-queries"


@pytest.fixture
def publication(monkeypatch, tmp_path):
    class Publisher:
        def __init__(self):
            self.head = "a" * 40
            self.objects = {self.head: {"catalog.json": encoded({"datasets": {
                name: {"id": name, "version": "b" * 64, "record_contract": name,
                       "files": {"index.json": pin(b"{}\n")}, "complete_download": {"old": True}}
                for name in ("participation-counts-2026", "participation-native-bindings-2026")
            }})}}
            self.objects[self.head].update({
                f"datasets/{name}/{'b' * 64}/index.json": b"{}\n"
                for name in ("participation-counts-2026", "participation-native-bindings-2026")
            })
            self.promotions = 0
            self.compilations = 0
            self.releases = 0
            self.interrupt = None

        def remote_head(self):
            return self.head

        def fetch_parent(self, parent):
            assert parent in self.objects

        def catalog(self, parent):
            return json.loads(self.objects[parent]["catalog.json"])

        def git(self, operation, target, check=False):
            assert operation == "show"
            commit, path = target.split(":", 1)
            return self.objects[commit].get(path, b"").decode()

        def tree(self, parent, bodies):
            return {**self.objects[parent], **bodies}

        def commit(self, tree, parent, message):
            identity = runtime.digest(encoded({
                "parent": parent, "files": {name: pin(body) for name, body in tree.items()}}))[:40]
            self.objects[identity] = tree
            return identity

        def promote(self, commit, expected):
            if self.head != expected:
                raise ValueError("Concurrent publication")
            self.head = commit
            self.promotions += 1

        def verify_files(self, commit, files):
            for name, expected in files.items():
                assert pin(self.objects[commit][name]) == expected
            phase = "activation" if "automatic/latest.json" in files else "staging"
            if self.interrupt == phase:
                self.interrupt = None
                raise OSError("Interrupted " + phase + " verification")

    publisher = Publisher()
    monkeypatch.setattr(runtime, "GitPublisher", lambda *args, **kwargs: publisher)
    monkeypatch.setattr(runtime, "results", lambda _: (
        {"version": "f" * 64, "checked_at": "2026-11-14T16:00:00+00:00"},
        {}, {"complete-results.zip": b"full-source-packet"}))
    monkeypatch.setattr(runtime, "dataset_files", lambda _: {"index.json": b"{}\n"})
    monkeypatch.setattr(runtime, "seed_files", lambda _: {"manifest.json": b"safe"})
    monkeypatch.setattr(runtime, "select_seed", lambda *args: ({}, {}))

    def compile_snapshot(*args):
        publisher.compilations += 1
        return {"counts": {"index.json": b'{"changed":true}\n'},
                "native": {"index.json": b"{}\n"}, "estimates": {"house_sources": {}},
                "model_files": {"all-results.json.gz": b"complete-public-queries"},
                "local_changes": []}
    monkeypatch.setattr(runtime, "compile_runtime", compile_snapshot)
    proof = {"passed": True, "network_requests": 0, "external_operations_blocked": True,
             "complete_outputs": 3}

    def package(*args):
        return runtime.archive_bytes({"code/reproduce.py": (
            "import json\nprint(json.dumps(" + repr(proof) + "))\n").encode()})
    monkeypatch.setattr(runtime, "scientific_package", package)

    def release(repository, version, path, journal, checkpoint):
        if not journal.get("release_id"):
            publisher.releases += 1
            journal["release_id"] = publisher.releases
            checkpoint()
        return {"url": "https://github.com/" + repository + "/releases/download/unit/complete-analysis.zip",
                **pin(path.read_bytes()), "immutable": True, "verified_anonymously": True}
    monkeypatch.setattr(runtime, "complete_release", release)
    from scripts import automatic_estimates
    monkeypatch.setattr(automatic_estimates, "bind_publication",
                        lambda result, base, download: {"house_sources": {"base_url": base}})
    return publisher, tmp_path / "work", proof


@pytest.mark.parametrize("interrupt", [None, "staging", "activation"])
def test_publication_resume_and_unchanged_input_do_not_reset_or_duplicate_activation(publication, interrupt):
    publisher, work, _ = publication
    original_catalog = publisher.catalog(publisher.head)
    publisher.interrupt = interrupt
    if interrupt:
        with pytest.raises(OSError, match="Interrupted"):
            runtime.run("not-used", work)
        if interrupt == "staging":
            assert publisher.catalog(publisher.head) == original_catalog
            assert "automatic/latest.json" not in publisher.objects[publisher.head]
    result = runtime.run("not-used", work)
    assert result["status"] in ("published", "unchanged")
    current = json.loads(publisher.objects[publisher.head]["automatic/latest.json"])
    catalog = publisher.catalog(publisher.head)
    assert current["counts"] == catalog["datasets"]["participation-counts-2026"]
    assert current["native"] == catalog["datasets"]["participation-native-bindings-2026"]
    assert current["native"]["version"] == "b" * 64
    assert current["counts"]["staged_commit"] == current["native"]["staged_commit"]
    assert publisher.releases == 1 and publisher.promotions == 2
    compilations, head = publisher.compilations, publisher.head
    assert runtime.run("not-used", work)["status"] == "unchanged"
    assert publisher.compilations == compilations and publisher.head == head
    assert publisher.promotions == 2


def test_concurrent_catalog_change_is_not_overwritten_after_archive_verification(publication, monkeypatch):
    publisher, work, _ = publication
    release = runtime.complete_release
    concurrent = "c" * 40

    def advance(*args, **kwargs):
        result = release(*args, **kwargs)
        publisher.objects[concurrent] = {
            **publisher.objects[publisher.head], "independent-data.json": b"preserved"}
        publisher.head = concurrent
        return result
    monkeypatch.setattr(runtime, "complete_release", advance)
    with pytest.raises(ValueError, match="Data branch advanced"):
        runtime.run("not-used", work)
    assert publisher.head == concurrent and publisher.promotions == 0
    assert publisher.objects[publisher.head]["independent-data.json"] == b"preserved"


@pytest.mark.parametrize("changed", [
    {"passed": False}, {"network_requests": 1}, {"complete_outputs": 0},
    {"external_operations_blocked": False},
])
def test_unqualified_extracted_replay_never_creates_a_release_or_promotes_data(publication, changed):
    publisher, work, proof = publication
    proof.update(changed)
    with pytest.raises(ValueError, match="extracted replay"):
        runtime.run("not-used", work)
    assert publisher.releases == publisher.promotions == 0
