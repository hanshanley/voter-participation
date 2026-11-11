"""Fit explicit common-frame transition scenarios to both same-office returns."""

import argparse
import csv
import hashlib
import io
import itertools
import json
import math
from pathlib import Path
import zipfile


CHOICES = "DRON"
TERMS = ("switching", "nonparticipation", "entry", "other_choice")
FRAME_SCALES = (0.8, 1.0, 1.25)
PERSISTENCE_SCALES = (0.5, 1.0, 2.0)
SUPPORT_MIX = 1e-10


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def margin(d, r):
    if not math.isfinite(d + r) or d < 0 or r < 0 or d + r <= 0:
        raise ValueError("A positive known-major-party denominator is required")
    return 100 * (d-r) / (d+r)


def collapse_prior(probabilities):
    if len(probabilities) != 25 or any(not math.isfinite(p) or p < 0 for p in probabilities):
        raise ValueError("Use the complete accepted synthetic prior, not private joint cells")
    result = [[0.0] * 4 for _ in CHOICES]
    for (before, after), value in zip(itertools.product("DRONU", repeat=2), probabilities):
        i, j = CHOICES.index("N" if before == "U" else before), CHOICES.index("N" if after == "U" else after)
        result[i][j] += value
    if not math.isclose(sum(map(sum, result)), 1, abs_tol=1e-9):
        raise ValueError("Unnormalized synthetic prior")
    return result


def fit(prior, rows, columns, tolerance=2e-13, max_iterations=10000):
    if any(not math.isfinite(v) or v < 0 for v in rows + columns):
        raise ValueError("Infeasible candidate-vote accounting frame")
    if not math.isclose(sum(rows), 1, abs_tol=1e-12) or not math.isclose(sum(columns), 1, abs_tol=1e-12):
        raise ValueError("Complete endpoint marginals are required")
    q = [[(1-SUPPORT_MIX)*prior[i][j] + SUPPORT_MIX*rows[i]*columns[j]
        for j in range(4)] for i in range(4)]
    for iteration in range(max_iterations):
        for i in range(4):
            total = sum(q[i])
            if rows[i] and total <= 0:
                raise ValueError("Absent assumed row support")
            q[i] = [value * rows[i] / total if rows[i] else 0.0 for value in q[i]]
        for j in range(4):
            total = sum(q[i][j] for i in range(4))
            if columns[j] and total <= 0:
                raise ValueError("Absent assumed column support")
            for i in range(4):
                q[i][j] = q[i][j] * columns[j] / total if columns[j] else 0.0
        error = max(abs(sum(q[i])-rows[i]) for i in range(4))
        if error <= tolerance:
            return q, dict(iterations=iteration+1, maximum_endpoint_residual=error,
                support_mix=SUPPORT_MIX)
    raise ValueError("Endpoint calibration failed to converge; do not hide a residual")


def summarize(q):
    rows = [sum(row) for row in q]
    columns = [sum(q[i][j] for i in range(4)) for j in range(4)]
    changes = {key: [0.0, 0.0] for key in TERMS}
    for i, before in enumerate(CHOICES):
        for j, after in enumerate(CHOICES):
            if before == after:
                continue
            kind = ("switching" if {before, after} == {"D", "R"} else
                "nonparticipation" if after == "N" else "entry" if before == "N" else "other_choice")
            for k, party in enumerate("DR"):
                changes[kind][k] += q[i][j] * (int(after == party) - int(before == party))
    values = {}
    for mask in range(16):
        d, r = rows[:2]
        for i, key in enumerate(TERMS):
            if mask & (1 << i):
                d += changes[key][0]
                r += changes[key][1]
        values[mask] = margin(d, r)
    parts = {}
    for i, key in enumerate(TERMS):
        parts[key] = sum(math.factorial(bin(mask).count("1")) * math.factorial(3-bin(mask).count("1")) / 24
            * (values[mask | (1 << i)] - values[mask])
            for mask in range(16) if not mask & (1 << i))
    actual = margin(*columns[:2]) - margin(*rows[:2])
    if not math.isclose(sum(parts.values()), actual, abs_tol=1e-8):
        raise ValueError("The transition mechanisms do not exactly reconcile")
    denominator = rows[0] + rows[1]
    gross = dict(retaining=(q[0][0]+q[1][1])/denominator,
        switching=(q[0][1]+q[1][0])/denominator,
        nonparticipation=(q[0][3]+q[1][3])/denominator,
        other_choice=(q[0][2]+q[1][2])/denominator)
    if not math.isclose(sum(gross.values()), 1, abs_tol=1e-10):
        raise ValueError("Gross outcomes do not partition prior major-party mass")
    return dict(components_pp=parts, previous_margin_pp=margin(*rows[:2]),
        current_margin_pp=margin(*columns[:2]), reported_change_pp=actual,
        gross_shares_of_modeled_previous_major_party=gross,
        algebraic_reconciliation_error_pp=actual-sum(parts.values()))


