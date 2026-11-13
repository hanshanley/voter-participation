"""Reproduce the official endpoint successor using complete public sufficient inputs."""

import argparse
import copy
import csv
import gzip
import io
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import compare_house_model_families as families
from scripts import house_comparability as comparability
from scripts import house_official_sources as official
from scripts import norc_house_model as simulation
from scripts import official_house_successor as successor
from scripts.native_products import encoded, pin, query
from scripts.native_reconciliation import reconcile

PROFILES = ("original", "attenuated", "full")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))


def replay_native(inputs, output):
    recipe = json.loads((inputs / "native/recipe.json").read_bytes())
    compiled = json.loads((inputs / "native/manifest.json").read_bytes())
    if compiled["recipe_pin"] != pin(encoded(recipe)):
        raise ValueError("The native compilation recipe changed")
    queries = {}
    for spec in recipe["products"]:
        name = spec["id"] + ".factual-tables.json.gz"
        body = (inputs / "native" / name).read_bytes()
        if pin(body) != compiled["outputs"][name]:
            raise ValueError("Changed complete factual tables")
        product = json.loads(gzip.decompress(body))
        if product["source"]["pin"] != spec["pin"] or product["source"]["url"] != spec["url"]:
            raise ValueError("Factual source lineage differs")
        for selection in recipe["queries"]:
            if selection["product"] == spec["id"]:
                queries[selection["id"]] = query(product, selection)
    body = encoded(dict(contract="participation.native_queries.v1", queries=queries))
    expected = (inputs / "native/complete-queries.json").read_bytes()
    if body != expected or pin(body) != compiled["outputs"]["complete-queries.json"]:
        raise ValueError("Full factual-grid query replay differs")
    checks_body = (inputs / "native/checks.json").read_bytes()
    checks = json.loads(checks_body)["checks"]
    review = reconcile(queries, checks)
    if not review["required_checks_passed"]:
        raise ValueError("Replayed required source checks failed")
    review["input_pins"] = dict(queries=pin(body), checks=pin(checks_body))
    if encoded(review) != (inputs / "native/reconciliation.json").read_bytes():
        raise ValueError("Complete reconciliation replay differs")
    write(output / "native-complete-queries.json", json.loads(body))
    write(output / "native-reconciliation.json", review)
    return body


def build(inputs, output):
    if output.exists():
        raise ValueError("Use a fresh output directory")
    manifest = json.loads((inputs / "manifest.json").read_bytes())
    for name, expected in manifest.items():
        if pin((inputs / name).read_bytes()) != expected:
            raise ValueError("Changed pinned public sufficient input: " + name)
    if official.CATALOG.read_bytes() != (inputs / "native/house-source-review.json").read_bytes():
        raise ValueError("Runtime and sufficient-input official review catalogs differ")
    queries_body = replay_native(inputs, output)
    with zipfile.ZipFile(inputs / "predecessor-complete-analysis.zip") as previous:
        load = lambda name: json.loads(previous.read(name))
        candidates = list(csv.DictReader(io.StringIO(gzip.decompress(
            previous.read("inputs/district-candidate-totals.csv.gz")).decode())))
        revised = official.replace_current(candidates, queries_body)
        controls = successor.controls(load("inputs/held-2026-House-controls.json"), revised, queries_body)
        review = comparability.audit(load("inputs/native-house-facts.json"), revised, controls, queries_body)
        write(output / "complete-audit.json", review)
        write(output / "current-candidate-queries.json", revised)
        write(output / "current-House-controls.json", controls)
        all_results, all_rows = {}, []
        for profile in PROFILES:
            results = {}
            for family in families.FAMILIES:
                print(json.dumps(dict(profile=profile, family=family,
                    stage="reconditioning_changed_official_endpoints_without_source_refit")), flush=True)
                priors = load(f"inputs/{profile}/{family}/synthetic-priors.json")
                prior = load(f"results/{profile}/{family}/complete-result.json")
                result = successor.build(priors, prior, review)
                changed = set(result["endpoint_update"]["changed_states"])
                if changed != {"HI", "WY"}:
                    raise ValueError("Only the reviewed changed state counts may be reconditioned")
                for field in ("rows", "complete_assumption_cases", "complete_seed_cases",
                              "complete_demographic_seed_cases"):
                    normalize = lambda values: sorted(encoded(row) for row in values if row["state_code"] not in changed)
                    if normalize(result[field]) != normalize(prior[field]):
                        raise ValueError("An unaffected complete state/query changed")
                directory = output / profile / family
                directory.mkdir(parents=True)
                for name, body in simulation.result_files(result).items():
                    (directory / name).write_bytes(body)
                results[family] = result
            viewer = copy.deepcopy(load(f"results/viewer-{profile}.json"))
            viewer["families"] = {family: {key: value for key, value in result.items()
                if not key.startswith("complete_")} for family, result in results.items()}
            viewer["state_comparisons"] = families.state_comparisons(results)
            viewer["family_dispersion"] = families.dispersion(results)
            viewer["summary"].update(source_models_refitted=False,
                changed_official_source_states=["HI", "WY"], source_weights_changed=False,
                margin_MAE_pp={family: result["preconditioning_margin_MAE_pp"]
                    for family, result in results.items()},
                Democratic_two_party_share_MAE_pp={family: result["preconditioning_margin_MAE_pp"] / 2
                    for family, result in results.items()},
                return_error_change_is_not_independent_model_fit_improvement=True)
            viewer["comparison_policy"] = results[families.BASELINE]["comparison_policy"]
            viewer["official_source_revisions"] = review["reviewed_official_source_revisions"]
            write(output / f"viewer-{profile}.json", viewer)
            all_results[profile] = results
            all_rows.extend(dict(profile=profile, **row) for row in viewer["state_comparisons"])
        (output / "complete-profile-family-state-comparisons.csv").write_bytes(families.csv_bytes(all_rows))
        summary = dict(contract="participation.official_house_successor.v1",
            profiles=list(PROFILES), families=list(families.FAMILIES),
            states=50, districts=435, changed_states=["HI", "WY"], source_refits=0,
            survey_weight_changes=0, source_acquisitions=0, source_count_repairs=0,
            qualified_states=all_results["original"][families.BASELINE]["summary"]["return_anchored"],
            unchanged_state_count=48, full_unchanged_state_and_seed_queries_reused=True,
            native_replay="Complete public factual grids; original workbook templates remain local.",
            official_source_revisions=review["reviewed_official_source_revisions"],
            current_candidate_scope_not_all_ballots_or_observed_histories=True)
        write(output / "summary.json", summary)
    return summary


