"""Publish verified automatic count and estimate successors without rebuilding the website."""

import argparse
from contextlib import contextmanager
import copy
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
import urllib.request
import zipfile

from scripts.participation_intake.contract import digest, encoded, pin
from scripts.participation_intake.publisher import GitPublisher
from scripts import results_granular
from scripts.nationwide import STATES


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "participation.automatic_runtime.v1"
RESULTS_REPOSITORY = "hanshanley/voter-participation"
WEBSITE_REPOSITORY = "hanshanley/margin_of_error"
RESULTS_POINTER = ("https://raw.githubusercontent.com/" + RESULTS_REPOSITORY
                   + "/results-data/latest.json")
CODE_PATHS = (
    "automatic_runtime.py", "automatic_estimates.py", "automatic_native_refresh.py",
    "results_granular.py", "norc_house_model.py", "current.py", "download.py",
    "native_tabular.py", "nationwide.py", "participation_intake/__init__.py",
    "participation_intake/contract.py", "participation_intake/publisher.py",
)


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def relative(name):
    path = PurePosixPath(name)
    if (not name or name == "." or path.is_absolute() or ".." in path.parts
            or "\\" in name or str(path) != name):
        raise ValueError("Unsafe automatic runtime path")
    return str(path)


def uncompressed(body, maximum=300_000_000):
    with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
        result = stream.read(maximum + 1)
    if len(result) > maximum:
        raise ValueError("Oversized uncompressed numerical query")
    return result


def packet_manifest(archive):
    entries = archive.infolist()
    names = [item.filename for item in entries]
    if (len(entries) > 4000 or len(set(names)) != len(names)
            or sum(item.file_size for item in entries) > 750_000_000
            or any(item.flag_bits & 1 for item in entries)):
        raise ValueError("Unqualified scientific packet inventory or size")
    for name in names:
        relative(name)
    manifest = json.loads(archive.read("checksums.json"))
    if set(names) != set(manifest) | {"checksums.json"}:
        raise ValueError("Unlisted or missing scientific packet members")
    for name, expected in manifest.items():
        if pin(archive.read(name)) != expected:
            raise ValueError("Changed source packet member: " + name)
    return manifest


def fetch(url, expected=None, maximum=250_000_000):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com"
            or parsed.username or parsed.password
            or not any(parsed.path.startswith("/" + repo + "/")
                       for repo in (RESULTS_REPOSITORY, WEBSITE_REPOSITORY))):
        raise ValueError("Automatic delivery reads only its two public pinned repositories")
    if expected is not None and (type(expected.get("bytes")) is not int
            or not 0 < expected["bytes"] <= maximum
            or not re.fullmatch(r"[a-f0-9]{64}", expected.get("sha256", ""))):
        raise ValueError("Invalid/oversized public body declaration")
    with urllib.request.urlopen(url, timeout=90) as response:
        if response.status != 200 or urlsplit(response.geturl()).hostname != parsed.hostname:
            raise ValueError("Public data response left its registered origin")
        body = response.read((expected["bytes"] if expected else maximum) + 1)
    if len(body) > maximum or expected is not None and pin(body) != expected:
        raise ValueError("Incomplete, changed or oversized automatic data body")
    return body


