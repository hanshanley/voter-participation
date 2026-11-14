"""Incrementally refresh accepted House estimates from a results-intake snapshot.

The module consumes only public aggregate synthetic priors and accepted numerical
outputs. It never fits a source model, exports respondents, or promotes a held
state into behavioral conditioning.
"""

import copy
from decimal import Decimal, localcontext
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path

from scripts import norc_house_model as accepted_model


CONTRACT = "participation.automatic_estimates.v1"
SEED_CONTRACT = "participation.automatic_estimates_seed.v1"
HOUSE_SOURCES_CONTRACT = "participation.automatic_house_sources.v1"
DESCRIPTOR_CONTRACT = "participation.automatic_house_source_descriptor.v1"
ELECTION_DATE = "2026-11-03"
PROFILES = ("original", "attenuated", "full")
FAMILIES = (
    "accepted_ridge_multinomial",
    "histogram_gradient_boosting",
    "extra_randomized_trees",
)
CHOICES = "DRONU"
MECHANISMS = ("switching", "exit", "entry", "other_choice", "unresolved")
PROTECTED_OFFICIAL_STATES = ("HI", "WY")
STATE_CODES = (
    "AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "IA", "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD",
    "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND", "NE", "NH",
    "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY",
)


def _encoded(value):
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ) + "\n").encode()


def _compressed(body):
    compressed = gzip.compress(body, compresslevel=9, mtime=0)
    return compressed[:9] + bytes([3]) + compressed[10:]


def _pin(body):
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def _artifact(value):
    decoded = _encoded(value)
    body = _compressed(decoded)
    return {
        "content": value,
        "compression": "gzip",
        "media_type": "application/json",
        **_pin(body),
        "decoded_bytes": len(decoded),
        "decoded_sha256": hashlib.sha256(decoded).hexdigest(),
    }


def render_artifacts(result):
    """Return deterministic gzip bytes keyed by the paths declared by build()."""
    if result.get("contract") != CONTRACT:
        raise ValueError("Wrong automatic-estimates result contract")
    rendered = {}
    for path, artifact in result["artifacts"].items():
        body = _compressed(_encoded(artifact["content"]))
        expected = {key: artifact[key] for key in ("bytes", "sha256")}
        if _pin(body) != expected:
            raise ValueError("Artifact pin changed: " + path)
        rendered[path] = body
    return rendered


def _read_pinned(root, item):
    path = root / item["path"]
    body = path.read_bytes()
    if _pin(body) != {key: item[key] for key in ("bytes", "sha256")}:
        raise ValueError("Changed seed member: " + item["path"])
    decoded = gzip.decompress(body) if item.get("compression") == "gzip" else body
    if len(decoded) != item["decoded_bytes"] or hashlib.sha256(decoded).hexdigest() != item["decoded_sha256"]:
        raise ValueError("Changed decoded seed member: " + item["path"])
    return json.loads(decoded)


def load_seed(path):
    """Load and verify an exported safe numerical seed directory."""
    root = Path(path)
    manifest = json.loads((root / "manifest.json").read_bytes())
    if (
        manifest.get("contract") != SEED_CONTRACT
        or manifest.get("election_date") != ELECTION_DATE
        or tuple(manifest.get("profiles", ())) != PROFILES
        or tuple(manifest.get("families", ())) != FAMILIES
    ):
        raise ValueError("Wrong automatic-estimates seed identity")
    seed = {key: copy.deepcopy(manifest[key]) for key in (
        "contract", "election_date", "profiles", "families", "qualification",
        "official_source_guards", "provenance",
    )}
    seed["accepted_candidates"] = _read_pinned(root, manifest["accepted_candidates"])
    seed["accepted_controls"] = _read_pinned(root, manifest["accepted_controls"])
    seed["participation_state_controls"] = _read_pinned(
        root, manifest["participation_state_controls"]
    )
    seed["scenarios"] = {}
    for key, scenario in manifest["scenarios"].items():
        seed["scenarios"][key] = {
            "profile": scenario["profile"],
            "family": scenario["family"],
            "prior": _read_pinned(root, scenario["prior"]),
            "accepted_result": _read_pinned(root, scenario["accepted_result"]),
        }
    seed["profile_viewers"] = {
        profile: _read_pinned(root, item)
        for profile, item in manifest["profile_viewers"].items()
    }
    _validate_seed(seed)
    return seed


def _validate_seed(seed):
    if (
        seed.get("contract") != SEED_CONTRACT
        or seed.get("election_date") != ELECTION_DATE
        or tuple(seed.get("profiles", ())) != PROFILES
        or tuple(seed.get("families", ())) != FAMILIES
    ):
        raise ValueError("Invalid seed contract")
    expected = {profile + "/" + family for profile in PROFILES for family in FAMILIES}
    if set(seed.get("scenarios", {})) != expected:
        raise ValueError("The safe seed must contain all nine profile/family scenarios")
    candidates = seed.get("accepted_candidates")
    if not isinstance(candidates, list) or len(candidates) != 1401:
        raise ValueError("The accepted 1,401-candidate inventory is required")
    districts = {row["district"] for row in candidates}
    if len(districts) != 435 or {row["state_code"] for row in candidates} != set(STATE_CODES):
        raise ValueError("The accepted 435-district/all-state inventory changed")
    qualified = tuple(seed["qualification"]["qualified_state_codes"])
    held = tuple(seed["qualification"]["held_state_codes"])
    if len(qualified) != 33 or len(held) != 17 or set(qualified) | set(held) != set(STATE_CODES):
        raise ValueError("The accepted 33-qualified/17-held mask changed")
    for state in PROTECTED_OFFICIAL_STATES:
        guard = seed["official_source_guards"].get(state)
        if not guard or guard.get("state_code") != state or not guard.get("guard_sha256"):
            raise ValueError("Missing official HI/WY source guard")
    controls = seed.get("participation_state_controls", {})
    if (
        controls.get("contract") != "participation.registered_control_display.v2"
        or controls.get("year") != 2026
        or controls.get("native_control_version") != 35
        or len(controls.get("states", ())) != 51
        or len(controls.get("scenarios", ())) != 34
        or len({row["state_code"] for row in controls["states"]}) != 51
        or len({row["control_id"] for row in controls["scenarios"]}) != 34
        or controls.get("model_variant_or_study_probabilities_changed") is not False
        or controls.get("native_outcome_fitting_applied") is not False
        or controls.get(
            "frame_exchangeability_or_observed_staying_home_qualified"
        ) is not False
    ):
        raise ValueError("Changed accepted public version35 registered controls")
    state_rows = {row["state_code"]: row for row in controls["states"]}
    if set(state_rows) != set(STATE_CODES) | {"DC"}:
        raise ValueError("Every state and D.C. control decision is required")
    for row in controls["scenarios"]:
        registered = Decimal(row["native_registered_denominator"])
        voter = Decimal(row["conditional_modeled_voter_count"])
        nonvoter = Decimal(row["conditional_modeled_nonvoter_count"])
        if (
            registered <= 0
            or voter < 0
            or nonvoter < 0
            or voter + nonvoter != registered
            or row["state_code"] not in state_rows
            or row["civic_source_n"] != state_rows[row["state_code"]]["civic_source_n"]
        ):
            raise ValueError("Changed registered-frame scenario accounting")
    reference_mask = None
    for key, scenario in seed["scenarios"].items():
        prior, result = scenario["prior"], scenario["accepted_result"]
        if (
            prior.get("contract") != "participation.norc_house_demographic_priors.v1"
            or prior.get("raw_records_or_private_fine_cells_exported") is not False
            or prior.get("old_synthetic_state_couplings_used") is not False
            or result.get("contract") != "participation.norc_house_demographic_model.v1"
            or len(result.get("rows", ())) != 50
        ):
            raise ValueError("Unsafe or incomplete public House seed: " + key)
        mask = tuple(sorted(
            row["state_code"] for row in result["rows"] if row["source_comparison_available"]
        ))
        if reference_mask is None:
            reference_mask = mask
        if mask != reference_mask or mask != tuple(sorted(qualified)):
            raise ValueError("Scenario qualification masks differ")


