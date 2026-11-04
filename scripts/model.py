"""Audit an independent turnout baseline before releasing any current estimates."""

import csv
import hashlib
import json
import math
import statistics
import zipfile
from collections import defaultdict

from scripts.download import ROOT, atomic_json

WINDOW = 3
FIRST_TEST_YEAR = 2012


def logit(rate):
    if not isinstance(rate, (int, float)) or isinstance(rate, bool) or not 0 < rate < 100:
        raise ValueError("Log-odds require a finite rate strictly between 0 and 100")
    return math.log(rate / (100 - rate))


def rate_from_logit(value):
    return 100 / (1 + math.exp(-value))


def series(rows):
    overall, groups = {}, defaultdict(dict)
    for row in rows:
        if row["denominator"] != "cvap" or not 2000 <= row["year"] <= 2024:
            continue
        year, dimension, group = row["year"], row["dimension"], row["group"]
        if row["election_type"] != ("presidential" if year % 4 == 0 else "midterm"):
            raise ValueError("Election type disagrees with election year")
        logit(row["turnout_pct"])
        if dimension == "overall" and row["age_group"] == "All ages":
            if year in overall:
                raise ValueError("Duplicate national overall observation")
            overall[year] = row
            continue
        if dimension == "overall":
            dimension, group = "age", row["age_group"]
        elif row["age_group"] != "All ages" or dimension not in {"race", "sex", "education"}:
            continue
        if dimension == "race" and year < 2004:
            continue
        if year in groups[(dimension, group)]:
            raise ValueError("Duplicate demographic observation")
        groups[(dimension, group)][year] = row
    return overall, groups


def backtest(rows):
    overall, groups = series(rows)
    predictions = []
    for (dimension, group), history in sorted(groups.items()):
        for year, target in sorted(history.items()):
            if year < FIRST_TEST_YEAR:
                continue
            training = sorted(prior for prior in history
                              if prior < year and prior % 4 == year % 4 and prior in overall)[-WINDOW:]
            if len(training) < WINDOW:
                continue
            # A missing immediately preceding same-type election is not a valid carry-forward test.
            if training[-1] != year - 4:
                continue
            gaps = [logit(history[prior]["turnout_pct"]) - logit(overall[prior]["turnout_pct"])
                    for prior in training]
            national_prior = overall[training[-1]]["turnout_pct"]
            prediction = rate_from_logit(logit(national_prior) + statistics.mean(gaps))
            baseline = history[training[-1]]["turnout_pct"]
            actual = target["turnout_pct"]
            predictions.append({
                "year": year, "election_type": target["election_type"],
                "dimension": dimension, "group": group,
                "denominator": "cvap", "training_years": training,
                "last_training_year": training[-1],
                "national_input_year": training[-1], "national_input_pct": national_prior,
                "predicted_pct": prediction, "baseline_pct": baseline, "observed_cps_pct": actual,
                "error_pp": prediction - actual,
                "absolute_error_pp": abs(prediction - actual),
                "baseline_absolute_error_pp": abs(baseline - actual),
                "target_source": target["source"], "target_source_row": target["source_row"],
                "training_sources": [
                    {"year": prior, "group_source": history[prior]["source"],
                     "group_source_row": history[prior]["source_row"],
                     "overall_source": overall[prior]["source"],
                     "overall_source_row": overall[prior]["source_row"]}
                    for prior in training
                ],
            })
    if not predictions:
        raise ValueError("Insufficient independent historical tests")
    return predictions


def metrics(rows):
    if not rows:
        raise ValueError("Cannot score empty tests")
    mae = statistics.mean(row["absolute_error_pp"] for row in rows)
    baseline = statistics.mean(row["baseline_absolute_error_pp"] for row in rows)
    return {
        "tests": len(rows), "years": sorted({row["year"] for row in rows}),
        "model_mae_pp": mae, "baseline_mae_pp": baseline,
        "relative_mae_improvement": (baseline - mae) / baseline if baseline > 0 else None,
        "max_absolute_error_pp": max(row["absolute_error_pp"] for row in rows),
    }


