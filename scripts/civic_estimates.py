#!/usr/bin/env python3
"""Private, source-weighted Civic estimates; not validated population transitions."""

import argparse
import csv
import hashlib
import io
import json
import os
import zipfile
from collections import Counter, defaultdict
from decimal import Decimal, getcontext
from pathlib import Path


SOURCE_SHA = "496a5b57fbc435210bdf78e2c1c3717879c0689c74081bee830d121b548c792f"
BOOK_SHA = "5c0e522820d36562d2610ea514ae693079f871b3352584ee070b628b02ac59c8"
STATES = set("AK AL AR AZ CA CO CT DE FL GA HI IA ID IL IN KS KY LA MA MD ME MI MN MO MS MT NC ND NE NH NJ NM NV NY OH OK OR PA RI SC SD TN TX UT VA VT WA WI WV WY".split())
DIMENSIONS = ("AGE6", "RACETH5", "EDUC", "SEX", "GENDER3", "INCOME", "RUCC")
PRIOR = {"1": "D", "2": "R", "3": "O", "4": "N", "99": "U", "MISSING": "U"}
CHOICE = {"1": "D", "2": "R", "3": "O", "99": "U", "MISSING": "U"}
COMPONENTS = ("switching", "modeled_nonparticipation", "no_prior_contest_vote_entry",
              "other_choice", "unresolved")
ZERO = Decimal(0)
HUNDRED = Decimal(100)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def code(value):
    value = value.strip()
    if not value:
        return "MISSING"
    number = Decimal(value)
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError("Nonintegral native code")
    return str(int(number))


def component(prior, current):
    delta = (int(current == "D") - int(current == "R")
             - int(prior == "D") + int(prior == "R"))
    if {prior, current} == {"D", "R"}:
        return "switching", delta
    if prior in {"D", "R"} and current == "N":
        return "modeled_nonparticipation", delta
    if prior == "N" and current in {"D", "R"}:
        return "no_prior_contest_vote_entry", delta
    if "U" in {prior, current}:
        return "unresolved", delta
    return "other_choice", delta


def decomposition(cells):
    m24 = sum(((int(p == "D") - int(p == "R")) * w for (p, _), w in cells.items()), ZERO)
    m26 = sum(((int(c == "D") - int(c == "R")) * w for (_, c), w in cells.items()), ZERO)
    t24 = sum((w for (p, _), w in cells.items() if p in {"D", "R"}), ZERO)
    t26 = sum((w for (_, c), w in cells.items() if c in {"D", "R"}), ZERO)
    parts = dict.fromkeys(COMPONENTS, ZERO)
    for (prior, current), weight in cells.items():
        key, multiplier = component(prior, current)
        parts[key] += multiplier * weight
    if sum(parts.values(), ZERO) != m26 - m24:
        raise AssertionError("Raw margin decomposition failed")
    return {"m24": m24, "m26": m26, "t24": t24, "t26": t26, **parts}


def csv_output(path, rows):
    with path.open("x", encoding="utf-8", newline="") as stream:
        os.chmod(path, 0o600)
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def private_destination(path):
    resolved = path.resolve()
    if any((parent / ".git").exists() for parent in (resolved, *resolved.parents)):
        raise ValueError("Private fine-grained outputs must remain outside Git repositories")
    return resolved


