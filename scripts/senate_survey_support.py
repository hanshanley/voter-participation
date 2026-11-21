"""Join released aggregate Senate survey audits without linking respondents."""

import argparse
import csv
import json
import math
from pathlib import Path

from scripts.ces_2022_senate_routing import FRAMES, historical_slate
from scripts.ces_senate_routing import frame
from scripts.norc_senate_routing import TIMINGS, contests
from scripts.participation_intake.contract import pin

FILES = (
    "active-comparisons.csv", "senate-survey-routing.csv", "ces-2020-senate-support.csv",
    "ces-2022-senate-support.csv", "ces-2020-comparisons.csv", "ces-2022-comparisons.csv",
)


def read(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def key_by(rows, key):
    result = {}
    for row in rows:
        index = key(row)
        if index in result:
            raise ValueError(f"Duplicate Senate audit key: {index}")
        result[index] = row
    return result


def candidate_frame(row):
    if row["qualified_comparison"] != "True":
        return None
    baseline = json.loads(row["baseline"])
    slate = tuple(sorted((c["fec_candidate_id"], c["candidate"], c["party_group"])
                         for c in json.loads(row["previous_candidates"])))
    return baseline["cycle_year"], baseline["seat"], baseline["election_kind"], baseline["stage"], slate


def combine(active, norc, ces20, ces22, audited20, audited22):
    timing = key_by(norc, lambda row: (row["state_code"], row["timing_cohort"]))
    old20 = key_by(ces20, lambda row: row["state_code"])
    old22 = key_by(ces22, lambda row: row["state_code"])
    if (set(timing) != {(state, cohort) for state in active for cohort in TIMINGS}
            or set(old20) != set(audited20) or set(old22) != set(FRAMES)):
        raise ValueError("Incomplete Senate aggregate audit inventory")
    keys = ("election_date", "seat", "election_kind", "stage", "provider_race_id")
    for state, current in sorted(active.items()):
        record = {"state_code": state, **{key: current[key] for key in keys},
                  "return_round": current["round"], "qualified_return_comparison": current["qualified_comparison"],
                  "prior_year": "", "prior_stage": "", "prior_election_kind": "",
                  "prior_survey_question": "", "prior_survey_slate_matched": "",
                  "prior_survey_reported_major_choice": "", "prior_survey_status": "return_comparison_held",
                  "survey_cohorts_linked": False, "transition_model_qualified": False,
                  "participation_rate_qualified": False}
        for cohort in TIMINGS:
            sample = timing[state, cohort]
            count, ess = int(sample["respondents_with_senate_answer"]), sample["weight_only_effective_n"]
            if (any(sample[key] != current[key] for key in keys) or count < 0
                    or (count == 0) != (ess == "")
                    or (ess and not (math.isfinite(float(ess)) and 0 < float(ess) <= count))
                    or sample["participation_rate_qualified"] != "False"
                    or sample["senate_transition_model_qualified"] != "False"):
                raise ValueError(f"Invalid current Senate survey cohort: {state}/{cohort}")
            record[f"current_{cohort}"] = count
            record[f"current_{cohort}_weight_only_effective_n"] = ess
        prior = json.loads(current["baseline"]) if current["baseline"] else {}
        record.update(prior_year=prior.get("cycle_year", ""), prior_stage=prior.get("stage", ""),
                      prior_election_kind=prior.get("election_kind", ""))
        eligible = candidate_frame(current)
        if eligible and eligible[0] in (2020, 2022):
            year = eligible[0]
            audited, aggregates = (audited20, old20) if year == 2020 else (audited22, old22)
            sample = aggregates.get(state)
            record["prior_survey_status"] = "prior_scope_not_audited"
            if sample and candidate_frame(audited[state]) == eligible:
                status, slate = frame(current) if year == 2020 else (
                    "same_seat_general_question_available", historical_slate(current, state))
                if slate:
                    question = sample["historical_source_question" if year == 2020 else "historical_question"]
                    expected = "CC20_411" if year == 2020 else FRAMES[state][2]
                    n, m = int(sample["matched_slate"]), int(sample["reported_major_choice"])
                    if (sample["seat"] != eligible[1] or question != expected
                            or not 0 <= m <= n <= int(sample["answered"])
                            or sample["transition_model_qualified"] != "False"):
                        raise ValueError(f"Invalid historical Senate survey cohort: {state}")
                    record.update(prior_survey_question=question, prior_survey_slate_matched=n,
                                  prior_survey_reported_major_choice=m)
                    status = "verified_historical_sample" if m else "no_verified_historical_sample"
                record["prior_survey_status"] = status
        elif eligible:
            record["prior_survey_status"] = "prior_year_not_audited"
        yield record


def reproduce(inputs, output):
    declarations = json.loads((inputs / "sources.json").read_bytes())
    if set(declarations) != set(FILES):
        raise ValueError("Incomplete Senate aggregate input pins")
    for name in FILES:
        expected = declarations[name]
        if pin((inputs / name).read_bytes()) != {key: expected[key] for key in ("bytes", "sha256")}:
            raise ValueError(f"Changed Senate aggregate input: {name}")
    comparison = lambda name: contests(read(inputs / name))
    data = list(combine(comparison("active-comparisons.csv"), read(inputs / "senate-survey-routing.csv"),
                        read(inputs / "ces-2020-senate-support.csv"), read(inputs / "ces-2022-senate-support.csv"),
                        comparison("ces-2020-comparisons.csv"), comparison("ces-2022-comparisons.csv")))
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=data[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    reproduce(args.inputs, args.output)
