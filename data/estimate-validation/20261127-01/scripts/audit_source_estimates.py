"""Check frozen source-model estimates against reported outcomes without refitting."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import statistics
import zipfile


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def load(path):
    body = path.read_bytes()
    return json.loads(gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body)


def share(counts):
    d, r = counts.get("D"), counts.get("R")
    if any(type(value) is not int or value < 0 for value in (d, r)) or d + r == 0:
        return None
    return 100 * d / (d + r)


def compare(model_rows, reported_states, old_recorded):
    actual = {row["state_code"]: row for row in reported_states}
    previous_reader = {row["state_code"]: row for row in old_recorded}
    if len(actual) != len(reported_states) or len(previous_reader) != len(old_recorded):
        raise ValueError("Duplicate state benchmark")
    output = []
    for model in model_rows:
        code = model["state_code"]
        observed = actual[code]
        now, prior = share(observed["current"]), share(observed["previous"])
        point = model["point"]
        model_now, model_prior = 50 + point["current_margin_pp"] / 2, 50 + point["previous_margin_pp"] / 2
        change = point["total_change_pp"] / 2
        if abs(model_now - model_prior - change) > 1e-8:
            raise ValueError("Model endpoints do not reconcile")
        recorded_change = None if now is None or prior is None else now - prior
        eligible = observed["qualified_comparison"] is True and recorded_change is not None
        error = None if recorded_change is None else change - recorded_change
        current_error = None if now is None else model_now - now
        prior_error = None if prior is None else model_prior - prior
        if error is not None and abs(error - (current_error - prior_error)) > 1e-8:
            raise ValueError("Change-error decomposition does not reconcile")
        bounds = model["sensitivity"]["total_change"]
        reader_share = previous_reader[code]["democratic_two_party_share_pct"]
        output.append(dict(state_code=code, qualified_outcome_comparison=eligible,
            comparison_holds=" | ".join(observed["comparison_holds"]),
            modeled_current_D_share=model_now, recorded_current_D_share=now,
            current_share_error_pp=current_error, modeled_previous_D_share=model_prior,
            recorded_previous_D_share=prior, previous_share_error_pp=prior_error,
            modeled_change_pp=change, recorded_change_pp=recorded_change,
            change_error_pp=error, model_sensitivity_minimum_pp=bounds["minimum"] / 2,
            model_sensitivity_maximum_pp=bounds["maximum"] / 2,
            outside_model_sensitivity=None if not eligible else not bounds["minimum"] / 2 <= recorded_change <= bounds["maximum"] / 2,
            previous_primary_recorded_D_share=reader_share,
            primary_recorded_count_source_differs=now is not None and abs(now - reader_share) > 1e-8))
    if len(output) != len(actual) or len({row["state_code"] for row in output}) != len(output):
        raise ValueError("State comparison inventory differs")
    qualified = [row for row in output if row["qualified_outcome_comparison"]]
    if not qualified:
        raise ValueError("No qualified outcomes; do not report a zero error")
    summary = dict(states_checked=len(output), qualified_comparisons=len(qualified),
        current_share_MAE_pp=statistics.mean(abs(row["current_share_error_pp"]) for row in qualified),
        baseline_share_MAE_pp=statistics.mean(abs(row["previous_share_error_pp"]) for row in qualified),
        change_MAE_pp=statistics.mean(abs(row["change_error_pp"]) for row in qualified),
        change_error_above_2pp=sum(abs(row["change_error_pp"]) > 2 for row in qualified),
        change_error_above_5pp=sum(abs(row["change_error_pp"]) > 5 for row in qualified),
        outside_model_sensitivity=sum(row["outside_model_sensitivity"] for row in qualified),
        primary_recorded_source_differences=sum(row["primary_recorded_count_source_differs"] for row in output),
        observed_individual_switching_or_staying_home_identified=False,
        population_calibration_or_independent_forecast_validation_established=False)
    return output, summary


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue().encode()


def audit(inputs):
    for name, pin in load(inputs / "input-pins.json").items():
        body = (inputs / name).read_bytes()
        if len(body) != pin["bytes"] or hashlib.sha256(body).hexdigest() != pin["sha256"]:
            raise ValueError("Changed captured public input: " + name)
    runtime = load(inputs / "runtime.json")
    source = load(inputs / "source-original.json.gz")
    congress = load(inputs / "congressional.json.gz")
    recorded = load(inputs / "recorded-states.json.gz")
    counts = load(inputs / "current-counts.json.gz")
    groups = load(inputs / "group-classifications.json")
    native = load(inputs / "native-npr-house.json.gz")
    rows, summary = compare(source["models"]["accepted_ridge_multinomial"]["rows"], congress["house_states"], recorded["states"])
    if len(rows) != 50:
        raise ValueError("The complete all-state query is required")
    selected_ids = {rid for row in congress["house_states"] for rid in row["selected_race_ids"]}
    accepted = {row["provider_race_id"]: row for row in congress["races"] if row["id"] in selected_ids}
    fresh = {row["id"]: row for row in native["results"] if row.get("office") == "H" and row.get("level") == "state"}
    race_checks = []
    for identity, old in accepted.items():
        row = fresh.get(identity)
        totals = dict(D=0, R=0, O=0, U=0)
        if row:
            for candidate in row["candidates"]:
                party = {"Dem": "D", "GOP": "R"}.get(candidate.get("party"), "O" if candidate.get("party") else "U")
                if candidate.get("votes") is None:
                    totals[party] = None
                elif totals[party] is not None:
                    totals[party] += candidate["votes"]
        race_checks.append(dict(state_code=old["state_code"], provider_race_id=identity,
            found_in_current_native_source=row is not None,
            counts_match_accepted=None if row is None else all(old[key] == totals[key] for key in totals),
            **{"accepted_" + key: old[key] for key in totals},
            **{"current_native_" + key: totals[key] if row else None for key in totals}))
    if len(race_checks) != 435 or not all(row["found_in_current_native_source"] for row in race_checks):
        raise ValueError("Fresh native House inventory is incomplete")
    survey = {row["state_code"]: row for row in groups["groups"] if row["dimension"] == "overall"}
    turnout = []
    for row in counts["uf_turnout"]["rows"]:
        code = row["state_code"]
        if code not in survey or survey[code]["modeled_voter_pct"] is None:
            continue
        turnout.append(dict(state_code=code, survey_source_classified_pct=survey[code]["modeled_voter_pct"],
            UF_VEP_turnout_pct=row["vep_rate"], UF_VAP_turnout_pct=row["vap_rate"],
            UF_count_status=row["ballots_status"], directly_comparable_population_qualified=False,
            demographic_completed_turnout_validation=False,
            reason="Survey population/calibration is not qualified against VEP/VAP or matched demographic completed-turnout denominators."))
    if len(turnout) != 50:
        raise ValueError("Missing statewide turnout context")
    summary.update(runtime_version=runtime["version"], runtime_checked_at=runtime["checked_at"],
        native_source_receipt=load(inputs / "native-npr-receipt.json"),
        native_contests_checked=len(race_checks), native_contest_count_differences=sum(not row["counts_match_accepted"] for row in race_checks),
        survey_classification_coding_checked=load(inputs / "codebook-facts.json"),
        matched_population_demographic_turnout_validation=False,
        conclusions=["The source-model change is not the recorded election change; estimated baseline error is material.",
            "Reported-result display must use current congressional counts, not frozen model endpoints.",
            "Aggregate returns cannot validate individual switching, staying home, or demographic turnout rates.",
            "UF VEP/VAP context has a different, explicit population denominator; differences are not like-for-like model errors.",
            "No outcome fitting, demographic scaling or source-model refitting was performed."])
    return {"summary.json": encoded(summary), "state-checks.json": encoded(rows), "all-state-house-model-check.csv": csv_bytes(rows),
        "all-native-contest-count-checks.csv": csv_bytes(race_checks),
        "all-state-turnout-target-checks.csv": csv_bytes(turnout)}


def export(inputs, output):
    if output.exists():
        raise ValueError("Use a fresh destination")
    files = audit(inputs)
    files.update({"inputs/" + path.name: path.read_bytes() for path in inputs.iterdir() if path.is_file()})
    root = Path(__file__).parents[1]
    for name in ("scripts/audit_source_estimates.py", "tests/test_audit_source_estimates.py"):
        files[name] = (root / name).read_bytes()
    files["README.txt"] = ("Outcome audit, not a refit or a validation of individual histories.\n"
        "All 50 state queries, all 435 selected native contests and all statewide turnout-frame decisions.\n"
        "Includes the complete captured public inputs, source receipts, code and tests. No private survey records.\n"
        "python3 -m scripts.audit_source_estimates --inputs inputs --output reproduced\n"
        "python3 -m unittest discover -s tests -p test_audit_source_estimates.py\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
                                     for name, body in sorted(files.items())})
    output.mkdir(parents=True)
    for name, body in files.items():
        path = output / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(body)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, body in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16; archive.writestr(info, body)
    print(files["summary.json"].decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); export(args.inputs, args.output)
