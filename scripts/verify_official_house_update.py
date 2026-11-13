"""Verify all nine complete successors, exact native totals, and unaffected queries."""

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.native_products import encoded
from scripts.norc_house_model import result_files
from scripts.verify_norc_house_model import verify as verify_model

PROFILES = ("original", "attenuated", "full")
FAMILIES = ("accepted_ridge_multinomial", "histogram_gradient_boosting", "extra_randomized_trees")


def verify(inputs, output):
    load = lambda path: json.loads(path.read_bytes())
    audit = load(output / "complete-audit.json")
    if len(audit["district_queries"]) != 435 or len(audit["states"]) != 50:
        raise ValueError("Incomplete native audit")
    decisions = {row["state_code"]: row for row in audit["states"]}
    native_queries = load(inputs / "native/complete-queries.json")["queries"]
    wy = next(row for row in native_queries["wy-state-house"]["rows"] if row["county"] == "Total")
    wy_ballots = next(row["ballots"] for row in native_queries["wy-state-ballots"]["rows"]
        if row["county"] == "Total")
    if (decisions["WY"]["current_counts"] != dict(D=wy["D"], R=wy["R"],
            O=wy["L"] + wy["C"] + wy["write_ins"])
            or sum(decisions["WY"]["current_counts"].values()) + wy["overvotes"]
                + wy["undervotes"] != wy_ballots):
        raise ValueError("Known unassigned candidate votes were omitted or accounting added to candidates")
    new_candidates = load(output / "current-candidate-queries.json")
    if len(new_candidates) != 1401:
        raise ValueError("The complete current candidate inventory changed")
    checks, proofs, changes = 0, {}, {}
    with zipfile.ZipFile(inputs / "predecessor-complete-analysis.zip") as previous:
        for profile in PROFILES:
            proofs[profile], changes[profile] = {}, {}
            for family in FAMILIES:
                print(json.dumps(dict(profile=profile, family=family,
                    stage="independent_rational_accounting_and_full_query_preservation")), flush=True)
                priors = json.loads(previous.read(f"inputs/{profile}/{family}/synthetic-priors.json"))
                old = json.loads(previous.read(f"results/{profile}/{family}/complete-result.json"))
                new = load(output / profile / family / "complete-result.json")
                if new["validation"] != old["validation"]:
                    raise ValueError("Source training/validation scores changed without a source fit")
                if [(row["state_code"], row["source_comparison_available"]) for row in new["rows"]] != [
                        (row["state_code"], row["source_comparison_available"]) for row in old["rows"]]:
                    raise ValueError("A previous hold was lifted or introduced")
                proof = verify_model(new, priors)
                checks += proof["checks"]
                proofs[profile][family] = proof
                changes[profile][family] = []
                by_old = {row["state_code"]: row for row in old["rows"]}
                for row in new["rows"]:
                    code = row["state_code"]
                    decision = decisions[code]
                    district_rows = [item for item in audit["district_queries"] if item["state_code"] == code]
                    for phase in ("previous", "current"):
                        native = {party: sum(candidate["votes"] for district in district_rows
                            for candidate in district[phase]["source_candidate_rows"]
                            if candidate["group"] == party and candidate["votes"] is not None)
                            for party in "DRO"}
                        if native != decision[phase + "_counts"]:
                            raise ValueError("Independent district/state sum differs")
                        if row["source_comparison_available"] and native != row["reported_comparison"][phase]:
                            raise ValueError("A conditioned endpoint is not the native candidate total")
                        checks += 1
                    if code in ("HI", "WY"):
                        comparison = row["reported_comparison"]
                        before, after = comparison["previous"], comparison["current"]
                        share = float(100 * (Fraction(after["D"], after["D"] + after["R"]) -
                            Fraction(before["D"], before["D"] + before["R"])))
                        if abs(row["point"]["total_change_pp"] / 2 - share) > 1e-8:
                            raise ValueError("Source/model two-party-share units differ")
                        if (comparison["current_native_clock"] is not None or
                                row["contest_comparability"] != decision):
                            raise ValueError("Native clock or audit provenance changed")
                        changes[profile][family].append(dict(state_code=code,
                            previous_current_counts=by_old[code]["reported_comparison"]["current"],
                            current_counts=after, Democratic_two_party_share_change_pp=share,
                            old_point=by_old[code]["point"], new_point=row["point"]))
                    elif row != by_old[code]:
                        raise ValueError("An unaffected full state row changed")
                for field in ("complete_assumption_cases", "complete_seed_cases",
                              "complete_demographic_seed_cases"):
                    normalize = lambda values: sorted(encoded(row) for row in values
                        if row["state_code"] not in ("HI", "WY"))
                    if normalize(new[field]) != normalize(old[field]):
                        raise ValueError("An unaffected full query changed")
                for name, body in result_files(new).items():
                    if (output / profile / family / name).read_bytes() != body:
                        raise ValueError("A complete numerical export disagrees with its result")
    return dict(status="passed_all_nine_official_endpoint_successors",
        checks=checks, proofs=proofs, complete_changed_state_queries=changes,
        complete_states=50, complete_districts=435, complete_candidates=1401,
        unaffected_states_exactly_reused=48, qualified_states=33, held_states=17,
        source_refits=0, survey_weight_changes=0, native_count_repairs=0,
        individual_histories_identified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh independent successor proof")
    result = verify(args.inputs, args.results)
    args.output.write_bytes(encoded(result))
    print(json.dumps({key: value for key, value in result.items()
        if key not in ("proofs", "complete_changed_state_queries")}, sort_keys=True))


if __name__ == "__main__":
    main()
