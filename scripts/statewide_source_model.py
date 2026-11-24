"""Uniform all-state House support estimates from accepted public fitted priors."""

import copy
import gzip
import hashlib
import json
import math
import re

from scripts import norc_house_model as model


CONTRACT = "participation.statewide_source_model.v1"
INDEX_CONTRACT = "participation.statewide_source_index.v1"
METHOD = "uniform_source_frame_house24_bridge_to_house26_v1"
PROFILES = ("original", "attenuated", "full")
FAMILIES = ("accepted_ridge_multinomial", "histogram_gradient_boosting", "extra_randomized_trees")
STATES = frozenset("AK AL AR AZ CA CO CT DE FL GA HI IA ID IL IN KS KY LA MA MD ME MI MN MO MS MT NC ND NE NH NJ NM NV NY OH OK OR PA RI SC SD TN TX UT VA VT WA WI WV WY".split())
DIMENSIONS = frozenset(("AGE6", "EDUC", "INCOME", "RACETH5", "RUCC", "SEX"))
METRICS = (*model.MECHANISMS, "net_participation", "total_change", "retaining")
PREFIX = "house/statewide-source/"


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def compressed(value):
    body = gzip.compress(encoded(value), compresslevel=9, mtime=0)
    return body[:9] + bytes([3]) + body[10:]


def pin(body):
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def _matrix(value):
    if (not isinstance(value, list) or len(value) != 5
            or any(not isinstance(row, list) or len(row) != 5 for row in value)
            or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for row in value for v in row)):
        raise ValueError("A finite nonnegative public DRONU prior is required")
    return value


def validate_prior(prior, profile):
    if (prior.get("contract") != "participation.norc_house_demographic_priors.v1"
            or prior.get("categories") != list(model.CHOICES)
            or prior.get("raw_records_or_private_fine_cells_exported") is not False
            or prior.get("old_synthetic_state_couplings_used") is not False
            or prior.get("design_confidence_intervals") is not None
            or prior.get("measured_staying_home") is not None
            or set(prior.get("states", {})) != STATES
            or set(prior.get("source_input_sha256", {})) != {"ap2024", "chep"}
            or any(not isinstance(v, str) or not re.fullmatch(r"[a-f0-9]{64}", v)
                   for v in prior["source_input_sha256"].values())):
        raise ValueError("Unqualified public source-prior scope or privacy contract")
    stress = prior.get("structural_association_stress")
    if profile != "original" and (not stress or stress.get("profile") != profile
            or stress.get("current_return_targets_used") is not False
            or stress.get("state_and_group_year_marginals_preserved") is not True):
        raise ValueError("Association profile was not a source-only fixed-margin stress")
    masks = {}
    for code, state in prior["states"].items():
        if (state.get("state_code") != code
                or state.get("source_joint_cells_reconstructed_or_exported") is not False):
            raise ValueError("Source state identity or disclosure contract differs")
        joint = _matrix(state["prior_joint"])
        if not math.isclose(math.fsum(map(math.fsum, joint)), 1, abs_tol=1e-10):
            raise ValueError("Source state prior is not normalized")
        groups, identifiers = state.get("groups"), set()
        if not isinstance(groups, list) or not groups:
            raise ValueError("Complete public demographic decisions are required")
        for group in groups:
            identity = (group.get("dimension"), group.get("group"))
            if (identity in identifiers or identity[0] not in DIMENSIONS
                    or not isinstance(identity[1], str) or not identity[1] or "|" in identity[1]
                    or type(group.get("available")) is not bool
                    or not isinstance(group.get("label"), str) or not group["label"]):
                raise ValueError("Invalid or duplicate public demographic identity")
            identifiers.add(identity)
            if group["available"]:
                _matrix(group["prior_joint"])
            elif group.get("prior_joint") is not None:
                raise ValueError("Held demographic inputs must remain withheld")
        for dimension in {g["dimension"] for g in groups}:
            selected = [g["prior_joint"] for g in groups if g["dimension"] == dimension and g["available"]]
            if any(abs(math.fsum(g[i][j] for g in selected) - joint[i][j]) > 1e-9
                   for i in range(5) for j in range(5)):
                raise ValueError("Public demographic partition does not preserve the source state")
        masks[code] = sorted((g["dimension"], g["group"], g["label"], g["available"]) for g in groups)
    return masks


def estimate(state, affinity=1):
    unavailable = {"status": "unavailable"}
    joint, factors, rows, columns, frame, normalizer = model.fit_state(state, unavailable, affinity=affinity)
    if frame is not None:
        raise ValueError("A source-only estimate cannot acquire a return-conditioned frame")
    result = {"state_code": state["state_code"], "available": True,
              "point": model.accounting(joint), "joint": joint,
              "gross_outcomes": model.coarse_outcomes(joint), "groups": []}
    for group in state["groups"]:
        item = {key: group[key] for key in ("dimension", "group", "label", "available")}
        item.update(point=None, joint=None, gross_outcomes=None)
        if group["available"]:
            transformed = [[group["prior_joint"][i][j] * factors[i][j] / normalizer
                            for j in range(5)] for i in range(5)]
            allocation = model.accounting(transformed, rows, columns)
            item.update(point={key: allocation[key] for key in (
                "contributions_pp", "allocated_change_pp", "net_participation_pp")}, joint=transformed,
                        gross_outcomes=model.coarse_outcomes(transformed)
                        if math.fsum(math.fsum(row) for row in transformed[:2]) > 0 else None)
        result["groups"].append(item)
    return result


