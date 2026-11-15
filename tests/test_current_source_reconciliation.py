import copy

from scripts.current_source_reconciliation import (
    BRIDGE_CONTRACT,
    CONTRACT,
    ELECTION_DATE,
    EVIDENCE_CONTRACT,
    PROPOSAL_CONTRACT,
    STATE_CODES,
    build_reconciliation,
    canonical_sha256,
    encoded,
    qualify_proposal,
)


def display():
    return {
        "contract": "participation.registered_control_display.v2",
        "states": [
            {
                "state_code": state,
                "control_id": "control-" + state,
                "control_denominator_basis": "active_registered_voters",
            }
            for state in STATE_CODES
        ],
        "scenarios": [{
            "state_code": "OR",
            "control_id": "control-OR",
            "native_denominator_basis": "active_registered_voters",
            "native_registered_denominator": "1000",
            "conditional_modeled_voter_count": "600",
            "conditional_modeled_nonvoter_count": "400",
            "source_url": "fixture://accepted",
        }],
    }


def qualification():
    states = [state for state in STATE_CODES if state != "DC"]
    return {
        "qualified_state_codes": states[:33],
        "held_state_codes": states[33:],
    }


def snapshot():
    return {
        "contract": "participation.automatic_results_snapshot.v1",
        "election_date": ELECTION_DATE,
        "participation_observations": [],
    }


def domain(**changes):
    value = {
        "election_date": ELECTION_DATE,
        "election_year": 2026,
        "geography": "state:OR",
        "population": "active_registered_voters",
        "office_endpoint": "all_method_participation",
        "ballot_stage": "counted_all_methods",
    }
    value.update(changes)
    return value


def proposal(**changes):
    value = {
        "contract": PROPOSAL_CONTRACT,
        "proposal_id": "proposal-OR-01",
        "state_code": "OR",
        "kind": "cross_source_registered_probability",
        "source_role": "point_estimate_joint_bridge",
        "operation": "replace_registered_probability",
        "target_control_id": "control-OR",
        "bridge_id": "bridge-OR-01",
        "source_domain": domain(),
        "target_domain": domain(),
        "probability_numerator": "7",
        "probability_denominator": "10",
    }
    value.update(changes)
    return value


def evidence(value=None, **changes):
    value = value or proposal()
    numerator = int(value["probability_numerator"])
    denominator = int(value["probability_denominator"])
    result = {
        "contract": EVIDENCE_CONTRACT,
        "evidence_id": "evidence-OR-01",
        "state_code": value["state_code"],
        "target_control_id": value["target_control_id"],
        "source_domain": value["source_domain"],
        "target_domain": value["target_domain"],
        "operation": value["operation"],
        "sufficient_aggregate_joint_counts": True,
        "source_provenance": {
            "source_id": "fixture-reviewed-joint",
            "source_url": "fixture://reviewed-joint",
            "source_clock": "2026-11-04T00:00:00Z",
            "source_artifact_sha256": "b" * 64,
        },
        "joint_counts": {
            "participation_numerator": str(numerator),
            "population_denominator": str(denominator),
            "nonparticipant_complement": str(denominator - numerator),
        },
    }
    result.update(changes)
    return result


def bridge(value=None, evidence_body=None, **changes):
    value = value or proposal()
    evidence_body = evidence_body or evidence(value)
    result = {
        "contract": BRIDGE_CONTRACT,
        "bridge_id": value["bridge_id"],
        "review_status": "approved",
        "review_scope": (
            "same_election_year_geography_population_endpoint_stage_joint"
        ),
        "reviewed_by": "fixture-reviewer",
        "reviewed_at": "2026-11-15T12:00:00-05:00",
        "joint_population_observed": True,
        "supports_point_estimate_update": True,
        "supports_proposal_ids": [value["proposal_id"]],
        "proposal_sha256": canonical_sha256(value),
        "evidence_id": evidence_body["evidence_id"],
        "evidence_sha256": canonical_sha256(evidence_body),
        "target_control_id": value["target_control_id"],
        "probability_numerator": value["probability_numerator"],
        "probability_denominator": value["probability_denominator"],
        "source_domain": value["source_domain"],
        "target_domain": value["target_domain"],
    }
    result.update(changes)
    return result