def counts(values, allow_unknown_other=False):
    if not {"D", "R"} <= set(values) or any(type(v) is not int or v < 0 for v in values.values()):
        raise ValueError("All native candidate counts, including true Other zeros, are required")
    if values["D"] <= 0 or values["R"] <= 0:
        raise ValueError("Uncontested or absent major-party endpoints are not filled")
    if "O" not in values and not allow_unknown_other:
        raise ValueError("Missing Other is not zero")
    return [values["D"], values["R"], values.get("O")]


def estimate(row, source):
    comparison = row["reported_comparison"]
    base = dict(id=row["id"], office=row["office"], state_code=row["state_code"],
        reported_comparison=comparison)
    if comparison["status"] != "reported_source_comparison":
        return dict(base, status="unavailable", reason=comparison["reason"],
            point=None, ranges_pp=None)
    previous, current = (counts(comparison[key], allow_unknown_other=True) for key in ("previous", "current"))
    other_observed = [votes[2] is not None for votes in (previous, current)]
    factor = source["persistence_calibration"]["selected_factor"]
    cases = []
    for persistence_scale in PERSISTENCE_SCALES:
        selected = next(value for value in source["effective_persistence_factors"]
            if math.isclose(value, factor*persistence_scale, rel_tol=1e-12))
        prior = collapse_prior(source["coupling_assumptions"][row["state_code"]+"|"+str(selected)]["probabilities"])
        current_source_choice_share = sum(prior[i][j] for i in range(4) for j in range(2))
        if not 0 < current_source_choice_share < 1:
            raise ValueError("Unknown source participation-proxy anchor")
        for frame_scale in FRAME_SCALES:
            raw_frame = sum(current[:2]) / current_source_choice_share * frame_scale
            lower = max(sum(v for v in previous if v is not None),
                sum(v for v in current if v is not None)) / (1-1e-6)
            frame = max(raw_frame, lower)
            marginal_priors = ([sum(row) for row in prior],
                [sum(prior[i][j] for i in range(4)) for j in range(4)])
            targets = []
            for votes, marginal in zip((previous, current), marginal_priors):
                d, r = (v/frame for v in votes[:2])
                other = votes[2]/frame if votes[2] is not None else (
                    (1-d-r)*marginal[2]/(marginal[2]+marginal[3]) if marginal[2]+marginal[3] else 0.0)
                targets.append([d, r, other, max(0.0, 1-d-r-other)])
            q, diagnostic = fit(prior, *targets)
            result = summarize(q)
            expected = comparison["reported_change_pp"]
            if abs(result["reported_change_pp"]-expected) > 1e-8:
                raise ValueError("Fitted endpoints differ from the actual reported comparison")
            cases.append(dict(persistence_scale=persistence_scale, frame_scale=frame_scale,
                assumed_common_frame_units=frame, lower_frame_bound_active=frame != raw_frame,
                target_rows=targets[0], target_columns=targets[1],
                synthetic_joint=q, fit=diagnostic, **result))
    point = next(c for c in cases if c["persistence_scale"] == c["frame_scale"] == 1)
    ranges = {key: dict(minimum=min(c["components_pp"][key] for c in cases),
        maximum=max(c["components_pp"][key] for c in cases)) for key in TERMS}
    return dict(base, status="return_constrained_scenario_not_identified_histories",
        point=point, ranges_pp=ranges, complete_scenarios=cases,
        fitted_to_both_reported_candidate_count_endpoints=True,
        observed_other_vote_endpoints=other_observed,
        unknown_other_endpoint_rule="Unreported Other stays absent in native counts; its synthetic marginal is prior-assumed, not set to zero",
        calibration_is_not_independent_validation=True, population_size_measured=False,
        eligibility_deaths_migration=None, measured_staying_home=None, confidence_intervals=None,
        source_prior_transport="Recalled-president/House synthetic associations used only as a prior, not the observed previous-office baseline",
        nonparticipation_definition="No counted candidate vote for the target office in the assumed common accounting frame; not administratively confirmed no ballot",
        outside_candidate_category="Original synthetic N and unresolved U pooled only in the model prior; no source observations recoded",
        uncertainty="Nine persistence/common-frame-size sensitivity scenarios, not confidence or identification intervals")