def prepare(predecessor, native, packet):
    if packet.exists():
        raise ValueError("Use a fresh complete packet")
    inputs = packet / "inputs"
    (inputs / "native").mkdir(parents=True)
    shutil.copyfile(predecessor, inputs / "predecessor-complete-analysis.zip")
    source = Path(__file__).resolve().parents[1] / "data/official-native-products"
    for name in ("manifest.json", "complete-queries.json", "reconciliation.json",
                 "independent-verification.json", "pdf-controls-verification.json",
                 "hi-summary.factual-tables.json.gz", "hi-precinct.factual-tables.json.gz",
                 "wy-workbooks.factual-tables.json.gz"):
        shutil.copyfile(native / name, inputs / "native" / name)
    for name, target in (("20261113-hi-wy.json", "recipe.json"),
                         ("20261113-hi-wy-checks.json", "checks.json"),
                         ("20261113-hi-wy-house.json", "house-source-review.json")):
        shutil.copyfile(source / name, inputs / "native" / target)
    write(inputs / "manifest.json", {str(path.relative_to(inputs)): pin(path.read_bytes())
        for path in sorted(inputs.rglob("*")) if path.is_file()})
    return inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predecessor", type=Path)
    parser.add_argument("--native", type=Path)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--expected", type=Path)
    args = parser.parse_args()
    if args.inputs:
        if args.packet.exists():
            raise ValueError("Use a fresh replay directory")
        inputs = args.packet / "inputs"
        inputs.parent.mkdir(parents=True)
        shutil.copytree(args.inputs, inputs)
    else:
        if not args.predecessor or not args.native:
            parser.error("Preparation requires --predecessor and --native")
        inputs = prepare(args.predecessor, args.native, args.packet)
    def blocked(*unused, **kwargs):
        raise RuntimeError("Network and external commands disabled for complete public reproduction")
    socket.socket = socket.create_connection = socket.getaddrinfo = blocked
    subprocess.Popen = subprocess.run = subprocess.check_output = blocked
    result = build(inputs, args.packet / "results")
    if args.expected:
        expected = {str(path.relative_to(args.expected)): pin(path.read_bytes())
            for path in args.expected.rglob("*") if path.is_file()}
        actual = {str(path.relative_to(args.packet / "results")): pin(path.read_bytes())
            for path in (args.packet / "results").rglob("*") if path.is_file()}
        if actual != expected:
            raise ValueError("Complete offline result inventory or bytes differ")
        write(args.packet / "reproduction.json", dict(status="passed",
            byte_identical_outputs=len(expected), network_and_external_commands_blocked=True,
            private_survey_inputs_used=False, source_refits=0))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
