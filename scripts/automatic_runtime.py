"""Publish verified automatic count and estimate successors without rebuilding the website."""

import argparse
from contextlib import contextmanager
import copy
from datetime import datetime
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

from scripts.participation_intake.contract import (
    digest, encoded, pin, require_general_election_publication_time, utc_now)
from scripts.participation_intake.publisher import GitPublisher
from scripts import results_granular
from scripts.maryland_precinct_history import ARCHIVE_INPUT as MD_ARCHIVE_INPUT, ARCHIVE_MEMBER as MD_ARCHIVE_MEMBER
from scripts import retained_bulk_turnout
from scripts.cps_published_state_tables import INPUT as CPS_INPUT, INPUT_PATH as CPS_INPUT_PATH
from scripts.senate_survey_support import ARCHIVE as SENATE_SURVEY_ARCHIVE, INPUT as SENATE_SURVEY_INPUT
from scripts.nationwide import STATES


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "participation.automatic_runtime.v1"
RESULTS_REPOSITORY = "hanshanley/voter-participation"
WEBSITE_REPOSITORY = "hanshanley/margin_of_error"
RESULTS_POINTER = ("https://raw.githubusercontent.com/" + RESULTS_REPOSITORY
                   + "/results-data/latest.json")
CODE_PATHS = (
    "automatic_runtime.py", "automatic_estimates.py", "automatic_native_refresh.py",
    "current_source_reconciliation.py",
    "results_granular.py", "results_native_louisiana.py",
    "results_native_louisiana_runtime.py", "louisiana_onboarding.py",
    "louisiana_bootstrap.py", "louisiana_group_history.py", "participation_count_additions.py",
    "senate_survey_support.py", "norc_senate_routing.py", "ces_senate_routing.py", "ces_2022_senate_routing.py",
    "norc_house_model.py", "current.py", "download.py",
    "native_tabular.py", "native_products.py", "nationwide.py", "participation_intake/__init__.py",
    "results_state_statistics.py", "results_uf_turnout.py", "results_official_congress.py",
    "results_aspx_congress.py", "results_json_congress.py",
    "results_clarity_congress.py", "results_connecticut_congress.py", "results_county_frame.py", "results_pdf_county_parent.py",
    "results_minnesota_turnout.py", "results_turnout_history.py", "national_turnout_release_watch.py",
    "washington_participation.py", "oregon_turnout_history.py", "retained_bulk_turnout.py", "southeast_turnout.py",
    "alabama_precinct_history.py", "alaska_precinct_history.py", "alaska_cards_history.py", "alaska_age_history.py",
    "connecticut_turnout_history.py", "bulk_participation_archives.py", "kansas_turnout_history.py",
    "virginia_precinct_turnout.py", "virginia_bulk_turnout.py", "virginia_absentee_history.py",
    "kansas_house_canvass.py", "idaho_turnout_history.py", "idaho_absentee_age.py", "massachusetts_ballot_canvass.py",
    "hawaii_turnout_history.py", "hawaii_precinct_turnout.py", "dakota_turnout_history.py", "new_jersey_periodic_counties.py",
    "north_carolina_participation.py", "new_mexico_turnout_history.py", "california_media.py", "california_turnout_history.py",
    "indiana_early_state_turnout.py", "indiana_early_county_turnout.py", "pa_audit_ballots.py",
    "south_carolina_voter_statistics.py",
    "wyoming_participation_statistics.py", "nebraska_canvass.py",
    "nebraska_county_reports.py",
    "colorado_voting_statistics.py", "maryland_precinct_history.py", "minnesota_precinct_history.py",
    "results_pdf_archive_ocr.py", "results_pdf_ocr.py",
    "results_indiana_turnout.py",
    "results_ca_county_scan_transcriptions.json",
    "connecticut_2018_verified_scan.json",
    "results_nc_vote_history.py",
    "results_pa_vote_history.py", "results_alaska_turnout.py",
    "eac_county_turnout.py", "cps_published_state_tables.py", "cps_archived_state_tables.py", "philadelphia_divisions.py",
    "results_native_congress.py", "results_native_dc.py", "results_native_state_family.py",
    "results_native_oregon.py", "results_native_north_carolina.py", "results_native_idaho.py", "results_native_virginia.py",
    "results_congress.py", "results_house.py",
    "congressional_analytical_bridge.py", "congressional_candidate_identity.py",
    "congressional_filing_identity.py",
    "congressional_category_reconciliation.py",
    "congressional_complete_categories.py",
    "congressional_baselines.py", "congressional_geography.py",
    "congressional_split_blocks.py", "house_district_map.py",
    "official_house_precedence.py", "native_official_house.py",
    "congressional_reference_identity.py",
    "supported_analytical_release.py", "nm_turnout_export.py", "results_native_rhode_island.py",
    "senate_legacy_bridge.py", "senate_complete_categories.py", "protected_official_house.py",
    "protected_official_wyoming.py", "statewide_ballot_totals.py", "calibrated_swing.py",
    "participation_intake/contract.py", "participation_intake/publisher.py",
)
REVIEWED_STATE_MIRROR_MIGRATIONS = {
    "CA": {
        "observation_id": "a96982ff0425b036eeaf1fa394c3b866",
        "legacy_view_pin": {
            "bytes": 3320,
            "sha256": "14f7aeb52f6534e5192f05bb9d8af8590315d7cebf9d36f398bd0db4d8856462",
        },
        "source_url": "https://media.sos.ca.gov/media/status_GG.json",
        "measure_literal": "voterTurnout",
    },
}


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


def results_pointer(pointer_url):
    pointer = json.loads(fetch(pointer_url, maximum=1_000_000))
    if (not isinstance(pointer, dict)
            or pointer.get("contract") != "participation.automatic_results_latest.v1"
            or not re.fullmatch(r"[a-f0-9]{64}", pointer.get("version", ""))
            or not re.fullmatch(r"[a-f0-9]{40}", pointer.get("results_commit", ""))):
        raise ValueError("Unqualified automatic results pointer")
    base = (f"https://raw.githubusercontent.com/{RESULTS_REPOSITORY}/"
            f"{pointer['results_commit']}/snapshots/{pointer['version']}/")
    if pointer.get("base_url") != base:
        raise ValueError("Result bodies must come from their exact immutable source commit")
    files = pointer.get("files")
    if not isinstance(files, dict):
        raise ValueError("Incomplete source results: full snapshot and package required")
    for name in ("snapshot.json.gz", "complete-results.zip"):
        expected = files.get(name)
        if (not isinstance(expected, dict) or set(expected) != {"bytes", "sha256"}
                or type(expected["bytes"]) is not int or not 0 < expected["bytes"] <= 250_000_000
                or not isinstance(expected["sha256"], str)
                or not re.fullmatch(r"[a-f0-9]{64}", expected["sha256"])):
            raise ValueError("Incomplete or invalid source snapshot/package declaration")
    result_time(pointer.get("checked_at"))
    return pointer