def build(viewer, source):
    if source["source_units_are_people"] is not False or source["private_joint_cells_reconstructed"] is not False:
        raise ValueError("Only accepted synthetic source priors are allowed")
    rows = [estimate(row, source) for row in viewer["rows"]]
    if len(rows) != 113 or len({row["id"] for row in rows}) != 113:
        raise ValueError("Changed model identity coverage")
    return dict(contract="participation.return_constrained_scenarios.v1", rows=rows,
        categories=list(CHOICES), terms=list(TERMS), support_mix=SUPPORT_MIX,
        source_point_persistence=source["persistence_calibration"]["selected_factor"],
        fitted_to_both_endpoints=True, identified_histories=False,
        measured_staying_home=None, confidence_intervals=None, local_allocation=False,
        summary=dict(total_decisions=len(rows), fitted=sum(row["point"] is not None for row in rows),
            unavailable=sum(row["point"] is None for row in rows),
            complete_fits=sum(len(row.get("complete_scenarios", [])) for row in rows)))


def viewer(result):
    return dict(result, rows=[{key: value for key, value in row.items()
        if key != "complete_scenarios"} for row in result["rows"]])


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=sorted({key for row in rows for key in row}), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def result_files(result):
    decisions, endpoints, cases, cells = [], [], [], []
    for row in result["rows"]:
        base = {key: row[key] for key in ("id", "state_code", "office")}
        decisions.append(dict(base, status=row["status"], reason=row.get("reason"),
            reported_change_pp=row["point"]["reported_change_pp"] if row["point"] else None,
            fitted_to_both_endpoints=row["point"] is not None, independently_validated_histories=False))
        for endpoint in ("previous", "current"):
            for party in "DRO":
                counts = row["reported_comparison"].get(endpoint, {})
                endpoints.append(dict(base, endpoint=endpoint, party=party,
                    native_candidate_count=counts.get(party), observed_count_supplied=party in counts))
        for index, case in enumerate(row.get("complete_scenarios", [])):
            identity = dict(base, scenario=index, persistence_scale=case["persistence_scale"], frame_scale=case["frame_scale"])
            cases.append(dict(identity, assumed_common_frame_units=case["assumed_common_frame_units"],
                reported_change_pp=case["reported_change_pp"], **case["components_pp"]))
            for i, before in enumerate(CHOICES):
                for j, after in enumerate(CHOICES):
                    cells.append(dict(identity, previous_category=before, current_category=after,
                        synthetic_probability=case["synthetic_joint"][i][j],
                        source_joint_observation=False, represents_measured_people=False))
    return {"complete-result.json": encoded(result), "viewer-data.json": encoded(viewer(result)),
        **{"complete-" + key + ".csv": csv_bytes(rows) for key, rows in (
            ("decisions", decisions), ("endpoints", endpoints), ("scenarios", cases), ("synthetic-cells", cells))}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-archive", type=Path, required=True)
    parser.add_argument("--returns", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh scientific output")
    with zipfile.ZipFile(args.prior_archive) as archive:
        source = json.loads(archive.read("complete-scenarios.json"))
    result = build(json.loads(args.returns.read_bytes()), source)
    result["input_sha256"] = {name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in (("complete_prior_science", args.prior_archive), ("complete_return_comparisons", args.returns))}
    args.output.mkdir(parents=True)
    for name, body in result_files(result).items():
        (args.output / name).write_bytes(body)
    print(json.dumps(result["summary"]))
    print(json.dumps(next(row for row in result["rows"] if row["id"] == "TX-house")["point"]["components_pp"]))