def metric_value(row, metric):
    if not row or not row.get("available"):
        return None
    if metric == "retaining":
        return (row.get("gross_outcomes") or {}).get("retaining")
    if metric == "total_change":
        return row["point"]["allocated_change_pp"]
    if metric == "net_participation":
        return row["point"]["net_participation_pp"]
    return row["point"]["contributions_pp"][metric]


def build(priors):
    expected = {profile + "/" + family for profile in PROFILES for family in FAMILIES}
    if set(priors) != expected:
        raise ValueError("All nine accepted source-prior variants are required")
    reference = priors["original/accepted_ridge_multinomial"]
    reference_mask = None
    inputs = {}
    cases, primary = {}, {}
    for key in sorted(priors):
        profile, family = key.split("/")
        prior = priors[key]
        mask = validate_prior(prior, profile)
        if reference_mask is None:
            reference_mask = mask
        if (mask != reference_mask or prior["source_input_sha256"] != reference["source_input_sha256"]
                or prior["source_cases"] != reference["source_cases"]):
            raise ValueError("Source variants changed inputs, populations or disclosure masks")
        inputs[key] = pin(encoded(prior))
        for affinity in (.5, 1, 2):
            rows = [estimate(prior["states"][code], affinity) for code in sorted(STATES)]
            cases[key + "/" + str(affinity)] = {"profile": profile, "family": family,
                                                 "affinity": affinity, "rows": rows}
            if affinity == 1:
                primary[key] = copy.deepcopy(rows)
    version = hashlib.sha256(encoded({"method": METHOD, "priors": inputs})).hexdigest()
    scopes = {}
    for case in cases.values():
        for row in case["rows"]:
            for group_key, item in [("", row)] + [(g["dimension"] + "|" + g["group"], g) for g in row["groups"]]:
                scope = scopes.setdefault((row["state_code"], group_key), {metric: [] for metric in METRICS})
                for metric in METRICS:
                    value = metric_value(item, metric)
                    if value is not None:
                        scope[metric].append(value)
    ranges = {key: {metric: {"minimum": min(values), "maximum": max(values)} if values else None
                    for metric, values in scope.items()} for key, scope in scopes.items()}
    for rows in primary.values():
        for row in rows:
            row["sensitivity"] = ranges[(row["state_code"], "")]
            for group in row["groups"]:
                group["sensitivity"] = ranges[(row["state_code"], group["dimension"] + "|" + group["group"])]
    metadata = {
        "method": METHOD, "version": version,
        "estimand": "CHEP2026 source-frame modeled House24-to-House26 support change",
        "baseline": "AP2024 President/House association bridges CHEP recalled President to modeled House24",
        "source_frame": "CHEP2026 source-weighted respondents, not either year's observed statewide electorate",
        "source_input_sha256": reference["source_input_sha256"], "source_cases": reference["source_cases"],
        "input_years": {"ap2024": 2024, "chep": 2026},
        "interview_dates": None, "source_fit_date": None,
        "date_qualification": "Input vintages are known; native interview and fit dates are not supplied by these public fitted priors",
        "priors": inputs, "states": 50, "profiles": list(PROFILES), "families": list(FAMILIES),
        "default_family": FAMILIES[0], "default_profile": "original",
        "previous_partisan_return_constraints_used": False, "current_partisan_return_constraints_used": False,
        "source_weight_calibration_independent_of_returns_qualified": False,
        "return_conditioned": False, "source_models_refitted": False,
        "population_calibrated": False, "model_units_are_people": False,
        "estimated_baseline_not_actual_2024_house_counts": True,
        "nonmajor_choices_remain_other": True, "unresolved_response_is_not_nonvote": True,
        "synthetic_flow_table_is_not_linked_histories": True,
        "measured_staying_home": None, "actual_first_ever_voting": None,
        "confidence_intervals": None, "local_allocation": False,
        "sensitivity": {"families": 3, "association_profiles": 3, "affinities": [.5, 1, 2],
                        "variants": 27, "confidence_interval": False,
                        "complete_sampling_or_transport_uncertainty": False},
        "assumptions": copy.deepcopy(reference["assumptions"]),
    }
    profiles = {profile: {"contract": CONTRACT, "metadata": metadata, "profile": profile,
                         "models": {family: {"rows": primary[profile + "/" + family]}
                                    for family in FAMILIES}} for profile in PROFILES}
    declarations = {}
    for profile, value in profiles.items():
        body, decoded = compressed(value), encoded(value)
        declarations[profile] = {"path": PREFIX + profile + ".json.gz", "compression": "gzip",
                                 "media_type": "application/json", **pin(body),
                                 "decoded_bytes": len(decoded), "decoded_sha256": pin(decoded)["sha256"]}
    index = {"contract": INDEX_CONTRACT, "metadata": metadata, "profiles": declarations}
    return {"index": index, "profiles": profiles,
            "queries": {"contract": "participation.statewide_source_queries.v1", "metadata": metadata, "cases": cases}}


def from_seed(seed):
    return build({key: value["prior"] for key, value in seed["scenarios"].items()})


def files(result):
    return {PREFIX + "index.json.gz": compressed(result["index"]),
            PREFIX + "complete-queries.json.gz": compressed(result["queries"]),
            **{PREFIX + profile + ".json.gz": compressed(value)
               for profile, value in result["profiles"].items()}}
