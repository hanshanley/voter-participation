"""Verify Utah's 2024 House counts and screen intact county components."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


ROOT = "https://electionresults.utah.gov/results/public/api/elections/"
ELECTION = "/General11052024/data"
OFFICE = re.compile(r"U\.S\. House ([1-4])(?: \(Multi-County\))?", re.I)
SEATS = {"01", "02", "03", "04"}
COUNTY_FIPS = {name + " County": f"49{2 * i + 1:03}" for i, name in enumerate((
    "Beaver", "Box Elder", "Cache", "Carbon", "Daggett", "Davis", "Duchesne", "Emery",
    "Garfield", "Grand", "Iron", "Juab", "Kane", "Millard", "Morgan", "Piute", "Rich",
    "Salt Lake", "San Juan", "Sanpete", "Sevier", "Summit", "Tooele", "Uintah", "Utah",
    "Wasatch", "Washington", "Wayne", "Weber",
))}
PINS = {
    "ut-2024-official-jurisdiction.json": "c62fe36b53007c8ef14d3b55a2992592cfc23ce92ea2e64511d9735632e847d0",
    "receipts.json": "a8fdc0c6a5f27ebea6447987ffb0bbfb2aa6fa0c860999062465b1b63c1564d7",
    "census-boundary-review.json": "9fc17fce1f678d5b1afc4f91a9206556fe4063a74350a4ba7231d4d0e3c8f4eb",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(body):
    return hashlib.sha256(body).hexdigest()


def english(values):
    texts = [row["text"] for row in values if row["languageId"] == "en"]
    require(len(texts) == 1 and texts[0].strip(), "Missing or ambiguous English label")
    return texts[0].strip()


def contests(data):
    event = data["election"]
    require(event["electionDate"] == "2024-11-05" and event["isOfficialResults"] is True
            and event["isPrimary"] is False, "Unexpected Utah election scope")
    result = {}
    for contest in data["ballotItems"]:
        label = english(contest["name"])
        match = OFFICE.fullmatch(label)
        if not match:
            require(not label.lower().startswith("u.s. house "), "Unrecognized House contest label")
            continue
        seat = match[1].zfill(2)
        require(seat not in result, "Duplicate Utah House contest")
        candidates = {}
        for candidate in contest["summaryResults"]["ballotOptions"]:
            key = candidate["nativeId"]
            require(isinstance(key, str) and key and key not in candidates
                    and type(candidate["voteCount"]) is int and candidate["voteCount"] >= 0,
                    "Invalid candidate identity or count")
            candidates[key] = {"candidate_name": english(candidate["name"]),
                               "literal_party": candidate["party"]["abbreviation"],
                               "votes": candidate["voteCount"]}
        require(candidates and sum(r["votes"] for r in candidates.values()) == contest["voteTotal"],
                "Candidate totals do not reconcile to the native contest")
        result[seat] = candidates
    return result


def block_assignments(path, congress):
    with zipfile.ZipFile(path) as archive, archive.open(f"NationalCD{congress}.txt") as member:
        rows = csv.reader(io.TextIOWrapper(member, encoding="ascii", newline=""))
        header = next(rows)
        require(header[0] == "GEOID" and header[-1] == "CDFP", "Unexpected Census schema")
        result = {}
        for row in rows:
            if not row[0].startswith("49"):
                continue
            require(len(row) == len(header) and re.fullmatch(r"49[0-9]{13}", row[0])
                    and row[0] not in result and row[-1] in SEATS, "Invalid Utah block assignment")
            result[row[0]] = row[-1]
    return result


def audit(root):
    originals = {}
    for name, expected in PINS.items():
        body = (root / name).read_bytes()
        require(digest(body) == expected, "Changed Utah audit input: " + name)
        originals[name] = json.loads(body)
    state = originals["ut-2024-official-jurisdiction.json"]
    state_contests = contests(state)
    require(state_contests.keys() == SEATS, "Incomplete statewide House inventory")
    counties = {r["shortName"]: r for r in state["jurisdiction"]["childLocalities"]}
    receipts = {r["slug"]: r for r in originals["receipts.json"]}
    require(len(counties) == len(receipts) == len(originals["receipts.json"]) == 29
            and counties.keys() == receipts.keys(), "Incomplete county catalog")

    county_votes, seen_components, summed, inventory = [], set(), Counter(), []
    for slug, declaration in sorted(counties.items()):
        receipt = receipts[slug]
        body = (root / "counties" / f"{slug}.json").read_bytes()
        require(receipt["status"] == "received" and receipt["url"] == ROOT + slug + ELECTION
                and len(body) == receipt["bytes"] and digest(body) == receipt["sha256"],
                "County source differs from its capture receipt")
        county = json.loads(body)
        name = english(declaration["name"])
        require(county["jurisdiction"]["id"].casefold() == declaration["id"].casefold()
                and english(county["jurisdiction"]["name"]) == name
                and receipt["protected"] is county["election"]["precinctResultsProtected"],
                "County identity or public precinct status differs")
        fips = COUNTY_FIPS[name]
        candidates = contests(county)
        inventory.append({"county_fips": fips, "county": name, "county_slug": slug,
                          "source_url": receipt["url"], "source_sha256": receipt["sha256"],
                          "source_last_updated": county["election"]["lastUpdated"],
                          "precinct_counts_protected": receipt["protected"],
                          "house_contests": ";".join(sorted(candidates))})
        for seat, results in sorted(candidates.items()):
            require(results.keys() == state_contests[seat].keys(), "County candidate roster differs from control")
            seen_components.add((fips, seat))
            for key, candidate in sorted(results.items()):
                control = state_contests[seat][key]
                require(candidate["candidate_name"].upper().split() == control["candidate_name"].upper().split(),
                        "Candidate native ID changed names")
                county_party = candidate["literal_party"].strip("()")
                require(county_party == control["literal_party"]
                        or (control["literal_party"], county_party) == ("UNA", "NON"),
                        "Candidate party differs from reviewed labels")
                summed[seat, key] += candidate["votes"]
                county_votes.append({"county_fips": fips, "old_district": seat, "native_candidate_id": key,
                                     "statewide_literal_party": control["literal_party"], **candidate})
    controls = []
    for seat, candidates in sorted(state_contests.items()):
        for key, control in sorted(candidates.items()):
            county_sum = summed[seat, key]
            require(county_sum == control["votes"], "County sums do not reconcile to statewide House totals")
            controls.append({"old_district": seat, "native_candidate_id": key,
                             "county_sum_votes": county_sum, **control})

    review = originals["census-boundary-review.json"]
    plans = []
    for year in (119, 120):
        name = f"cd{year}.zip"
        require(digest((root / name).read_bytes()) == review["evidence"][name]["sha256"]
                and not any(r["state_fips"] == "49" for r in review["split_blocks"][str(year)]),
                "Changed or unresolved split-block evidence")
        plans.append(block_assignments(root / name, year))
    old, new = plans
    require(old.keys() == new.keys() and len(old) == 71207, "Utah block universes differ")
    transfers = defaultdict(Counter)
    for geoid, seat in old.items():
        transfers[geoid[:5], seat][new[geoid]] += 1
    require(transfers.keys() == seen_components, "County-by-old-district geometry differs from the canvass")
    components = [{"county_fips": county, "old_district": seat,
                   "new_districts": ";".join(sorted(destinations)),
                   "blocks_by_new_district": json.dumps(destinations, sort_keys=True),
                   "whole_component": len(destinations) == 1, "votes_allocated": False}
                  for (county, seat), destinations in sorted(transfers.items())]
    intact_votes = [
        {**row, "new_district": next(iter(destinations)),
         "scope": "whole_component_only_not_complete_district", "votes_allocated": False}
        for row in county_votes
        if len(destinations := transfers[row["county_fips"], row["old_district"]]) == 1
    ]
    district_rows = []
    for seat in sorted(SEATS):
        incoming = {k: v for k, v in transfers.items() if seat in v}
        split = [k for k, v in incoming.items() if len(v) > 1]
        district_rows.append({"district": f"UT-{seat}", "incoming_components": len(incoming),
                              "intact_components": len(incoming) - len(split), "split_components": len(split),
                              "exact_complete_county_components": not split,
                              "new_swing_qualified_by_audit": False})
    return {
        "utah-house-county-catalog.csv": inventory,
        "utah-house-county-candidate-votes.csv": county_votes,
        "utah-house-statewide-controls.csv": controls,
        "utah-house-county-components.csv": components,
        "utah-house-intact-component-votes.csv": intact_votes,
        "utah-house-district-holds.csv": district_rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    outputs = audit(args.inputs)
    args.output.mkdir()
    for name, records in outputs.items():
        with (args.output / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(records)
    print(json.dumps({name: len(records) for name, records in outputs.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