def analyze(rows):
    predictions = backtest(rows)
    scores = []
    for field in ("election_type", "dimension", "year"):
        for value in sorted({row[field] for row in predictions}):
            scores.append({"slice": field, "value": value,
                           **metrics([row for row in predictions if row[field] == value])})
    summary = metrics(predictions)
    groups = defaultdict(list)
    for row in predictions:
        groups[(row["dimension"], row["group"])].append(row)
    latest_midterm = max(row["year"] for row in predictions if row["election_type"] == "midterm")
    latest = metrics([row for row in predictions if row["year"] == latest_midterm])
    checks = [
        {"requirement": "At least 10% lower mean absolute error than same-type carry-forward",
         "passed": summary["relative_mae_improvement"] is not None
                   and summary["relative_mae_improvement"] >= .10},
        {"requirement": "Lower mean absolute error in both presidential and midterm tests",
         "passed": all(row["model_mae_pp"] < row["baseline_mae_pp"]
                       for row in scores if row["slice"] == "election_type")},
        {"requirement": "Lower mean absolute error in every demographic dimension",
         "passed": all(row["model_mae_pp"] < row["baseline_mae_pp"]
                       for row in scores if row["slice"] == "dimension")},
        {"requirement": "No worse mean absolute error in the latest held-out midterm",
         "passed": latest["model_mae_pp"] <= latest["baseline_mae_pp"]},
        {"requirement": "Mean absolute error no greater than 5 percentage points for every group",
         "passed": all(metrics(group)["model_mae_pp"] <= 5 for group in groups.values())},
    ]
    return {
        "status": "research_only_not_a_2026_estimate",
        "method": "Same-election historical log-odds gap transfer",
        "independence": "Own calculations from archived public Census tables only. No NYT estimates, "
                        "poll responses, commercial voter files, party labels or candidate votes are inputs.",
        "specification": {
            "window_same_type_elections": WINDOW, "first_test_year": FIRST_TEST_YEAR,
            "formula": "p_hat(g,t) = logistic(logit(p_all,t-4) + mean_k(logit(p_g,k) - logit(p_all,k)))",
            "training": "k is the last three earlier elections of the same type; race starts in 2004.",
            "baseline": "The group's turnout rate in the immediately previous election of the same type.",
            "target": "Published CPS self-reported turnout among civilian noninstitutionalized adult citizens.",
            "scoring": "Equal-weight group/election errors in percentage points; overlapping groups "
                       "are not independent samples and are never summed into an electorate.",
            "thresholds": "Working research criteria fixed before running this experiment, not a "
                          "general statistical certification or a model-uncertainty interval.",
        },
        "summary": summary, "scores": scores, "checks": checks,
        "historical_gate_passed": all(check["passed"] for check in checks),
        "estimates_2026": [],
        "release_2026": {
            "allowed": False,
            "reasons": [
                "No complete, matched 2026 national demographic participation and population inputs.",
                "No survey-design, measurement-error or model-uncertainty intervals have been fitted.",
                "Historical persistence does not identify 2026 demographic turnout shifts.",
                "Historical CPS targets are self-reported, not validated individual turnout.",
                "Retrospective year holdouts use today's archived tables, not verified historical release vintages.",
            ],
        },
        "predictions": predictions,
    }


def export(root=ROOT, rebundle=True):
    source = root / "public/data/national.json"
    raw = source.read_bytes()
    result = analyze(json.loads(raw))
    result["input"] = {
        "path": "national.json", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "source_manifest": "sources.json",
    }
    output = root / "public/data/model"
    output.mkdir(parents=True, exist_ok=True)
    (output / "methodology.md").write_bytes((root / "METHODOLOGY.md").read_bytes())
    atomic_json(output / "validation.json", result)
    with (output / "backtests.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result["predictions"][0]))
        writer.writeheader()
        for row in result["predictions"]:
            writer.writerow({key: json.dumps(value, ensure_ascii=True) if isinstance(value, list) else value
                             for key, value in row.items()})
    with zipfile.ZipFile(output / "complete-validation.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("validation.json", "backtests.csv"):
            archive.write(output / name, name)
        archive.writestr("inputs/national.json", raw)
        archive.write(root / "public/data/sources.json", "inputs/sources.json")
        archive.write(root / "METHODOLOGY.md", "METHODOLOGY.md")
    if rebundle:
        from scripts.current import update_downloads
        update_downloads(root)
    return result


if __name__ == "__main__":
    result = export()
    print(json.dumps({key: result[key] for key in ("summary", "historical_gate_passed", "release_2026")}, indent=2))
