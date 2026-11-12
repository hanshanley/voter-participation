"""Reproduce the all-state contest audit and recondition only incompatible endpoints."""

import argparse
import copy
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import compare_house_model_families as families
from scripts import house_comparability as comparability
from scripts import norc_house_model as simulation


def load(path):
    return json.loads(path.read_bytes())


def pin(path):
    body = path.read_bytes()
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(simulation.encoded(value))


def build(inputs, output):
    if output.exists():
        raise ValueError("Use a fresh output directory")
    manifest = load(inputs/"manifest.json")
    for name, expected in manifest.items():
        if pin(inputs/name) != expected:
            raise ValueError("Changed pinned sufficient input: "+name)
    if pin(inputs/"statistics2024.pdf")["sha256"] != (
            "d4ba800fc17135b616ae556c92861080ab962d95916ace34b546c5aac824aec4"):
        raise ValueError("Wrong pinned native Clerk PDF")
    current = list(csv.DictReader(io.StringIO(
        gzip.decompress((inputs/"district-candidate-totals.csv.gz").read_bytes()).decode())))
    review = comparability.audit(load(inputs/"native-house-facts.json"), current,
                                  load(inputs/"held-2026-House-controls.json"))
    write(output/"complete-audit.json", review)
    original_viewer = load(inputs/"viewer-original.json")
    all_results, all_rows = {}, []
    for profile in ("original", "attenuated", "full"):
        results = {}
        for family in families.FAMILIES:
            prefix = inputs/profile/family
            previous = load(prefix/"complete-result.json")
            priors = load(prefix/"synthetic-priors.json")
            print(json.dumps(dict(profile=profile, family=family,
                                  stage="requalifying_endpoints_without_source_refit")), flush=True)
            result = comparability.requalify_model(priors, previous, review)
            results[family] = result
            directory = output/profile/family
            directory.mkdir(parents=True)
            for name, body in simulation.result_files(result).items():
                (directory/name).write_bytes(body)
            changed = set(result["comparison_policy"]["changed_state_scenarios_recomputed"])
            for old in previous["rows"]:
                new = next(row for row in result["rows"] if row["state_code"] == old["state_code"])
                if old["state_code"] not in changed:
                    for field in ("joint", "point", "groups", "gross_outcomes", "sensitivity_ranges_pp",
                                  "before_current_party_conditioning", "assumed_accounting_frame_units"):
                        if new[field] != old[field]:
                            raise ValueError("Unchanged state numerics were not reused")
            for field in ("complete_assumption_cases", "complete_seed_cases", "complete_demographic_seed_cases"):
                old = [row for row in previous[field] if row["state_code"] not in changed]
                new = [row for row in result[field] if row["state_code"] not in changed]
                normalize = lambda rows: sorted(simulation.encoded(row) for row in rows)
                if normalize(old) != normalize(new):
                    raise ValueError("An unaffected complete query changed")
        viewer = copy.deepcopy(original_viewer if profile == "original" else load(inputs/f"viewer-{profile}.json"))
        viewer["families"] = {family: {key: value for key, value in result.items() if not key.startswith("complete_")}
                              for family, result in results.items()}
        viewer["state_comparisons"] = families.state_comparisons(results)
        viewer["family_dispersion"] = families.dispersion(results)
        coverage = {result["summary"]["return_anchored"] for result in results.values()}
        if len(coverage) != 1:
            raise ValueError("Family endpoint masks differ")
        viewer["summary"].update(qualified_comparisons_per_family=coverage.pop(),
            margin_MAE_pp={family: result["preconditioning_margin_MAE_pp"] for family, result in results.items()},
            Democratic_two_party_share_MAE_pp={family: result["preconditioning_margin_MAE_pp"]/2
                                               for family, result in results.items()},
            endpoint_policy_changed=True, return_error_population_changed_not_a_fit_improvement=True,
            source_models_refitted=False)
        viewer["summary"].pop("baseline_fits_or_simulations_repeated", None)
        viewer["summary"].update(affected_return_scenarios_recomputed=True,
                                 unchanged_baseline_simulations_repeated=False)
        viewer["comparison_policy"] = results[families.BASELINE]["comparison_policy"]
        write(output/f"viewer-{profile}.json", viewer)
        all_results[profile] = results
        all_rows.extend(dict(profile=profile, **row) for row in viewer["state_comparisons"])
    (output/"complete-profile-family-state-comparisons.csv").write_bytes(families.csv_bytes(all_rows))
    summary = dict(contract="participation.house_comparability_results.v1",
        audit_states=50, audit_districts=435, profiles=list(all_results), families=list(families.FAMILIES),
        policy_held_states=[row["state_code"] for row in review["states"]
                            if not row["like_for_like_statewide_source_comparison"]],
        model_qualified_states=all_results["original"][families.BASELINE]["summary"]["return_anchored"],
        current_counting_complete_independently_qualified=False,
        margin_errors={profile: {family: result["preconditioning_margin_MAE_pp"]
                                 for family, result in results.items()} for profile, results in all_results.items()},
        source_refits=0, source_acquisitions=0, native_counts_changed=False,
        previous_complete_queries_preserved_for_unaffected_states=True,
        return_error_population_changed_not_a_fit_improvement=True)
    write(output/"summary.json", summary)
    from scripts.verify_house_comparability import verify
    write(output/"independent-verification.json", verify(inputs, output))
    return summary


