"""Audit Senate survey coverage without releasing individual responses or estimating turnout."""

import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re

ELECTION = "2026-11-03"
EXPECTED_CONTESTS = 35
SPECIALS = {"FL": "3", "OH": "3"}
VOTED = {"1", "2", "3", "4"}
PLANNED = {"1", "2", "3", "4", "5"}
RESPONSE = {"1", "2", "3"}
UNKNOWN = {"", "99"}
TIMINGS = ("reported_already_voted", "reported_plan", "voting_timing_unresolved")


def contests(reader):
    races, ids = {}, set()
    for row in reader:
        if row["chamber"] != "senate" or row["advertised"] != "True":
            continue
        state, source_id = row["state_code"], row["provider_race_id"]
        seat = SPECIALS.get(state, "2")
        kind = "special" if state in SPECIALS else "regular"
        if (row["election_date"], row["stage"], row["seat"], row["election_kind"]) != (ELECTION, "general", seat, kind):
            raise ValueError(f"Unreviewed Senate seat or stage: {state}")
        if state in races or source_id in ids or not re.fullmatch(r"[0-9]+", source_id):
            raise ValueError(f"Missing or ambiguous Senate race ID: {state}")
        races[state] = row
        ids.add(source_id)
    if len(races) != EXPECTED_CONTESTS or SPECIALS.keys() - races.keys():
        raise ValueError("Incomplete accepted Senate general-election frame")
    return races


def timing(row):
    reported, planned = row["WVA"], row["WVB"]
    if reported not in VOTED | UNKNOWN or planned not in PLANNED | UNKNOWN:
        raise ValueError("Unreviewed NORC voting-timing code")
    if reported in VOTED and planned in PLANNED:
        raise ValueError("Conflicting NORC voting-timing routes")
    return TIMINGS[0] if reported in VOTED else TIMINGS[1] if planned in PLANNED else TIMINGS[2]


def audit(reader, races):
    if not {"P_STATE", "RACE1_RACEID", "RACE1_OFFICEID", "SENVOTE", "WVA", "WVB", "CHEP_WEIGHT"} <= set(
            reader.fieldnames or ()):
        raise ValueError("Missing NORC Senate questionnaire or weight fields")
    cohorts = defaultdict(list)
    for row in reader:
        answer = row["SENVOTE"]
        if answer in UNKNOWN:
            continue
        state = row["P_STATE"]
        if (answer not in RESPONSE or state not in races or row["RACE1_OFFICEID"] != "S"
                or row["RACE1_RACEID"] != races[state]["provider_race_id"]):
            raise ValueError("Unmatched NORC Senate respondent routing")
        try:
            weight = float(row["CHEP_WEIGHT"])
        except ValueError as exc:
            raise ValueError("Invalid NORC population weight") from exc
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError("Invalid NORC population weight")
        cohorts[state, timing(row)].append(weight)
    if {state for state, _ in cohorts} != races.keys():
        raise ValueError("One or more accepted Senate contests have no survey support")
    result = []
    for state, source in sorted(races.items()):
        for choice in TIMINGS:
            weights = cohorts[state, choice]
            maximum = max(weights) if weights else None
            scaled = [weight / maximum for weight in weights] if weights else []
            ess = math.fsum(scaled) ** 2 / math.fsum(w * w for w in scaled) if weights else None
            result.append({
                "state_code": state, "election_date": ELECTION,
                "seat": source["seat"], "election_kind": source["election_kind"],
                "stage": source["stage"], "return_round": source["round"],
                "provider_race_id": source["provider_race_id"],
                "timing_cohort": choice, "respondents_with_senate_answer": len(weights),
                "weight_only_effective_n": f"{ess:.2f}" if ess is not None else "",
                "participation_rate_qualified": False, "senate_transition_model_qualified": False,
            })
    return result


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def reproduce(respondents, returns, output):
    with returns.open(encoding="utf-8-sig", newline="") as stream:
        races = contests(csv.DictReader(stream))
    with respondents.open(encoding="utf-8-sig", newline="") as stream:
        rows = audit(csv.DictReader(stream), races)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "senate-survey-routing.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    report = {
        "respondent_csv_sha256": digest(respondents), "congress_races_csv_sha256": digest(returns),
        "matched_contests": len(races), "timing_totals": {
            cohort: sum(row["respondents_with_senate_answer"] for row in rows if row["timing_cohort"] == cohort)
            for cohort in TIMINGS
        },
        "weight_variable": "CHEP_WEIGHT",
        "denominator": "NORC survey respondents with a recognized Senate answer, not the eligible electorate",
        "weight_only_effective_n_is_not_design_based_uncertainty": True,
        "return_round_counts_calibrate_survey": False,
        "senate_transition_model_qualified": False,
        "prior_measure_hold": "The historical choice questions in this survey are 2022 House and 2024 President, not the previous Senate seat election.",
    }
    (output / "senate-survey-routing.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                                                      encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("respondents", "returns", "output"):
        parser.add_argument("--" + flag, required=True, type=Path)
    print(json.dumps(reproduce(**vars(parser.parse_args())), sort_keys=True))