def result_time(value):
    if not isinstance(value, str):
        raise ValueError("Missing source snapshot check time")
    observed = datetime.fromisoformat(value)
    if observed.utcoffset() is None:
        raise ValueError("Source snapshot check time has no offset")
    return observed


def result_bodies(pointer):
    bodies = {name: fetch(pointer["base_url"] + name, pointer["files"][name])
              for name in ("snapshot.json.gz", "complete-results.zip")}
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
    return snapshot, bodies


def results(pointer_url):
    pointer = results_pointer(pointer_url)
    snapshot, bodies = result_bodies(pointer)
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


def refresh_current(files, snapshot, previous_files=None):
    index = json.loads(files["index.json"])
    declaration = index.get("current_snapshot")
    if not declaration:
        return files
    before = json.loads(uncompressed(files[declaration["file"]]))
    current = copy.deepcopy(before)
    if previous_files is not None:
        from scripts.automatic_native_refresh import observation_identity

        previous_index = json.loads(previous_files["index.json"])
        for row in current.get("reviewed_states", []):
            state = row.get("state_code")
            prior = previous_index.get("states", {}).get(state)
            if prior is None:
                continue
            old = json.loads(uncompressed(previous_files[prior["file"]]))
            matches = [item for item in old["records"] if item.get("view") == row]
            migration = REVIEWED_STATE_MIRROR_MIGRATIONS.get(state)
            migrating = not matches and migration and pin(encoded(row)) == migration["legacy_view_pin"]
            if migrating:
                matches = [item for item in old["records"]
                           if item["id"] == migration["observation_id"]]
            if not matches:
                continue
            if len(matches) != 1 or matches[0].get("geography", {}).get("level") != "state":
                raise ValueError("Ambiguous canonical binding for reviewed statewide mirror")
            old_record = matches[0]
            updated = json.loads(uncompressed(files[index["states"][state]["file"]]))
            successors = [item for item in updated["records"] if item["id"] == old_record["id"]]
            if len(successors) != 1 or observation_identity(successors[0]) != observation_identity(
                    old_record):
                raise ValueError("Changed canonical identity for reviewed statewide mirror")
            if migrating:
                successor = successors[0]
                if (successor["view"].get("automatic_source_refresh") is not True
                        or successor["source"].get("url") != migration["source_url"]
                        or successor["measure"].get("literal") != migration["measure_literal"]):
                    continue
                current.setdefault("reviewed_state_mirror_bindings", {})[state] = {
                    "contract": "participation.reviewed_state_mirror_migration.v1",
                    **copy.deepcopy(migration),
                }
            row.clear()
            row.update(copy.deepcopy(successors[0]["view"]))
    from scripts.results_state_statistics import WEBFORMS_STATE_PROFILES, refresh_webforms_mirror
    for row in current.get("snapshot", {}).get("reporting", []):
        profile = WEBFORMS_STATE_PROFILES.get(row.get("source_url"))
        if profile is None or row.get("state_code") != profile["state_code"]:
            continue
        state = profile["state_code"]
        state_declaration = index.get("states", {}).get(state)
        if state_declaration is None:
            continue
        shard = json.loads(uncompressed(files[state_declaration["file"]]))
        matches = [record for record in shard["records"]
                   if record["id"] == profile["observation_id"]]
        if len(matches) != 1:
            raise ValueError("Ambiguous native statewide header mirror")
        if matches[0].get("view", {}).get("automatic_source_refresh") is True:
            previous = previous_files if previous_files is not None else files
            previous_index = json.loads(previous["index.json"])
            prior_shard = json.loads(uncompressed(previous[
                previous_index["states"][state]["file"]]))
            prior, = [record for record in prior_shard["records"]
                      if record["id"] == profile["observation_id"]]
            refresh_webforms_mirror(row, matches[0], prior)
    for row in current.get("snapshot", {}).get("reporting", []):
        state = row["state_code"]
        if "statewide_ballot_parent" in row:
            continue
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
        if "native_state_statistics" in data:
            from scripts.results_state_statistics import refresh as refresh_state_statistics
            row.update(refresh_state_statistics(row, data, provenance))
            continue
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
    uf = snapshot.get("uf_turnout")
    if uf is not None and uf.get("data") is not None:
        from scripts.results_uf_turnout import view as uf_view
        current["uf_turnout"] = uf_view(uf)
    if current == before:
        return files
    result = dict(files)
    raw = bytearray(gzip.compress(encoded(current), compresslevel=6, mtime=0))
    raw[9] = 3
    result[declaration["file"]] = bytes(raw)
    declaration.update(pin(result[declaration["file"]]))
    result["index.json"] = encoded(index)
    return result


