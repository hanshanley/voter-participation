"""Reconcile certified California House returns with exact county components."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

import openpyxl


PINS = {
    "ca-2024-official-house.xlsx": "855a59ee865e933d6725922869119897018b518db00fed12e9441f79a0062e1b",
    "ca-ab604-blocks.csv": "ac11292bf0e862a0b2716dc687a9eb91fdc4b480ae115c0a21848f3fbd7173b2",
    "census-boundary-review.json": "9fc17fce1f678d5b1afc4f91a9206556fe4063a74350a4ba7231d4d0e3c8f4eb",
}
COUNTIES = (
    "Alameda|Alpine|Amador|Butte|Calaveras|Colusa|Contra Costa|Del Norte|El Dorado|Fresno|Glenn|"
    "Humboldt|Imperial|Inyo|Kern|Kings|Lake|Lassen|Los Angeles|Madera|Marin|Mariposa|Mendocino|"
    "Merced|Modoc|Mono|Monterey|Napa|Nevada|Orange|Placer|Plumas|Riverside|Sacramento|San Benito|"
    "San Bernardino|San Diego|San Francisco|San Joaquin|San Luis Obispo|San Mateo|Santa Barbara|"
    "Santa Clara|Santa Cruz|Shasta|Sierra|Siskiyou|Solano|Sonoma|Stanislaus|Sutter|Tehama|Trinity|"
    "Tulare|Tuolumne|Ventura|Yolo|Yuba"
).split("|")
FIPS = {county: f"06{2 * i + 1:03}" for i, county in enumerate(COUNTIES)}
SEATS = {f"{seat:02}" for seat in range(1, 53)}
HEADING = re.compile(r"([0-9]+)(?:st|nd|rd|th) Congressional District")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_canvass(rows):
    rows = iter(rows)
    controls, components = {}, {}
    for label, *cells in rows:
        if not label and not any(cells):
            continue
        heading = HEADING.fullmatch(str(label))
        require(heading and all(c is None for c in cells), "Unexpected California district heading")
        seat = heading[1].zfill(2)
        require(seat in SEATS and seat not in controls, "Invalid or duplicate California district")
        blank, names, parties = (next(rows) for _ in range(3))
        require(not any(blank) and names[0] is None and parties[0] is None
                and all(isinstance(s, str) and s.strip() for s in names[1:3])
                and all(p in {"DEM", "REP", "NPP"} for p in parties[1:3])
                and not any(names[3:]) and not any(parties[3:]), "Unexpected candidate headers")
        candidates = [(" ".join(name.split()), party) for name, party in zip(names[1:3], parties[1:3])]
        sums = [0, 0]
        for county, left, right, *rest in rows:
            require(all(x is None for x in rest)
                    and all(type(v) is int and v >= 0 for v in (left, right)), "Invalid certified House count")
            if county == "District Totals":
                require([left, right] == sums, "County counts do not reconcile to certified district totals")
                controls[seat] = [(name, party, votes) for (name, party), votes in zip(candidates, sums)]
                break
            require(county in FIPS and (FIPS[county], seat) not in components,
                    "Unknown or duplicate California county component")
            components[FIPS[county], seat] = [
                (name, party, votes) for (name, party), votes in zip(candidates, (left, right))]
            sums[0] += left
            sums[1] += right
        require(seat in controls and str(next(rows)[0]).strip() == "Percent",
                "Missing California district control")
    require(controls.keys() == SEATS, "Incomplete California House inventory")
    return controls, components


def assignments(rows, *, statewide=False):
    result = {}
    for row in rows:
        if not statewide and not row[0].startswith("06"):
            continue
        geoid, seat = row[0], row[-1].zfill(2)
        require(re.fullmatch(r"06[0-9]{13}", geoid) and geoid not in result and seat in SEATS,
                "Invalid or duplicate California block")
        result[geoid] = seat
    require(len(result) == 519723, "Incomplete California block inventory")
    return result


def audit(root):
    def checked(name, sha):
        body = (root / name).read_bytes()
        require(hashlib.sha256(body).hexdigest() == sha, "Changed California audit input: " + name)
        return body

    review = json.loads(checked("census-boundary-review.json", PINS["census-boundary-review.json"]))
    plans = []
    for congress in (119, 120):
        name = f"cd{congress}.zip"
        require(not any(row["state_fips"] == "06" for row in review["split_blocks"][str(congress)]),
                "Unresolved California split Census blocks")
        with zipfile.ZipFile(io.BytesIO(checked(name, review["evidence"][name]["sha256"]))) as archive:
            with archive.open(f"NationalCD{congress}.txt") as member:
                reader = csv.reader(io.TextIOWrapper(member, encoding="ascii", newline=""))
                header = next(reader)
                require(header[0] == "GEOID" and header[-1] == "CDFP", "Unexpected Census assignment schema")
                plans.append(assignments(reader))
    old, new = plans
    enacted = assignments(csv.reader(io.StringIO(
        checked("ca-ab604-blocks.csv", PINS["ca-ab604-blocks.csv"]).decode("utf-8-sig"))), statewide=True)
    require(old.keys() == new.keys() and enacted == new, "California enacted plan and Census evidence differ")
    workbook = openpyxl.load_workbook(io.BytesIO(
        checked("ca-2024-official-house.xlsx", PINS["ca-2024-official-house.xlsx"])),
        read_only=True, data_only=True)
    try:
        controls, components = parse_canvass(workbook["Representative in Congress"].values)
    finally:
        workbook.close()

    destinations = defaultdict(Counter)
    for geoid, seat in old.items():
        destinations[geoid[:5], seat][new[geoid]] += 1
    require(components.keys() == destinations.keys(), "Certified components disagree with prior plan geography")

    all_votes, component_rows = [], []
    for key, candidates in sorted(components.items()):
        targets = destinations[key]
        complete = len(targets) == 1
        component_rows.append({"county_fips": key[0], "old_district": key[1],
                               "blocks_by_new_district": json.dumps(targets, sort_keys=True),
                               "new_districts": ";".join(sorted(targets)), "intact": complete,
                               "candidate_votes": sum(votes for _, _, votes in candidates)})
        all_votes.extend({"county_fips": key[0], "old_district": key[1],
                          "candidate": name, "literal_party": party, "votes": votes,
                          "intact_component_destination": next(iter(targets)) if complete else "",
                          "fragment_votes_allocated": False} for name, party, votes in candidates)
    district_rows = []
    for seat in sorted(SEATS):
        members = [r for r in component_rows if seat in r["new_districts"].split(";")]
        intact = [r for r in members if r["intact"]]
        district_rows.append({"new_district": f"CA-{seat}", "incoming_components": len(members),
                              "intact_components": len(intact), "split_components": len(members) - len(intact),
                              "intact_candidate_votes": sum(r["candidate_votes"] for r in intact),
                              "all_components_intact": len(intact) == len(members),
                              "swing_qualified_by_audit": False})
    return {
        "california-house-certified-district-controls.csv": [
            {"old_district": seat, "candidate": name, "literal_party": party, "votes": count}
            for seat, candidates in sorted(controls.items()) for name, party, count in candidates],
        "california-house-certified-county-votes.csv": all_votes,
        "california-house-county-component-geography.csv": component_rows,
        "california-house-intact-component-votes.csv": [r for r in all_votes if r["intact_component_destination"]],
        "california-house-new-district-coverage.csv": district_rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    outputs = audit(args.inputs)
    args.output.mkdir()
    for name, rows in outputs.items():
        with (args.output / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps({name: len(rows) for name, rows in outputs.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
