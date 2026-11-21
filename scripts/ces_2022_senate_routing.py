"""Audit same-seat historical survey support for the three 2022 Senate baselines."""

import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path

from scripts.ces_senate_routing import FIPS, candidate_match
from scripts.norc_senate_routing import contests, digest


CES_SHA = "dcdaeba631e0bdf50f3d7dcf4dcde7cc980e4281ff5dab87efcaa7353ca089bc"
LABEL_SHA = "6846921c812313feb18206698a8e7512a78174415686f49421bf538072956030"
FRAMES = {
    "FL": ("3", "regular", "CC22_411", "_post", frozenset("12345678")),
    "OH": ("3", "regular", "CC22_411", "_post", frozenset("12345678")),
    "OK": ("2", "special", "CC22_411b", "2_post", frozenset(("1", "2", "7", "8", "9", "10"))),
}
VALID_VOTE = set("123456")


def historical_slate(row, state):
    seat, kind, _, _, _ = FRAMES[state]
    b = json.loads(row["baseline"])
    if (row["qualified_comparison"], row["seat"], b["cycle_year"], b["seat"],
            b["stage"], b["election_kind"]) != ("True", seat, 2022, seat, "general", kind):
        raise ValueError(f"{state}: wrong historical Senate seat, stage or election")
    office = "S-Unexpired Term" if kind == "special" else "S"
    names = {}
    for candidate in json.loads(row["previous_candidates"]):
        party = candidate["party_group"]
        if party not in {"D", "R"}:
            continue
        if (party in names or not candidate["fec_candidate_id"].strip()
                or (candidate["state_code"], candidate["native_office"], candidate["seat"],
                    candidate["stage"], candidate["year"], candidate["election_kind"])
                != (state, office, seat, "general", 2022, kind)):
            raise ValueError(f"{state}: invalid reviewed candidate frame")
        names[party] = candidate["candidate"]
    if set(names) != {"D", "R"}:
        raise ValueError(f"{state}: incomplete historical Senate candidate slate")
    return names


def evaluate(responses, accepted, labels):
    slates = {state: historical_slate(accepted[state], state) for state in FRAMES}
    if set(labels.values()) != set(FIPS.values()) or len(labels) != len(FIPS):
        raise ValueError("Incomplete CES registration-state labels")
    counts = {state: Counter() for state in FRAMES}
    for row in responses:
        state = FIPS.get(row["inputstate_post"])
        if state not in FRAMES:
            continue
        _, _, question, suffix, codes = FRAMES[state]
        value = row[question]
        if value in ("", "NA", "98", "99"):
            continue
        if value not in codes:
            raise ValueError(f"{state}: unknown Senate response code")
        count = counts[state]
        count["answered"] += 1
        if labels.get(row["TS_state"]) != state or row["TS_g2022"] not in VALID_VOTE:
            continue
        raw_weight = row["vvweight_post"]
        if raw_weight in ("", "NA"):
            continue
        weight = float(raw_weight)
        if not math.isfinite(weight) or weight <= 0:
            continue
        count["same_state_validated_voter"] += 1
        party_positions = {}
        for i in range(1, (2 if state == "OK" else 4) + 1):
            name, party = row[f"SenCand{i}Name{suffix}"], row[f"SenCand{i}Party{suffix}"]
            party = {"Democratic": "D", "Republican": "R"}.get(party)
            if not party:
                continue
            # The Ohio question prints dotted initials; the official frame uses JD.
            if state == "OH" and name == "J.D. Vance":
                name = "JD Vance"
            if candidate_match(name, slates[state][party]):
                party_positions.setdefault(party, []).append(str(i))
        if set(party_positions) != {"D", "R"} or any(len(slots) != 1 for slots in party_positions.values()):
            continue
        count["matched_slate"] += 1
        if any(value in slots for slots in party_positions.values()):
            count["reported_major_choice"] += 1
    fields = ("answered", "same_state_validated_voter", "matched_slate", "reported_major_choice")
    return [{
        "state_code": state, "seat": seat, "historical_year": 2022, "historical_stage": "general",
        "historical_election_kind": kind, "historical_question": question,
        "verified_historical_sample": counts[state]["reported_major_choice"] > 0,
        **{field: counts[state][field] for field in fields},
        "transition_model_qualified": False,
    } for state, (seat, kind, question, _, _) in sorted(FRAMES.items())]


def reproduce(ces, comparisons, labels, output):
    pins = {name: digest(path) for name, path in (("ces", ces), ("comparisons", comparisons), ("labels", labels))}
    if (pins["ces"], pins["labels"]) != (CES_SHA, LABEL_SHA):
        raise ValueError("CES source or verified label bytes changed")
    field = json.loads(labels.read_bytes())["selected_variables"]["TS_state"]["codes"]
    with comparisons.open(encoding="utf-8-sig", newline="") as stream:
        accepted = contests(csv.DictReader(stream))
    with ces.open(encoding="utf-8-sig", newline="") as stream:
        rows = evaluate(csv.DictReader(stream), accepted, field)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "ces-2022-senate-support.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    report = {
        "input_sha256": pins, "survey_doi": "10.7910/DVN/PR4L8P", "survey_version": "4.0",
        "survey_csv_file_id": 10140882, "historical_post_weight": "vvweight_post",
        "senate_choice_used_in_weight_calibration": True, "vote_choice_independently_validated": False,
        "current_and_historical_respondents_linked": False, "transition_model_qualified": False,
    }
    (output / "ces-2022-senate-support.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("ces", "comparisons", "labels", "output"):
        parser.add_argument("--" + flag, required=True, type=Path)
    print(json.dumps(reproduce(**vars(parser.parse_args())), sort_keys=True))