def hydrate_granular_sources(snapshot, source_packet):
    """Restore checksum-bound granular replay data externalized from the bounded snapshot."""
    compact = snapshot.get("granular_sources", {})
    if not isinstance(compact, dict):
        raise ValueError("Malformed compact granular source inventory")
    references = {}
    for identity, entry in compact.items():
        if not isinstance(entry, dict):
            raise ValueError("Malformed compact granular source entry")
        data = entry.get("data")
        if data is None:
            continue
        reference = data.get("full_data") if isinstance(data, dict) else None
        if reference is None:
            continue
        if (
            not isinstance(reference, dict)
            or reference.get("file") != "granular-source-queries.json.gz"
            or reference.get("key") != identity
            or type(reference.get("bytes")) is not int
            or reference["bytes"] <= 0
            or not re.fullmatch(r"[a-f0-9]{64}", reference.get("sha256", ""))
        ):
            raise ValueError("Malformed granular replay-data reference")
        references[identity] = reference
    if not references:
        if any(isinstance(row, dict) and isinstance(row.get("observation"), dict)
               and row["observation"].get("contract")
               == "participation.externalized_native_query.v1"
               for row in snapshot.get("participation_observations", [])):
            raise ValueError("Externalized participation observation has no granular query")
        return snapshot
    if not isinstance(source_packet, bytes):
        raise ValueError("Referenced granular replay data requires the complete source packet")
    with zipfile.ZipFile(io.BytesIO(source_packet)) as archive:
        packet_manifest(archive)
        name = "queries/granular-source-queries.json.gz"
        if name not in archive.namelist():
            raise ValueError("Complete source packet is missing granular replay data")
        body = archive.read(name)
    declared = {(item["bytes"], item["sha256"]) for item in references.values()}
    if len(declared) != 1 or pin(body) != {
            "bytes": next(iter(declared))[0], "sha256": next(iter(declared))[1]}:
        raise ValueError("Granular replay data disagrees with its snapshot checksum")
    full = json.loads(uncompressed(body))
    if not isinstance(full, dict) or set(full) != set(compact):
        raise ValueError("Granular replay inventory differs from the compact snapshot")
    for identity, compact_entry in compact.items():
        full_entry = full.get(identity)
        if not isinstance(full_entry, dict):
            raise ValueError("Missing granular replay entry: " + identity)
        if ({key: value for key, value in compact_entry.items() if key != "data"}
                != {key: value for key, value in full_entry.items() if key != "data"}):
            raise ValueError("Granular replay entry metadata changed: " + identity)
        compact_data, full_data = compact_entry.get("data"), full_entry.get("data")
        if compact_data is None:
            if full_data is not None:
                raise ValueError("Compact granular absence disagrees with replay data")
            continue
        if identity not in references or not isinstance(full_data, dict):
            raise ValueError(
                "Compact granular data is missing its exact replay reference: " + identity)
        summary = compact_data.get("summary")
        expected_summary = {
            key: value for key, value in full_data.items()
            if value is None or isinstance(value, (bool, int, float, str))
        }
        updates = full_data.get("updates")
        if isinstance(updates, list):
            expected_summary["projected_updates"] = {
                "records": len(updates),
                "reported": sum(update.get("value") is not None for update in updates),
                "unknown": sum(update.get("value") is None for update in updates),
                "observation_ids_pin": digest(encoded(sorted(update["id"] for update in updates))),
            }
        if summary != expected_summary:
            raise ValueError("Granular replay summary changed: " + identity)
        bridge = compact_data.get("reviewed_source_url_bridge")
        if bridge != full_data.get("reviewed_source_url_bridge"):
            raise ValueError("Granular replay source bridge changed: " + identity)
    hydrated = copy.deepcopy(snapshot)
    hydrated["granular_sources"] = full
    for row in hydrated.get("participation_observations", []):
        observation = row.get("observation") if isinstance(row, dict) else None
        if not isinstance(observation, dict) or observation.get("contract") \
                != "participation.externalized_native_query.v1":
            continue
        reference = observation.get("full_data")
        identity = row.get("channel")
        expected = references.get(identity)
        if (
            expected is None or reference != {
                **expected,
                "qualification": (
                    "Lossless exact native data externalized from the bounded snapshot."),
            }
            or identity not in full
            or full[identity].get("data") is None
            or observation.get("summary") != compact[identity]["data"].get("summary")
            or row.get("source") != full[identity].get("source")
            or row.get("status") != full[identity].get("status")
            or row.get("state_code") != identity.split("-")[0]
        ):
            raise ValueError("Externalized participation observation reference changed")
        row["observation"] = copy.deepcopy(full[identity]["data"])
    return hydrated