def results(pointer_url):
    pointer = json.loads(fetch(pointer_url, maximum=1_000_000))
    if (pointer.get("contract") != "participation.automatic_results_latest.v1"
            or not re.fullmatch(r"[a-f0-9]{64}", pointer.get("version", ""))
            or not re.fullmatch(r"[a-f0-9]{40}", pointer.get("results_commit", ""))):
        raise ValueError("Unqualified automatic results pointer")
    base = (f"https://raw.githubusercontent.com/{RESULTS_REPOSITORY}/"
            f"{pointer['results_commit']}/snapshots/{pointer['version']}/")
    if pointer.get("base_url") != base:
        raise ValueError("Result bodies must come from their exact immutable source commit")
    bodies = {}
    for name in ("snapshot.json.gz", "complete-results.zip"):
        expected = pointer["files"].get(name)
        if expected is None:
            raise ValueError("Incomplete source results: full snapshot and package required")
        bodies[name] = fetch(base + name, expected)
    snapshot = json.loads(uncompressed(bodies["snapshot.json.gz"]))
    if (snapshot.get("contract") != "participation.automatic_results_snapshot.v1"
            or snapshot.get("election_date") != "2026-11-03"
            or len(snapshot.get("jurisdictions", [])) != 51
            or {row.get("state_code") for row in snapshot["jurisdictions"]}
            != set(STATES)):
        raise ValueError("Wrong election or incomplete all-jurisdiction decisions")
    with zipfile.ZipFile(io.BytesIO(bodies["complete-results.zip"])) as archive:
        packet_manifest(archive)
        if archive.read("queries/snapshot.json.gz") != bodies["snapshot.json.gz"]:
            raise ValueError("Source packet and runtime snapshot disagree")
    return pointer, snapshot, bodies


def dataset_files(description):
    prefix = f"datasets/{description['id']}/{description['version']}/"
    base = (f"https://raw.githubusercontent.com/{WEBSITE_REPOSITORY}/"
            f"{description['staged_commit']}/{prefix}")
    if (description.get("contract") != "participation.dataset.v1"
            or not re.fullmatch(r"[a-f0-9]{40}", description.get("staged_commit", ""))
            or description.get("base_url") != base):
        raise ValueError("Existing dataset is not pinned to the website data repository")
    return {relative(name): fetch(base + name, expected)
            for name, expected in description["files"].items()}


def descriptor(before, files, download=None):
    pins = {name: pin(body) for name, body in sorted(files.items())}
    inherited = {key: copy.deepcopy(value) for key, value in before.items()
                 if key not in ("base_url", "staged_commit", "status")}
    return {**inherited, "files": pins,
            "version": digest(encoded({"files": pins, "contract": before["record_contract"]})),
            "index": {"file": "index.json", **pins["index.json"]},
            "complete_download": download}


def seed_files(directory):
    from scripts.automatic_estimates import FAMILIES, PROFILES

    directory = Path(directory)
    body = (directory / "manifest.json").read_bytes()
    manifest = json.loads(body)
    expected = {
        "accepted/candidates.json.gz", "accepted/controls.json.gz",
        "participation/registered-controls-v35.json.gz",
        *("accepted/viewer-" + profile + ".json.gz" for profile in PROFILES),
        *("scenarios/" + profile + "/" + family + "/" + name + ".json.gz"
          for profile in PROFILES for family in FAMILIES
          for name in ("complete-result", "synthetic-priors")),
    }
    declarations = [manifest[name] for name in (
        "accepted_candidates", "accepted_controls", "participation_state_controls")]
    declarations.extend(manifest["profile_viewers"].values())
    declarations.extend(item[name] for item in manifest["scenarios"].values()
                        for name in ("prior", "accepted_result"))
    paths = [relative(item["path"]) for item in declarations]
    if len(paths) != len(expected) or set(paths) != expected:
        raise ValueError("The bootstrap seed must contain exactly its declared safe aggregate members")
    result = {"manifest.json": body}
    for item in declarations:
        value = (directory / item["path"]).read_bytes()
        if pin(value) != {key: item[key] for key in ("bytes", "sha256")}:
            raise ValueError("Changed safe seed member: " + item["path"])
        result[item["path"]] = value
    return result


