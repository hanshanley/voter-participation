#!/usr/bin/env python3
"""Select sufficient whole-state NORC moments and held candidate-return facts."""

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

from return_attribution import TERMS, count, serial


def pin(path):
    body = path.read_bytes()
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def rows(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def party(label):
    text = label.strip().lower()
    return "D" if text in ("democratic", "democrat", "dem") else (
        "R" if text in ("republican", "rep") else "O")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--norc-directory", type=Path, required=True)
    parser.add_argument("--house-controls", type=Path, required=True)
    parser.add_argument("--senate-directory", type=Path, required=True)
    parser.add_argument("--governor-csv", type=Path, required=True)
    parser.add_argument("--survey-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refuse to replace an input version")
    native_summary = json.loads((args.norc_directory / "summary.json").read_bytes())
    for name in ("participation.csv", "margin-decomposition.csv"):
        expected = native_summary["outputs"][name]
        if pin(args.norc_directory / name) != expected:
            raise ValueError("Completed NORC reduction pin differs: " + name)
    dimensions = ("scope", "dimension", "prior_election", "prior_office", "current_office",
                  "m24", "m26", "t24", "t26", *TERMS)
    moments = {row["scope"] + "|" + row["prior_election"]: {key: row[key] for key in dimensions}
        for row in rows(args.norc_directory / "margin-decomposition.csv")
        if row["dimension"] == "overall" and row["scope"] != "POOLED_SOURCE"
        and row["prior_election"] == "2024"}
    participation = {row["scope"]: {key: row[key] for key in (
        "n", "source_effective_n", "modeled_voter_weight", "modeled_nonvoter_weight")}
        for row in rows(args.norc_directory / "participation.csv")
        if row["dimension"] == "overall" and row["scope"] != "POOLED_SOURCE"}
    if len(moments) != 50 or len(participation) != 50:
        raise ValueError("Native whole-state frame inventory differs")
    controls, exclusions = [], []
    house = rows(args.house_controls)
    grouped = defaultdict(list)
    for row in house:
        grouped[row["state_code"]].append(row)
    for state, group in sorted(grouped.items()):
        totals = dict(D=0, R=0, O=0)
        missing = []
        for index, row in enumerate(group):
            if row["reported_district_votes"] == "":
                missing.append(index)
            else:
                totals[party(row["literal_party"])] += int(count(row["reported_district_votes"]))
        controls.append(dict(id=state+"-house", state_code=state, office="house", year=2026,
            geography_level="state", current=totals, previous=None, previous_year=None,
            source_scope="sum_of_held_reported_district_candidate_controls_not_ballots_or_turnout",
            source_snapshot="20261107T125502Z", source_native_clock=None,
            missing_candidate_control_indices=missing, literal_party_labels_not_candidate_coalitions=True,
            full_candidate_control_rows=group))
    national_path = args.senate_directory / "national-index.json"
    national = json.loads(national_path.read_bytes())
    for region_key, region in national["region_results"].items():
        if region["type"] != "State":
            raise ValueError("Unexpected Senate national-index hierarchy")
        path = args.senate_directory / "races" / (region_key.upper()+".json")
        native = json.loads(path.read_bytes())
        state = native["province"]
        if state.lower() != region_key or native["test_data"]:
            raise ValueError("Declared Senate source identity differs")
        totals = dict(D=0, R=0, O=0)
        for candidate in native["candidates"]:
            totals[party(candidate["party"])] += int(count(candidate["votes"]))
        controls.append(dict(id=state+"-senate-"+str(region["election_id"]),
            state_code=state, office="senate", year=2026, geography_level="state",
            current=totals, previous=None, previous_year=None,
            source_scope="native_state_race_candidate_counts_not_ballots_or_turnout",
            source_url="https://civicapi.org/api/v2/race/"+str(region["election_id"]),
            source_native_clock=native["last_updated"], source_round=native["round"],
            source_election_scope=native["election_scope"], source_percent_reporting=native["percent_reporting"],
            full_candidate_rows=native["candidates"], source_original_pin=pin(path)))
    governor_rows = rows(args.governor_csv)
    grouped = defaultdict(list)
    seen = set()
    for row in governor_rows:
        key = row["state_abbr"], row["fips"]
        if key in seen:
            raise ValueError("Duplicate native governor geography; no duplicate source sums")
        seen.add(key)
        grouped[row["state_abbr"]].append(row)
    for state, group in sorted(grouped.items()):
        totals = dict(D=0, R=0)
        previous = dict(D=0, R=0)
        complete_previous = True
        for row in group:
            if any(row[key] == "" for key in ("dem_2026", "rep_2026")):
                raise ValueError("Missing current governor candidate count is not zero")
            for label, key in [("D", "dem"), ("R", "rep")]:
                totals[label] += int(count(row[key+"_2026"]))
                if row[key+"_2022"] == "":
                    complete_previous = False
                else:
                    previous[label] += int(count(row[key+"_2022"]))
        controls.append(dict(id=state+"-governor-held-county-frame", state_code=state,
            office="governor", year=2026, geography_level="state", current=totals,
            previous=previous if complete_previous else None, previous_year=2022,
            source_scope="held_native_county_frame_D_R_counts_not_all_candidate_totals_or_turnout",
            source_url="https://pages.stat.wisc.edu/~karlrohe/lr333/governor_2026.csv",
            source_native_clock=None, native_county_rows=len(group), full_factual_county_rows=group))
    # Retain exact zeros; a missing/zero known-choice denominator cannot yield an estimate.
    accepted = []
    for control in controls:
        if control["current"]["D"] + control["current"]["R"] == 0:
            exclusions.append(dict(control=control, reason="no_reported_known_major_party_denominator"))
        else:
            accepted.append(control)
    poll_tables = json.loads(args.survey_review.read_bytes())["tables"]
    polls = {}
    office_codes = {"SG": "senate", "GG": "governor", "HG": "house"}
    for control in accepted:
        matches = [row for row in poll_tables if row["state_code"] == control["state_code"]
            and row["subset"]["sub"] == 0 and row["status"] == "published_joint_question_reviewed"
            and office_codes.get(row["contest_code"]) == control["office"]]
        if len(matches) > 1:
            raise ValueError("Nonunique office-specific switching frame")
        if matches:
            polls[control["id"]] = dict(matches[0], office=control["office"])
    result = dict(status="selected_sufficient_whole_state_model_moments_and_held_return_facts",
        state_moments=moments, state_participation=participation, return_controls=accepted,
        return_control_exclusions=exclusions, office_poll_switching=polls,
        sources=dict(norc_native_reduction=native_summary,
            house_controls=pin(args.house_controls), senate_index=pin(national_path),
            governor_csv=pin(args.governor_csv), survey_review=pin(args.survey_review)),
        privacy=dict(geographic_scope="whole-state only", respondent_records=False,
            private_joint_cells=False, private_demographic_cells=False,
            inputs_are_signed_whole_frame_moments_not_individual_transition_counts=True),
        known_limits=[
            "Current House controls may omit reported district-candidate totals; missing indices are retained.",
            "Governor counts describe the supplied county frame, not certified whole-state coverage.",
            "Native candidate counts never supply a participation denominator.",
            "Literal D/R party labels are not fusion-candidate coalitions; independents remain Other.",
            "State NORC sources and office-specific current-voter polls are different frames.",
            "Senate special elections and native rounds stay explicit; no unreviewed same-seat historical pairing."])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, default=serial, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(dict(state_frames=len(moments), return_controls=len(accepted),
        office_specific_switching=len(polls), excluded=len(exclusions))))


if __name__ == "__main__":
    main()