def compile_runtime(snapshot, count_files, native_files, seed, source_packet=None, *, boundary_source_root=None):
    from scripts import philadelphia_divisions, results_pa_vote_history, results_turnout_history as turnout_history
    from scripts.automatic_estimates import _artifact, build, render_artifacts
    from scripts.automatic_native_refresh import refresh
    from scripts.results_county_frame import (
        project as county_frames, project_bath, project_buxton, project_cuyahoga, project_douglas, project_georgia,
        project_ohio, project_philadelphia,
        project_illinois, project_oktibbeha, project_sumner, project_summit, project_sussex,
        project_votingworks_towns, project_wilson,
    )
    from scripts.statewide_ballot_totals import project as state_totals, exports as state_exports

    snapshot = hydrate_granular_sources(snapshot, source_packet)
    updated, changes = results_granular.project(count_files, snapshot.get("granular_sources", {}))
    updated = refresh_current(updated, snapshot, previous_files=count_files)
    updated, state_changes = state_totals(updated, snapshot, seed.get("nc_retained_original"),
                                          seed.get("oh_retained_original"),
                                          georgia_retained_original=seed.get("ga_retained_original"))
    changes.extend(state_changes)
    native = refresh(count_files, updated, native_files)
    updated, native, county_changes = county_frames(updated, native, snapshot)
    changes.extend(county_changes)
    updated, native, county_changes = project_cuyahoga(updated, native, snapshot)
    changes.extend(county_changes)
    updated, native, county_changes = project_ohio(updated, native)
    changes.extend(county_changes)
    updated, native, county_changes = project_georgia(updated, native)
    changes.extend(county_changes)
    updated, native, county_changes = project_wilson(updated, native, snapshot)
    changes.extend(county_changes)
    updated, native, county_changes = project_sumner(updated, native, snapshot)
    changes.extend(county_changes)
    retained_canvasses = seed.get("retained_county_canvasses")
    updated, native, county_changes = project_summit(updated, native, snapshot, retained_canvasses=retained_canvasses)
    changes.extend(county_changes)
    updated, native, county_changes = project_sussex(updated, native, snapshot, retained_canvasses=retained_canvasses)
    changes.extend(county_changes)
    updated, native, county_changes = project_douglas(updated, native, snapshot, retained_canvasses=retained_canvasses)
    changes.extend(county_changes)
    updated, native, county_changes = project_oktibbeha(updated, native, snapshot)
    changes.extend(county_changes)
    updated, native, county_changes = project_illinois(updated, native, snapshot)
    changes.extend(county_changes)
    updated, native, town_changes = project_buxton(updated, native, snapshot)
    changes.extend(town_changes)
    updated, native, town_changes = project_bath(updated, native, snapshot)
    changes.extend(town_changes)
    updated, native, town_changes = project_votingworks_towns(updated, native, snapshot)
    changes.extend(town_changes)
    updated, native, county_changes = project_philadelphia(updated, native, snapshot)
    changes.extend(county_changes)
    updated, native = philadelphia_divisions.project(updated, native, snapshot)
    model_seed = {key: value for key, value in seed.items()
                  if key not in {"historical_eac_county_facts", "nc_retained_original", "oh_retained_original",
                                 "ga_retained_original", "retained_county_canvasses",
                                 "tx_retained_history", "md_retained_history", "retained_bulk_turnout",
                                 "cps_published_state_workbooks", "senate_survey_archive"}}
    estimates = build(snapshot, model_seed)
    history_exports = {}
    for code, feed, state_name in (("WA", turnout_history.WA_FEED, "washington"),
                                  ("VA", turnout_history.VA_FEED, "virginia"),
                                  ("TX", turnout_history.TX_FEED, "texas"),
                                  ("NC", turnout_history.NC_HISTORY_FEED, "north-carolina")):
        entry = snapshot.get("granular_sources", {}).get(feed, {})
        if code == "TX":
            entry = turnout_history.texas_history_entry(entry, seed.get("tx_retained_history"))
        if not entry.get("data"):
            continue
        prefix = f"participation/{state_name}-general-election-turnout-history"
        facts = turnout_history.north_carolina_history_facts(entry) if code == "NC" else entry["data"]
        data = {"contract": "participation.statewide_general_election_history.v1",
                "state_code": code, "status": entry["status"], "source": entry["source"], **facts}
        artifact = _artifact(data)
        path, csv_path = prefix + ".json.gz", prefix + ".csv"
        estimates["artifacts"][path] = artifact
        csv_body = turnout_history.history_csv(entry, virginia=code == "VA", texas=code == "TX",
                                               north_carolina=code == "NC")
        history_exports[csv_path] = csv_body
        estimates["house_sources"].setdefault("general_election_turnout_history", {})[code] = {
            "data": {"path": path, **{key: value for key, value in artifact.items() if key != "content"}},
            "csv": {"path": csv_path, **pin(csv_body)},
        }
    for feed, product, filename, export in (
        (turnout_history.WY_HISTORY_FEED, "wyoming_turnout_profile",
         "wyoming-primary-general-turnout-profile", turnout_history.wyoming_history_exports),
        (turnout_history.WY_CANVASS_FEED, "wyoming_precinct_canvass",
         "wyoming-2026-precinct-ballot-canvass", turnout_history.wyoming_precinct_exports),
    ):
        wy_entry = snapshot.get("granular_sources", {}).get(feed, {})
        if not wy_entry.get("data"):
            continue
        data, csv_body = export(wy_entry)
        path = "participation/" + filename
        data_path, csv_path = path + ".json.gz", path + ".csv"
        artifact = _artifact(data)
        estimates["artifacts"][data_path] = artifact
        history_exports[csv_path] = csv_body
        estimates["house_sources"][product] = {
            "data": {"path": data_path, **{key: value for key, value in artifact.items() if key != "content"}},
            "csv": {"path": csv_path, **pin(csv_body)},
        }
    pa_history, pa_csv = results_pa_vote_history.exports(snapshot.get("granular_sources", {}))
    if pa_history is not None:
        prefix = "participation/pennsylvania-general-election-vote-history"
        path, csv_path = prefix + ".json.gz", prefix + ".csv"
        artifact = _artifact(pa_history)
        estimates["artifacts"][path] = artifact
        history_exports[csv_path] = pa_csv
        estimates["house_sources"]["pennsylvania_general_vote_history"] = {
            "data": {"path": path, **{key: value for key, value in artifact.items() if key != "content"}},
            "csv": {"path": csv_path, **pin(pa_csv)},
        }
    artifacts = render_artifacts(estimates)
    artifacts.update(state_exports(updated))
    artifacts.update(history_exports)
    uf = snapshot.get("uf_turnout")
    if uf is not None and uf.get("data") is not None:
        from scripts.results_uf_turnout import exports as uf_exports
        artifacts.update({"participation/" + name: body for name, body in uf_exports(uf).items()})
    result = {"counts": updated, "native": native, "estimates": estimates,
              "model_files": artifacts, "local_changes": changes}
    if "nc_retained_original" in seed:
        result["nc_retained_original"] = seed["nc_retained_original"]
    if "oh_retained_original" in seed:
        result["oh_retained_original"] = seed["oh_retained_original"]
    if "ga_retained_original" in seed:
        result["ga_retained_original"] = seed["ga_retained_original"]
    if "retained_county_canvasses" in seed:
        result["retained_county_canvasses"] = seed["retained_county_canvasses"]
    if "tx_retained_history" in seed:
        result["tx_retained_history"] = seed["tx_retained_history"]
    if "md_retained_history" in seed:
        result["md_retained_history"] = seed["md_retained_history"]
    if "retained_bulk_turnout" in seed:
        result["retained_bulk_turnout"] = seed["retained_bulk_turnout"]
    if "historical_eac_county_facts" in seed:
        from scripts.eac_county_turnout import exports as eac_exports
        eac_files, descriptor = eac_exports(seed["historical_eac_county_facts"])
        artifacts.update(eac_files)
        estimates["house_sources"]["historical_eac_counties"] = descriptor
        result["historical_eac_county_facts"] = seed["historical_eac_county_facts"]
    if "supported_release_review" in seed:
        from scripts.supported_analytical_release import build as build_release
        congressional = {}
        if "congress" in snapshot:
            from scripts.results_congress import runtime as congressional_runtime
            congressional_files, declaration = congressional_runtime(
                snapshot["congress"], seed["supported_release_review"],
                analytical_review=seed.get("congressional_analytical_review"),
                estimates=estimates)
            artifacts.update(congressional_files)
            result["congressional"] = declaration
            congressional = json.loads(gzip.decompress(congressional_files["congressional/results.json.gz"]))
        release = build_release(snapshot, updated, seed, estimates, changes,
                                congressional_races=congressional.get("races"),
                                congressional_states=congressional.get("house_states"),
                                congressional_comparisons=artifacts.get("congressional/congress-comparisons.csv"),
                                boundary_source_root=boundary_source_root)
        artifacts.update(release["files"])
        estimates["house_sources"]["supported_release"] = release["descriptor"]
        result["release_review"] = seed["supported_release_review"]
        if "cps_published_state_workbooks" in seed:
            result["cps_published_state_workbooks"] = seed["cps_published_state_workbooks"]
        if "senate_survey_archive" in seed:
            result["senate_survey_archive"] = seed["senate_survey_archive"]
    if "congressional_analytical_review" in seed:
        result["congressional_analytical_review"] = seed["congressional_analytical_review"]
    if "senate_legacy_review" in seed:
        from scripts.senate_legacy_bridge import exports as senate_exports
        artifacts.update(senate_exports(estimates["senate_legacy_handoff"]["result"]))
        result["senate_legacy_review"] = seed["senate_legacy_review"]
    if "senate_complete_review" in seed:
        from scripts.senate_complete_categories import exports as complete_senate_exports
        artifacts.update(complete_senate_exports(estimates["senate_complete_handoff"]["result"]))
        result["senate_complete_review"] = seed["senate_complete_review"]
    if "protected_official_house_review" in seed:
        result["protected_official_house_review"] = seed["protected_official_house_review"]
    return result


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


def numerical_runtime():
    return {"implementation": sys.implementation.name,
            "python_major_minor": list(sys.version_info[:2])}