def prepare(args):
    inputs = args.packet/"inputs"
    if args.packet.exists():
        raise ValueError("Use a fresh complete packet")
    inputs.mkdir(parents=True)
    for source, name in ((args.facts, "native-house-facts.json"), (args.pdf, "statistics2024.pdf"),
                         (args.candidates, "district-candidate-totals.csv.gz"),
                         (args.controls, "held-2026-House-controls.json"),
                         (args.baseline_results/"viewer-data.json", "viewer-original.json")):
        shutil.copyfile(source, inputs/name)
    for profile in ("original", "attenuated", "full"):
        if profile != "original":
            shutil.copyfile(args.profiles/f"viewer-{profile}.json", inputs/f"viewer-{profile}.json")
        for family in families.FAMILIES:
            directory = inputs/profile/family
            directory.mkdir(parents=True)
            base = args.baseline_results/family if profile == "original" else args.profiles/profile/family
            shutil.copyfile(base/"complete-result.json", directory/"complete-result.json")
            priors = (args.baseline_priors/(family+"-priors.json") if profile == "original"
                      else base/"synthetic-priors.json")
            shutil.copyfile(priors, directory/"synthetic-priors.json")
            if profile != "original":
                shutil.copyfile(base/"source-projection-decisions.json", directory/"source-projection-decisions.json")
    write(inputs/"manifest.json", {str(path.relative_to(inputs)): pin(path)
                                   for path in sorted(inputs.rglob("*")) if path.is_file()})
    return inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--expected", type=Path)
    for name in ("facts", "pdf", "candidates", "controls", "baseline-priors", "baseline-results", "profiles"):
        parser.add_argument("--"+name, type=Path)
    args = parser.parse_args()
    if args.inputs:
        if args.packet.exists():
            raise ValueError("Use a fresh replay packet")
        args.packet.mkdir(parents=True)
        inputs = args.packet/"inputs"
        shutil.copytree(args.inputs, inputs)
        def blocked(*unused, **kwargs):
            raise RuntimeError("Network and external commands disabled for public reproduction")
        socket.socket = socket.create_connection = socket.getaddrinfo = blocked
        subprocess.Popen = subprocess.run = subprocess.check_output = blocked
    else:
        required = ("facts", "pdf", "candidates", "controls", "baseline_priors", "baseline_results", "profiles")
        if any(getattr(args, name) is None for name in required):
            parser.error("Preparing a packet requires every sufficient-input path")
        inputs = prepare(args)
    print(json.dumps(build(inputs, args.packet/"results"), sort_keys=True), flush=True)
    if args.expected:
        expected = [path for path in sorted(args.expected.rglob("*")) if path.is_file()]
        actual = [path for path in sorted((args.packet/"results").rglob("*")) if path.is_file()]
        if [path.relative_to(args.expected) for path in expected] != [
                path.relative_to(args.packet/"results") for path in actual]:
            raise ValueError("Replay output inventory differs")
        for path in expected:
            if path.read_bytes() != (args.packet/"results"/path.relative_to(args.expected)).read_bytes():
                raise ValueError("Replay output differs: "+str(path.relative_to(args.expected)))
        write(args.packet/"reproduction.json", dict(status="passed", byte_identical_outputs=len(expected),
            network_and_external_commands_blocked=True, source_refits=0, private_inputs_used=False))


if __name__ == "__main__":
    main()