def select_seed(previous, directory):
    from scripts.automatic_estimates import load_seed, load_rolling_seed_bytes

    if previous is None:
        members = seed_files(directory)
        return load_seed(directory), members
    if previous.get("contract") != CONTRACT:
        raise ValueError("Cannot reset an unqualified previous automatic publication to the bootstrap seed")
    item = previous.get("house_sources", {}).get("next_seed")
    if not isinstance(item, dict):
        raise ValueError("Previous publication is missing its rolling last-good seed")
    version = previous.get("version", "")
    pattern = (r"https://raw\.githubusercontent\.com/" + re.escape(WEBSITE_REPOSITORY)
               + r"/[a-f0-9]{40}/automatic/versions/" + re.escape(version)
               + r"/rolling/next-seed\.json\.gz")
    if (not re.fullmatch(r"[a-f0-9]{64}", version)
            or item.get("path") != "rolling/next-seed.json.gz"
            or not re.fullmatch(pattern, item.get("url", ""))):
        raise ValueError("Rolling last-good seed is not bound to its immutable publication")
    expected = {key: item[key] for key in ("bytes", "sha256")}
    body = fetch(item["url"], expected, maximum=50_000_000)
    if pin(body) != expected:
        raise ValueError("Changed rolling last-good seed")
    uncompressed(body)
    return load_rolling_seed_bytes(body, item), {
        "rolling-seed.json.gz": body, "rolling-seed-descriptor.json": encoded(item)}


def bind_datasets(catalog, descriptions, staged, repository):
    candidate, checks = copy.deepcopy(catalog), {}
    for identity in ("participation-counts-2026", "participation-native-bindings-2026"):
        description = copy.deepcopy(descriptions.get(identity, catalog["datasets"][identity]))
        prefix = f"datasets/{identity}/{description['version']}/"
        description.update(status="loaded", staged_commit=staged,
            base_url=f"https://raw.githubusercontent.com/{repository}/{staged}/{prefix}")
        candidate["datasets"][identity] = description
        checks.update({prefix + relative(name): expected
                       for name, expected in description["files"].items()})
    return candidate, checks


def refresh_current(files, snapshot):
    index = json.loads(files["index.json"])
    declaration = index.get("current_snapshot")
    if not declaration:
        return files
    before = json.loads(uncompressed(files[declaration["file"]]))
    current = copy.deepcopy(before)
    for row in current.get("snapshot", {}).get("reporting", []):
        state = row["state_code"]
        decision = next((item for item in snapshot["jurisdictions"]
                         if item["state_code"] == state), {})
        data = decision.get("statewide_administrative_observation")
        source = next((item for item in snapshot["source_status"]
                       if item["source"] == state + "-official"), {})
        if (decision.get("statewide_administrative_status") != "reported" or not data
                or source.get("source_url") != row.get("source_url")
                or data.get("denominator_basis") != row.get("denominator_basis")):
            continue
        observations = [item for item in snapshot.get("participation_observations", [])
                        if item.get("channel") == state + "-official"
                        and item.get("status") == "reported"
                        and item.get("observation") == data
                        and item.get("source", {}).get("url") == row.get("source_url")]
        if len(observations) != 1 or not re.fullmatch(
                r"[a-f0-9]{64}", observations[0]["source"].get("sha256", "")):
            raise ValueError("Fresh statewide values need their exact native source pin")
        provenance = observations[0]["source"]
        row.setdefault("accepted_source_provenance", {
            name: copy.deepcopy(row.get(name)) for name in (
                "source_sha256", "source_snapshot", "source_date", "source_retrieved_at",
                "source_update_label", "source_update_timezone")})
        row.update({name: copy.deepcopy(data[name]) for name in (
            "ballots", "denominator", "denominator_basis", "published_pct",
            "validated_pct", "source_update_label", "reported_units", "total_units",
            "reporting_unit", "quality") if name in data})
        row.update(automatic_source_refresh=True, source_sha256=provenance["sha256"],
                   source_snapshot="automatic-native:" + provenance["sha256"],
                   source_date=data.get("source_date"),
                   source_retrieved_at=data.get("source_retrieved_at"),
                   source_update_timezone=data.get("source_update_timezone"))
    if current == before:
        return files
    result = dict(files)
    raw = bytearray(gzip.compress(encoded(current), compresslevel=6, mtime=0))
    raw[9] = 3
    result[declaration["file"]] = bytes(raw)
    declaration.update(pin(result[declaration["file"]]))
    result["index.json"] = encoded(index)
    return result