def scientific_package(snapshot, source_packet, count_files, native_files, seed_inputs, compiled):
    members = {"inputs/snapshot.json": encoded(snapshot),
               "inputs/complete-source-results.zip": source_packet,
               "inputs/numerical-runtime.json": encoded(numerical_runtime())}
    for role, files in (("before-counts", count_files), ("before-native", native_files),
                        ("after-counts", compiled["counts"]), ("after-native", compiled["native"]),
                        ("model-queries", compiled["model_files"])):
        for name, body in files.items():
            members[("inputs/" if role.startswith("before-") else "queries/") + role + "/" + name] = body
    for name, body in seed_inputs.items():
        members["inputs/model-seed/" + relative(name)] = body
    if "historical_eac_county_facts" in compiled:
        members["inputs/historical-eac-county-facts.json.gz"] = compiled["historical_eac_county_facts"]
    if "cps_published_state_workbooks" in compiled:
        members["inputs/" + CPS_INPUT] = compiled["cps_published_state_workbooks"]
    if "senate_survey_archive" in compiled:
        members["inputs/" + SENATE_SURVEY_ARCHIVE] = compiled["senate_survey_archive"]
    if "nc_retained_original" in compiled:
        members["inputs/nc-retained-original.json"] = compiled["nc_retained_original"]
    if "oh_retained_original" in compiled:
        members["inputs/oh-retained-original.json"] = compiled["oh_retained_original"]
    if "ga_retained_original" in compiled:
        members["inputs/ga-retained-original.json"] = compiled["ga_retained_original"]
    if "retained_county_canvasses" in compiled:
        members["inputs/retained-county-canvasses.json"] = compiled["retained_county_canvasses"]
    if "tx_retained_history" in compiled:
        members["inputs/tx-retained-history.json"] = compiled["tx_retained_history"]
    if "md_retained_history" in compiled:
        members["inputs/" + MD_ARCHIVE_MEMBER] = compiled["md_retained_history"]
    if "retained_bulk_turnout" in compiled:
        members["inputs/" + retained_bulk_turnout.MEMBER] = compiled["retained_bulk_turnout"]
    if "release_review" in compiled:
        members["inputs/supported-release-review.json"] = encoded(compiled["release_review"])
    if "congressional_analytical_review" in compiled:
        from scripts.congressional_analytical_bridge import data_paths
        members["inputs/congressional-analytical-review.json"] = encoded(
            compiled["congressional_analytical_review"])
        reviewed_paths = data_paths(compiled["congressional_analytical_review"])
        if "official_house_precedence" in compiled["congressional_analytical_review"]:
            from scripts.congressional_split_blocks import DATA_PATHS as SPLIT_PATHS
            reviewed_paths = tuple(dict.fromkeys(reviewed_paths + SPLIT_PATHS))
        for name in reviewed_paths:
            members["inputs/reviewed-congressional-sources/" + name] = (ROOT / name).read_bytes()
        if "official_house_precedence" in compiled["congressional_analytical_review"]:
            name = "tests/fixtures/ri-official-congress.json"
            members["code/" + name] = (ROOT / name).read_bytes()
        if "native_official_house" in compiled["congressional_analytical_review"]:
            name = "tests/fixtures/virginia-federal-candidates.json"
            members["code/" + name] = (ROOT / name).read_bytes()
    if "senate_legacy_review" in compiled:
        from scripts.senate_legacy_bridge import DATA_PATHS as SENATE_PATHS
        members["inputs/senate-legacy-review.json"] = encoded(compiled["senate_legacy_review"])
        for name in SENATE_PATHS:
            members["inputs/reviewed-senate-sources/" + name] = (ROOT / name).read_bytes()
        for fixture in ("tests/fixtures/senate-legacy-alabama.json",
                        "tests/fixtures/senate-legacy-new-mexico.json"):
            members["code/" + fixture] = (ROOT / fixture).read_bytes()
    if "senate_complete_review" in compiled:
        from scripts.senate_complete_categories import DATA_PATHS as COMPLETE_SENATE_PATHS
        members["inputs/senate-complete-review.json"] = encoded(compiled["senate_complete_review"])
        for name in COMPLETE_SENATE_PATHS:
            members["inputs/reviewed-senate-sources/" + name] = (ROOT / name).read_bytes()
        name = "tests/fixtures/ri-official-senate.json"
        members["code/" + name] = (ROOT / name).read_bytes()
    if "protected_official_house_review" in compiled:
        from scripts.protected_official_house import DATA_PATHS as PROTECTED_PATHS
        members["inputs/protected-official-house-review.json"] = encoded(
            compiled["protected_official_house_review"])
        for name in PROTECTED_PATHS:
            members["inputs/reviewed-protected-house-sources/" + name] = (ROOT / name).read_bytes()
    for name in CODE_PATHS:
        members["code/scripts/" + name] = (ROOT / "scripts" / name).read_bytes()
    for name in ("test_automatic_runtime.py", "test_results_granular.py",
                 "test_automatic_estimates.py", "test_automatic_native_refresh.py",
                 "test_current_source_reconciliation.py", "test_supported_analytical_release.py",
                 "test_cps_published_state_tables.py",
                 "test_congressional_analytical_bridge.py", "test_congressional_baselines.py",
                 "test_congressional_candidate_identity.py",
                 "test_congressional_category_reconciliation.py",
                 "test_congressional_complete_categories.py",
                 "test_congressional_geography.py",
                 "test_congressional_split_blocks.py",
                 "test_official_house_precedence.py", "test_native_official_house.py",
                 "test_congressional_reference_identity.py",
                 "test_senate_legacy_bridge.py", "test_senate_complete_categories.py", "test_protected_official_house.py",
                 "test_protected_official_wyoming.py", "test_statewide_ballot_totals.py",
                 "test_results_congress.py", "test_ohio_retained_turnout.py", "test_retained_turnout.py"):
        path = ROOT / "tests" / name
        if path.is_file():
            members["code/tests/" + name] = path.read_bytes()
    members["code/reproduce.py"] = (
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0,str(Path(__file__).resolve().parent))\n"
        "from scripts.automatic_runtime import main\nmain()\n").encode()
    python_version = ".".join(map(str, sys.version_info[:2]))
    members["REPRODUCE.txt"] = (
        f"{sys.implementation.name} {python_version}; requests>=2.31 is an existing project dependency.\n"
        f"python{python_version} code/reproduce.py --replay-package . --output reproduced\n"
        "Use the producer's Python major/minor and implementation from inputs/numerical-runtime.json;\n"
        "floating-point summation differs between Python versions. No numerical tolerance is substituted.\n"
        "Recomputes the complete count/native/model numerical query sets from included\n"
        "public aggregate source facts and safe accepted priors. No source requests,\n"
        "private survey refits, new geographic joins or observed-history claims.\n").encode()
    if "inputs/" + CPS_INPUT in members:
        members["REPRODUCE.txt"] += (
            "\nThe published CPS tables require openpyxl==3.1.5 and xlrd>=2. The included original "
            "workbooks and source checksums reproduce the comprehensive state CSV.\n"
            f"PYTHONPATH=code python{python_version} -m scripts.cps_published_state_tables "
            f"inputs/{CPS_INPUT} reproduced-cps.csv\n"
        ).encode()
    if "queries/model-queries/release/house-boundary-changed-blocks.csv.gz" in members:
        members["REPRODUCE.txt"] += (
            "\nThe House boundary CSVs describe block assignments, not populations or votes. "
            "Blank district codes mean a block is missing from that edition; ZZ is a literal Census code. "
            "Split-block counts are source flags, separate from reviewed geometry decisions. "
            "The main replay regenerates all three tables from the included national Census files.\n"
        ).encode()
    if "inputs/reviewed-congressional-sources/data/results-intake/district-splits/20261118-01/review.json" in members:
        members["REPRODUCE.txt"] += (
            "\nSeparate split-geometry evidence reproduction uses the project's existing\n"
            "shapely>=2.0, pyshp>=2.3 and pyproj>=3.6 dependencies:\n"
            "PYTHONPATH=code python3 -m scripts.congressional_split_blocks "
            "--repository inputs/reviewed-congressional-sources "
            "--output reproduced-split-review.json\n"
            "cmp reproduced-split-review.json inputs/reviewed-congressional-sources/"
            "data/results-intake/district-splits/20261118-01/review.json\n"
            "Both complete original district ZIPs and the full Census block response are included.\n"
        ).encode()
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
    if "inputs/numerical-runtime.json" in manifest:
        expected_runtime = read(package / "inputs/numerical-runtime.json")
        if expected_runtime != numerical_runtime():
            raise ValueError(
                "Exact numerical replay requires the producer's Python implementation and major/minor: "
                + json.dumps(expected_runtime, sort_keys=True))
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
    if "inputs/supported-release-review.json" in manifest:
        seed["supported_release_review"] = read(package / "inputs/supported-release-review.json")
    if "inputs/historical-eac-county-facts.json.gz" in manifest:
        seed["historical_eac_county_facts"] = (package / "inputs/historical-eac-county-facts.json.gz").read_bytes()
    if "inputs/" + CPS_INPUT in manifest:
        seed["cps_published_state_workbooks"] = (package / "inputs" / CPS_INPUT).read_bytes()
    if "inputs/" + SENATE_SURVEY_ARCHIVE in manifest:
        seed["senate_survey_archive"] = (package / "inputs" / SENATE_SURVEY_ARCHIVE).read_bytes()
    if "inputs/nc-retained-original.json" in manifest:
        seed["nc_retained_original"] = (package / "inputs/nc-retained-original.json").read_bytes()
    if "inputs/oh-retained-original.json" in manifest:
        seed["oh_retained_original"] = (package / "inputs/oh-retained-original.json").read_bytes()
    if "inputs/ga-retained-original.json" in manifest:
        seed["ga_retained_original"] = (package / "inputs/ga-retained-original.json").read_bytes()
    if "inputs/retained-county-canvasses.json" in manifest:
        seed["retained_county_canvasses"] = (package / "inputs/retained-county-canvasses.json").read_bytes()
    if "inputs/tx-retained-history.json" in manifest:
        seed["tx_retained_history"] = (package / "inputs/tx-retained-history.json").read_bytes()
    if "inputs/" + MD_ARCHIVE_MEMBER in manifest:
        seed["md_retained_history"] = (package / "inputs" / MD_ARCHIVE_MEMBER).read_bytes()
    if "inputs/" + retained_bulk_turnout.MEMBER in manifest:
        seed["retained_bulk_turnout"] = (package / "inputs" / retained_bulk_turnout.MEMBER).read_bytes()
    boundary_source_root = None
    if "inputs/congressional-analytical-review.json" in manifest:
        seed["congressional_analytical_review"] = read(package / "inputs/congressional-analytical-review.json")
        boundaries = seed["congressional_analytical_review"].get("house_boundaries") or {}
        if boundaries:
            boundary_source_root = package / "inputs/reviewed-congressional-sources"
        if "split_geometry_review" in boundaries:
            from scripts.congressional_geography import load_review as load_boundaries
            if load_boundaries(package / "inputs/reviewed-congressional-sources") != boundaries:
                raise ValueError("Packaged House boundary review differs from its original evidence")
        if any(seed["congressional_analytical_review"].get(key) is not None
               for key in ("official_house_precedence", "native_official_house", "explicit_reference_names")):
            from scripts.congressional_analytical_bridge import load_review as load_analytical
            if load_analytical(package / "inputs/reviewed-congressional-sources",
                               include_split_geometry="split_geometry_review" in boundaries) != seed[
                    "congressional_analytical_review"]:
                raise ValueError("Packaged analytical extensions differ from their complete reviewed evidence")
    if "inputs/senate-legacy-review.json" in manifest:
        from scripts.senate_legacy_bridge import load_review as load_senate_review
        senate_review = load_senate_review(package / "inputs/reviewed-senate-sources")
        if senate_review != read(package / "inputs/senate-legacy-review.json"):
            raise ValueError("Packaged Senate review differs from its original scientific evidence")
        seed["senate_legacy_review"] = senate_review
    if "inputs/senate-complete-review.json" in manifest:
        from scripts.senate_complete_categories import load_review as load_complete_senate_review
        complete_review = load_complete_senate_review(package / "inputs/reviewed-senate-sources")
        if complete_review != read(package / "inputs/senate-complete-review.json"):
            raise ValueError("Packaged complete Senate review differs from its original evidence")
        seed["senate_complete_review"] = complete_review
    if "inputs/protected-official-house-review.json" in manifest:
        from scripts.protected_official_house import load_review as load_protected_review
        protected_review = load_protected_review(package / "inputs/reviewed-protected-house-sources", seed)
        if protected_review != read(package / "inputs/protected-official-house-review.json"):
            raise ValueError("Packaged protected official House review differs from its original evidence")
        seed["protected_official_house_review"] = protected_review
    source_packet = (package / "inputs/complete-source-results.zip").read_bytes()
    snapshot = hydrate_granular_sources(
        read(package / "inputs/snapshot.json"), source_packet)
    with offline() as attempts:
        compiled = compile_runtime(
            snapshot, files("before-counts"), files("before-native"), seed, source_packet,
            boundary_source_root=boundary_source_root)
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


