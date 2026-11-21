"""Audit prior Senate survey support without inferring individual transitions."""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import re
import unicodedata

from scripts.norc_senate_routing import contests, digest

FIPS = dict(zip(
    "1 2 4 5 6 8 9 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 "
    "31 32 33 34 35 36 37 38 39 40 41 42 44 45 46 47 48 49 50 51 53 54 55 56".split(),
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT "
    "NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split(),
))
LABEL_PIN = "b1515337165dd3d439f1040274e862fceaf649ba203270992ba8fae710aee126"


def tokens(name):
    letters = unicodedata.normalize("NFKD", name.casefold())
    return re.findall(r"[a-z]+", "".join(c for c in letters if not unicodedata.combining(c)))


def candidate_match(question_name, official_name):
    surname, comma, rest = official_name.partition(",")
    if not comma or not tokens(surname) or not tokens(rest):
        return False
    expected = tokens(surname)
    words = tokens(question_name)
    if words and words[-1] in {"jr", "sr", "ii", "iii", "iv"}:
        words.pop()
    return len(words) > len(expected) and words[0] == tokens(rest)[0] and words[-len(expected):] == expected


def frame(row):
    if row["qualified_comparison"] != "True":
        return "comparison_held", None
    baseline = json.loads(row["baseline"])
    if baseline["cycle_year"] != 2020:
        return "different_baseline_year", None
    if (baseline["stage"], baseline["seat"], baseline["election_kind"]) != ("general", "2", "regular"):
        return "historical_stage_or_seat_not_covered", None
    names = {}
    for candidate in json.loads(row["previous_candidates"]):
        party = candidate["party_group"]
        if party not in {"D", "R"}:
            continue
        if (party in names or not candidate["fec_candidate_id"].strip()
                or (candidate["state_code"], candidate["native_office"], candidate["seat"],
                    candidate["stage"], candidate["year"]) != (row["state_code"], "S", "2", "general", 2020)):
            raise ValueError("Invalid reviewed 2020 Senate candidate frame")
        names[party] = candidate["candidate"]
    if set(names) != {"D", "R"}:
        raise ValueError("Missing reviewed major candidate")
    return "same_seat_general_question_available", names


def evaluate(responses, accepted, labels):
    frames = {state: frame(row) for state, row in accepted.items()}
    if set(labels.values()) != set(FIPS.values()) or len(labels) != len(FIPS):
        raise ValueError("Incomplete CES verified registration-state labels")
    counts = {state: Counter() for state in accepted}
    for row in responses:
        state = FIPS.get(row["inputstate_post"])
        if state not in frames or frames[state][1] is None or row["CC20_411"] in {"", "NA", "98", "99"}:
            continue
        names = frames[state][1]
        stats = counts[state]
        stats["answered"] += 1
        if labels.get(row["CL_state"]) != state or row["CL_2020gvm"] not in {"1", "2", "3", "4", "5"}:
            continue
        if row["vvweight_post"] in {"", "NA"}:
            continue
        weight = float(row["vvweight_post"])
        if not math.isfinite(weight) or weight <= 0:
            continue
        stats["matched_state_validated_voter"] += 1
        slate = {row[f"SenCand{i}Party_post"]: row[f"SenCand{i}Name_post"] for i in (1, 2)}
        if (not candidate_match(slate.get("Democratic", ""), names["D"])
                or not candidate_match(slate.get("Republican", ""), names["R"])):
            stats["slate_unverified"] += 1
            continue
        stats["matched_slate"] += 1
        if row["CC20_411"] in {"1", "2"}:
            stats["reported_major_choice"] += 1
    return [{
        "state_code": state, "seat": accepted[state]["seat"], "stage": accepted[state]["stage"],
        "historical_source_question": "CC20_411" if names else "",
        "disposition": ("verified_historical_sample" if counts[state]["reported_major_choice"] else
                        "no_verified_historical_sample" if names else decision),
        **{key: counts[state][key] for key in ("answered", "matched_state_validated_voter",
                                              "slate_unverified", "matched_slate", "reported_major_choice")},
        "transition_model_qualified": False,
    } for state, (decision, names) in sorted(frames.items())]


def reproduce(ces, comparisons, labels, output):
    if digest(labels) != LABEL_PIN:
        raise ValueError("CES registration-state decoding differs from the reviewed input")
    with comparisons.open(encoding="utf-8-sig", newline="") as stream:
        accepted = contests(csv.DictReader(stream))
    with ces.open(encoding="utf-8-sig", newline="") as stream:
        rows = evaluate(csv.DictReader(stream), accepted, json.loads(labels.read_bytes())["labels"])
    output.mkdir(parents=True, exist_ok=True)
    with (output / "ces-2020-senate-support.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    report = {
        "input_sha256": {name: digest(path) for name, path in
                         (("ces", ces), ("comparisons", comparisons), ("labels", labels))},
        "state_dispositions": dict(Counter(row["disposition"] for row in rows)),
        "historical_post_weight": "vvweight_post",
        "reported_vote_is_not_independently_validated_vote_choice": True,
        "historical_and_current_surveys_are_not_a_joint_panel": True,
        "transition_model_qualified": False,
    }
    (output / "ces-2020-senate-support.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                                                        encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("ces", "comparisons", "labels", "output"):
        parser.add_argument("--" + flag, required=True, type=Path)
    print(json.dumps(reproduce(**vars(parser.parse_args())), sort_keys=True))