def compile_runtime(snapshot, count_files, native_files, seed):
    from scripts.automatic_estimates import build, render_artifacts
    from scripts.automatic_native_refresh import refresh

    updated, changes = results_granular.project(count_files, snapshot.get("granular_sources", {}))
    updated = refresh_current(updated, snapshot)
    native = refresh(count_files, updated, native_files)
    estimates = build(snapshot, seed)
    artifacts = render_artifacts(estimates)
    return {"counts": updated, "native": native, "estimates": estimates,
            "model_files": artifacts, "local_changes": changes}


def archive_bytes(members):
    all_members = dict(members)
    all_members["checksums.json"] = encoded({name: pin(body) for name, body in sorted(members.items())})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, body in sorted(all_members.items()):
            relative(name)
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type, item.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(item, body)
    return buffer.getvalue()


def scientific_package(snapshot, source_packet, count_files, native_files, seed_inputs, compiled):
    members = {"inputs/snapshot.json": encoded(snapshot),
               "inputs/complete-source-results.zip": source_packet}
    for role, files in (("before-counts", count_files), ("before-native", native_files),
                        ("after-counts", compiled["counts"]), ("after-native", compiled["native"]),
                        ("model-queries", compiled["model_files"])):
        for name, body in files.items():
            members[("inputs/" if role.startswith("before-") else "queries/") + role + "/" + name] = body
    for name, body in seed_inputs.items():
        members["inputs/model-seed/" + relative(name)] = body
    for name in CODE_PATHS:
        members["code/scripts/" + name] = (ROOT / "scripts" / name).read_bytes()
    for name in ("test_automatic_runtime.py", "test_results_granular.py",
                 "test_automatic_estimates.py", "test_automatic_native_refresh.py"):
        path = ROOT / "tests" / name
        if path.is_file():
            members["code/tests/" + name] = path.read_bytes()
    members["code/reproduce.py"] = (
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0,str(Path(__file__).resolve().parent))\n"
        "from scripts.automatic_runtime import main\nmain()\n").encode()
    members["REPRODUCE.txt"] = (
        "Python >=3.9; requests>=2.31 is an existing project dependency.\n"
        "python3 code/reproduce.py --replay-package . --output reproduced\n"
        "Recomputes the complete count/native/model numerical query sets from included\n"
        "public aggregate source facts and safe accepted priors. No source requests,\n"
        "private survey refits, new geographic joins or observed-history claims.\n").encode()
    return archive_bytes(members)


@contextmanager
def offline():
    from unittest.mock import patch
    attempts = []
    def deny(*args, **kwargs):
        attempts.append(True)
        raise RuntimeError("External operations are forbidden during numerical replay")
    with patch.object(socket, "socket", deny), patch.object(socket, "create_connection", deny), \
            patch.object(socket, "getaddrinfo", deny), patch.object(subprocess, "Popen", deny), \
            patch.object(os, "system", deny):
        yield attempts


