"""Independently check the complete public comparison and unchanged predecessor."""

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile


FAMILIES = ("accepted_ridge_multinomial", "histogram_gradient_boosting", "extra_randomized_trees")
TERMS = ("switching", "exit", "entry", "other_choice", "unresolved")


def verify(inputs, results):
    checks = 0

    def require(condition):
        nonlocal checks
        checks += 1
        if not condition:
            raise ValueError("Comparison verification failed at check " + str(checks))

    def same(a, b):
        require(math.isclose(a, b, rel_tol=0, abs_tol=1e-8))

    manifest = json.loads((inputs / "manifest.json").read_bytes())
    for name, pin in manifest.items():
        body = (inputs / name).read_bytes()
        require(len(body) == pin["bytes"] and hashlib.sha256(body).hexdigest() == pin["sha256"])
    models = {f: json.loads((results / f / "complete-result.json").read_bytes()) for f in FAMILIES}
    priors = {f: json.loads((inputs / (f + "-priors.json")).read_bytes()) for f in FAMILIES}
    baseline = models[FAMILIES[0]]
    with zipfile.ZipFile(inputs / "accepted-48-state-science.zip") as previous:
        for name in previous.namelist():
            if name.startswith("results/") and not name.endswith("/"):
                require(previous.read(name) == (results / FAMILIES[0] / Path(name).name).read_bytes())
    for family, model in models.items():
        require(len(model["rows"]) == 50 and model["summary"]["return_anchored"] == 48)
        require(priors[family]["raw_records_or_private_fine_cells_exported"] is False)
        for row, original in zip(model["rows"], baseline["rows"]):
            require(row["state_code"] == original["state_code"])
            require(row["reported_comparison"] == original["reported_comparison"])
            require([(g["dimension"], g["group"], g["available"]) for g in row["groups"]] ==
                    [(g["dimension"], g["group"], g["available"]) for g in original["groups"]])
            same(sum(row["point"]["contributions_pp"].values()), row["point"]["total_change_pp"])
            same(row["point"]["net_participation_pp"],
                 row["point"]["contributions_pp"]["entry"] + row["point"]["contributions_pp"]["exit"])
        for key in ("complete_assumption_cases", "complete_seed_cases", "complete_demographic_seed_cases"):
            require(len(model[key]) == len(baseline[key]))
    with (results / "complete-state-family-comparisons.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 150 and len({(r["family"], r["state_code"]) for r in rows}) == 150)
    for row in rows:
        state = next(r for r in models[row["family"]]["rows"] if r["state_code"] == row["state_code"])
        for term in TERMS:
            same(float(row[term + "_margin_pp"]), state["point"]["contributions_pp"][term])
            same(float(row[term + "_Democratic_two_party_share_pp"]) * 2,
                 state["point"]["contributions_pp"][term])
        same(float(row["gross_retained_share_pct"]), state["gross_outcomes"]["retaining"] * 100)
        if state["source_comparison_available"]:
            same(float(row["observed_Democratic_two_party_share_change_pp"]) * 2,
                 state["reported_comparison"]["reported_change_pp"])
        else:
            require(row["observed_Democratic_two_party_share_change_pp"] == "")
    with (results / "complete-family-dispersion.csv").open(newline="") as stream:
        spreads = list(csv.DictReader(stream))
    require(len(spreads) == 300 and len({(r["state_code"], r["mechanism"]) for r in spreads}) == 300)
    for row in spreads:
        states = [next(s for s in model["rows"] if s["state_code"] == row["state_code"])
                  for model in models.values()]
        values = [s["point"]["net_participation_pp"] if row["mechanism"] == "net_participation"
                  else s["point"]["contributions_pp"][row["mechanism"]] for s in states]
        same(float(row["minimum_margin_pp"]), min(values))
        same(float(row["maximum_margin_pp"]), max(values))
        same(float(row["family_spread_margin_pp"]), max(values) - min(values))
        require(row["confidence_interval"] == "False")
    metrics = list(csv.DictReader(io.StringIO((results / "complete-source-validation.csv").read_text())))
    require(len(metrics) == 9)
    lookup = {(r["family"], r["role"]): r for r in metrics}
    eligible = []
    for family in FAMILIES:
        scores = [(family, "historical_transfer", "source_weighted_log_loss"),
                  (family, "historical_transfer", "source_weighted_multiclass_brier"),
                  (family, "house26_response", "source_weighted_multiclass_brier")]
        if all(float(lookup[(f, role)][metric]) <= float(lookup[(FAMILIES[0], role)][metric])
               for f, role, metric in scores):
            eligible.append(family)
    preferred = min(eligible, key=lambda f: (float(lookup[(f, "historical_transfer")]["source_weighted_log_loss"]),
                                           FAMILIES.index(f)))
    selection = json.loads((results / "selection-before-return-evaluation.json").read_bytes())
    require(selection["preferred_family"] == preferred)
    require(selection["current_partisan_returns_used"] is False)
    viewer = json.loads((results / "viewer-data.json").read_bytes())
    require(viewer["preferred_family"] == preferred)
    for family, model in models.items():
        require(viewer["families"][family] == {k: v for k, v in model.items() if not k.startswith("complete_")})
    return dict(status="passed", checks=checks, state_family_decisions=150, dispersion_decisions=300,
                baseline_eight_outputs_unchanged=True, preferred_family=preferred,
                current_returns_used_for_selection=False, private_records_exported=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.inputs, args.results)
    with args.proof.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
