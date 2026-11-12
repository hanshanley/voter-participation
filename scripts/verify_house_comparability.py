"""Verify native totals, endpoint holds and all nine complete public model results."""

import json
import math
from scripts.verify_norc_house_model import verify as verify_model


def verify(inputs, output):
    load = lambda path: json.loads(path.read_bytes())
    review = load(output/"complete-audit.json")
    districts = review["district_queries"]
    if len(districts) != 435 or len({row["district"] for row in districts}) != 435:
        raise ValueError("Incomplete district queries")
    decisions = {row["state_code"]: row for row in review["states"]}
    original_masks = None
    checks = 0
    model_proofs = {}
    for profile in ("original", "attenuated", "full"):
        model_proofs[profile] = {}
        for family in ("accepted_ridge_multinomial", "histogram_gradient_boosting", "extra_randomized_trees"):
            result = load(output/profile/family/"complete-result.json")
            priors = load(inputs/profile/family/"synthetic-priors.json")
            old = load(inputs/profile/family/"complete-result.json")
            if result["validation"] != old["validation"]:
                raise ValueError("Source-validation scores changed without a source fit")
            proof = verify_model(result, priors)
            model_proofs[profile][family] = proof
            checks += proof["checks"]
            masks = [(row["state_code"], row["source_comparison_available"]) for row in result["rows"]]
            if original_masks is None:
                original_masks = masks
            elif masks != original_masks:
                raise ValueError("Endpoint masks differ between profiles or families")
            for row in result["rows"]:
                decision = decisions[row["state_code"]]
                local = [district for district in districts if district["state_code"] == row["state_code"]]
                coverage_ok = True
                for district in local:
                    party_masks = []
                    for phase in ("previous", "current"):
                        source = district[phase]["source_candidate_rows"]
                        names = {party: [candidate for candidate in source
                                         if candidate["named"] and candidate["group"] == party] for party in "DR"}
                        party_masks.append(tuple(bool(names[party]) for party in "DR"))
                        if any(len(names[party]) > 1 for party in "DR") or any(
                                candidate["group"] in "DR" and candidate["votes"] is None for candidate in source):
                            coverage_ok = False
                    if party_masks[0] != party_masks[1]:
                        coverage_ok = False
                if row["source_comparison_available"] and not coverage_ok:
                    raise ValueError("An incompatible contest still constrains a modeled history")
                for phase in ("previous", "current"):
                    native = {party: sum(candidate["votes"] for district in local
                        for candidate in district[phase]["source_candidate_rows"]
                        if candidate["group"] == party and candidate["votes"] is not None) for party in "DRO"}
                    if native != decision[phase+"_counts"]:
                        raise ValueError("Audit totals do not equal the native candidate queries")
                    if row["source_comparison_available"] and native != row["reported_comparison"][phase]:
                        raise ValueError("Conditioned endpoint is not the native source total")
                    checks += 1
                if not row["source_comparison_available"] and row["before_current_party_conditioning"] is not None:
                    raise ValueError("Unavailable target was used for a prediction error")
    ma = decisions["MA"]
    if (ma["previous_named_R_districts"], ma["current_named_R_districts"]) != (2, 5):
        raise ValueError("Massachusetts source candidate coverage changed unexpectedly")
    if ma["like_for_like_statewide_source_comparison"] or not math.isclose(
            ma["raw_reported_aggregate_margin_change_pp"], -22.905071428374576, abs_tol=1e-10):
        raise ValueError("Massachusetts raw aggregate was silently repaired or treated as comparable")
    return dict(status="passed_native_counts_comparability_and_all_nine_models",
        checks=checks, all_native_candidate_counts_unchanged=True, districts=435, states=50,
        qualified_state_comparisons=sum(available for _, available in original_masks),
        held_states=[code for code, available in original_masks if not available],
        native_completeness_or_individual_histories_not_claimed=True,
        family_profile_proofs=model_proofs)