def analytical_policy(root, *, split_block_geometry=False):
    from scripts.congressional_analytical_bridge import REVIEW_PATH, load_review
    return (load_review(root, include_split_geometry=split_block_geometry)
            if (Path(root) / REVIEW_PATH).exists() else None)


PENDING_RUNTIME = "automatic/pending-publication.json"


def activate_staged_runtime(publisher, staged, catalog, pending, repository):
    from scripts.automatic_estimates import bind_publication

    if publisher.remote_head() != staged:
        raise ValueError("Staged runtime was superseded; last-good version preserved")
    if pending["parent"] != publisher.parent_of(staged):
        raise ValueError("Staged runtime receipt does not belong to this commit")
    version = pending["manifest"]["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[a-f0-9]{64}", version):
        raise ValueError("Invalid staged runtime version")
    if pending["catalog"] != pin(encoded(catalog)):
        raise ValueError("Staged runtime no longer matches the active catalog")
    previous = publisher.git("show", staged + ":automatic/latest.json", check=False)
    if pending["previous"] != pin(encoded(json.loads(previous) if previous else None)):
        raise ValueError("Staged runtime no longer matches the rolling predecessor")
    model_prefix = f"automatic/versions/{version}/"
    base = f"https://raw.githubusercontent.com/{repository}/{staged}/{model_prefix}"
    candidate, checks = bind_datasets(catalog, pending["datasets"], staged, repository)
    if any(pending["files"].get(name, expected) != expected for name, expected in checks.items()):
        raise ValueError("Staged files do not match the dataset descriptors")
    publisher.verify_files(staged, {**checks, **pending["files"]})
    manifest = copy.deepcopy(pending["manifest"])
    download = manifest["complete_download"]
    manifest["counts"] = candidate["datasets"]["participation-counts-2026"]
    manifest["native"] = candidate["datasets"]["participation-native-bindings-2026"]
    manifest["house_sources"] = bind_publication(pending["estimates"], base, download)["house_sources"]
    if "congressional" in manifest:
        manifest["congressional"].update(base_url=base, complete_download=download)
    activation = {"catalog.json": encoded(candidate), "automatic/latest.json": encoded(manifest),
                  PENDING_RUNTIME: encoded(None)}
    promoted = publisher.commit(publisher.tree(staged, activation), staged,
                                "Atomically activate automatic counts and qualified estimates")
    publisher.promote(promoted, staged)
    publisher.verify_files(promoted, {name: pin(body) for name, body in activation.items()})
    return {"status": "published", "version": version, "data_commit": promoted,
            "staged_commit": staged, "website_builds_started": 0, "complete_download": download}