def observation(value=None, control_id=None):
    value = value if value is not None else proposal()
    target = value["target_domain"] if isinstance(value, dict) else domain()
    return {
        "state_code": "OR",
        "channel": "fixture",
        "status": "reported",
        "estimate_update": value,
        "observation": {
            "control_id": control_id or "control-OR",
            "denominator_basis": "active_registered_voters",
            "denominator": 1000,
            "ballots": 500,
            "source_url": "fixture://current",
            "estimate_domain": target,
        },
    }


def decision(value, bridge_body=None, evidence_body=None):
    evidence_body = evidence_body or evidence(value)
    bridge_body = bridge_body or bridge(value, evidence_body)
    return qualify_proposal(
        "OR", value, display(),
        {bridge_body["bridge_id"]: bridge_body},
        {evidence_body["evidence_id"]: evidence_body},
    )


def test_supported_pinned_joint_evidence_is_eligible():
    result = decision(proposal())
    assert result["eligible"] is True
    assert result["disposition"] == "qualified_reviewed_joint_bridge"
    assert result["probability_numerator"] == "7"
    assert result["evidence_id"] == "evidence-OR-01"


def test_zero_probability_is_valid_endpoint():
    value = proposal(probability_numerator="0")
    result = decision(value)
    assert result["eligible"] is True
    assert result["probability_numerator"] == "0"


def test_changed_probability_fails_bridge_proposal_binding():
    approved = proposal()
    evidence_body = evidence(approved)
    bridge_body = bridge(approved, evidence_body)
    changed = proposal(probability_numerator="6")
    result = qualify_proposal(
        "OR", changed, display(),
        {bridge_body["bridge_id"]: bridge_body},
        {evidence_body["evidence_id"]: evidence_body},
    )
    assert result["disposition"] == "held_unqualified_joint_bridge"


def test_changed_evidence_body_fails_evidence_pin():
    value = proposal()
    approved_evidence = evidence(value)
    bridge_body = bridge(value, approved_evidence)
    changed_evidence = copy.deepcopy(approved_evidence)
    changed_evidence["source_provenance"]["source_clock"] = "changed"
    result = qualify_proposal(
        "OR", value, display(),
        {bridge_body["bridge_id"]: bridge_body},
        {changed_evidence["evidence_id"]: changed_evidence},
    )
    assert result["disposition"] == "held_unqualified_joint_bridge"


def test_missing_evidence_body_fails_closed():
    value = proposal()
    evidence_body = evidence(value)
    bridge_body = bridge(value, evidence_body)
    result = qualify_proposal(
        "OR", value, display(), {bridge_body["bridge_id"]: bridge_body}, {}
    )
    assert result["disposition"] == "held_missing_reviewed_evidence"


def test_wrong_population_year_geography_stage_and_diagnostic_fail_closed():
    cases = (
        (proposal(source_domain=domain(population="current_voters")),
         "held_wrong_population"),
        (proposal(source_domain=domain(election_year=2024)),
         "held_wrong_election_or_year"),
        (proposal(source_domain=domain(geography="county:41051")),
         "held_wrong_geography"),
        (proposal(source_domain=domain(ballot_stage="returned")),
         "held_wrong_ballot_stage"),
        (proposal(source_role="diagnostic_only"), "held_diagnostic_only_source"),
    )
    for value, expected in cases:
        assert decision(value)["disposition"] == expected


def test_malformed_proposal_and_review_collections_do_not_crash():
    assert qualify_proposal("OR", [], display(), {}, {})[
        "disposition"
    ] == "held_invalid_proposal"
    value = proposal()
    assert qualify_proposal("OR", value, display(), None, None)[
        "disposition"
    ] == "held_invalid_review_collection"
    malformed_bridge = bridge(value, evidence(value), supports_proposal_ids=None)
    assert qualify_proposal(
        "OR", value, display(), {malformed_bridge["bridge_id"]: malformed_bridge},
        {evidence(value)["evidence_id"]: evidence(value)},
    )["disposition"] == "held_invalid_bridge_support_collection"


def test_malformed_proposal_identifiers_hold_without_blocking_legacy_updates():
    from scripts.automatic_estimates import _participation

    for changes, expected in (
        ({"target_control_id": []}, "held_invalid_target_control_id"),
        ({"target_control_id": {}}, "held_invalid_target_control_id"),
        ({"proposal_id": []}, "held_missing_proposal_id"),
        ({"proposal_id": {}}, "held_missing_proposal_id"),
    ):
        legacy = observation()
        del legacy["estimate_update"]
        legacy["observation"]["denominator"] = 2000
        snap = snapshot()
        snap["participation_observations"] = [
            observation(proposal(**changes)), legacy
        ]
        result = _participation(snap, {
            "participation_state_controls": display(),
            "qualification": qualification(),
        })
        update = result["automatic_update"]
        assert update["decisions"][0]["gate_subreason"] == expected
        assert update["decisions"][0]["qualification"]["eligible"] is False
        assert update["fresh_compatible_scenarios"] == 1
        assert result["scenarios"][0]["conditional_modeled_voter_count"] == "1200"


