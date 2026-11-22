"""Reproduce the Alabama House vote-unit audit without allocating split votes."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

import xlrd


COUNTIES = (
    "AUTAUGA BALDWIN BARBOUR BIBB BLOUNT BULLOCK BUTLER CALHOUN CHAMBERS CHEROKEE CHILTON CHOCTAW "
    "CLARKE CLAY CLEBURNE COFFEE COLBERT CONECUH COOSA COVINGTON CRENSHAW CULLMAN DALE DALLAS DEKALB "
    "ELMORE ESCAMBIA ETOWAH FAYETTE FRANKLIN GENEVA GREENE HALE HENRY HOUSTON JACKSON JEFFERSON LAMAR "
    "LAUDERDALE LAWRENCE LEE LIMESTONE LOWNDES MACON MADISON MARENGO MARION MARSHALL MOBILE MONROE "
    "MONTGOMERY MORGAN PERRY PICKENS PIKE RANDOLPH RUSSELL STCLAIR SHELBY SUMTER TALLADEGA TALLAPOOSA "
    "TUSCALOOSA WALKER WASHINGTON WILCOX WINSTON"
).split()
FIPS = {county: f"01{2 * i + 1:03}" for i, county in enumerate(COUNTIES)}
SEATS = {f"{i:02}" for i in range(1, 8)}
OFFICE = re.compile(r"UNITED STATES REPRESENTATIVE, ([1-7])(?:ST|ND|RD|TH) CONGRESSIONAL DISTRICT")
PINS = {
    "AL-2024-general-precinct-ballot-archive.zip": "4ecca55fc235018aeb2385debd375e6fa7aaa553c5bd67786add08d850efcc96",
    "congress-comparisons.csv": "bce3a5bb6f8ba72c795ca83f1c4fdd54febb0011f25b47b89d340b64bc180327",
    "census-boundary-review.json": "9fc17fce1f678d5b1afc4f91a9206556fe4063a74350a4ba7231d4d0e3c8f4eb",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact_original(root, name, sha):
    body = (root / name).read_bytes()
    require(hashlib.sha256(body).hexdigest() == sha, "Changed audit input: " + name)
    return body


def vote_rows(body):
    rows, seen = [], set()
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        for member in sorted(archive.namelist()):
            match = re.fullmatch(r"2024-General-([A-Za-z ._'-]+)\.xls", member)
            require(match, "Unexpected Alabama workbook name")
            county = re.sub(r"[^A-Z]", "", match[1].upper())
            require(county in FIPS and county not in seen, "Unexpected Alabama county roster")
            seen.add(county)
            sheet = xlrd.open_workbook(file_contents=archive.read(member)).sheet_by_name("Precinct Results")
            header = [str(x).strip() for x in sheet.row_values(0)]
            labels = header[3:]
            require(header[:3] == ["Contest Title", "Party", "Candidate"] and all(labels)
                    and len(labels) == len(set(labels)), "Unexpected Alabama workbook columns")
            candidates = set()
            for index in range(3, sheet.nrows):
                title, party, name, *counts = sheet.row_values(index)
                title, party, name = (str(value).strip() for value in (title, party, name))
                match = OFFICE.fullmatch(title)
                if not match:
                    require(not title.startswith("UNITED STATES REPRESENTATIVE,"), "Unknown House title")
                    continue
                if name in ("Over Votes", "Under Votes"):
                    continue
                seat = match[1].zfill(2)
                identity = (seat, name, party)
                require(name and party in {"DEM", "REP", "NON"} and identity not in candidates,
                        "Unexpected or duplicated candidate row")
                candidates.add(identity)
                for col, (label, value) in enumerate(zip(labels, counts), 4):
                    if value == "":
                        continue
                    require(type(value) is float and value.is_integer() and value >= 0, "Invalid native vote count")
                    rows.append({"county_fips": FIPS[county], "county": county, "old_district": seat,
                                 "reporting_unit": label,
                                 "central_mode_label": label if re.search(r"ABSENTEE|PROVISIONAL", label) else "",
                                 "candidate": name, "literal_party": party, "votes": int(value),
                                 "workbook": member, "row": index + 1, "column": col})
    require(seen == FIPS.keys(), "Incomplete Alabama county roster")
    return rows


def assignments(body, congress):
    result = {}
    with zipfile.ZipFile(io.BytesIO(body)) as archive, archive.open(f"NationalCD{congress}.txt") as member:
        reader = csv.reader(io.TextIOWrapper(member, encoding="ascii", newline=""))
        header = next(reader)
        require(header[0] == "GEOID" and header[-1] == "CDFP", "Unexpected Census header")
        for row in reader:
            if not row[0].startswith("01"):
                continue
            geoid, seat = row[0], row[-1]
            require(len(row) == len(header) and re.fullmatch(r"01[0-9]{13}", geoid)
                    and geoid not in result and seat in SEATS, "Invalid Alabama block")
            result[geoid] = seat
    require(len(result) == 185976, "Incomplete Alabama block inventory")
    return result


def audit(root):
    bodies = {name: exact_original(root, name, sha) for name, sha in PINS.items()}
    review = json.loads(bodies["census-boundary-review.json"])
    plans = []
    for year in (119, 120):
        require(not any(row["state_fips"] == "01" for row in review["split_blocks"][str(year)]),
                "Unresolved Alabama Census block split")
        name = f"cd{year}.zip"
        plans.append(assignments(exact_original(root, name, review["evidence"][name]["sha256"]), year))
    old, new = plans
    require(old.keys() == new.keys(), "Alabama block universes differ")
    targets = defaultdict(Counter)
    for geoid, seat in old.items():
        targets[geoid[:5], seat][new[geoid]] += 1
    rows = vote_rows(bodies["AL-2024-general-precinct-ballot-archive.zip"])
    require({(row["county_fips"], row["old_district"]) for row in rows} == targets.keys(),
            "Vote archives and old district geography disagree")

    controls, actual = {}, defaultdict(Counter)
    for row in csv.DictReader(io.StringIO(bodies["congress-comparisons.csv"].decode())):
        if row["chamber"] == "house" and row["state_code"] == "AL" and row["advertised"] == "True":
            baseline = json.loads(row["baseline"])
            seat = row["seat"].zfill(2)
            require(seat not in controls and baseline["year"] == 2024, "Duplicate or incorrect House control")
            controls[seat] = baseline["query"]["reported_counts"]
    require(controls.keys() == SEATS, "Missing Alabama historical controls")
    county_votes = Counter()
    for row in rows:
        seat, county, party, candidate = (row[k] for k in ("old_district", "county_fips", "literal_party", "candidate"))
        group = {"DEM": "D", "REP": "R", "NON": "O"}[party]
        actual[seat][group] += row["votes"]
        county_votes[county, seat, party, candidate] += row["votes"]
    require(all({p: actual[seat][p] for p in "DRO"} == controls[seat] for seat in sorted(SEATS)),
            "Native archive differs from historical House controls")

    components = [{"county_fips": county, "old_district": seat, "new_districts": ";".join(sorted(destinations)),
                   "blocks_by_new_district": json.dumps(destinations, sort_keys=True),
                   "intact": len(destinations) == 1} for (county, seat), destinations in sorted(targets.items())]
    county_rows = [
        {"county_fips": county, "old_district": seat, "literal_party": party, "candidate": candidate, "votes": votes,
         "intact_component_destination": next(iter(destinations)) if len(destinations) == 1 else "",
         "fragment_votes_allocated": False}
        for (county, seat, party, candidate), votes in sorted(county_votes.items())
        for destinations in (targets[county, seat],)
    ]
    for row in rows:
        row["component_split"] = len(targets[row["county_fips"], row["old_district"]]) > 1
        row["fragment_votes_allocated"] = False
    district_rows = []
    for seat in sorted(SEATS):
        incoming = [r for r in components if seat in r["new_districts"].split(";")]
        split = [r for r in incoming if not r["intact"]]
        district_rows.append({"district": f"AL-{seat}", "incoming_components": len(incoming),
                              "split_components": len(split), "complete_at_county_component_level": not split,
                              "swing_qualified_by_audit": False})
    return {"alabama-house-reporting-unit-votes.csv": rows, "alabama-house-county-candidate-votes.csv": county_rows,
            "alabama-house-county-components.csv": components, "alabama-house-district-holds.csv": district_rows,
            "alabama-house-historical-controls.csv": [
                {"old_district": seat, **{p: actual[seat][p] for p in "DRO"}} for seat in sorted(SEATS)]}


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