def run(repository, work, pointer_url=RESULTS_POINTER, seed_dir=None,
        github_repository=WEBSITE_REPOSITORY, publish=True, split_block_geometry=False):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    pointer = results_pointer(pointer_url)
    if publish:
        require_general_election_publication_time(pointer["checked_at"], year=2026, now=utc_now())
    publisher = GitPublisher(repository, github_repository=github_repository)
    parent = publisher.remote_head()
    publisher.fetch_parent(parent)
    catalog = publisher.catalog(parent)
    source_pin = pin(encoded(pointer))
    seed_dir = Path(seed_dir or ROOT / "data/results-intake/model-seed")
    review_path = ROOT / "data/results-intake/reviewed-eligibility.json"
    release_review = read(review_path) if review_path.exists() else None
    from scripts.congressional_analytical_bridge import data_paths
    analytical_review = analytical_policy(ROOT, split_block_geometry=split_block_geometry)
    from scripts.senate_legacy_bridge import (
        REVIEW_PATH as SENATE_REVIEW_PATH, DATA_PATHS as SENATE_PATHS, load_review as load_senate_review)
    senate_review = load_senate_review(ROOT) if (ROOT / SENATE_REVIEW_PATH).exists() else None
    from scripts.senate_complete_categories import (
        REVIEW_PATH as COMPLETE_SENATE_REVIEW_PATH, DATA_PATHS as COMPLETE_SENATE_PATHS,
        load_review as load_complete_senate_review)
    complete_senate_review = (load_complete_senate_review(ROOT)
                             if (ROOT / COMPLETE_SENATE_REVIEW_PATH).exists() else None)
    from scripts.protected_official_house import (
        REVIEW_PATH as PROTECTED_REVIEW_PATH, DATA_PATHS as PROTECTED_PATHS,
        load_review as load_protected_review)
    protected_review = load_protected_review(ROOT) if (ROOT / PROTECTED_REVIEW_PATH).exists() else None
    from scripts.eac_county_turnout import INPUT as EAC_INPUT
    from scripts.statewide_ballot_totals import GA_INPUT, NC_INPUT, OH_INPUT
    from scripts.results_county_frame import RETAINED_CANVASSES_INPUT
    from scripts.results_turnout_history import TX_ARCHIVE_INPUT
    eac_path = ROOT / EAC_INPUT
    eac_facts = eac_path.read_bytes() if eac_path.exists() else None
    cps_path = ROOT / CPS_INPUT_PATH
    cps_workbooks = cps_path.read_bytes() if cps_path.exists() else None
    senate_survey_path = ROOT / SENATE_SURVEY_INPUT
    senate_survey_archive = senate_survey_path.read_bytes() if senate_survey_path.exists() else None
    nc_path = ROOT / NC_INPUT
    nc_original = nc_path.read_bytes() if nc_path.exists() else None
    oh_path = ROOT / OH_INPUT
    oh_original = oh_path.read_bytes() if oh_path.exists() else None
    ga_path = ROOT / GA_INPUT
    ga_original = ga_path.read_bytes() if ga_path.exists() else None
    canvass_path = ROOT / RETAINED_CANVASSES_INPUT
    retained_canvasses = canvass_path.read_bytes() if canvass_path.exists() else None
    tx_path = ROOT / TX_ARCHIVE_INPUT
    tx_archive = tx_path.read_bytes() if tx_path.exists() else None
    md_path = ROOT / MD_ARCHIVE_INPUT
    md_archive = md_path.read_bytes() if md_path.exists() else None
    bulk_path = ROOT / retained_bulk_turnout.INPUT
    bulk_archive = bulk_path.read_bytes() if bulk_path.exists() else None
    processing = digest(encoded({
        "numerical_runtime": numerical_runtime(),
        "code": {name: pin((ROOT / "scripts" / name).read_bytes()) for name in CODE_PATHS},
        "seed": {name: pin(body) for name, body in seed_files(seed_dir).items()},
        "supported_release_review": pin(encoded(release_review)) if release_review else None,
        "historical_eac_counties": pin(eac_facts) if eac_facts is not None else None,
        "cps_published_state_workbooks": pin(cps_workbooks) if cps_workbooks is not None else None,
        "senate_survey_archive": pin(senate_survey_archive) if senate_survey_archive is not None else None,
        "nc_retained_original": pin(nc_original) if nc_original is not None else None,
        "oh_retained_original": pin(oh_original) if oh_original is not None else None,
        "ga_retained_original": pin(ga_original) if ga_original is not None else None,
        "retained_county_canvasses": pin(retained_canvasses) if retained_canvasses is not None else None,
        "tx_retained_history": pin(tx_archive) if tx_archive is not None else None,
        "md_retained_history": pin(md_archive) if md_archive is not None else None,
        "retained_bulk_turnout": pin(bulk_archive) if bulk_archive is not None else None,
        "congressional_analytical_review": {
            name: pin((ROOT / name).read_bytes()) for name in data_paths(analytical_review)
        } if analytical_review else None,
        "senate_legacy_review": {
            name: pin((ROOT / name).read_bytes()) for name in SENATE_PATHS
        } if senate_review else None,
        "senate_complete_review": {
            name: pin((ROOT / name).read_bytes()) for name in COMPLETE_SENATE_PATHS
        } if complete_senate_review else None,
        "protected_official_house_review": {
            name: pin((ROOT / name).read_bytes()) for name in PROTECTED_PATHS
        } if protected_review else None}))
    previous = publisher.git("show", parent + ":automatic/latest.json", check=False) if parent else ""
    if previous:
        previous = json.loads(previous)
        same_input = previous.get("input_results_version") == pointer["version"]
        prior_source_pin = previous.get("input_results_pointer")
        if same_input and prior_source_pin is not None and prior_source_pin != source_pin:
            raise ValueError("Accepted source version changed its immutable pointer")
        if (not same_input and result_time(pointer["checked_at"]) < result_time(previous["checked_at"])):
            raise ValueError("Source snapshot predates the active runtime; refusing rollback")
        if (same_input and prior_source_pin == source_pin
                and previous.get("processing_version") == processing
                and all(previous.get(field) == catalog["datasets"].get(identity)
                        for field, identity in (("counts", "participation-counts-2026"),
                                                ("native", "participation-native-bindings-2026")))):
            return {"status": "unchanged", "version": previous["version"],
                    "data_commit": parent, "website_builds_started": 0}
    pending = publisher.git("show", parent + ":" + PENDING_RUNTIME, check=False) if parent else ""
    staged_work = json.loads(pending) if pending else None
    if publish and staged_work is not None:
        staged_manifest = staged_work["manifest"]
        same_staged_input = staged_manifest["input_results_version"] == pointer["version"]
        if same_staged_input and staged_manifest["input_results_pointer"] != source_pin:
            raise ValueError("Staged source version changed its immutable pointer")
        if same_staged_input and staged_manifest["processing_version"] == processing:
            result = activate_staged_runtime(publisher, parent, catalog, staged_work, github_repository)
            write(work / "publication.json", result)
            return {**result, "resumed_staging": True}
        if result_time(staged_manifest["checked_at"]) > result_time(pointer["checked_at"]):
            raise ValueError("Source snapshot predates the staged runtime; refusing rollback")
    snapshot, source = result_bodies(pointer)
    count_description = catalog["datasets"]["participation-counts-2026"]
    native_description = catalog["datasets"]["participation-native-bindings-2026"]
    counts, native = dataset_files(count_description), dataset_files(native_description)
    seed, seed_inputs = select_seed(previous or None, seed_dir)
    if release_review is not None:
        seed["supported_release_review"] = release_review
    if eac_facts is not None:
        seed["historical_eac_county_facts"] = eac_facts
    if cps_workbooks is not None:
        seed["cps_published_state_workbooks"] = cps_workbooks
    if senate_survey_archive is not None:
        seed["senate_survey_archive"] = senate_survey_archive
    if nc_original is not None:
        seed["nc_retained_original"] = nc_original
    if oh_original is not None:
        seed["oh_retained_original"] = oh_original
    if ga_original is not None:
        seed["ga_retained_original"] = ga_original
    if retained_canvasses is not None:
        seed["retained_county_canvasses"] = retained_canvasses
    if tx_archive is not None:
        seed["tx_retained_history"] = tx_archive
    if md_archive is not None:
        seed["md_retained_history"] = md_archive
    if bulk_archive is not None:
        seed["retained_bulk_turnout"] = bulk_archive
    if analytical_review is not None:
        seed["congressional_analytical_review"] = analytical_review
    if senate_review is not None:
        seed["senate_legacy_review"] = senate_review
    if complete_senate_review is not None:
        seed["senate_complete_review"] = complete_senate_review
    if protected_review is not None:
        seed["protected_official_house_review"] = protected_review
    runtime_snapshot = hydrate_granular_sources(snapshot, source["complete-results.zip"])
    compiled = compile_runtime(
        runtime_snapshot, counts, native, seed, source["complete-results.zip"],
        boundary_source_root=ROOT if (analytical_review or {}).get("house_boundaries") else None)
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
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"})
        if replayed.returncode != 0:
            raise ValueError(f"Extracted replay exited {replayed.returncode}:\n"
                             + replayed.stderr.decode(errors="replace")[-4000:])
        proof = json.loads(replayed.stdout)
    if (proof.get("passed") is not True or proof.get("network_requests") != 0
            or proof.get("external_operations_blocked") is not True
            or proof.get("complete_outputs") != sum(len(compiled[name])
                for name in ("counts", "native", "model_files"))):
        raise ValueError("Fresh extracted replay did not verify every output offline")
    write(work / "report.json", {"version": version, "input_results_version": pointer["version"],
        "local_changes": compiled["local_changes"], "complete_download": pin(packet),
        "estimate_summary": compiled["estimates"].get("decisions", {}).get("summary"),
        "offline_replay": proof, "website_builds_started": 0, "source_models_refitted": False})
    if not publish:
        return {"status": "prepared_not_published", "version": version, "work_dir": str(work)}
    journal_path = work / ("publication-" + version + ".json")
    journal = read(journal_path) if journal_path.exists() else {"parent": parent, "version": version}
    if parent != journal["parent"]:
        raise ValueError("Active data advanced outside this publication; prepare against its new catalog")
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
    manifest = {"contract": CONTRACT, "version": version, "election_date": "2026-11-03",
        "processing_version": processing,
        "input_results_version": pointer["version"], "checked_at": pointer["checked_at"],
        "input_results_pointer": source_pin,
        "complete_download": download,
        "source_models_refitted": False, "geographic_joins_changed": False,
        "all_states_certified_or_precinct_complete": False}
    if "congressional" in compiled:
        manifest["congressional"] = compiled["congressional"]
    pending = {"manifest": manifest, "catalog": pin(encoded(catalog)), "parent": parent,
               "previous": pin(encoded(previous or None)), "datasets": descriptions,
               "files": {name: pin(body) for name, body in bodies.items()},
               "estimates": {key: compiled["estimates"][key] for key in ("contract", "house_sources")
                             if key in compiled["estimates"]}}
    bodies[PENDING_RUNTIME] = encoded(pending)
    staged = publisher.commit(publisher.tree(parent, bodies), parent,
                              "Stage automatic count and estimate successors")
    if publisher.remote_head() != parent:
        raise ValueError("Data branch advanced; last-good version preserved")
    publisher.promote(staged, parent)
    result = activate_staged_runtime(publisher, staged, catalog, pending, github_repository)
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
    parser.add_argument("--accept-reviewed-house-split-geometry", action="store_true",
                        help="Enable only after delivery of the compatible district reader")
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
                     args.github_repository, publish=not args.no_publish,
                     split_block_geometry=args.accept_reviewed_house_split_geometry)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