def _integer(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a candidate count")
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ValueError("Candidate count must be a nonnegative literal integer")


def _party_group(party):
    label = str(party).strip().lower()
    if label in ("democratic", "democrat", "dem"):
        return "D"
    if label in ("republican", "rep"):
        return "R"
    return "O"


def _candidate_key(row):
    return (
        str(row.get("district", "")),
        str(row.get("name", "")),
        str(row.get("party", "")),
    )


def _candidate_source(row):
    source = row.get("source")
    if isinstance(source, dict):
        return source.get("url") or source.get("id") or json.dumps(source, sort_keys=True)
    return source


def _margin(counts):
    if counts["D"] <= 0 or counts["R"] <= 0:
        raise ValueError("A positive D/R denominator is required")
    return float(Fraction(100 * (counts["D"] - counts["R"]), counts["D"] + counts["R"]))


def _totals(rows):
    result = {"D": 0, "R": 0, "O": 0}
    for row in rows:
        result[_party_group(row["party"])] += _integer(row["votes"])
    return result


def _recorded(state, previous, counts, source_status, source_labels, fresh):
    denominator = counts["D"] + counts["R"]
    previous_denominator = previous["D"] + previous["R"]
    previous_margin = (
        _margin(previous) if previous["D"] > 0 and previous["R"] > 0 else None
    )
    current_margin = _margin(counts) if counts["D"] > 0 and counts["R"] > 0 else None
    return {
        "state_code": state,
        "previous": copy.deepcopy(previous),
        "current": copy.deepcopy(counts),
        "D": counts["D"],
        "R": counts["R"],
        "O": counts["O"],
        "candidate_votes": sum(counts.values()),
        "major_party_votes": denominator,
        "previous_democratic_two_party_share_pct":
            100 * previous["D"] / previous_denominator if previous_denominator else None,
        "democratic_two_party_share_pct": 100 * counts["D"] / denominator if denominator else None,
        "previous_margin_pp": previous_margin,
        "margin_pp": current_margin,
        "recorded_margin_change_pp":
            current_margin - previous_margin
            if current_margin is not None and previous_margin is not None else None,
        "fresh_reported_inventory": fresh,
        "source_status": source_status,
        "source_update_labels": sorted(set(label for label in source_labels if label is not None)),
        "candidate_votes_are_not_ballots_or_turnout": True,
    }


def _blocked_house_sources(snapshot, state):
    blocked = []
    prefix = "house-" + state
    for row in snapshot.get("source_status", []):
        source = str(row.get("source", ""))
        status = str(row.get("status", ""))
        if source.startswith(prefix) and status != "reported":
            blocked.append({"source": source, "status": status, "error": row.get("error")})
    return blocked


def _official_guard_ok(rows, guard):
    supplied = set()
    for row in rows:
        source = row.get("source")
        if isinstance(source, dict):
            supplied.add(source.get("automatic_estimates_official_scope"))
    return supplied == {guard["guard_sha256"]}


def _house_decisions(snapshot, seed):
    accepted = seed["accepted_candidates"]
    by_state = {state: [] for state in STATE_CODES}
    for row in accepted:
        by_state[row["state_code"]].append(row)
    incoming = {state: [] for state in STATE_CODES}
    global_issues = []
    for index, row in enumerate(snapshot.get("house_candidates", [])):
        state = row.get("state_code")
        if state not in incoming:
            global_issues.append({"row": index, "reason": "unknown_state_code", "state_code": state})
            continue
        incoming[state].append(row)
    qualification = set(seed["qualification"]["qualified_state_codes"])
    controls = {row["state_code"]: row for row in seed["accepted_controls"]["return_controls"]}
    accepted_counts = {state: _totals(rows) for state, rows in by_state.items()}
    accepted_reference = {
        row["state_code"]: row
        for row in seed["scenarios"][
            "original/accepted_ridge_multinomial"
        ]["accepted_result"]["rows"]
    }
    previous_counts = {}
    for state, row in accepted_reference.items():
        comparison = row["reported_comparison"]
        previous = comparison.get("previous")
        if previous is None:
            previous = (row.get("contest_comparability") or {}).get("previous_counts")
        if not previous or set(previous) != set("DRO"):
            raise ValueError("Missing accepted previous House counts for " + state)
        previous_counts[state] = copy.deepcopy(previous)
    decisions, comparisons, recorded = [], {}, []
    for state in STATE_CODES:
        expected_rows = by_state[state]
        rows = incoming[state]
        fresh_rows = [row for row in rows if row.get("status") == "reported"]
        blocked = _blocked_house_sources(snapshot, state)
        accepted_control = controls[state]
        reason = None
        action = "retained_accepted_snapshot"
        counts = accepted_counts[state]
        fresh_complete = False
        source_labels = []
        if fresh_rows:
            expected_keys = [_candidate_key(row) for row in expected_rows]
            actual_keys = [_candidate_key(row) for row in rows]
            if len(actual_keys) != len(set(actual_keys)):
                reason = "duplicate_candidate_identity"
            elif set(actual_keys) != set(expected_keys):
                reason = "candidate_identity_party_or_scope_changed"
            elif any(row.get("status") != "reported" for row in rows):
                reason = "mixed_fresh_and_retained_candidate_inventory"
            elif any(str(row.get("year")) != "2026" for row in rows):
                reason = "wrong_candidate_year"
            elif state in PROTECTED_OFFICIAL_STATES and not _official_guard_ok(
                rows, seed["official_source_guards"][state]
            ):
                reason = "accepted_official_HI_WY_scope_cannot_be_replaced_by_provider_rows"
            else:
                try:
                    counts = _totals(rows)
                    if counts["D"] <= 0 or counts["R"] <= 0:
                        reason = "nonpositive_major_party_endpoint"
                    else:
                        fresh_complete = True
                        source_labels = [row.get("source_update_label") for row in rows]
                except ValueError as error:
                    reason = str(error)
        elif rows and any(row.get("status") not in ("accepted_snapshot_not_refreshed",) for row in rows):
            reason = "no_complete_reported_candidate_inventory"
        elif blocked:
            reason = "fresh_house_source_blocked_or_failed"
        if reason:
            action = "held_retain_last_good"
            counts = accepted_counts[state]
        elif fresh_complete:
            if counts == accepted_counts[state]:
                action = "retained_fresh_unchanged"
            elif state in qualification:
                action = "changed_recompute_behavioral"
            else:
                action = "changed_recorded_behavioral_hold_preserved"
        recorded.append(_recorded(
            state, previous_counts[state], counts, action, source_labels, fresh_complete
        ))
        comparisons[state] = {
            "counts": counts,
            "fresh_complete": fresh_complete,
            "behaviorally_qualified": state in qualification,
            "changed": counts != accepted_counts[state],
            "accepted_counts": accepted_counts[state],
            "source_urls": sorted(set(
                str(value) for value in (_candidate_source(row) for row in rows) if value
            )),
            "source_update_labels": sorted(set(
                value for value in source_labels if value is not None
            )),
        }
        decisions.append({
            "state_code": state,
            "decision": action,
            "reason": reason,
            "fresh_candidate_rows": len(fresh_rows),
            "candidate_inventory_rows": len(rows),
            "expected_candidate_rows": len(expected_rows),
            "expected_districts": len({row["district"] for row in expected_rows}),
            "blocked_sources": blocked,
            "behaviorally_qualified": state in qualification,
            "behavioral_hold_preserved": state not in qualification,
            "accepted_official_scope_preserved": state not in PROTECTED_OFFICIAL_STATES or not fresh_complete
                or _official_guard_ok(rows, seed["official_source_guards"][state]),
            "recorded_counts_changed": counts != accepted_counts[state],
        })
    return decisions, comparisons, recorded, global_issues


def _new_comparisons(accepted, endpoint_states, changed_states):
    result = {}
    old_rows = {row["state_code"]: row for row in accepted["rows"]}
    for state in changed_states:
        old = copy.deepcopy(old_rows[state]["reported_comparison"])
        current = endpoint_states[state]["counts"]
        previous = old["previous"]
        old.update(
            status="reported_source_comparison",
            current=copy.deepcopy(current),
            previous_margin_pp=_margin(previous),
            current_margin_pp=_margin(current),
            reported_change_pp=_margin(current) - _margin(previous),
            current_snapshot="automatic-results:" + hashlib.sha256(_encoded({
                "state_code": state,
                "counts": current,
                "source_urls": endpoint_states[state]["source_urls"],
                "source_update_labels": endpoint_states[state]["source_update_labels"],
            })).hexdigest(),
            current_native_clock=endpoint_states[state]["source_update_labels"] or None,
            current_source_scope=(
                "Complete same-district accepted candidate inventory; reported candidate votes, "
                "not ballots, turnout, or observed individual histories"
            ),
            automatic_estimate_update={
                "candidate_identity_party_scope_stable": True,
                "complete_same_district_inventory": True,
                "source_urls": endpoint_states[state]["source_urls"],
                "source_update_labels": endpoint_states[state]["source_update_labels"],
            },
        )
        result[state] = old
    return result


def _incremental_result(prior, accepted, endpoint_states, changed_states):
    changed = sorted(changed_states)
    if not changed:
        return copy.deepcopy(accepted)
    comparisons = _new_comparisons(accepted, endpoint_states, changed)
    accepted_input = {
        "rows": [
            {
                "office": "house",
                "state_code": row["state_code"],
                "reported_comparison": copy.deepcopy(
                    comparisons.get(row["state_code"], row["reported_comparison"])
                ),
            }
            for row in accepted["rows"]
        ]
    }
    calculated = accepted_model.build(prior, accepted_input, state_codes=changed)
    result = copy.deepcopy(accepted)
    for field in (
        "rows", "complete_assumption_cases", "complete_seed_cases",
        "complete_demographic_seed_cases",
    ):
        retained = [
            row for row in accepted[field] if row["state_code"] not in changed_states
        ]
        result[field] = sorted(
            retained + calculated[field],
            key=lambda row: (
                row["state_code"], row.get("frame_scale", 0), row.get("affinity", 0),
                row.get("seed", 0), row.get("dimension", "")
            ),
        )
        if len(result[field]) != len(accepted[field]):
            raise ValueError("A complete accepted state/query inventory changed")
    accepted_mask = {
        row["state_code"] for row in accepted["rows"] if row["source_comparison_available"]
    }
    result_mask = {
        row["state_code"] for row in result["rows"] if row["source_comparison_available"]
    }
    if result_mask != accepted_mask:
        raise ValueError("Incremental refresh changed the qualification mask")
    anchored = [row for row in result["rows"] if row["source_comparison_available"]]
    result["preconditioning_margin_MAE_pp"] = math.fsum(
        abs(row["before_current_party_conditioning"][
            "prediction_error_observed_minus_predicted_pp"
        ])
        for row in anchored
    ) / len(anchored)
    result["summary"] = copy.deepcopy(accepted["summary"])
    result["comparison_policy"] = copy.deepcopy(accepted["comparison_policy"])
    result["comparison_policy"].update(
        automatic_changed_state_scenarios_recomputed=changed,
        automatic_other_state_numerics_and_complete_queries_reused=True,
        source_model_refitted=False,
        source_weights_changed=False,
        existing_behavioral_holds_preserved=True,
    )
    result["endpoint_update"] = {
        "contract": CONTRACT,
        "changed_states": changed,
        "source_model_refitted": False,
        "source_weights_changed": False,
        "unchanged_state_numerics_and_seeds_reused": True,
        "qualification_mask_preserved": True,
        "official_HI_WY_scope_preserved": True,
        "candidate_votes_are_not_ballots_or_turnout": True,
    }
    return result


def _state_comparisons(results):
    rows = []
    for family in FAMILIES:
        for state in results[family]["rows"]:
            point = state["point"]
            prediction = state["before_current_party_conditioning"]
            observed = state["reported_comparison"] if state["source_comparison_available"] else None
            row = {
                "family": family,
                "state_code": state["state_code"],
                "observed_comparison_available": observed is not None,
                "observed_previous_margin_pp": observed["previous_margin_pp"] if observed else None,
                "observed_current_margin_pp": observed["current_margin_pp"] if observed else None,
                "observed_margin_change_pp": observed["reported_change_pp"] if observed else None,
                "observed_Democratic_two_party_share_previous_pct":
                    50 + observed["previous_margin_pp"] / 2 if observed else None,
                "observed_Democratic_two_party_share_current_pct":
                    50 + observed["current_margin_pp"] / 2 if observed else None,
                "observed_Democratic_two_party_share_change_pp":
                    observed["reported_change_pp"] / 2 if observed else None,
                "predicted_current_margin_before_party_conditioning_pp":
                    prediction["current_margin_pp"] if prediction else None,
                "observed_minus_predicted_margin_pp":
                    prediction["prediction_error_observed_minus_predicted_pp"]
                    if prediction else None,
                "observed_minus_predicted_Democratic_two_party_share_pp":
                    prediction["prediction_error_observed_minus_predicted_pp"] / 2
                    if prediction else None,
                "gross_retained_share_pct": state["gross_outcomes"]["retaining"] * 100,
                "gross_switched_share_pct": state["gross_outcomes"]["switching"] * 100,
                "gross_modeled_exit_share_pct": state["gross_outcomes"]["exit"] * 100,
                "model_family_not_independent_behavioral_truth": True,
            }
            for key, value in point["contributions_pp"].items():
                row[key + "_margin_pp"] = value
                row[key + "_Democratic_two_party_share_pp"] = value / 2
            row["net_participation_margin_pp"] = point["net_participation_pp"]
            row["net_participation_Democratic_two_party_share_pp"] = (
                point["net_participation_pp"] / 2
            )
            rows.append(row)
    return rows


def _dispersion(results):
    values = {
        family: {row["state_code"]: row for row in result["rows"]}
        for family, result in results.items()
    }
    rows = []
    for code in sorted(values[FAMILIES[0]]):
        available = values[FAMILIES[0]][code]["source_comparison_available"]
        for key in (*MECHANISMS, "net_participation"):
            estimates = [
                values[family][code]["point"]["net_participation_pp"]
                if key == "net_participation"
                else values[family][code]["point"]["contributions_pp"][key]
                for family in FAMILIES
            ]
            rows.append({
                "state_code": code,
                "mechanism": key,
                "families": len(FAMILIES),
                "observed_comparison_available": available,
                "minimum_margin_pp": min(estimates),
                "maximum_margin_pp": max(estimates),
                "family_spread_margin_pp": max(estimates) - min(estimates),
                "minimum_Democratic_two_party_share_pp": min(estimates) / 2,
                "maximum_Democratic_two_party_share_pp": max(estimates) / 2,
                "confidence_interval": False,
                "identified_behavioral_effect": False,
            })
    return rows


def _participation(snapshot, seed):
    display = copy.deepcopy(seed["participation_state_controls"])
    scenarios = {row["control_id"]: row for row in display["scenarios"]}
    selected_states = {row["state_code"]: row for row in display["states"]}
    decisions = []
    for item in snapshot.get("participation_observations", []):
        state = item.get("state_code")
        if not state or item.get("status") != "reported":
            continue
        observation = item.get("observation") or {}
        ballots = observation.get("ballots")
        denominator = observation.get("denominator")
        basis = observation.get("denominator_basis")
        if denominator is None or not basis:
            continue
        try:
            denominator = _integer(denominator)
            ballots = _integer(ballots) if ballots is not None else None
        except ValueError:
            decisions.append({
                "state_code": state, "decision": "held_invalid_native_reference"
            })
            continue
        if (
            denominator <= 0
            or (ballots is not None and ballots > denominator)
            or "registered" not in str(basis)
        ):
            decisions.append({
                "state_code": state, "decision": "held_registration_frame_check_failed",
                "native_ballots": ballots, "native_denominator": denominator,
                "denominator_basis": basis,
            })
            continue
        requested = observation.get("control_id")
        matches = [
            row for row in display["scenarios"]
            if row["state_code"] == state
            and row["native_denominator_basis"] == basis
            and (requested is None or row["control_id"] == requested)
        ]
        if len(matches) != 1:
            decisions.append({
                "state_code": state,
                "decision": (
                    "held_ambiguous_registered_frame"
                    if len(matches) > 1 else "native_registered_reference_only"
                ),
                "native_ballots": ballots,
                "native_registered_denominator": denominator,
                "denominator_basis": basis,
                "matching_accepted_scenarios": [row["control_id"] for row in matches],
                "local_or_demographic_estimate": False,
            })
            continue
        scenario = scenarios[matches[0]["control_id"]]
        old_registered = Decimal(scenario["native_registered_denominator"])
        old_voter = Decimal(scenario["conditional_modeled_voter_count"])
        old_nonvoter = Decimal(scenario["conditional_modeled_nonvoter_count"])
        if old_voter + old_nonvoter != old_registered:
            raise ValueError("Accepted registered scenario no longer reconciles")
        new_registered = Decimal(denominator)
        if new_registered == old_registered:
            new_voter, new_nonvoter = old_voter, old_nonvoter
        else:
            with localcontext() as context:
                context.prec = 100
                new_voter = old_voter * new_registered / old_registered
                new_nonvoter = new_registered - new_voter
        source_label = observation.get("source_update_label")
        source = item.get("source") or observation.get("source")
        source_url = (
            source.get("url") if isinstance(source, dict) else source
        ) or observation.get("source_url") or scenario["source_url"]
        scenario.update(
            native_registered_denominator=format(new_registered, "f"),
            conditional_modeled_voter_count=format(new_voter, "f"),
            conditional_modeled_nonvoter_count=format(new_nonvoter, "f"),
            source_time_label=source_label,
            source_url=source_url,
        )
        selected = selected_states[state]
        if selected["control_id"] == scenario["control_id"]:
            selected.update(
                control_registered_denominator=format(new_registered, "f"),
                control_native_time=source_label,
                control_source_url=source_url,
            )
        decision = {
            "state_code": state,
            "control_id": scenario["control_id"],
            "decision": (
                "compatible_registered_frame_R_times_p_changed"
                if new_registered != old_registered
                else "compatible_registered_frame_R_times_p_retained"
            ),
            "denominator_basis": basis,
            "previous_registered_denominator": format(old_registered, "f"),
            "current_registered_denominator": format(new_registered, "f"),
            "registered_denominator_difference": format(
                new_registered - old_registered, "f"
            ),
            "previous_conditional_modeled_voter_count": format(old_voter, "f"),
            "conditional_modeled_voter_count": format(new_voter, "f"),
            "conditional_modeled_voter_unit_difference": format(
                new_voter - old_voter, "f"
            ),
            "previous_conditional_modeled_nonvoter_count": format(old_nonvoter, "f"),
            "conditional_modeled_nonvoter_count": format(new_nonvoter, "f"),
            "conditional_modeled_nonvoter_unit_difference": format(
                new_nonvoter - old_nonvoter, "f"
            ),
            "native_ballots": ballots,
            "native_clock": source_label,
            "native_clock_supplied": source_label is not None,
            "source_url": source_url,
            "frozen_civic_probability_numerator": format(old_voter, "f"),
            "frozen_civic_probability_denominator": format(old_registered, "f"),
            "source_weights_probabilities_and_fits_unchanged": True,
            "frame_exchangeability_or_observed_staying_home_qualified": False,
            "native_outcome_fitting_applied": False,
            "local_or_demographic_estimate": False,
        }
        if ballots is not None:
            decision.update(
                native_registered_fraction=ballots / denominator,
                native_minus_conditional_modeled_voter_count=format(
                    Decimal(ballots) - new_voter, "f"
                ),
                native_minus_model_is_not_validation_or_observed_staying_home=True,
            )
        decisions.append(decision)
    changed = [
        row for row in decisions
        if row["decision"] == "compatible_registered_frame_R_times_p_changed"
    ]
    compatible = [
        row for row in decisions
        if row["decision"].startswith("compatible_registered_frame_R_times_p_")
    ]
    display["automatic_update"] = {
        "contract": "participation.automatic_registered_control_update.v1",
        "base_native_control_version": 35,
        "accepted_state_decisions_retained": 51,
        "accepted_scenarios_retained": 34,
        "fresh_compatible_scenarios": len(compatible),
        "changed_registered_frames": len(changed),
        "fresh_jurisdictions": sorted({row["state_code"] for row in compatible}),
        "decisions": decisions,
        "new_scenarios_created": 0,
        "source_weights_probabilities_or_fits_changed": False,
        "frame_exchangeability_or_observed_staying_home_qualified": False,
        "native_outcome_fitting_applied": False,
        "unsupported_local_or_demographic_estimates_created": False,
        "coverage_claim": (
            "All 51 accepted control decisions and 34 accepted scenarios are retained; "
            "only explicitly listed fresh compatible scenarios were refreshed."
        ),
    }
    return display


def _metric_values(row, group=None):
    point = row["point"] if group is None else group
    contributions = point["contributions_pp"]
    result = {
        key: contributions[key]
        for key in ("switching", "exit", "entry", "other_choice", "unresolved")
    }
    result["modeled_nonparticipation"] = point["net_participation_pp"]
    result["total"] = (
        point["total_change_pp"] if group is None else point["total_contribution_pp"]
    )
    gross = row.get("gross_outcomes") if group is None else group.get("gross_outcomes")
    result["retaining"] = gross.get("retaining") if gross else None
    return result


def _sensitivity(profile_viewers, source_pins):
    metrics = (
        "switching", "exit", "entry", "modeled_nonparticipation",
        "other_choice", "unresolved", "total", "retaining",
    )
    variants = []
    for profile in PROFILES:
        data = profile_viewers[profile]
        for family in FAMILIES:
            variants.append((
                profile + "|" + family,
                {row["state_code"]: row for row in data["families"][family]["rows"]},
            ))
    baseline = variants[0][1]
    output = []
    for code in sorted(STATE_CODES):
        original = baseline[code]
        qualified = original["source_comparison_available"]
        groups = {
            item["dimension"] + "|" + item["group"]: item
            for item in original["groups"]
        }
        grouped_variants = {}
        for identifier, rows in variants:
            row = rows[code]
            other = {
                item["dimension"] + "|" + item["group"]: item
                for item in row["groups"]
            }
            if (
                row["source_comparison_available"] is not qualified
                or row["reported_comparison"] != original["reported_comparison"]
                or set(other) != set(groups)
                or any(
                    other[key]["available"] is not groups[key]["available"]
                    for key in groups
                )
            ):
                raise ValueError("Nine-variant endpoint or disclosure masks differ")
            grouped_variants[identifier] = other
        scopes = {}
        for key in ("", *sorted(groups)):
            supported = qualified and (not key or groups[key]["available"])
            reason = None if supported else (
                original["reported_comparison"].get("reason") if not qualified
                else groups[key].get("reason") or "Source demographic group is withheld"
            )
            ranges = {metric: None for metric in metrics}
            if supported:
                matrix = {
                    identifier: _metric_values(
                        rows[code], grouped_variants[identifier][key] if key else None
                    )
                    for identifier, rows in variants
                }
                for metric in metrics:
                    values = [matrix[identifier][metric] for identifier, _ in variants]
                    if all(type(value) in (int, float) and math.isfinite(value) for value in values):
                        ranges[metric] = {
                            "minimum": min(values),
                            "maximum": max(values),
                            "default": values[0],
                            "variants": 9,
                        }
            scopes[key] = {"available": supported, "reason": reason, "metrics": ranges}
        comparison = original["reported_comparison"]
        output.append({
            "state_code": code,
            "qualified": qualified,
            "reason": None if qualified else comparison.get("reason"),
            "endpoint": {
                "snapshot": comparison.get("current_snapshot"),
                "native_clock": comparison.get("current_native_clock"),
                "counting_complete_independently_qualified": comparison.get(
                    "current_counting_complete_independently_qualified"
                ),
                "source_coverage_certified": comparison.get("source_coverage_certified"),
            },
            "scopes": scopes,
        })
    widths = {}
    for metric in ("switching", "modeled_nonparticipation", "entry", "other_choice"):
        values = [
            row["scopes"][""]["metrics"][metric]["maximum"]
            - row["scopes"][""]["metrics"][metric]["minimum"]
            for row in output
            if row["qualified"] and row["scopes"][""]["metrics"][metric] is not None
        ]
        ordered = sorted(values)
        median = (
            ordered[len(ordered) // 2] if len(ordered) % 2
            else (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2
        ) if ordered else None
        widths[metric] = {
            "median": median,
            "maximum": max(values) if values else None,
            "states_with_complete_variants": len(values),
        }
    return {
        "contract": "participation.house_model_sensitivity.v1",
        "source_pins": source_pins,
        "profiles": list(PROFILES),
        "families": list(FAMILIES),
        "default_variant": "original|accepted_ridge_multinomial",
        "variant_count": 9,
        "contribution_units": "statewide_D_minus_R_margin_percentage_points",
        "retaining_units": "fraction_of_model_assigned_prior_DR_mass",
        "group_ranges_are_not_group_vote_shares": True,
        "confidence_intervals": None,
        "not_all_model_survey_transport_or_endpoint_uncertainty": True,
        "source_fits_reproduced": False,
        "fitted_aggregate_projection_replay_only": True,
        "new_models_or_weights_or_source_counts": False,
        "summary": {
            "states": 50,
            "qualified_states": sum(row["qualified"] for row in output),
            "held_states": sum(not row["qualified"] for row in output),
            "group_decisions": sum(len(row["scopes"]) - 1 for row in output),
            "supported_group_decisions": sum(
                scope["available"] for row in output
                for key, scope in row["scopes"].items() if key
            ),
            "statewide_spread_margin_pp": widths,
        },
        "rows": output,
    }


def _shared_max_abs_margin(profile_viewers, recorded):
    recorded_by_state = {row["state_code"]: row for row in recorded}
    groups = {""}
    for viewer in profile_viewers.values():
        for model in viewer["families"].values():
            for row in model["rows"]:
                groups.update(
                    group["dimension"] + "|" + group["group"]
                    for group in row["groups"]
                    if group["available"]
                )
    result = {}
    for group_key in sorted(groups):
        maximum = 0.0
        for viewer in profile_viewers.values():
            for model in viewer["families"].values():
                for row in model["rows"]:
                    recorded_change = recorded_by_state[row["state_code"]][
                        "recorded_margin_change_pp"
                    ]
                    if recorded_change is not None:
                        maximum = max(maximum, abs(recorded_change))
                    if not row["source_comparison_available"]:
                        continue
                    maximum = max(
                        maximum, abs(row["reported_comparison"]["reported_change_pp"])
                    )
                    selected = None
                    if group_key:
                        selected = next((
                            item for item in row["groups"]
                            if item["dimension"] + "|" + item["group"] == group_key
                            and item["available"]
                        ), None)
                        if selected is None:
                            continue
                    values = _metric_values(row, selected)
                    for key, value in values.items():
                        if key != "retaining" and value is not None:
                            maximum = max(maximum, abs(value))
        result[group_key] = maximum
    return result


def bind_publication(result, base_url, complete_download):
    """Bind relative artifact paths to immutable URLs after parent publication."""
    if result.get("contract") != CONTRACT:
        raise ValueError("Wrong automatic-estimates result contract")
    if not isinstance(base_url, str) or not base_url.startswith("https://"):
        raise ValueError("An immutable HTTPS artifact base URL is required")
    required = ("url", "bytes", "sha256", "media_type")
    if (
        not isinstance(complete_download, dict)
        or any(key not in complete_download for key in required)
        or complete_download["media_type"] != "application/zip"
        or not isinstance(complete_download["bytes"], int)
        or complete_download["bytes"] <= 0
        or not isinstance(complete_download["sha256"], str)
        or len(complete_download["sha256"]) != 64
    ):
        raise ValueError("A complete pinned ZIP descriptor is required")
    bound = copy.deepcopy(result)
    sources = bound["house_sources"]
    sources["base_url"] = base_url.rstrip("/")
    sources["publication_bound"] = True
    sources["complete_download"] = {
        "required": True,
        "path": sources["complete_download"]["path"],
        **copy.deepcopy(complete_download),
    }

    def bind(item):
        item["url"] = sources["base_url"] + "/" + item["path"]

    for descriptor in sources["descriptors"].values():
        bind(descriptor["complete_result"])
        bind(descriptor["viewer_data"])
    for descriptor in sources["profile_viewers"].values():
        bind(descriptor["viewer_data"])
    bind(sources["recorded_states"])
    bind(sources["sensitivity"])
    bind(sources["participation_state_projections"])
    bind(sources["next_seed"])
    return bound


def load_rolling_seed(value):
    """Validate a previously published rolling-seed JSON object."""
    seed = copy.deepcopy(value)
    _validate_seed(seed)
    return seed


def load_rolling_seed_bytes(body, descriptor):
    """Verify and decode a prior publication's pinned rolling-seed artifact."""
    required = (
        "bytes", "sha256", "decoded_bytes", "decoded_sha256", "compression"
    )
    if (
        not isinstance(body, bytes)
        or not isinstance(descriptor, dict)
        or any(key not in descriptor for key in required)
        or descriptor["compression"] != "gzip"
        or _pin(body) != {
            key: descriptor[key] for key in ("bytes", "sha256")
        }
    ):
        raise ValueError("Changed or incomplete rolling-seed artifact")
    decoded = gzip.decompress(body)
    if (
        len(decoded) != descriptor["decoded_bytes"]
        or hashlib.sha256(decoded).hexdigest() != descriptor["decoded_sha256"]
    ):
        raise ValueError("Changed decoded rolling-seed artifact")
    return load_rolling_seed(json.loads(decoded))


def _advanced_seed(snapshot, seed, decisions, artifacts, participation):
    advanced = copy.deepcopy(seed)
    advanced["participation_state_controls"] = copy.deepcopy(participation)
    for profile in PROFILES:
        advanced["profile_viewers"][profile] = copy.deepcopy(
            artifacts["house/viewer-" + profile + ".json.gz"]["content"]
        )
        for family in FAMILIES:
            key = profile + "/" + family
            advanced["scenarios"][key]["accepted_result"] = copy.deepcopy(
                artifacts["house/" + key + "/complete-result.json.gz"]["content"]
            )
    accepted_actions = {
        "changed_recompute_behavioral",
        "changed_recorded_behavioral_hold_preserved",
        "retained_fresh_unchanged",
    }
    accepted_states = {
        row["state_code"] for row in decisions if row["decision"] in accepted_actions
    }
    incoming = {state: {} for state in accepted_states}
    for row in snapshot.get("house_candidates", []):
        state = row.get("state_code")
        if state in incoming and row.get("status") == "reported":
            incoming[state][_candidate_key(row)] = row
    for row in advanced["accepted_candidates"]:
        state = row["state_code"]
        if state not in accepted_states:
            continue
        fresh = incoming[state][_candidate_key(row)]
        row["votes"] = str(_integer(fresh["votes"]))
        row["source_updated_at"] = fresh.get("source_update_label")
        source = fresh.get("source")
        row["source_url"] = (
            source.get("url") if isinstance(source, dict) else source
        )
    controls = {
        row["state_code"]: row
        for row in advanced["accepted_controls"]["return_controls"]
    }
    recorded = {
        row["state_code"]: row
        for row in artifacts["house/recorded-states.json.gz"]["content"]["states"]
    }
    model_rows = {
        row["state_code"]: row
        for row in advanced["scenarios"][
            "original/accepted_ridge_multinomial"
        ]["accepted_result"]["rows"]
    }
    for state in accepted_states:
        control = controls[state]
        control["current"] = copy.deepcopy(recorded[state]["current"])
        control["missing_candidate_control_indices"] = []
        fresh_rows = incoming[state]
        for row in control["full_candidate_control_rows"]:
            key = (row["district"], row["candidate"], row["literal_party"])
            fresh = fresh_rows[key]
            row.update(
                reported_district_votes=str(_integer(fresh["votes"])),
                located_county_rows=None,
                located_county_votes=None,
                located_minus_reported=None,
                independent_validation=False,
                status="automatic_last_good_reported_candidate_source",
            )
        comparison = model_rows[state]["reported_comparison"]
        if comparison["status"] == "reported_source_comparison":
            control["source_snapshot"] = comparison.get("current_snapshot")
            control["source_native_clock"] = comparison.get("current_native_clock")
            control["source_scope"] = comparison.get("current_source_scope")
        else:
            control["source_snapshot"] = "automatic-results:" + hashlib.sha256(
                _encoded({
                    "state_code": state,
                    "current": control["current"],
                    "candidate_rows": sorted(
                        (
                            key[0], key[1], key[2], str(_integer(value["votes"]))
                        )
                        for key, value in fresh_rows.items()
                    ),
                })
            ).hexdigest()
            labels = sorted({
                row.get("source_update_label") for row in fresh_rows.values()
                if row.get("source_update_label") is not None
            })
            control["source_native_clock"] = labels or None
            control["source_scope"] = (
                "Complete same-district accepted candidate inventory; recorded counts "
                "updated while the existing behavioral hold remains."
            )
    previous_generation = int(advanced["provenance"].get("rolling_generation", 0))
    advanced["provenance"].update(
        rolling_generation=previous_generation + 1,
        rolling_last_good_house_states=sorted(accepted_states),
        rolling_participation_fresh_controls=[
            row["control_id"] for row in participation.get(
                "automatic_update", {}
            ).get("decisions", [])
            if row.get("decision", "").startswith(
                "compatible_registered_frame_R_times_p_"
            )
        ],
        source_models_refitted=False,
        old_simulations_replayed=False,
        raw_respondents_or_private_fine_cells_exported=False,
    )
    _validate_seed(advanced)
    return advanced


def advance_seed(snapshot, seed, result):
    """Create the safe last-good seed for the next automatic run."""
    if result.get("contract") != CONTRACT:
        raise ValueError("Wrong automatic-estimates result contract")
    return _advanced_seed(
        snapshot,
        seed,
        result["decisions"]["states"],
        result["artifacts"],
        result["participation"],
    )


def build(snapshot, seed):
    """Build changed/retained/held decisions and all nine accepted-shape outputs."""
    _validate_seed(seed)
    if (
        snapshot.get("contract") != "participation.automatic_results_snapshot.v1"
        or snapshot.get("election_date") != ELECTION_DATE
    ):
        raise ValueError("Wrong results-intake snapshot contract or election")
    decisions, endpoints, recorded, global_issues = _house_decisions(snapshot, seed)
    changed_states = {
        row["state_code"] for row in decisions
        if row["decision"] == "changed_recompute_behavioral"
    }
    scenarios, artifacts, descriptors = {}, {}, {}
    profile_results = {profile: {} for profile in PROFILES}
    for profile in PROFILES:
        for family in FAMILIES:
            key = profile + "/" + family
            scenario = seed["scenarios"][key]
            result = _incremental_result(
                scenario["prior"], scenario["accepted_result"], endpoints, changed_states
            )
            profile_results[profile][family] = result
            result_path = "house/" + key + "/complete-result.json.gz"
            viewer_path = "house/" + key + "/viewer-data.json.gz"
            result_artifact = _artifact(result)
            viewer_artifact = _artifact({
                name: value for name, value in result.items()
                if not name.startswith("complete_")
            })
            artifacts[result_path] = result_artifact
            artifacts[viewer_path] = viewer_artifact
            scenario_version = hashlib.sha256(
                (result_artifact["decoded_sha256"] + viewer_artifact["decoded_sha256"]).encode()
            ).hexdigest()
            descriptor = {
                "contract": DESCRIPTOR_CONTRACT,
                "control_key": key,
                "profile": profile,
                "family": family,
                "election_date": ELECTION_DATE,
                "version": scenario_version,
                "estimate_contract": "participation.norc_house_demographic_model.v1",
                "qualified_state_codes": seed["qualification"]["qualified_state_codes"],
                "held_state_codes": seed["qualification"]["held_state_codes"],
                "qualification_mask_sha256": seed["qualification"]["mask_sha256"],
                "hold_identity_sha256": seed["qualification"]["hold_identity_sha256"],
                "gate_identity_sha256": seed["qualification"]["gate_identity_sha256"],
                "official_source_guard_sha256": seed["qualification"]["official_source_guard_sha256"],
                "official_source_states": list(PROTECTED_OFFICIAL_STATES),
                "changed_states": sorted(changed_states),
                "complete_result": {
                    "path": result_path,
                    **{name: result_artifact[name] for name in (
                        "compression", "media_type", "bytes", "sha256",
                        "decoded_bytes", "decoded_sha256",
                    )},
                },
                "viewer_data": {
                    "path": viewer_path,
                    **{name: viewer_artifact[name] for name in (
                        "compression", "media_type", "bytes", "sha256",
                        "decoded_bytes", "decoded_sha256",
                    )},
                },
                "source_model_refitted": False,
                "source_weights_changed": False,
                "unchanged_state_numerics_and_complete_queries_reused": True,
                "existing_17_behavioral_holds_preserved": True,
                "official_HI_WY_scope_guarded": True,
            }
            descriptors[key] = descriptor
            scenarios[key] = {
                "profile": profile,
                "family": family,
                "version": scenario_version,
                "recomputed_states": sorted(changed_states),
                "retained_states": sorted(set(STATE_CODES) - changed_states),
            }
    profile_viewers, profile_descriptors = {}, {}
    for profile in PROFILES:
        results = profile_results[profile]
        viewer = copy.deepcopy(seed["profile_viewers"][profile])
        viewer["families"] = {
            family: {
                name: value for name, value in result.items()
                if not name.startswith("complete_")
            }
            for family, result in results.items()
        }
        viewer["state_comparisons"] = _state_comparisons(results)
        viewer["family_dispersion"] = _dispersion(results)
        viewer["summary"].update(
            source_models_refitted=False,
            automatic_changed_states=sorted(changed_states),
            automatic_unchanged_state_numerics_reused=True,
            margin_MAE_pp={
                family: result["preconditioning_margin_MAE_pp"]
                for family, result in results.items()
            },
            Democratic_two_party_share_MAE_pp={
                family: result["preconditioning_margin_MAE_pp"] / 2
                for family, result in results.items()
            },
        )
        viewer["comparison_policy"] = results[FAMILIES[0]]["comparison_policy"]
        viewer["automatic_estimate_update"] = {
            "contract": CONTRACT,
            "changed_states": sorted(changed_states),
            "qualification_mask_sha256": seed["qualification"]["mask_sha256"],
            "existing_17_behavioral_holds_preserved": True,
            "official_HI_WY_scope_guarded": True,
        }
        path = "house/viewer-" + profile + ".json.gz"
        artifact = _artifact(viewer)
        artifacts[path] = artifact
        profile_viewers[profile] = {
            "path": path,
            **{name: artifact[name] for name in (
                "compression", "media_type", "bytes", "sha256",
                "decoded_bytes", "decoded_sha256",
            )},
        }
        profile_descriptors[profile] = {
            "contract": "participation.automatic_house_profile_viewer.v1",
            "profile": profile,
            "families": list(FAMILIES),
            "control_keys": [profile + "/" + family for family in FAMILIES],
            "viewer_data": profile_viewers[profile],
        }
    recorded_artifact = _artifact({
        "contract": "participation.automatic_recorded_house_states.v1",
        "election_date": ELECTION_DATE,
        "states": recorded,
    })
    participation = _participation(snapshot, seed)
    participation_artifact = _artifact(participation)
    artifacts["house/recorded-states.json.gz"] = recorded_artifact
    artifacts["participation/registered-control-display.json.gz"] = participation_artifact
    sensitivity = _sensitivity(
        {
            profile: artifacts[
                "house/viewer-" + profile + ".json.gz"
            ]["content"]
            for profile in PROFILES
        },
        {
            profile: copy.deepcopy(profile_viewers[profile])
            for profile in PROFILES
        },
    )
    sensitivity_artifact = _artifact(sensitivity)
    artifacts["house/sensitivity.json.gz"] = sensitivity_artifact
    shared_max_abs_margin = _shared_max_abs_margin(
        {
            profile: artifacts[
                "house/viewer-" + profile + ".json.gz"
            ]["content"]
            for profile in PROFILES
        },
        recorded,
    )
    decision_summary = {
        "states": 50,
        "changed_behavioral": len(changed_states),
        "recorded_changed_behavioral_hold_preserved": sum(
            row["decision"] == "changed_recorded_behavioral_hold_preserved"
            for row in decisions
        ),
        "held_retain_last_good": sum(
            row["decision"] == "held_retain_last_good" for row in decisions
        ),
        "retained": sum(row["decision"].startswith("retained") for row in decisions),
        "qualified_states": 33,
        "held_states": 17,
    }
    next_seed = _advanced_seed(
        snapshot, seed, decisions, artifacts, participation
    )
    next_seed_artifact = _artifact(next_seed)
    artifacts["rolling/next-seed.json.gz"] = next_seed_artifact
    global_version = hashlib.sha256(_encoded({
        "artifacts": {
            path: artifact["sha256"] for path, artifact in sorted(artifacts.items())
        },
        "qualification_mask_sha256": seed["qualification"]["mask_sha256"],
    })).hexdigest()
    house_sources = {
        "contract": HOUSE_SOURCES_CONTRACT,
        "election_date": ELECTION_DATE,
        "version": global_version,
        "base_url": None,
        "publication_bound": False,
        "profiles": list(PROFILES),
        "families": list(FAMILIES),
        "controls": {
            profile: {family: profile + "/" + family for family in FAMILIES}
            for profile in PROFILES
        },
        "descriptors": descriptors,
        "profile_viewers": profile_descriptors,
        "recorded_states": {
            "contract": "participation.automatic_recorded_house_states.v1",
            "path": "house/recorded-states.json.gz",
            **{name: recorded_artifact[name] for name in (
                "compression", "media_type", "bytes", "sha256",
                "decoded_bytes", "decoded_sha256",
            )},
        },
        "sensitivity": {
            "contract": "participation.house_model_sensitivity.v1",
            "path": "house/sensitivity.json.gz",
            **{name: sensitivity_artifact[name] for name in (
                "compression", "media_type", "bytes", "sha256",
                "decoded_bytes", "decoded_sha256",
            )},
        },
        "shared_max_abs_margin": shared_max_abs_margin,
        "participation_state_projections": {
            "contract": "participation.registered_control_display.v2",
            "path": "participation/registered-control-display.json.gz",
            **{name: participation_artifact[name] for name in (
                "compression", "media_type", "bytes", "sha256",
                "decoded_bytes", "decoded_sha256",
            )},
        },
        "next_seed": {
            "contract": SEED_CONTRACT,
            "path": "rolling/next-seed.json.gz",
            **{name: next_seed_artifact[name] for name in (
                "compression", "media_type", "bytes", "sha256",
                "decoded_bytes", "decoded_sha256",
            )},
        },
        "qualification": copy.deepcopy(seed["qualification"]),
        "complete_download": {
            "required": True,
            "path": "complete-results.zip",
            "url": None,
            "bytes": None,
            "sha256": None,
            "media_type": "application/zip",
        },
        "atomic_rejection_required_if_any_selected_body_pin_or_identity_fails": True,
    }
    return {
        "contract": CONTRACT,
        "election_date": ELECTION_DATE,
        "house_sources": house_sources,
        "scenarios": scenarios,
        "decisions": {
            "contract": "participation.automatic_estimate_decisions.v1",
            "states": decisions,
            "summary": decision_summary,
            "global_issues": global_issues,
        },
        "participation": participation,
        "next_seed": house_sources["next_seed"],
        "artifacts": artifacts,
        "behavioral_models_refitted": False,
        "source_raw_respondents_or_private_fine_cells_exported": False,
        "preserved_original_model_count": seed["provenance"]["preserved_original_model_count"],
    }
