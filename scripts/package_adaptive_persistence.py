"""Package the entire cached-input adaptive-persistence experiment and its predecessor."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile


PREDECESSOR_SHA256 = "422d14209bc6be35919e95a5b69aee6af58e9721c095453bf343139f59f883a2"
PREDECESSOR_URL = ("https://github.com/hanshanley/margin_of_error/releases/download/"
    "participation-transition-simulation-20261111-01/complete-analysis.zip")


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def csv_bytes(rows):
    rows = list(rows)
    if not rows:
        raise ValueError("A complete query cannot silently become an empty table")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value, sort_keys=True, separators=(",", ":"))
            if isinstance(value, (dict, list)) else value for key, value in row.items()})
    return output.getvalue().encode()


def query_members(result):
    predictions = [dict((key, value) for key, value in row.items() if key != "analytic")
        for row in result["complete_heldout_predictions"]]
    for row, original in zip(predictions, result["complete_heldout_predictions"]):
        row.update(original["analytic"])
    folds = [dict(block_type=row["block_type"], block=row["block"], model=row["model"],
        heldout_states=row["heldout_states"], **row["fit"]) for row in result["complete_outer_folds"]]
    metrics = [dict(block_type=kind, model=name, **values)
        for kind, models in result["metrics"].items() for name, values in models.items()]
    coverage = [dict(block_type=kind, model=name, **values)
        for kind, models in result["feature_and_factor_coverage"].items() for name, values in models.items()]
    return {
        "queries/complete-heldout-predictions.csv": csv_bytes(predictions),
        "queries/complete-feature-availability.csv": csv_bytes(result["complete_feature_availability"]),
        "queries/complete-benchmark-decisions.csv": csv_bytes(result["complete_benchmark_decisions"]),
        "queries/complete-outer-fold-selections.csv": csv_bytes(folds),
        "queries/complete-metrics.csv": csv_bytes(metrics),
        "queries/complete-factor-coverage.csv": csv_bytes(coverage),
        "metrics.json": json_bytes(result["metrics"]),
        "factor-coverage.json": json_bytes(result["feature_and_factor_coverage"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("result", "predecessor-archive", "verification", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    spec_root = root / "data/participation-model-validation/20261111-adaptive-persistence"
    result_body, predecessor = args.result.read_bytes(), args.predecessor_archive.read_bytes()
    result = json.loads(result_body)
    proof = json.loads(args.verification.read_bytes())
    if proof["status"] != "passed_independent_adaptive_persistence_verification":
        raise ValueError("Independent numerical verification is required")
    if hashlib.sha256(predecessor).hexdigest() != PREDECESSOR_SHA256:
        raise ValueError("The complete accepted predecessor packet differs")
    with zipfile.ZipFile(io.BytesIO(predecessor)) as archive:
        simulation_body = archive.read("complete-scenarios.json")
    spec_body = (spec_root / "spec.json").read_bytes()
    if result["input_sha256"] != dict(simulation=hashlib.sha256(simulation_body).hexdigest(),
            specification=hashlib.sha256(spec_body).hexdigest()):
        raise ValueError("Complete experiment inputs differ")
    region_body = (spec_root / "census-regions.pdf").read_bytes()
    region_source = json.loads((spec_root / "region-source.json").read_bytes())
    if len(region_body) != region_source["bytes"] \
            or hashlib.sha256(region_body).hexdigest() != region_source["sha256"] \
            or region_source["url"] != result["specification"]["region_source_url"]:
        raise ValueError("Complete official region reference differs")
    from verify_adaptive_persistence import verify

    if verify(json.loads(simulation_body), result, json.loads(spec_body)) != proof:
        raise ValueError("Independent receipt does not qualify this result")
    members = {
        "inputs/accepted-simulation-complete.zip": predecessor,
        "inputs/spec.json": spec_body,
        "inputs/census-regions.pdf": region_body,
        "inputs/region-source.json": (spec_root / "region-source.json").read_bytes(),
        "complete-results.json": result_body,
        "independent-verification.json": args.verification.read_bytes(),
        **query_members(result),
    }
    for name in ("docs/TRANSITION_SIMULATION.md", "scripts/adaptive_persistence.py",
            "scripts/verify_adaptive_persistence.py", "scripts/package_adaptive_persistence.py",
            "scripts/reproduce_adaptive_persistence.py", "tests/test_adaptive_persistence.py"):
        members[name] = (root / name).read_bytes()
    members["source-provenance.json"] = json_bytes(dict(
        predecessor=dict(url=PREDECESSOR_URL, bytes=len(predecessor), sha256=PREDECESSOR_SHA256),
        inputs=result["input_sha256"], region_reference=region_source,
        accepted_entropy_fits_or_seed_draws_repeated=False, live_model_changed=False))
    members["requirements-adaptive.txt"] = b"Python >=3.9; standard library only. No NumPy or model refitting dependencies.\n"
    members["README.txt"] = (
        "Complete adaptive-persistence negative-result experiment.\n"
        "All 215 outer folds, 550 predictions, every inner fit/tuning decision,\n"
        "feature/benchmark hold, original sufficient inputs and code are included.\n"
        "The entire immutable predecessor packet is in inputs/, not just its manifest.\n"
        "No original entropy fitting or seed simulation is repeated by this experiment.\n"
        "The age+rurality candidate does not improve the held-out baseline; no UI promotion.\n"
        "See docs/TRANSITION_SIMULATION.md for scope, metrics and nonidentification limits.\n"
        "Reproduce: python scripts/reproduce_adaptive_persistence.py "
        "--archive complete-analysis.zip --output reproduction.json\n"
    ).encode()
    manifest = {name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
        for name, body in sorted(members.items())}
    members["manifest.json"] = json_bytes(manifest)
    args.output.mkdir(parents=True, exist_ok=False)
    packet = args.output / "complete-analysis.zip"
    with zipfile.ZipFile(packet, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, body)
    assets = {"complete-analysis.zip": dict(bytes=packet.stat().st_size,
        sha256=hashlib.sha256(packet.read_bytes()).hexdigest())}
    for name in ("complete-results.json", "independent-verification.json", "metrics.json",
            "factor-coverage.json", "queries/complete-heldout-predictions.csv",
            "queries/complete-feature-availability.csv", "queries/complete-benchmark-decisions.csv",
            "queries/complete-outer-fold-selections.csv"):
        filename = Path(name).name
        (args.output / filename).write_bytes(members[name])
        assets[filename] = manifest[name]
    (args.output / "checksums.json").write_bytes(json_bytes(assets))
    print(json.dumps(dict(status="complete_adaptive_persistence_scientific_packet",
        archive_members=len(members), assets=assets), sort_keys=True))


if __name__ == "__main__":
    main()