def replay(package, output):
    from scripts.automatic_estimates import load_seed, load_rolling_seed_bytes
    package, output = Path(package), Path(output)
    if output.exists():
        raise ValueError("Reproduction needs a fresh output directory")
    manifest = read(package / "checksums.json")
    for name, expected in manifest.items():
        if pin((package / relative(name)).read_bytes()) != expected:
            raise ValueError("Changed scientific packet member: " + name)
    def files(role):
        prefix = "inputs/" + role + "/"
        return {name[len(prefix):]: (package / name).read_bytes()
                for name in manifest if name.startswith(prefix)}
    seed_directory = package / "inputs/model-seed"
    seed_inventory = {name[len("inputs/model-seed/"):] for name in manifest
                      if name.startswith("inputs/model-seed/")}
    if "manifest.json" in seed_inventory:
        if set(seed_files(seed_directory)) != seed_inventory:
            raise ValueError("Unexpected bootstrap-seed packet member")
        seed = load_seed(seed_directory)
    elif seed_inventory == {"rolling-seed.json.gz", "rolling-seed-descriptor.json"}:
        body = (seed_directory / "rolling-seed.json.gz").read_bytes()
        uncompressed(body)
        seed = load_rolling_seed_bytes(body, read(seed_directory / "rolling-seed-descriptor.json"))
    else:
        raise ValueError("Incomplete rolling last-good seed in scientific packet")
    with offline() as attempts:
        compiled = compile_runtime(read(package / "inputs/snapshot.json"),
            files("before-counts"), files("before-native"), seed)
    outputs = {}
    for role in ("counts", "native", "model_files"):
        label = {"counts": "after-counts", "native": "after-native",
                 "model_files": "model-queries"}[role]
        outputs.update({"queries/" + label + "/" + name: body
                        for name, body in compiled[role].items()})
    if set(outputs) != {name for name in manifest if name.startswith("queries/")}:
        raise ValueError("Incomplete automatic numerical output inventory")
    for name, body in outputs.items():
        if body != (package / name).read_bytes():
            raise ValueError("Automatic numerical reproduction differs: " + name)
    for name, body in outputs.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    return {"passed": True, "complete_outputs": len(outputs),
            "network_requests": len(attempts), "external_operations_blocked": True}


def gh(*arguments, body=None, check=True):
    result = subprocess.run(["gh", *arguments], input=body, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=check)
    return result.stdout


def complete_release(repository, version, path, journal, checkpoint=lambda: None):
    tag = "automatic-participation-" + version
    expected = pin(Path(path).read_bytes())
    if not journal.get("release_id"):
        found = gh("api", "repos/" + repository + "/releases/tags/" + tag, check=False)
        try:
            release = json.loads(found)
        except ValueError:
            release = None
        if not release or not release.get("id"):
            recent = json.loads(gh("api", "repos/" + repository + "/releases?per_page=100"))
            release = next((item for item in recent if item["tag_name"] == tag), None)
        if release is None or not release.get("id"):
            release = json.loads(gh("api", "--method", "POST", "repos/" + repository + "/releases",
                "--input", "-", body=encoded({"tag_name": tag, "target_commitish": "main",
                "name": "Automatic participation data " + version[:12], "draft": True,
                "body": "Complete public aggregate results, qualified estimates, inputs, code and offline replay. "
                        "Unreported sources and scientific holds remain explicit; not certification."})))
        journal["release_id"] = release["id"]
        checkpoint()
    release_id = journal["release_id"]
    release = json.loads(gh("api", f"repos/{repository}/releases/{release_id}"))
    asset = next((item for item in release["assets"] if item["name"] == "complete-analysis.zip"), None)
    if asset is None:
        if not release["draft"]:
            raise ValueError("Published automatic release is missing its complete archive")
        gh("release", "upload", tag, str(path) + "#Complete numerical analysis", "--repo", repository)
        release = json.loads(gh("api", f"repos/{repository}/releases/{release_id}"))
        asset = next(item for item in release["assets"] if item["name"] == "complete-analysis.zip")
    authenticated = gh("api", f"repos/{repository}/releases/assets/{asset['id']}",
                       "-H", "Accept: application/octet-stream")
    if pin(authenticated) != expected or asset["size"] != expected["bytes"]:
        raise ValueError("Draft complete archive did not match its scientific packet")
    if release["draft"]:
        gh("api", "--method", "PATCH", f"repos/{repository}/releases/{release_id}",
           "--input", "-", body=encoded({"draft": False}))
    release = json.loads(gh("api", f"repos/{repository}/releases/{release_id}"))
    if release.get("draft") or release.get("immutable") is not True:
        raise ValueError("Automatic archive is not server-immutable; active website data retained")
    url = f"https://github.com/{repository}/releases/download/{tag}/complete-analysis.zip"
    # No authentication is supplied for this final public full-body verification.
    with urllib.request.urlopen(url, timeout=180) as response:
        public = response.read(expected["bytes"] + 1)
    if pin(public) != expected:
        raise ValueError("Anonymous complete archive verification failed")
    return {"url": url, **expected, "media_type": "application/zip",
            "immutable": True, "verified_anonymously": True}


