"""Fail-closed qualification for current cross-source participation updates.

Existing reviewed House comparisons, unchanged source priors, and exact
registered-frame R*p scenarios retain their accepted behavior. A newly proposed
cross-source probability can change a point estimate only through an explicitly
approved joint bridge with an exact election, geography, population, endpoint,
and ballot-stage match.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


CONTRACT = "participation.current_source_reconciliation.v1"
BRIDGE_CONTRACT = "participation.reviewed_joint_bridge.v1"
PROPOSAL_CONTRACT = "participation.cross_source_estimate_update.v1"
EVIDENCE_CONTRACT = "participation.reviewed_joint_evidence.v1"
ELECTION_DATE = "2026-11-03"
ELECTION_YEAR = 2026
DOMAIN_FIELDS = (
    "election_date",
    "election_year",
    "geography",
    "population",
    "office_endpoint",
    "ballot_stage",
)
STATE_CODES = (
    "AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "GA",
    "HI", "IA", "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME",
    "MI", "MN", "MO", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM",
    "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX",
    "UT", "VA", "VT", "WA", "WI", "WV", "WY",
)
CONTEXT_STAGE_KINDS = (
    "applications", "issued", "returned", "accepted", "rejected",
    "outstanding", "inperson", "counted", "official",
)
REQUIRED_BALLOT_STAGES = (
    "issued", "returned", "accepted", "rejected", "outstanding", "counted",
)


def encoded(value):
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode()


def pin(body):
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def canonical_sha256(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def load_json(path):
    path = Path(path)
    body = path.read_bytes()
    decoded = gzip.decompress(body) if path.suffix == ".gz" else body
    return json.loads(decoded), pin(body)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _strict_integer(value, label, minimum):
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(label + " must be an exact integer")
    try:
        integer = int(value)
    except (TypeError, ValueError):
        raise ValueError(label + " must be an exact integer") from None
    if integer < minimum or str(integer) != str(value):
        raise ValueError(label + " must be an exact integer")
    return integer


def _strict_nonnegative_integer(value, label):
    return _strict_integer(value, label, 0)


def _strict_positive_integer(value, label):
    return _strict_integer(value, label, 1)


def _valid_sha256(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_display(display):
    _require(
        display.get("contract") in (
            "participation.registered_control_display.v2",
            "participation.registered_control_display.v1",
        ),
        "Wrong registered-control display contract",
    )
    states = display.get("states")
    scenarios = display.get("scenarios")
    _require(isinstance(states, list) and len(states) == 51,
             "All 51 registered-control dispositions are required")
    _require(
        tuple(sorted(row.get("state_code") for row in states)) == STATE_CODES,
        "Registered-control state identity changed",
    )
    _require(isinstance(scenarios, list), "Registered scenarios are required")
    controls = [row.get("control_id") for row in scenarios]
    _require(
        len(controls) == len(set(controls)),
        "Registered scenario control IDs must be unique",
    )


def _validate_snapshot(snapshot):
    _require(
        snapshot.get("contract") == "participation.automatic_results_snapshot.v1",
        "Wrong automatic-results snapshot contract",
    )
    _require(
        snapshot.get("election_date") == ELECTION_DATE,
        "Wrong automatic-results election date",
    )
    _require(
        isinstance(snapshot.get("participation_observations"), list),
        "Participation observations are required",
    )


def _qualification_sets(qualification):
    qualified = tuple(qualification.get("qualified_state_codes", ()))
    held = tuple(qualification.get("held_state_codes", ()))
    _require(
        len(qualified) == 33 and len(held) == 17,
        "The accepted 33-qualified/17-held House mask changed",
    )
    _require(
        set(qualified).isdisjoint(held)
        and set(qualified) | set(held) == set(STATE_CODES) - {"DC"},
        "The accepted House mask no longer covers exactly 50 states",
    )
    return set(qualified), set(held)


def _scenario_indexes(display):
    by_id = {row["control_id"]: row for row in display["scenarios"]}
    by_state_basis = {}
    for row in display["scenarios"]:
        by_state_basis.setdefault(
            (row["state_code"], row["native_denominator_basis"]), []
        ).append(row)
    return by_id, by_state_basis


def _reported_registered_candidates(snapshot, by_state_basis):
    result = {state: [] for state in STATE_CODES}
    for item in snapshot["participation_observations"]:
        if not isinstance(item, dict) or item.get("status") != "reported":
            continue
        state = item.get("state_code")
        observation = item.get("observation")
        if (
            not isinstance(state, str)
            or state not in result
            or not isinstance(observation, dict)
        ):
            continue
        if (
            observation.get("denominator") is None
            or not isinstance(observation.get("denominator_basis"), str)
            or not observation["denominator_basis"]
        ):
            continue
        basis = observation["denominator_basis"]
        requested = observation.get("control_id")
        matches = [
            row for row in by_state_basis.get((state, basis), ())
            if requested is None or row["control_id"] == requested
        ]
        result[state].append({
            "channel": item.get("channel"),
            "control_id": requested,
            "denominator_basis": basis,
            "matching_control_ids": [row["control_id"] for row in matches],
            "exact_reviewed_registered_frame": len(matches) == 1,
        })
    return result


def _collection_index(snapshot, key, identity_field):
    if key not in snapshot:
        return {"items": {}, "invalid_ids": set(), "errors": []}
    values = snapshot[key]
    if not isinstance(values, list):
        return {
            "items": {},
            "invalid_ids": set(),
            "errors": ["held_invalid_" + key + "_collection"],
        }
    items = {}
    invalid_ids = set()
    errors = []
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            errors.append("{}[{}]_not_object".format(key, index))
            continue
        identity = value.get(identity_field)
        if not isinstance(identity, str) or not identity:
            errors.append("{}[{}]_invalid_identity".format(key, index))
            continue
        if identity in items or identity in invalid_ids:
            items.pop(identity, None)
            invalid_ids.add(identity)
            errors.append("{}_duplicate_identity:{}".format(key, identity))
            continue
        items[identity] = value
    return {"items": items, "invalid_ids": invalid_ids, "errors": errors}


def _direct_index(values, identity_field):
    if (
        isinstance(values, dict)
        and set(("items", "invalid_ids", "errors")) <= set(values)
        and isinstance(values["items"], dict)
    ):
        return values
    if isinstance(values, dict):
        return {"items": values, "invalid_ids": set(), "errors": []}
    return _collection_index({"values": values}, "values", identity_field)


def _proposal_id(proposal):
    identity = proposal.get("proposal_id") if isinstance(proposal, dict) else None
    return identity if isinstance(identity, str) and identity else None


def _hold(proposal, reason, **details):
    return {
        "proposal_id": _proposal_id(proposal),
        "eligible": False,
        "disposition": reason,
        "point_estimate_change_allowed": False,
        **details,
    }


def _validate_evidence(evidence, proposal, scenario):
    if not isinstance(evidence, dict):
        return "held_missing_reviewed_evidence"
    if evidence.get("contract") != EVIDENCE_CONTRACT:
        return "held_wrong_evidence_contract"
    if (
        evidence.get("state_code") != proposal["state_code"]
        or evidence.get("target_control_id") != proposal["target_control_id"]
        or evidence.get("source_domain") != proposal["source_domain"]
        or evidence.get("target_domain") != proposal["target_domain"]
        or evidence.get("operation") != proposal["operation"]
        or evidence.get("sufficient_aggregate_joint_counts") is not True
    ):
        return "held_evidence_binding_mismatch"
    provenance = evidence.get("source_provenance")
    if (
        not isinstance(provenance, dict)
        or not isinstance(provenance.get("source_id"), str)
        or not provenance["source_id"]
        or not isinstance(provenance.get("source_url"), str)
        or not provenance["source_url"]
        or "source_clock" not in provenance
        or (
            provenance["source_clock"] is not None
            and not isinstance(provenance["source_clock"], str)
        )
        or not _valid_sha256(provenance.get("source_artifact_sha256"))
    ):
        return "held_incomplete_evidence_provenance"
    counts = evidence.get("joint_counts")
    if not isinstance(counts, dict):
        return "held_missing_sufficient_joint_counts"
    try:
        numerator = _strict_nonnegative_integer(
            counts.get("participation_numerator"), "participation_numerator"
        )
        denominator = _strict_positive_integer(
            counts.get("population_denominator"), "population_denominator"
        )
        complement = _strict_nonnegative_integer(
            counts.get("nonparticipant_complement"), "nonparticipant_complement"
        )
    except ValueError:
        return "held_invalid_sufficient_joint_counts"
    if (
        numerator > denominator
        or numerator + complement != denominator
        or str(numerator) != str(proposal.get("probability_numerator"))
        or str(denominator) != str(proposal.get("probability_denominator"))
        or scenario["native_denominator_basis"]
        != evidence["target_domain"]["population"]
    ):
        return "held_evidence_probability_mismatch"
    return None


def qualify_proposal(
    state, proposal, display, bridges, evidence=None, collection_errors=()
):
    """Return a machine-readable eligibility decision for one proposed update."""
    if not isinstance(proposal, dict):
        return _hold({}, "held_invalid_proposal")
    if proposal.get("contract") != PROPOSAL_CONTRACT:
        return _hold(proposal, "held_wrong_proposal_contract")
    if proposal.get("state_code") != state:
        return _hold(proposal, "held_state_mismatch")
    proposal_id = proposal.get("proposal_id")
    if not isinstance(proposal_id, str) or not proposal_id:
        return _hold(proposal, "held_missing_proposal_id")
    kind = proposal.get("kind")
    if kind == "unchanged_source_prior":
        return {
            "proposal_id": proposal_id,
            "eligible": True,
            "disposition": "retained_unchanged_source_prior",
            "point_estimate_change_allowed": False,
            "joint_bridge_required": False,
        }
    if kind != "cross_source_registered_probability":
        return _hold(proposal, "held_unsupported_proposal_kind")
    if collection_errors:
        return _hold(
            proposal, "held_invalid_review_collection",
            collection_errors=list(collection_errors),
        )
    if proposal.get("source_role") != "point_estimate_joint_bridge":
        return _hold(proposal, "held_diagnostic_only_source")
    if proposal.get("operation") != "replace_registered_probability":
        return _hold(proposal, "held_unsupported_point_operation")

    scenarios, _ = _scenario_indexes(display)
    control_id = proposal.get("target_control_id")
    if not isinstance(control_id, str) or not control_id:
        return _hold(proposal, "held_invalid_target_control_id")
    scenario = scenarios.get(control_id)
    if scenario is None or scenario.get("state_code") != state:
        return _hold(proposal, "held_unknown_target_scenario")
    source = proposal.get("source_domain")
    target = proposal.get("target_domain")
    if not isinstance(source, dict) or not isinstance(target, dict):
        return _hold(proposal, "held_missing_domain")
    missing = [
        field for field in DOMAIN_FIELDS
        if field not in source or field not in target
    ]
    if missing:
        return _hold(proposal, "held_incomplete_domain", missing_fields=missing)

    if (
        source["election_date"] != ELECTION_DATE
        or target["election_date"] != ELECTION_DATE
        or source["election_year"] != ELECTION_YEAR
        or target["election_year"] != ELECTION_YEAR
    ):
        return _hold(proposal, "held_wrong_election_or_year")
    if (
        source["geography"] != "state:" + state
        or target["geography"] != "state:" + state
        or source["geography"] != target["geography"]
    ):
        return _hold(proposal, "held_wrong_geography")
    if (
        source["population"] != target["population"]
        or target["population"] != scenario["native_denominator_basis"]
    ):
        return _hold(proposal, "held_wrong_population")
    if (
        source["office_endpoint"] != target["office_endpoint"]
        or target["office_endpoint"] != "all_method_participation"
    ):
        return _hold(proposal, "held_incomparable_office_endpoint")
    if (
        source["ballot_stage"] != target["ballot_stage"]
        or target["ballot_stage"] != "counted_all_methods"
    ):
        return _hold(proposal, "held_wrong_ballot_stage")

    bridge_index = _direct_index(bridges, "bridge_id")
    evidence_index = _direct_index(
        evidence if evidence is not None else {}, "evidence_id"
    )
    if bridge_index["errors"] or evidence_index["errors"]:
        return _hold(proposal, "held_invalid_review_collection")
    bridge_id = proposal.get("bridge_id")
    if not isinstance(bridge_id, str) or not bridge_id:
        return _hold(proposal, "held_invalid_bridge_id")
    if bridge_id in bridge_index["invalid_ids"]:
        return _hold(proposal, "held_ambiguous_bridge_id")
    bridge = bridge_index["items"].get(bridge_id)
    if bridge is None:
        return _hold(proposal, "held_missing_reviewed_joint_bridge")
    support = bridge.get("supports_proposal_ids")
    if (
        not isinstance(support, list)
        or not support
        or any(not isinstance(value, str) or not value for value in support)
        or len(support) != len(set(support))
    ):
        return _hold(proposal, "held_invalid_bridge_support_collection")
    evidence_id = bridge.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        return _hold(proposal, "held_invalid_evidence_id")
    if evidence_id in evidence_index["invalid_ids"]:
        return _hold(proposal, "held_ambiguous_evidence_id")
    evidence_body = evidence_index["items"].get(evidence_id)
    if evidence_body is None:
        return _hold(proposal, "held_missing_reviewed_evidence")
    if (
        bridge.get("contract") != BRIDGE_CONTRACT
        or bridge.get("review_status") != "approved"
        or bridge.get("review_scope")
        != "same_election_year_geography_population_endpoint_stage_joint"
        or not isinstance(bridge.get("reviewed_by"), str)
        or not bridge["reviewed_by"]
        or not isinstance(bridge.get("reviewed_at"), str)
        or not bridge["reviewed_at"]
        or bridge.get("joint_population_observed") is not True
        or bridge.get("supports_point_estimate_update") is not True
        or proposal_id not in support
        or bridge.get("proposal_sha256") != canonical_sha256(proposal)
        or bridge.get("evidence_sha256") != canonical_sha256(evidence_body)
        or bridge.get("target_control_id") != control_id
        or str(bridge.get("probability_numerator"))
        != str(proposal.get("probability_numerator"))
        or str(bridge.get("probability_denominator"))
        != str(proposal.get("probability_denominator"))
    ):
        return _hold(proposal, "held_unqualified_joint_bridge")
    if (
        bridge.get("source_domain") != source
        or bridge.get("target_domain") != target
    ):
        return _hold(proposal, "held_bridge_domain_mismatch")
    evidence_error = _validate_evidence(evidence_body, proposal, scenario)
    if evidence_error:
        return _hold(proposal, evidence_error)
    try:
        numerator = _strict_nonnegative_integer(
            proposal.get("probability_numerator"), "probability_numerator"
        )
        denominator = _strict_positive_integer(
            proposal.get("probability_denominator"), "probability_denominator"
        )
    except ValueError:
        return _hold(proposal, "held_invalid_probability")
    if numerator > denominator:
        return _hold(proposal, "held_invalid_probability")
    return {
        "proposal_id": proposal_id,
        "eligible": True,
        "disposition": "qualified_reviewed_joint_bridge",
        "point_estimate_change_allowed": True,
        "joint_bridge_required": True,
        "bridge_id": bridge_id,
        "evidence_id": evidence_id,
        "proposal_sha256": canonical_sha256(proposal),
        "evidence_sha256": canonical_sha256(evidence_body),
        "target_control_id": control_id,
        "target_domain": target,
        "probability_numerator": str(numerator),
        "probability_denominator": str(denominator),
    }


def _context_stages(context, state):
    if context is None:
        return []
    rows = []
    for identity, item in sorted(context.get("datasets", {}).items()):
        if item.get("state") != state or item.get("status") != "reported":
            continue
        kind = item.get("kind")
        base = kind.split("-", 1)[0] if isinstance(kind, str) else None
        if base not in CONTEXT_STAGE_KINDS:
            continue
        data = item.get("data") or {}
        value = data.get("total")
        if kind == "official":
            value = data.get("ballots")
        rows.append({
            "dataset_id": identity,
            "source_kind": kind,
            "stage": (
                "official_source_defined_ballots" if kind == "official" else base
            ),
            "value": value,
            "separate_not_additive": True,
            "point_estimate_update_eligible": False,
        })
    return rows


def _ballot_stage_gates(rows):
    return {
        stage: {
            "present": any(row["stage"] == stage for row in rows),
            "dataset_ids": [
                row["dataset_id"] for row in rows if row["stage"] == stage
            ],
            "separate_not_additive": True,
            "all_method_turnout_substitute": False,
        }
        for stage in REQUIRED_BALLOT_STAGES
    }


def build_reconciliation(
    snapshot,
    display,
    qualification,
    *,
    joint_review=None,
    context=None,
    source_qualification=None,
    validation=None,
):
    """Build deterministic all-state gates without changing numerical estimates."""
    _validate_snapshot(snapshot)
    _validate_display(display)
    qualified, held = _qualification_sets(qualification)
    _, by_state_basis = _scenario_indexes(display)
    registered_candidates = _reported_registered_candidates(
        snapshot, by_state_basis
    )
    bridges = _collection_index(
        snapshot, "reviewed_joint_bridges", "bridge_id"
    )
    evidence = _collection_index(
        snapshot, "reviewed_joint_evidence", "evidence_id"
    )
    collection_errors = tuple(bridges["errors"] + evidence["errors"])
    proposals = {state: [] for state in STATE_CODES}
    proposal_rows = []
    for observation_index, item in enumerate(snapshot["participation_observations"]):
        if not isinstance(item, dict):
            continue
        state = item.get("state_code")
        proposal = item.get("estimate_update")
        if isinstance(state, str) and state in proposals and proposal is not None:
            decision = qualify_proposal(
                state, proposal, display, bridges, evidence, collection_errors
            )
            decision["observation_index"] = observation_index
            decision["proposal_sha256"] = (
                canonical_sha256(proposal) if isinstance(proposal, dict) else None
            )
            if decision["eligible"] and decision["point_estimate_change_allowed"]:
                observation = item.get("observation")
                if not isinstance(observation, dict):
                    decision = {
                        **decision,
                        "eligible": False,
                        "point_estimate_change_allowed": False,
                        "disposition": "held_invalid_observation_binding",
                    }
                elif observation.get("control_id") != decision["target_control_id"]:
                    decision = {
                        **decision,
                        "eligible": False,
                        "point_estimate_change_allowed": False,
                        "disposition": "held_observation_target_control_mismatch",
                    }
                elif (
                    observation.get("denominator_basis")
                    != proposal["target_domain"]["population"]
                ):
                    decision = {
                        **decision,
                        "eligible": False,
                        "point_estimate_change_allowed": False,
                        "disposition": "held_observation_population_mismatch",
                    }
                elif observation.get("estimate_domain") != proposal["target_domain"]:
                    decision = {
                        **decision,
                        "eligible": False,
                        "point_estimate_change_allowed": False,
                        "disposition": "held_observation_domain_mismatch",
                    }
            proposal_rows.append((state, decision))

    identities = {}
    for position, (state, decision) in enumerate(proposal_rows):
        identity = decision.get("proposal_id")
        if isinstance(identity, str) and identity:
            identities.setdefault((state, identity), []).append(position)
    duplicates = {
        identity for identity, positions in identities.items() if len(positions) > 1
    }
    for position, (state, decision) in enumerate(proposal_rows):
        if (state, decision.get("proposal_id")) in duplicates:
            proposal_rows[position] = (state, {
                **decision,
                "eligible": False,
                "point_estimate_change_allowed": False,
                "disposition": "held_duplicate_proposal_identity",
            })
    for state, decision in proposal_rows:
        proposals[state].append(decision)

    joint_by_state = {}
    if joint_review is not None:
        _require(
            joint_review.get("status")
            == "reported_joint_survey_tables_not_population_decomposition",
            "Wrong current-voter joint-review identity",
        )
        joint_by_state = {
            row["state_code"]: row for row in joint_review.get("jurisdictions", [])
        }
        _require(
            tuple(sorted(joint_by_state)) == STATE_CODES,
            "Current-voter review must retain all 51 jurisdiction dispositions",
        )
    if context is not None:
        _require(
            context.get("election_date") == ELECTION_DATE,
            "Wrong current context election date",
        )
        context_states = {
            row.get("state") for row in context.get("datasets", {}).values()
        }
        _require(
            context_states == set(STATE_CODES),
            "Current context must retain all 51 jurisdictions",
        )
    if source_qualification is not None:
        _require(
            source_qualification.get("chep_scope", {}).get(
                "state_inference_qualification_established"
            ) is False,
            "CHEP state inference was unexpectedly qualified",
        )
    if validation is not None:
        _require(
            validation.get("schema")
            == "participation.adaptive_persistence_observations.v1"
            and validation.get("qualifications", {}).get(
                "population_transport_validated"
            ) is False,
            "Population transport validation identity changed",
        )

    scenario_counts = {
        state: sum(row["state_code"] == state for row in display["scenarios"])
        for state in STATE_CODES
    }
    ap_excluded = set()
    ap_evidence_loaded = source_qualification is not None
    if source_qualification is not None:
        ap_excluded = set(
            source_qualification["historical_ap_scope"][
                "excluded_from_train_and_score"
            ]
        )
    rows = []
    for state in STATE_CODES:
        joint = joint_by_state.get(state)
        current_voter_tables = joint.get("reviewed_joint_tables", 0) if joint else 0
        proposal_rows = proposals[state]
        stage_rows = _context_stages(context, state)
        rows.append({
            "state_code": state,
            "observed_office_endpoint": {
                "endpoint": "2024_House_to_2026_House_candidate_contest_totals",
                "existing_house_comparison_disposition": (
                    "accepted_qualified_directional_comparison"
                    if state in qualified
                    else "accepted_behavioral_hold"
                    if state in held
                    else "not_in_50_state_house_model"
                ),
                "existing_behavior_preserved": True,
                "accepted_mask_is_only_automatic_conditioning_authority": True,
                "new_cross_source_point_update_eligible": any(
                    row["point_estimate_change_allowed"] for row in proposal_rows
                ),
            },
            "survey_population": {
                "ap_role": (
                    "not_sampled"
                    if state == "DC" and ap_evidence_loaded
                    else "excluded_from_historical_transfer"
                    if state in ap_excluded
                    else "source_weighted_repeated_cross_section_diagnostic"
                    if ap_evidence_loaded
                    else "runtime_evidence_not_loaded"
                ),
                "ap_repeated_cross_section_is_person_transition": False,
                "chep_role": (
                    "pooled_source_weighted_diagnostic"
                    if state != "DC" else "not_sampled"
                ),
                "chep_state_inference_qualified": False,
                "current_voter_reviewed_joint_tables": current_voter_tables,
                "current_voter_population_decomposition_available": (
                    joint.get("population_decomposition_available", False)
                    if joint else False
                ),
                "current_voter_can_supply_nonvoter_or_full_population": False,
                "repeated_cross_sections_are_person_transitions": False,
            },
            "registered_frame": {
                "accepted_scenarios": scenario_counts[state],
                "reported_candidate_rows": registered_candidates[state],
                "exact_registered_R_times_p_remains_allowed_without_new_bridge": True,
                "population_exchangeability_newly_validated": False,
            },
            "resident_context": {
                "census_or_acs_joint_bridge_present": False,
                "role": "resident_context_only",
                "precinct_or_county_allocation_eligible": False,
            },
            "ballot_stages": stage_rows,
            "ballot_stage_gates": _ballot_stage_gates(stage_rows),
            "proposed_updates": proposal_rows,
            "disposition": (
                "qualified_reviewed_joint_bridge_present"
                if any(row["point_estimate_change_allowed"] for row in proposal_rows)
                else "held_no_new_compatible_joint_bridge"
            ),
        })
    eligible = [
        proposal
        for row in rows
        for proposal in row["proposed_updates"]
        if proposal["point_estimate_change_allowed"]
    ]
    return {
        "contract": CONTRACT,
        "election_date": ELECTION_DATE,
        "states": rows,
        "summary": {
            "state_dispositions": 51,
            "existing_house_qualified": 33,
            "existing_house_held": 17,
            "dc_not_in_house_model": 1,
            "accepted_registered_scenarios": len(display["scenarios"]),
            "reviewed_joint_bridges": len(bridges["items"]),
            "reviewed_joint_evidence": len(evidence["items"]),
            "invalid_review_collection_entries": len(collection_errors),
            "duplicate_proposal_identities": len(duplicates),
            "proposed_updates": sum(len(row["proposed_updates"]) for row in rows),
            "eligible_new_point_updates": len(eligible),
            "source_weights_probabilities_or_fits_changed": False,
            "existing_masks_or_priors_changed": False,
            "ballot_stages_summed_into_all_method_turnout": False,
            "resident_context_allocated_locally": False,
        },
        "rules": {
            "new_cross_source_updates_fail_closed": True,
            "same_election_year_geography_population_endpoint_stage_required": True,
            "reviewed_joint_bridge_required_for_new_cross_source_probability": True,
            "supplied_pinned_sufficient_joint_evidence_required": True,
            "proposal_probability_and_target_bound_to_review_approval": True,
            "existing_registered_R_times_p_requires_no_new_bridge": True,
            "unchanged_source_priors_require_no_new_bridge": True,
            "current_voter_poll_is_diagnostic_population": True,
            "cps_or_ap_repeated_cross_sections_are_not_person_transitions": True,
            "census_or_acs_is_resident_context_only": True,
            "mail_and_early_ballot_stages_remain_separate": True,
        },
    }


def build_held_reconciliation(
    snapshot,
    rolling_seed,
    registered_display,
    joint_review,
    context,
    source_qualification,
    validation,
):
    _require(
        rolling_seed.get("contract") == "participation.automatic_estimates_seed.v1"
        and rolling_seed.get("election_date") == ELECTION_DATE,
        "Wrong rolling seed identity",
    )
    display = rolling_seed.get("participation_state_controls")
    result = build_reconciliation(
        snapshot,
        display,
        rolling_seed["qualification"],
        joint_review=joint_review,
        context=context,
        source_qualification=source_qualification,
        validation=validation,
    )
    _validate_display(registered_display)
    result["held_input_checks"] = {
        "rolling_seed_state_dispositions": len(display["states"]),
        "rolling_seed_registered_scenarios": len(display["scenarios"]),
        "published_display_state_dispositions": len(registered_display["states"]),
        "published_display_registered_scenarios": len(
            registered_display["scenarios"]
        ),
        "published_display_is_context_not_probability_override": True,
        "joint_review_tables": len(joint_review["tables"]),
        "current_context_datasets": len(context["datasets"]),
        "chep_state_inference_qualified": source_qualification["chep_scope"][
            "state_inference_qualification_established"
        ],
        "population_transport_validated": validation["qualifications"][
            "population_transport_validated"
        ],
    }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--rolling-seed", required=True)
    parser.add_argument("--registered-display", required=True)
    parser.add_argument("--joint-review", required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--source-qualification", required=True)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    inputs = {}
    pins = {}
    for name in (
        "snapshot", "rolling_seed", "registered_display", "joint_review",
        "context", "source_qualification", "validation",
    ):
        value, value_pin = load_json(getattr(args, name))
        inputs[name] = value
        pins[name] = {"path": str(Path(getattr(args, name))), **value_pin}
    result = build_held_reconciliation(**inputs)
    result["input_pins"] = pins
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded(result))


if __name__ == "__main__":
    main()