def main():
    getcontext().prec = 80
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--codebook", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = private_destination(args.output)
    if args.output.exists() or digest(args.csv) != SOURCE_SHA or digest(args.codebook) != BOOK_SHA:
        raise ValueError("Existing output or unreviewed source bytes")
    labels = defaultdict(dict)
    with zipfile.ZipFile(args.codebook) as archive:
        for row in csv.DictReader(io.StringIO(archive.read("response_options.csv").decode("utf-8-sig"))):
            if row["variable"] in (*DIMENSIONS, "LVB"):
                labels[row["variable"]][code(row["value"])] = row["value_label"].strip('"')
    required = ("P_STATE", "CHEP_WEIGHT", "VOTE24_CHOICE", "VOTE22_CHOICE",
                "LIKELYVOTER", "HOUSEVOTE", "LVB", *DIMENSIONS)
    measures = defaultdict(lambda: {"n": 0, "weight": ZERO, "weight_squared": ZERO,
                                    "modeled_voter_weight": ZERO, "modeled_nonvoter_weight": ZERO})
    joints = defaultdict(lambda: defaultdict(lambda: [0, ZERO]))
    likelihood = defaultdict(lambda: [0, ZERO])
    checks = Counter()
    with args.csv.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        positions = {field: header.index(field) for field in required}
        for raw in reader:
            if len(raw) != len(header):
                raise ValueError("Invalid source width; no record contents logged")
            row = {field: raw[position] for field, position in positions.items()}
            state = row["P_STATE"].strip()
            if state not in STATES:
                raise ValueError("Unexpected source state")
            weight = Decimal(row["CHEP_WEIGHT"])
            if not weight.is_finite() or weight <= 0:
                raise ValueError("Unexpected nonpositive source weight")
            model, current_choice, lvb = map(code, (row["LIKELYVOTER"], row["HOUSEVOTE"], row["LVB"]))
            if model not in {"1", "2"} or current_choice not in CHOICE:
                raise ValueError("Unexpected consumed core code")
            current = CHOICE[current_choice] if model == "1" else "N"
            group_keys = [("overall", "all")] + [(field, code(row[field])) for field in DIMENSIONS]
            for dimension, group in group_keys[1:]:
                if group != "MISSING" and group not in labels[dimension]:
                    raise ValueError("Unreviewed demographic code")
            for scope in (state, "POOLED_SOURCE"):
                for dimension, group in group_keys:
                    key = scope, dimension, group
                    target = measures[key]
                    target["n"] += 1
                    target["weight"] += weight
                    target["weight_squared"] += weight * weight
                    target["modeled_voter_weight" if model == "1" else "modeled_nonvoter_weight"] += weight
                    for year in ("24", "22"):
                        prior = PRIOR[code(row["VOTE" + year + "_CHOICE"])]
                        cell = joints[(year, *key)][prior, current]
                        cell[0] += 1
                        cell[1] += weight
                    likelihood[(scope, dimension, group, PRIOR[code(row["VOTE24_CHOICE"])], lvb)][0] += 1
                    likelihood[(scope, dimension, group, PRIOR[code(row["VOTE24_CHOICE"])], lvb)][1] += weight
            checks["native_rows"] += 1
    if checks["native_rows"] != 113020:
        raise ValueError("Unexpected native row count")
    scopes = sorted({key[0] for key in measures})
    if set(scopes) != STATES | {"POOLED_SOURCE"}:
        raise ValueError("Source scope inventory changed")
    participation_rows, joint_rows, decomposition_rows = [], [], []
    for (scope, dimension, group), values in sorted(measures.items()):
        total = values["weight"]
        participation_rows.append({
            "scope": scope, "dimension": dimension, "group": group,
            "label": "All respondents" if dimension == "overall" else labels[dimension].get(group, "Missing"),
            **values, "source_effective_n": total * total / values["weight_squared"],
            "modeled_voter_pct": HUNDRED * values["modeled_voter_weight"] / total,
            "modeled_nonvoter_pct": HUNDRED * values["modeled_nonvoter_weight"] / total,
            "population_representativeness_qualified": False,
            "administratively_observed_turnout": False,
        })
    for year in ("24", "22"):
        overall = {
            scope: decomposition({cell: values[1] for cell, values in joints[(year, scope, "overall", "all")].items()})
            for scope in scopes
        }
        for (pair_year, scope, dimension, group), native_cells in sorted(joints.items()):
            if pair_year != year:
                continue
            source_cells = {cell: values[1] for cell, values in native_cells.items()}
            result = decomposition(source_cells)
            parent = overall[scope]
            if parent["t24"] <= 0 or parent["t26"] <= 0:
                raise ValueError("No known-major-party denominator")
            scale = (1 / parent["t24"] + 1 / parent["t26"]) / 2
            denominator_pp = HUNDRED * (result["m24"] + result["m26"]) / 2 * (
                1 / parent["t26"] - 1 / parent["t24"]
            )
            group_delta = HUNDRED * (
                result["m26"] / parent["t26"] - result["m24"] / parent["t24"]
            )
            normalized = {name + "_pp": HUNDRED * scale * result[name] for name in COMPONENTS}
            if abs(sum(normalized.values(), ZERO) + denominator_pp - group_delta) > Decimal("1e-20"):
                raise AssertionError("Normalized margin decomposition failed")
            decomposition_rows.append({
                "prior_election": "20" + year, "current_election": "2026",
                "prior_office": "president" if year == "24" else "house",
                "current_office": "house", "scope": scope, "dimension": dimension, "group": group,
                "source_weight_units_not_people": True,
                **result, **normalized, "denominator_pp": denominator_pp,
                "total_known_choice_margin_change_pp": group_delta,
                "eligibility_residence_component": None,
                "original_coalition_population_validation": False,
            })
            prior_totals = defaultdict(lambda: ZERO)
            for (prior, _), (_, weight) in native_cells.items():
                prior_totals[prior] += weight
            for prior, current in ((p, c) for p in "DRONU" for c in "DRONU"):
                n, weight = native_cells.get((prior, current), (0, ZERO))
                joint_rows.append({
                    "prior_election": "20" + year, "scope": scope, "dimension": dimension,
                    "group": group, "prior_choice": prior, "modeled_current_destination": current,
                    "n": n, "weight": weight,
                    "pct_of_full_prior_source_group": (
                        HUNDRED * weight / prior_totals[prior] if prior_totals[prior] else None
                    ),
                })
        for scope in scopes:
            for dimension in DIMENSIONS:
                selected = [r for r in decomposition_rows if r["prior_election"] == "20" + year
                            and r["scope"] == scope and r["dimension"] == dimension]
                control = next(r for r in decomposition_rows if r["prior_election"] == "20" + year
                               and r["scope"] == scope and r["dimension"] == "overall")
                for field in (*COMPONENTS, *(name + "_pp" for name in COMPONENTS),
                              "denominator_pp", "total_known_choice_margin_change_pp"):
                    if abs(sum((r[field] for r in selected), ZERO) - control[field]) > Decimal("1e-18"):
                        raise AssertionError("Separate demographic partition does not reconcile")
                    checks["partition_component_checks"] += 1
                checks["partition_checks"] += 1
    likelihood_rows = [{
        "scope": scope, "dimension": dimension, "group": group, "prior_choice": prior,
        "LVB": lvb, "LVB_label": labels["LVB"].get(lvb, "Missing"),
        "n": values[0], "weight": values[1],
    } for (scope, dimension, group, prior, lvb), values in sorted(likelihood.items())]
    if digest(args.csv) != SOURCE_SHA:
        raise ValueError("Source changed during reduction")
    args.output.mkdir(mode=0o700)
    for filename, rows in (
        ("participation.csv", participation_rows), ("choice-transitions.csv", joint_rows),
        ("margin-decomposition.csv", decomposition_rows), ("reported-intended-likelihood.csv", likelihood_rows),
    ):
        csv_output(args.output / filename, rows)
    summary = {
        "status": "computed_private_exploratory_source_weighted_estimates",
        "source_sha256": SOURCE_SHA, "codebook_sha256": BOOK_SHA,
        "code_sha256": digest(Path(__file__)), "scopes": len(scopes), "states": 50,
        "row_counts": {"participation": len(participation_rows), "joint": len(joint_rows),
                       "decomposition": len(decomposition_rows), "likelihood": len(likelihood_rows)},
        "checks": dict(checks), "pooled_source_is_not_qualified_national_estimate": True,
        "representativeness_and_variance_qualified": False,
        "public_release_qualified": False,
        "original_frame_deaths_migration_eligibility_components": None,
        "methods": [
            "All positive native CHEP_WEIGHT rows retained; no reweighting or population scaling.",
            "Two retrospective comparisons: 2024 President and 2022 House, each to modeled 2026 House.",
            "Model class2 is modeled nonparticipation; it is not administrative evidence of staying home.",
            "N is no recalled prior presidential/House vote, not no ballot, new eligibility or first-ever voting.",
            "Known D/R choice margins use the same current source frame and different known-choice denominators.",
            "All separate demographics use a common scope denominator so signed contributions add to the state.",
            "Intended/already-voted LVB responses remain separate; no fabricated design confidence intervals.",
            "Original native dictionaries and earlier support-only contracts remain unchanged.",
        ],
        "outputs": {p.name: {"bytes": p.stat().st_size, "sha256": digest(p)}
                    for p in sorted(args.output.glob("*.csv"))},
    }
    with (args.output / "summary.json").open("x") as stream:
        os.chmod(stream.name, 0o600)
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    print(json.dumps({key: summary[key] for key in ("status", "states", "scopes", "row_counts", "checks")}), flush=True)


if __name__ == "__main__":
    main()
