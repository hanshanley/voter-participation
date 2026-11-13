"""Run registered public participation sources without per-state importer routing."""

import argparse
import copy
import gzip
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import tempfile
from urllib.parse import urljoin

from scripts.participation_intake.adapters import field
from scripts.participation_intake.contract import IntakeError, STATES, digest, encoded, pin, validate_all
from scripts.participation_intake.engine import Store, run
from scripts.participation_intake.publisher import validate_dataset
from scripts.participation_batch_publish import publish_datasets
from scripts.package_historical_source_sets import build as package


IDENTITY_VIEW = ("county_id", "county", "unit_key", "unit", "precinct", "unit_kind",
    "county_fips", "geography_level", "reference_geometry", "maps_approved")


def local(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name:
        raise ValueError("Unsafe registered relative path")
    target = Path(root) / str(relative)
    if target.is_symlink() or not target.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("Registered input escapes its supplied root")
    return target


def compressed(value):
    body = bytearray(gzip.compress(encoded(value), compresslevel=9, mtime=0))
    body[9] = 3
    return bytes(body)


def baseline_files(root):
    description = validate_dataset(root)
    if description["record_contract"] != "participation.count_snapshot.v1":
        raise ValueError("This compiler requires the existing count snapshot contract")
    files = {name: local(root, name).read_bytes() for name in description["files"]}
    index = json.loads(files[description["index"]["file"]])
    if set(index["states"]) != set(STATES):
        raise ValueError("The baseline must retain all 50 states and DC")
    for declaration in index["states"].values():
        if description["files"].get(declaration["file"]) != {
                key: declaration[key] for key in ("bytes", "sha256")}:
            raise ValueError("State declaration differs from the accepted dataset")
    return description, files, index


def discover(spec, acquire):
    declaration = spec.get("discovery")
    if not declaration:
        return spec
    if not declaration["index"].get("redistribution_approved"):
        raise IntakeError("source_requires_review", "The declaration original needs a qualified complete-download policy")
    body, _ = acquire(declaration["index"], None)

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = set()

        def handle_starttag(self, tag, attributes):
            href = dict(attributes).get("href")
            if tag.lower() == "a" and href:
                url = urljoin(declaration["index"]["url"], href)
                if re.fullmatch(declaration["url_pattern"], url):
                    self.urls.add(url)

    parser = Links()
    parser.feed(body.decode(declaration.get("encoding", "utf-8")))
    if len(parser.urls) != 1:
        raise IntakeError("source_discovery", "Declared qualified product is missing or ambiguous")
    url = next(iter(parser.urls))
    if url not in declaration["approved_urls"]:
        raise IntakeError("source_requires_review", "Newly declared product needs scope review before ingestion")
    result = copy.deepcopy(spec)
    result["inputs"][declaration["input"]]["url"] = url
    return result


def display(row, spec):
    if "view" in row:
        return row
    binding = spec.get("view", {})
    identity = binding.get("identities", {}).get(row["geography"]["id"])
    if identity is None:
        raise IntakeError("view_binding", "New observations need explicit reviewed display identities")
    view = dict(binding.get("constants", {}), **identity)
    for name, path in binding.get("columns", {}).items():
        view[name] = field(row["source"]["fields"], path)
    denominator = row["denominator"]
    view.update(year=row["election"]["year"], state_code=row["geography"]["state_code"],
        ballots=row["count"]["value"], denominator=(denominator or {}).get("value"),
        reported_pct=(100 * row["count"]["value"] / denominator["value"]
            if denominator and denominator["qualified"] else None),
        source_url=row["source"]["url"], source_update_label=row["source_clock"]["literal"],
        source_update_timezone=row["source_clock"]["timezone"],
        source_status_literal=row["reporting_status"]["literal"], native_record=row["source"]["fields"],
        participation_measure_literal=row["measure"]["literal"], quality=row["quality"]["notes"])
    return dict(row, view=view)


def compile_counts(description, files, index, sources):
    changes, changed_rows = {}, 0
    candidate_index = copy.deepcopy(index)
    for code in sorted({source["spec"]["geography"]["state_code"] for source in sources}):
        declaration = candidate_index["states"][code]
        state = json.loads(gzip.decompress(files[declaration["file"]]))
        original = copy.deepcopy(state)
        for source in (item for item in sources if item["spec"]["geography"]["state_code"] == code):
            spec, rows = source["spec"], source["rows"]
            selected = set(source["baseline_source_ids"])
            old = [row for row in state["records"] if row["source"]["id"] in selected]
            key = lambda row: (row["geography"]["id"], row["measure"]["id"], row["measure"]["mode"])
            before, after = {key(row): row for row in old}, {key(row): row for row in rows}
            if not old or len(before) != len(old) or len(after) != len(rows) or before.keys() != after.keys():
                raise IntakeError("replacement_scope", "Changed source inventory requires a separately reviewed binding")
            replacements = {}
            for identity, previous in before.items():
                row = display(after[identity], spec)
                validate_all([row])
                if (row["election"] != previous["election"] or row["geography"] != previous["geography"]
                        or row["measure"] != previous["measure"]):
                    raise IntakeError("replacement_scope", "Routine updates cannot introduce election, measure or geographic joins")
                if any(row["view"].get(name) != previous["view"].get(name) for name in IDENTITY_VIEW):
                    raise IntakeError("replacement_scope", "Routine updates cannot change approved display identities")
                if row["view"]["ballots"] != row["count"]["value"]:
                    raise IntakeError("view_count", "Displayed and canonical count differ")
                replacements[previous["id"]] = row
                changed_rows += row != previous
            state["records"] = [replacements.get(row["id"], row) for row in state["records"]]
            for frame in state["views"].values():
                for partition in ("counties", "precincts", "nongeographic"):
                    frame[partition] = [replacements[identity]["id"] if identity in replacements else identity
                        for identity in frame[partition]]
        if state == original:
            continue
        by_id = {row["id"]: row for row in state["records"]}
        if len(by_id) != len(state["records"]):
            raise IntakeError("duplicate_observation", "Replacement duplicates an existing observation")
        for mode, frame in state["views"].items():
            for partition in ("counties", "precincts", "nongeographic"):
                selected_rows = [by_id[identity] for identity in frame[partition]]
                if any(row["geography"]["state_code"] != code for row in selected_rows):
                    raise IntakeError("replacement_scope", "Cross-state runtime selection")
                declaration["views"][mode]["dispositions"][partition].update(
                    reported=sum(row["count"]["status"] == "reported" for row in selected_rows),
                    unknown=sum(row["count"]["status"] == "unknown" for row in selected_rows),
                    withheld=sum(row["count"]["status"] == "withheld" for row in selected_rows),
                    qualified_fractions=sum(bool(row["denominator"] and row["denominator"]["qualified"])
                        for row in selected_rows))
        records = state["records"]
        candidate_index["coverage"][code].update(records=len(records),
            reported=sum(row["count"]["status"] == "reported" for row in records),
            zeros=sum(row["count"]["value"] == 0 for row in records),
            unknown=sum(row["count"]["status"] == "unknown" for row in records),
            withheld=sum(row["count"]["status"] == "withheld" for row in records),
            qualified_fractions=sum(bool(row["denominator"] and row["denominator"]["qualified"]) for row in records))
        changes[declaration["file"]] = compressed(state)
        declaration.update(pin(changes[declaration["file"]]))
    if not changes:
        return description, files, changed_rows
    changes["index.json"] = encoded(candidate_index)
    result = dict(files, **changes)
    pins = {name: pin(body) for name, body in sorted(result.items())}
    descriptor = dict(description, files=pins, index=dict(file="index.json", **pins["index.json"]),
        version=digest(encoded(dict(files=pins, contract=description["record_contract"]))),
        complete_download=None)
    return descriptor, result, changed_rows


def execute(registry, baseline, work, supplied_root=None, refresh=False, offline=False,
            website_repo=None, complete_download=None):
    registry, baseline, work = Path(registry), Path(baseline), Path(work)
    plan = json.loads(registry.read_bytes())
    if plan.get("contract") != "participation.routine_batch.v1":
        raise ValueError("Unknown routine registry contract")
    entries = plan["sources"]
    if len({entry["id"] for entry in entries}) != len(entries):
        raise ValueError("Duplicate registered source")
    if len({entry["spec"]["id"] for entry in entries}) != len(entries):
        raise ValueError("Duplicate source packet identity")
    selected_sources = set()
    for entry in entries:
        state = entry["spec"]["geography"]["state_code"]
        if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value)
                for value in (entry["id"], entry["spec"]["id"])):
            raise ValueError("Unsafe registered source identity")
        if entry["spec"].get("classification") != "public_aggregate":
            raise IntakeError("private_record_input", "Only reviewed public aggregate products enter a routine batch")
        if not entry["spec"].get("review_evidence"):
            raise IntakeError("unreviewed_source", "Every registered product needs explicit source/scope review evidence")
        if state not in STATES:
            raise ValueError("Unknown registered jurisdiction")
        for source in entry["baseline_source_ids"]:
            key = (state, source)
            if key in selected_sources:
                raise ValueError("Overlapping source replacement scopes")
            selected_sources.add(key)
    description, files, index = baseline_files(baseline)
    if plan.get("baseline_version") != description["version"]:
        raise ValueError("Registered baseline advanced; rebase rather than overwrite")
    store = None
    requests = 0

    def acquire(declaration, supplied):
        nonlocal store, requests
        if declaration.get("stopped"):
            raise IntakeError("source_stopped", "Registered access hold; source not requested")
        cached = None
        db = work / "intake/intake.sqlite3"
        if db.exists():
            connection = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
            cached = connection.execute("SELECT sha,stopped FROM inputs WHERE url=?",
                (declaration["url"],)).fetchone()
            connection.close()
        if cached and cached[1]:
            raise IntakeError("source_stopped", "Persisted access hold; no cached-source bypass")
        if supplied is not None and supplied.exists():
            body = supplied.read_bytes()
        else:
            if cached and cached[0] and not refresh:
                supplied = work / "intake/objects" / cached[0]
                body = supplied.read_bytes()
                if digest(body) != cached[0]:
                    raise IntakeError("cache_corruption", "Cached original changed")
            else:
                if offline:
                    raise IntakeError("offline_missing", "No held original for registered input")
                if store is None:
                    store = Store(work / "intake")
                requests += 1
                body, _ = store.acquire(declaration)
                supplied = store.object(body)
        if declaration.get("pin") and pin(body) != declaration["pin"]:
            raise IntakeError("source_integrity", "Registered immutable original changed")
        return body, supplied

    def finish(result, output, cached=False):
        returned = dict(result, no_op=cached, source_requests=requests,
            parsed_inputs=0 if cached else result["parsed_inputs"],
            compiled_rows=0 if cached else result["compiled_rows"], publication_attempts=0,
            directory=str(output))
        if website_repo is None or result["status"] == "held":
            return returned
        journal_path = work / "publication" / (recipe + ".json")
        if journal_path.exists():
            journal = json.loads(journal_path.read_bytes())
            expected_download = (complete_download or journal["complete_download"]) if result["changed_rows"] else description["complete_download"]
            if (journal["expected_versions"] != {description["id"]: description["version"]}
                    or journal["complete_download"] != expected_download):
                raise ValueError("Publication resume inputs changed")
            if journal.get("result"):
                return dict(returned, publication=journal["result"])
        root = output / "counts"
        if result["changed_rows"]:
            if complete_download is None:
                return dict(returned, status="awaiting_publication")
            if {key: complete_download[key] for key in ("bytes", "sha256")} != pin(
                    (output / "complete-analysis.zip").read_bytes()):
                raise IntakeError("incomplete_download", "Download does not bind this complete compiled batch")
            root = work / "publication" / recipe / "counts"
            for name in [*files, "dataset.json"]:
                target = local(root, name)
                expected_body = (output / "counts" / name).read_bytes()
                if name == "dataset.json":
                    descriptor = json.loads(expected_body)
                    descriptor["complete_download"] = complete_download
                    expected_body = encoded(descriptor)
                if target.exists() and target.read_bytes() != expected_body:
                    raise IntakeError("cache_corruption", "Publication staging changed")
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(expected_body)
            download = complete_download
        else:
            download = description["complete_download"]
        publication = publish_datasets(website_repo, [root],
            {description["id"]: description["version"]}, download, journal_path)
        return dict(returned, publication=publication, publication_attempts=1)

    prepared, dispositions = [], []
    try:
        for entry in entries:
            if entry.get("hold"):
                dispositions.append(dict(id=entry["id"], state_code=entry["spec"]["geography"]["state_code"],
                    status="held", reason=entry["hold"]))
                continue
            try:
                discovery_input = {}

                def acquire_index(declaration, unused):
                    supplied = local(supplied_root, entry["id"] + "/discovery-index") if supplied_root else None
                    body, path = acquire(declaration, supplied)
                    discovery_input.update(path=path, **pin(body))
                    return body, path

                spec = discover(entry["spec"], acquire_index)
                inputs = {}
                for name, declaration in spec["inputs"].items():
                    supplied = local(supplied_root, entry["id"] + "/" + name) if supplied_root else None
                    body, supplied = acquire(declaration, supplied)
                    inputs[name] = dict(path=supplied, **pin(body))
                prepared.append(dict(entry=entry, spec=spec, inputs=inputs, discovery_input=discovery_input))
            except IntakeError as error:
                dispositions.append(dict(id=entry["id"], state_code=entry["spec"]["geography"]["state_code"],
                    status="held", reason=error.as_dict()))
        code_paths = [Path(__file__), Path(__file__).with_name("participation_batch_publish.py"),
                Path(__file__).with_name("package_historical_source_sets.py"),
                Path(__file__).with_name("historical_precinct_rows.py"),
                *sorted((Path(__file__).parent / "participation_intake").glob("*.py"))]
        test = Path(__file__).parents[1] / "tests/test_participation_batch.py"
        if test.is_file():
            code_paths.append(test)
        code = {str(path.relative_to(Path(__file__).parents[1])): pin(path.read_bytes()) for path in code_paths}
        recipe = digest(encoded(dict(plan=plan, baseline=pin((baseline / "dataset.json").read_bytes()),
            inputs={item["entry"]["id"]: {name: {key: value[key] for key in ("bytes", "sha256")}
                for name, value in item["inputs"].items()} for item in prepared},
            discovery_inputs={item["entry"]["id"]: {key: item["discovery_input"][key]
                for key in ("bytes", "sha256")} for item in prepared if item["discovery_input"]},
            holds=dispositions, code=code)))
        output = work / "batches" / recipe
        if output.exists():
            manifest = json.loads((output / "manifest.json").read_bytes())
            for name, expected in manifest.items():
                if pin(local(output, name).read_bytes()) != expected:
                    raise IntakeError("cache_corruption", "Previously verified batch output changed: " + name)
            result = json.loads((output / "result.json").read_bytes())
            return finish(result, output, cached=True)
        if store is None:
            store = Store(work / "intake")
        sources, parsed = [], 0
        for item in prepared:
            outcome = run(item["spec"], store,
                supplied={name: value["path"] for name, value in item["inputs"].items()},
                references=item["entry"].get("references", {}))
            if outcome["status"] == "rejected":
                item["quarantined"] = outcome.get("raw_inputs_quarantined_not_packaged", False)
                dispositions.append(dict(id=item["entry"]["id"], state_code=item["spec"]["geography"]["state_code"],
                    status="held", reason=outcome["errors"]))
                continue
            native_inputs = [(item["spec"]["inputs"][name]["url"], value)
                for name, value in item["inputs"].items()]
            if item["discovery_input"]:
                value = item["discovery_input"]
                store.object(value["path"].read_bytes())
                native_inputs.append((item["spec"]["discovery"]["index"]["url"], value))
            for url, value in native_inputs:
                store.db.execute("INSERT INTO inputs VALUES(?,?,?,?,NULL) ON CONFLICT(url) DO UPDATE SET "
                    "etag=CASE WHEN inputs.sha=excluded.sha THEN inputs.etag ELSE NULL END,"
                    "modified=CASE WHEN inputs.sha=excluded.sha THEN inputs.modified ELSE NULL END,sha=excluded.sha",
                    (url, value["sha256"], None, None))
            store.db.commit()
            rows = json.loads((Path(outcome["directory"]) / "queries.json").read_bytes())
            sources.append(dict(spec=item["spec"], rows=rows,
                baseline_source_ids=item["entry"]["baseline_source_ids"], outcome=outcome))
            parsed += outcome["parsed_inputs"]
            dispositions.append(dict(id=item["entry"]["id"], state_code=item["spec"]["geography"]["state_code"],
                status="verified", observations=len(rows), unknown=sum(row["count"]["status"] == "unknown" for row in rows),
                zeros=sum(row["count"]["value"] == 0 for row in rows)))
        descriptor, runtime, changed = compile_counts(description, files, index, sources)
        staging = work / "staging"
        staging.mkdir(parents=True, exist_ok=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=staging) as temporary:
            stage = Path(temporary)
            for name, body in runtime.items():
                target = local(stage / "counts", name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
            (stage / "counts/dataset.json").write_bytes(encoded(descriptor))
            coverage = [dict(state_code=state, baseline_observations=index["states"][state]["records"],
                registered_sources=[row for row in dispositions if row["state_code"] == state],
                baseline_retained=True, new_geographic_qualification=False) for state in STATES]
            (stage / "all-51-jurisdictions.json").write_bytes(encoded(coverage))
            (stage / "complete-source-dispositions.json").write_bytes(encoded(dispositions))
            result = dict(status="held" if any(row["status"] == "held" for row in dispositions)
                else "changed" if changed else "unchanged",
                recipe=recipe, no_op=False, source_requests=requests, parsed_inputs=parsed,
                compiled_rows=sum(len(source["rows"]) for source in sources), changed_rows=changed,
                jurisdictions=51, candidate_version=descriptor["version"],
                baseline_version=description["version"], publication_attempts=0,
                website_builds_started=0, complete_selected_source_queries=True)
            (stage / "result.json").write_bytes(encoded(result))
            members = {"originals/registry.json": registry, "originals/baseline/dataset.json": baseline / "dataset.json"}
            members.update({"originals/baseline/" + name: local(baseline, name) for name in files})
            for item in prepared:
                if item.get("quarantined"):
                    continue
                if item["discovery_input"]:
                    members["originals/supplied/" + item["entry"]["id"] + "/discovery-index"] = (
                        item["discovery_input"]["path"])
                members.update({"originals/supplied/" + item["entry"]["id"] + "/" + name: value["path"]
                    for name, value in item["inputs"].items()})
            for source in sources:
                members["originals/source-packets/" + source["spec"]["id"] + ".zip"] = (
                    Path(source["outcome"]["directory"]) / "complete-analysis.zip")
            for path in stage.rglob("*"):
                if path.is_file():
                    members["queries/" + str(path.relative_to(stage))] = path
            for path in (Path(__file__), Path(__file__).with_name("participation_batch_publish.py"),
                    Path(__file__).with_name("package_historical_source_sets.py"),
                    Path(__file__).with_name("historical_precinct_rows.py"),
                    *sorted((Path(__file__).parent / "participation_intake").glob("*.py"))):
                members["code/scripts/" + str(path.relative_to(Path(__file__).parent))] = path
            test = Path(__file__).parents[1] / "tests/test_participation_batch.py"
            if test.is_file():
                members["code/tests/" + test.name] = test
            package(stage / "complete-analysis.zip", members,
                "From code/: python -m scripts.participation_batch --registry ../originals/registry.json "
                "--baseline ../originals/baseline --supplied-root ../originals/supplied --work-dir ../replayed --offline\n"
                "Compare queries/counts and complete source/jurisdiction queries. Sources and modes remain separate.\n"
                "Whole source packets retain their own exact extraction code. No new boundary or turnout qualification.\n")
            (stage / "manifest.json").write_bytes(encoded({str(path.relative_to(stage)): pin(path.read_bytes())
                for path in stage.rglob("*") if path.is_file()}))
            stage.rename(output)
        return finish(result, output)
    finally:
        if store is not None:
            store.db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--supplied-root", type=Path)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--website-repo", type=Path)
    parser.add_argument("--complete-download", type=Path)
    args = parser.parse_args()
    result = execute(args.registry, args.baseline, args.work_dir, args.supplied_root,
        args.refresh, args.offline, args.website_repo,
        json.loads(args.complete_download.read_bytes()) if args.complete_download else None)
    print(json.dumps(result, sort_keys=True))
    return 2 if result["status"] == "held" else 0


if __name__ == "__main__":
    raise SystemExit(main())
