"""Sharp conditional gross-flow bounds, without choosing or fitting histories."""

import argparse
from collections import deque
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import zipfile


ZERO = Decimal(0)
METRICS = ("retention", "switching", "outside_major_party", "entry_to_major_party",
    "no_current_contest_vote", "other_choice")


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def text(value):
    return format(value, "f")


def mask_for(categories, metric):
    if metric not in METRICS:
        raise ValueError("Unknown gross-flow measure")
    if "X" in categories and metric in ("no_current_contest_vote", "other_choice"):
        return None
    predicates = {
        "retention": lambda a, b: a == b and a in "DR",
        "switching": lambda a, b: a in "DR" and b in "DR" and a != b,
        "outside_major_party": lambda a, b: a in "DR" and b not in "DR",
        "entry_to_major_party": lambda a, b: a not in "DR" and b in "DR",
        "no_current_contest_vote": lambda a, b: a in "DR" and b == "N",
        "other_choice": lambda a, b: a in "DR" and b == "O",
    }
    return [[predicates[metric](a, b) for b in categories] for a in categories]


def maximum(rows, columns, selected):
    n, total = len(rows), sum(rows)
    if (n not in (3, 4) or len(columns) != n or sum(columns) != total or total <= 0
            or any(not v.is_finite() or v < 0 for v in rows + columns)
            or len(selected) != n or any(len(row) != n for row in selected)):
        raise ValueError("Complete finite, nonnegative equal-total marginals required")
    source, sink = 2*n, 2*n+1
    capacity = [[ZERO] * (2*n+2) for _ in range(2*n+2)]
    for i in range(n):
        capacity[source][i], capacity[n+i][sink] = rows[i], columns[i]
        for j in range(n):
            capacity[i][n+j] = total if selected[i][j] else ZERO
    residual = [row[:] for row in capacity]
    flow = ZERO
    while True:
        previous = {source: None}
        queue = deque([source])
        while queue and sink not in previous:
            node = queue.popleft()
            for other, value in enumerate(residual[node]):
                if value > 0 and other not in previous:
                    previous[other] = node
                    queue.append(other)
        if sink not in previous:
            break
        path, node = [], sink
        while previous[node] is not None:
            path.append((previous[node], node))
            node = previous[node]
        amount = min(residual[a][b] for a, b in path)
        for a, b in path:
            residual[a][b] -= amount
            residual[b][a] += amount
        flow += amount
    table = [[capacity[i][n+j]-residual[i][n+j] for j in range(n)] for i in range(n)]
    left = [rows[i]-sum(table[i]) for i in range(n)]
    right = [columns[j]-sum(table[i][j] for i in range(n)) for j in range(n)]
    for i in range(n):
        for j in range(n):
            amount = min(left[i], right[j])
            if amount and selected[i][j]:
                raise ValueError("Nonmaximum selected-edge flow")
            table[i][j] += amount
            left[i] -= amount
            right[j] -= amount
    cuts = []
    for subset in range(1 << n):
        neighbors = {j for i in range(n) if subset & (1 << i)
            for j in range(n) if selected[i][j]}
        value = sum((rows[i] for i in range(n) if not subset & (1 << i)), ZERO)
        value += sum((columns[j] for j in neighbors), ZERO)
        cuts.append((value, subset, sorted(neighbors)))
    cut, subset, neighbors = min(cuts)
    if flow != cut or any(left + right):
        raise ValueError("Primal/dual sharpness failure")
    return dict(value=text(flow), witness=[[text(v) for v in row] for row in table],
        cut=dict(row_subset=subset, column_neighbors=neighbors, capacity=text(cut)))


def bounds(rows, columns, categories, metric):
    selected = mask_for(categories, metric)
    if selected is None:
        return dict(status="unavailable_unknown_other_not_no_contest_vote",
            lower=None, upper=None, denominator=None)
    upper = maximum(rows, columns, selected)
    complement = [[not v for v in row] for row in selected]
    lower = maximum(rows, columns, complement)
    lower["value"] = text(sum(rows)-Decimal(lower["value"]))
    denominator = sum(columns[:2]) if metric == "entry_to_major_party" else sum(rows[:2])
    return dict(status="sharp_conditional_accounting_bounds", lower=lower, upper=upper,
        denominator=text(denominator),
        denominator_definition="current_D_plus_R" if metric == "entry_to_major_party" else "previous_D_plus_R",
        lower_percent=text(100*Decimal(lower["value"])/denominator),
        upper_percent=text(100*Decimal(upper["value"])/denominator))


