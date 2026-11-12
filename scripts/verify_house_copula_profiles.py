"""Verify new current profiles, exact source margins, masks and complete simulations."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_norc_house_model import verify
from scripts.compare_house_model_families import FAMILIES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("profiles", "original-priors", "baseline-results", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    args = parser.parse_args()
    files = ("accepted_ridge_multinomial-priors.json", "histogram_gradient_boosting-priors.json",
             "extra_randomized_trees-priors.json")
    checks, independent_checks = 0, {}

    def equal(left, right):
        nonlocal checks
        assert left == right, "Profile changed an accepted source or mask"
        checks += 1

    def close(left, right, tolerance=1e-10):
        nonlocal checks
        assert math.isfinite(left) and math.isfinite(right) and abs(left-right) <= tolerance
        checks += 1

    def margins(table):
        return ([math.fsum(row) for row in table],
                [math.fsum(row[j] for row in table) for j in range(5)])

    def verify_margins(before, after):
        for a, b in zip(sum(margins(before), []), sum(margins(after), [])):
            close(a, b)

    for profile in ("attenuated", "full"):
        for family, filename in zip(FAMILIES, files):
            root = args.profiles/profile/family
            prior = json.loads((root/"synthetic-priors.json").read_bytes())
            original = json.loads((args.original_priors/filename).read_bytes())
            result = json.loads((root/"complete-result.json").read_bytes())
            baseline = json.loads((args.baseline_results/family/"complete-result.json").read_bytes())
            controls = {row["state_code"]: row for row in baseline["rows"]}
            proof_path = root/"independent-accounting-proof.json"
            pins = {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
                    for name in ("complete-result.json", "synthetic-priors.json")}
            if proof_path.exists():
                saved = json.loads(proof_path.read_bytes())
                equal(saved["pins"], pins)
                accounting_proof = saved["verification"]
            else:
                accounting_proof = verify(result, prior)
                proof_path.write_text(json.dumps(dict(pins=pins, verification=accounting_proof),
                                                indent=2, sort_keys=True)+"\n")
            independent_checks[profile+"|"+family] = accounting_proof["checks"]
            for field in ("source_input_sha256", "source_cases", "validation"):
                equal(prior[field], original[field])
            equal(set(prior["states"]), set(original["states"]))
            for code, state in prior["states"].items():
                old = original["states"][code]
                verify_margins(old["prior_joint"], state["prior_joint"])
                equal(state["direct_2022_house_prior_joint"], old["direct_2022_house_prior_joint"])
                equal(len(state["groups"]), len(old["groups"]))
                for before, after in zip(old["groups"], state["groups"]):
                    for field in ("dimension", "group", "label", "available"):
                        equal(before[field], after[field])
                    if before["available"]:
                        verify_margins(before["prior_joint"], after["prior_joint"])
                    else:
                        equal(before["prior_joint"], after["prior_joint"])
                for dimension in {group["dimension"] for group in state["groups"]}:
                    selected = [group["prior_joint"] for group in state["groups"]
                                if group["available"] and group["dimension"] == dimension]
                    for i in range(5):
                        for j in range(5):
                            close(math.fsum(table[i][j] for table in selected), state["prior_joint"][i][j])
            for row in result["rows"]:
                old = controls[row["state_code"]]
                equal(row["reported_comparison"], old["reported_comparison"])
                equal(row["source_comparison_available"], old["source_comparison_available"])
                equal(row["direct_recalled_2022_house_source_scenario"], old["direct_recalled_2022_house_source_scenario"])
                for field in ("previous_margin_pp", "current_margin_pp", "total_change_pp"):
                    close(row["point"][field], old["point"][field], 1e-8)
                if row["source_comparison_available"]:
                    close(row["assumed_accounting_frame_units"], old["assumed_accounting_frame_units"], .001)
            for field in ("summary", "source_input_sha256", "validation", "endpoint_update"):
                if field in baseline:
                    equal(result[field], baseline[field])
            close(result["preconditioning_margin_MAE_pp"], math.fsum(
                abs(row["before_current_party_conditioning"]["prediction_error_observed_minus_predicted_pp"])
                for row in result["rows"] if row["source_comparison_available"])/48, 1e-12)
            print(json.dumps(dict(profile=profile, family=family,
                                  independent_model_checks=independent_checks[profile+"|"+family])), flush=True)
    report = dict(status="pass", original_qualified_comparisons=48, source_model_profiles_verified=6,
        new_margin_mask_partition_direct2022_checks=checks, independent_model_checks=independent_checks,
        independent_model_check_total=sum(independent_checks.values()), source_fits_repeated=False,
        original_default_replaced=False, state_and_group_source_year_margins_preserved=True,
        current_party_return_errors_used_for_parameter_selection=False,
        historical_parameter_transport_validated=False,
        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