def run(repository, work, pointer_url=RESULTS_POINTER, seed_dir=None,
        github_repository=WEBSITE_REPOSITORY, publish=True):
    from scripts.automatic_estimates import bind_publication
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    publisher = GitPublisher(repository, github_repository=github_repository)
    parent = publisher.remote_head()
    publisher.fetch_parent(parent)
    catalog = publisher.catalog(parent)
    pointer, snapshot, source = results(pointer_url)
    seed_dir = Path(seed_dir or ROOT / "data/results-intake/model-seed")
    processing = digest(encoded({
        "code": {name: pin((ROOT / "scripts" / name).read_bytes()) for name in CODE_PATHS},
        "seed": {name: pin(body) for name, body in seed_files(seed_dir).items()}}))
    previous = publisher.git("show", parent + ":automatic/latest.json", check=False) if parent else ""
    if previous:
        previous = json.loads(previous)
        if (previous.get("input_results_version") == pointer["version"]
                and previous.get("processing_version") == processing
                and all(previous.get(field, {}).get("version")
                        == catalog["datasets"].get(identity, {}).get("version")
                        for field, identity in (("counts", "participation-counts-2026"),
                                                ("native", "participation-native-bindings-2026")))):
            return {"status": "unchanged", "version": previous["version"],
                    "data_commit": parent, "website_builds_started": 0}
    count_description = catalog["datasets"]["participation-counts-2026"]
    native_description = catalog["datasets"]["participation-native-bindings-2026"]
    counts, native = dataset_files(count_description), dataset_files(native_description)
    seed, seed_inputs = select_seed(previous or None, seed_dir)
    compiled = compile_runtime(snapshot, counts, native, seed)
    packet = scientific_package(snapshot, source["complete-results.zip"], counts, native, seed_inputs, compiled)
    version = digest(encoded({"input_results_version": pointer["version"],
        "packet": pin(packet), "counts": {name: pin(body) for name, body in compiled["counts"].items()},
        "native": {name: pin(body) for name, body in compiled["native"].items()}}))
    packet_path = work / "complete-analysis.zip"
    packet_path.write_bytes(packet)
    with tempfile.TemporaryDirectory(prefix="automatic-replay-") as directory:
        extraction = Path(directory) / "packet"
        extraction.mkdir()
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:
            packet_manifest(archive)
            archive.extractall(extraction)
        replayed = subprocess.run([sys.executable, "code/reproduce.py", "--replay-package", ".",
            "--output", str(Path(directory) / "reproduced")], cwd=extraction,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"})
        proof = json.loads(replayed.stdout)
    if (proof.get("passed") is not True or proof.get("network_requests") != 0
            or proof.get("external_operations_blocked") is not True
            or proof.get("complete_outputs") != sum(len(compiled[name])
                for name in ("counts", "native", "model_files"))):
        raise ValueError("Fresh extracted replay did not verify every output offline")
    write(work / "report.json", {"version": version, "input_results_version": pointer["version"],
        "local_changes": compiled["local_changes"], "complete_download": pin(packet),
        "estimate_summary": compiled["estimates"].get("decision_summary"),
        "offline_replay": proof, "website_builds_started": 0, "source_models_refitted": False})
    if not publish:
        return {"status": "prepared_not_published", "version": version, "work_dir": str(work)}
    journal_path = work / ("publication-" + version + ".json")
    journal = read(journal_path) if journal_path.exists() else {"parent": parent, "version": version}
    if parent not in (journal["parent"], journal.get("staged"), journal.get("promoted")):
        raise ValueError("Active data advanced outside this publication; prepare against its new catalog")
    if parent != journal["parent"]:
        original_catalog = publisher.catalog(journal["parent"])
        if original_catalog != catalog:
            raise ValueError("Interrupted publication no longer matches its original catalog")
        parent = journal["parent"]
    download = complete_release(github_repository, version, packet_path, journal,
                                checkpoint=lambda: write(journal_path, journal))
    write(journal_path, journal)
    bodies, descriptions = {}, {}
    for identity, before, files in (
            ("participation-counts-2026", count_description, compiled["counts"]),
            ("participation-native-bindings-2026", native_description, compiled["native"])):
        if files == (counts if identity == "participation-counts-2026" else native):
            continue
        description = descriptor(before, files, download)
        prefix = f"datasets/{identity}/{description['version']}/"
        bodies.update({prefix + name: body for name, body in files.items()})
        bodies[prefix + "dataset.json"] = encoded(description)
        descriptions[identity] = description
    model_prefix = "automatic/versions/" + version + "/"
    bodies.update({model_prefix + name: body for name, body in compiled["model_files"].items()})
    if "staged" not in journal:
        staged = publisher.commit(publisher.tree(parent, bodies), parent,
                                  "Stage automatic count and estimate successors")
        journal["staged"] = staged
        write(journal_path, journal)
    staged = journal["staged"]
    if publisher.remote_head() == parent:
        publisher.promote(staged, parent)
    elif publisher.remote_head() not in (staged, journal.get("promoted")):
        raise ValueError("Data branch advanced; rebase without overwriting active data")
    publisher.verify_files(staged, {name: pin(body) for name, body in bodies.items()})
    candidate, coherent_checks = bind_datasets(catalog, descriptions, staged, github_repository)
    publisher.verify_files(staged, coherent_checks)
    bound = bind_publication(compiled["estimates"],
        f"https://raw.githubusercontent.com/{github_repository}/{staged}/{model_prefix}", download)
    manifest = {"contract": CONTRACT, "version": version, "election_date": "2026-11-03",
        "processing_version": processing,
        "input_results_version": pointer["version"], "checked_at": pointer["checked_at"],
        "counts": candidate["datasets"]["participation-counts-2026"],
        "native": candidate["datasets"]["participation-native-bindings-2026"],
        "house_sources": bound["house_sources"], "complete_download": download,
        "source_models_refitted": False, "geographic_joins_changed": False,
        "all_states_certified_or_precinct_complete": False}
    activation = {"catalog.json": encoded(candidate), "automatic/latest.json": encoded(manifest)}
    if "promoted" not in journal:
        journal["promoted"] = publisher.commit(publisher.tree(staged, activation), staged,
            "Atomically activate automatic counts and qualified estimates")
        write(journal_path, journal)
    promoted = journal["promoted"]
    if publisher.remote_head() == staged:
        publisher.promote(promoted, staged)
    elif publisher.remote_head() != promoted:
        raise ValueError("Active data advanced; last-good version preserved")
    publisher.verify_files(promoted, {name: pin(body) for name, body in activation.items()})
    result = {"status": "published", "version": version, "data_commit": promoted,
              "staged_commit": staged, "website_builds_started": 0, "complete_download": download}
    write(work / "publication.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--results-pointer", default=RESULTS_POINTER)
    parser.add_argument("--github-repository", default=WEBSITE_REPOSITORY)
    parser.add_argument("--model-seed", type=Path)
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--replay-package", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.replay_package:
        if not args.output:
            parser.error("--replay-package requires --output")
        result = replay(args.replay_package, args.output)
    else:
        if not args.repository or not args.work_dir:
            parser.error("--repository and --work-dir are required for automatic delivery")
        result = run(args.repository, args.work_dir, args.results_pointer, args.model_seed,
                     args.github_repository, publish=not args.no_publish)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