def endpoints(comparison, frame):
    votes = [comparison[name] for name in ("previous", "current")]
    for counts in votes:
        if (not {"D", "R"} <= counts.keys()
                or any(type(v) is not int or v < 0 for v in counts.values())
                or any(counts[key] <= 0 for key in "DR")):
            raise ValueError("Native positive D/R counts and literal Other required")
    supplied = ["O" in counts for counts in votes]
    if supplied[0] != supplied[1]:
        raise ValueError("Mixed Other endpoint coverage needs separate qualification")
    categories = "DRON" if all(supplied) else "DRX"
    targets = []
    for counts in votes:
        native = [Decimal(counts[key]) for key in categories[:-1]]
        targets.append(native + [frame-sum(native)])
    if any(v < 0 or not v.is_finite() for target in targets for v in target):
        raise ValueError("Assumed frame below recorded endpoints")
    return categories, targets


def build(accepted):
    if accepted["contract"] != "participation.return_constrained_scenarios.v1":
        raise ValueError("Use the complete accepted endpoint-calibration output")
    if len(accepted["rows"]) != 113 or len({r["id"] for r in accepted["rows"]}) != 113:
        raise ValueError("Every original state/office decision must remain")
    decisions, cases = [], []
    for original in accepted["rows"]:
        identity = {key: original[key] for key in ("id", "state_code", "office")}
        comparison = original["reported_comparison"]
        if original["point"] is None:
            decisions.append(dict(identity, status="unavailable", reason=original["reason"],
                case_ids=[], reported_comparison=comparison))
            continue
        if comparison["status"] != "reported_source_comparison":
            raise ValueError("Unsupported comparison cannot receive bounds")
        frames = [(f"accepted_frame_{scale}", Decimal(str(next(
            c["assumed_common_frame_units"] for c in original["complete_scenarios"]
            if c["persistence_scale"] == 1 and c["frame_scale"] == scale))))
            for scale in (0.8, 1.0, 1.25)]
        disjoint_frame = Decimal(sum(comparison[name].get(k, 0)
            for name in ("previous", "current") for k in "DRO"))
        frames.append(("large_frame_counterexample", disjoint_frame))
        ids = []
        for name, frame in frames:
            categories, (rows, columns) = endpoints(comparison, frame)
            case_id = original["id"] + "|" + name
            ids.append(case_id)
            case = dict(identity, case_id=case_id, frame_name=name, frame_units=text(frame),
                frame_is_measured_population=False, categories=list(categories),
                target_rows=list(map(text, rows)), target_columns=list(map(text, columns)),
                counterexample_not_fitted_estimate=name == "large_frame_counterexample",
                unknown_other_is_opaque_X=categories == "DRX",
                metrics={key: bounds(rows, columns, categories, key) for key in METRICS})
            if name == "large_frame_counterexample":
                # Disjoint before/after accounting sets preserve every native total.
                joint = [[ZERO] * len(categories) for _ in categories]
                for i in range(len(categories)-1):
                    joint[i][-1], joint[-1][i] = rows[i], columns[i]
                if sum(rows[:-1]) != columns[-1] or sum(columns[:-1]) != rows[-1]:
                    raise ValueError("Invalid large-frame counterexample")
                case["joint_zero_retention_and_switching_witness"] = [
                    list(map(text, row)) for row in joint]
            cases.append(case)
        decisions.append(dict(identity, status="conditional_bounds_not_identified_histories",
            case_ids=ids, reported_comparison=comparison))
    available = [value for case in cases for value in case["metrics"].values()
        if value["lower"] is not None]
    return dict(contract="participation.gross_flow_identification.v1", decisions=decisions,
        cases=cases, gross_metrics=list(METRICS), sharp_bounds_conditional_on_frame=True,
        endpoints_determine_individual_histories=False, independently_measured_population=False,
        probability_model_or_partisan_fit_performed=False, old_fits_rerun=False,
        confidence_intervals=None, measured_staying_home=None, eligibility_deaths_migration=None,
        local_allocation=False, joint_attainability_of_separate_bounds=False,
        unknown_other_rule="Both Other endpoints absent: DRX, not observed zero or a no-vote category",
        units="Continuous candidate-vote accounting units, not identified people or net-margin percentage points",
        summary=dict(total_decisions=len(decisions), available=sum(bool(r["case_ids"]) for r in decisions),
            unavailable=sum(not r["case_ids"] for r in decisions), frame_cases=len(cases),
            bounded_metrics=len(available), held_metrics=len(cases)*len(METRICS)-len(available),
            primal_witnesses=2*len(available), large_frame_counterexamples=len(cases)//4))


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=sorted({key for row in rows for key in row}),
        lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def viewer(result):
    central = {case["id"]: case for case in result["cases"]
        if case["frame_name"] == "accepted_frame_1.0"}
    rows = []
    for decision in result["decisions"]:
        identity = {key: decision[key] for key in ("id", "state_code", "office", "status")}
        case = central.get(decision["id"])
        if case is None:
            rows.append(dict(identity, frame_units=None, bounds=None, reason=decision["reason"]))
            continue
        rows.append(dict(identity, frame_units=case["frame_units"],
            unknown_other_is_opaque_X=case["unknown_other_is_opaque_X"],
            bounds={key: {k: v for k, v in value.items() if k not in ("lower", "upper")}
                for key, value in case["metrics"].items()}))
    return dict(contract="participation.gross_flow_identification_viewer.v1",
        rows=rows, accepted_science_sha256=result["accepted_science_sha256"],
        conditional_accounting_bounds_not_confidence_intervals=True,
        measured_staying_home=None, frame_is_measured_population=False,
        gross_shares_not_net_margin_contributions=True)


def result_files(result):
    decisions, limits, cells, constraints = [], [], [], []
    for row in result["decisions"]:
        decisions.append({key: value for key, value in row.items()
            if key not in ("case_ids", "reported_comparison")})
    for case in result["cases"]:
        identity = {key: case[key] for key in ("id", "state_code", "office", "case_id", "frame_name")}
        for side in ("rows", "columns"):
            for category, count in zip(case["categories"], case["target_"+side]):
                constraints.append(dict(identity, side=side, category=category, accounting_units=count,
                    native_candidate_count=category in "DRO", assumed_outside_margin=category in "NX"))
        for metric, value in case["metrics"].items():
            limits.append(dict(identity, metric=metric, **{key: v for key, v in value.items()
                if key not in ("lower", "upper")},
                lower_units=value["lower"]["value"] if value["lower"] else None,
                upper_units=value["upper"]["value"] if value["upper"] else None))
            for end in ("lower", "upper"):
                if value[end] is None:
                    continue
                for i, a in enumerate(case["categories"]):
                    for j, b in enumerate(case["categories"]):
                        cells.append(dict(identity, metric=metric, extremum=end, previous_category=a,
                            current_category=b, accounting_units=value[end]["witness"][i][j],
                            identified_person_observation=False))
    return {"complete-result.json": encoded(result), "viewer-data.json": encoded(viewer(result)),
        "complete-decisions.csv": csv_bytes(decisions),
        "complete-bounds.csv": csv_bytes(limits), "complete-witness-cells.csv": csv_bytes(cells),
        "complete-endpoint-constraints.csv": csv_bytes(constraints)}


def read_accepted(archive):
    with zipfile.ZipFile(archive) as source:
        return json.loads(source.read("results/complete-result.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-science", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh output directory")
    result = build(read_accepted(args.accepted_science))
    result["accepted_science_sha256"] = hashlib.sha256(args.accepted_science.read_bytes()).hexdigest()
    args.output.mkdir(parents=True)
    for name, body in result_files(result).items():
        (args.output / name).write_bytes(body)
    print(json.dumps(result["summary"]))