def test_malformed_observation_entries_do_not_block_valid_registered_frame():
    from scripts.automatic_estimates import _participation

    legacy = observation()
    del legacy["estimate_update"]
    legacy["observation"]["denominator"] = 2000
    snap = snapshot()
    snap["participation_observations"] = [
        None, [], {"state_code": [], "status": "reported"}, legacy
    ]
    result = _participation(snap, {
        "participation_state_controls": display(),
        "qualification": qualification(),
    })
    assert result["automatic_update"]["fresh_compatible_scenarios"] == 1
    assert result["scenarios"][0]["conditional_modeled_voter_count"] == "1200"


def test_observation_target_and_domain_are_bound_before_eligibility():
    value = proposal()
    evidence_body = evidence(value)
    bridge_body = bridge(value, evidence_body)
    snap = snapshot()
    snap["reviewed_joint_bridges"] = [bridge_body]
    snap["reviewed_joint_evidence"] = [evidence_body]
    snap["participation_observations"] = [observation(value, "other-OR")]
    result = build_reconciliation(snap, display(), qualification())
    row = next(item for item in result["states"] if item["state_code"] == "OR")
    assert row["proposed_updates"][0][
        "disposition"
    ] == "held_observation_target_control_mismatch"

    snap["participation_observations"] = [observation(value)]
    snap["participation_observations"][0]["observation"]["estimate_domain"] = domain(
        geography="state:WA"
    )
    result = build_reconciliation(snap, display(), qualification())
    row = next(item for item in result["states"] if item["state_code"] == "OR")
    assert row["proposed_updates"][0][
        "disposition"
    ] == "held_observation_domain_mismatch"


def test_duplicate_state_proposal_identity_holds_every_duplicate():
    valid = proposal()
    invalid = proposal(source_domain=domain(population="current_voters"))
    evidence_body = evidence(valid)
    bridge_body = bridge(valid, evidence_body)
    snap = snapshot()
    snap["reviewed_joint_bridges"] = [bridge_body]
    snap["reviewed_joint_evidence"] = [evidence_body]
    snap["participation_observations"] = [observation(invalid), observation(valid)]
    result = build_reconciliation(snap, display(), qualification())
    row = next(item for item in result["states"] if item["state_code"] == "OR")
    assert len(row["proposed_updates"]) == 2
    assert {
        item["disposition"] for item in row["proposed_updates"]
    } == {"held_duplicate_proposal_identity"}
    assert {item["observation_index"] for item in row["proposed_updates"]} == {0, 1}


def test_all_state_gate_is_deterministic_and_preserves_legacy_authority():
    first = build_reconciliation(snapshot(), display(), qualification())
    second = build_reconciliation(
        copy.deepcopy(snapshot()), copy.deepcopy(display()), qualification()
    )
    assert encoded(first) == encoded(second)
    assert first["contract"] == CONTRACT
    assert len(first["states"]) == 51
    assert first["summary"]["existing_house_qualified"] == 33
    assert first["summary"]["existing_house_held"] == 17
    assert first["summary"]["eligible_new_point_updates"] == 0
    assert first["summary"]["source_weights_probabilities_or_fits_changed"] is False


def test_exact_registered_frame_remains_allowed_without_bridge():
    value = snapshot()
    value["participation_observations"] = [{
        "state_code": "OR",
        "channel": "OR-official",
        "status": "reported",
        "observation": {
            "denominator": 1001,
            "denominator_basis": "active_registered_voters",
            "control_id": "control-OR",
        },
    }]
    result = build_reconciliation(value, display(), qualification())
    gate = next(row for row in result["states"] if row["state_code"] == "OR")
    assert gate["registered_frame"][
        "exact_registered_R_times_p_remains_allowed_without_new_bridge"
    ] is True
    assert gate["registered_frame"]["reported_candidate_rows"][0][
        "exact_reviewed_registered_frame"
    ] is True
