"""Reproduce the North Carolina 2024 House vote-geography audit without allocating votes."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

import shapefile


PINS = {
    "census-boundary-review.json": "9fc17fce1f678d5b1afc4f91a9206556fe4063a74350a4ba7231d4d0e3c8f4eb",
    "nc-results-2024.zip": "2fab44e9b12e03c0d88ef832c2e6dc8c569e2b020d64df06a8b551b62bbdb426",
    "nc-precinct-crosswalk.dbf": "0ef20ecc136e7a31a6b1c536013e510eb6879d4691428ac8a9f2771efa663424",
    "nc-precinct-sort-2024.txt": "1c36648c7bb1ef81e05cad34b9ca4bd217b0baaca6fbf68c1ee13fda927491b9",
}
OFFICE = re.compile(r"US HOUSE OF REPRESENTATIVES DISTRICT (0[1-9]|1[0-4])")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def assignments(path, congress):
    with zipfile.ZipFile(path) as archive, archive.open(f"NationalCD{congress}.txt") as member:
        rows = csv.reader(io.TextIOWrapper(member, encoding="ascii", newline=""))
        header = next(rows)
        require(header[0] == "GEOID" and header[-1] == "CDFP", "Unexpected Census assignment schema")
        result = {}
        for row in rows:
            block = row[0]
            if not block.startswith("37"):
                continue
            require(len(row) == len(header) and re.fullmatch(r"37[0-9]{13}", block)
                    and block not in result, "Invalid or duplicate NC Census block")
            result[block] = row[-1]
    return result


def audit(root):
    for name, pin in PINS.items():
        require(digest(root / name) == pin, "Changed NC original: " + name)
    review = json.loads((root / "census-boundary-review.json").read_bytes())
    for congress in (119, 120):
        name = f"cd{congress}.zip"
        require(digest(root / name) == review["evidence"][name]["sha256"], "Changed Census original: " + name)
    old, new = (assignments(root / f"cd{congress}.zip", congress) for congress in (119, 120))
    require(old.keys() == new.keys(), "NC block universes differ")
    moved = {g for g in old if old[g] != new[g]}
    keys, blocks, unassigned = defaultdict(set), defaultdict(set), set()
    with shapefile.Reader(dbf=str(root / "nc-precinct-crosswalk.dbf")) as reader:
        for record in reader.iterRecords(fields=["county_nam", "prec_id", "GEOID20"]):
            fact = record.as_dict()
            g, key = fact["GEOID20"], (fact["county_nam"], fact["prec_id"])
            require(g in old and (all(key) or not any(key)), "Crosswalk block or precinct identity differs")
            if not any(key):
                require(g not in moved, "Moved block is unassigned in the precinct crosswalk")
                unassigned.add(g)
                continue
            keys[g].add(key)
            blocks[key].add(g)
    require(all(len(keys[g]) == 1 for g in moved), "Moved block lacks a unique crosswalk assignment")

    precinct_candidates, source, seen, all_votes = defaultdict(Counter), Counter(), set(), []
    with (root / "nc-precinct-sort-2024.txt").open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            office = OFFICE.fullmatch(row["contest_title"])
            require(office or not row["contest_title"].startswith("US HOUSE OF REPRESENTATIVES DISTRICT "),
                    "Unrecognized NC precinct-sort House district")
            if not office or row["result_type_lbl"] != "STD":
                continue
            seat, county, precinct = int(office[1]), row["county"], row["precinct_code"]
            party, name, mode = row["candidate_party_lbl"].strip(), row["candidate_name"], row["voting_method_lbl"]
            identity = seat, county, precinct, row["candidate_id"], row["group_num"], mode
            require(row["election_dt"] == "11/05/2024" and row["contest_vote_for"] == "1"
                    and mode in {"V", "EV", "M", "P", "T"} and identity not in seen,
                    "Duplicate or incompatible NC precinct-sorted row")
            seen.add(identity)
            votes = int(row["vote_ct"])
            require(votes >= 0, "Negative NC vote count")
            key = county, precinct
            precinct_candidates[key][(seat, party, name, mode)] += votes
            source[seat, county, name, party] += votes
            all_votes.append({"historic_district": seat, "county": county, "precinct": precinct,
                              "candidate_id": row["candidate_id"], "candidate": name, "party": party,
                              "mode": mode, "source_group": row["group_num"], "votes": votes})
    totals = Counter()
    with (zipfile.ZipFile(root / "nc-results-2024.zip") as archive,
          archive.open("results_pct_20241105.txt") as stream):
        for row in csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"), delimiter="\t"):
            office = OFFICE.fullmatch(row["Contest Name"])
            require(office or not row["Contest Name"].startswith("US HOUSE OF REPRESENTATIVES DISTRICT "),
                    "Unrecognized NC statewide House district")
            if office:
                counts = [int(row[k]) for k in ("Election Day", "Early Voting", "Absentee by Mail", "Provisional")]
                require(sum(counts) == int(row["Total Votes"]) and min(counts) >= 0,
                        "Statewide return mode totals do not reconcile")
                totals[int(office[1]), row["County"], row["Choice"], row["Choice Party"].strip()] += sum(counts)
    require({k[0] for k in source} == {k[0] for k in totals} == set(range(1, 15)),
            "Incomplete candidate returns across the 14 House districts")
    reconciliation = [{"historic_district": seat, "county": county, "candidate": name, "party": party,
                       "precinct_sort_votes": source.get((seat, county, name, party)),
                       "statewide_return_votes": totals.get((seat, county, name, party)),
                       "difference": source[seat, county, name, party] - totals[seat, county, name, party]}
                      for seat, county, name, party in sorted(source.keys() | totals.keys())]
    geography_rows, vote_rows = [], []
    for county, precinct in sorted(set().union(*(keys[g] for g in moved))):
        ids = blocks[county, precinct]
        old_ids, new_ids = ({assignment[g] for g in ids} for assignment in (old, new))
        geography_rows.append({"county": county, "precinct": precinct,
                               "old_districts": ";".join(sorted(old_ids)),
                               "new_districts": ";".join(sorted(new_ids)),
                               "blocks": len(ids), "moved_blocks": len(ids & moved),
                               "new_plan_split": len(new_ids) > 1, "votes_allocated": False})
        for (seat, party, name, mode), count in sorted(precinct_candidates[county, precinct].items()):
            vote_rows.append({"county": county, "precinct": precinct, "old_contest": seat,
                              "candidate": name, "party": party, "mode": mode, "votes": count,
                              "new_plan_split": len(new_ids) > 1, "votes_allocated": False})
    return {
        "nc-house-unassigned-blocks.csv": [
            {"geoid": g, "old_district": old[g], "new_district": new[g],
             "precinct_unassigned": True, "district_assignment_changed": False} for g in sorted(unassigned)],
        "nc-house-moved-blocks.csv": [
            {"geoid": g, "old_district": old[g], "new_district": new[g],
             "county": next(iter(keys[g]))[0], "precinct": next(iter(keys[g]))[1]} for g in sorted(moved)],
        "nc-house-affected-precincts.csv": geography_rows,
        "nc-house-affected-precinct-votes.csv": vote_rows,
        "nc-house-candidate-reconciliation.csv": reconciliation,
        "nc-house-precinct-sort-source-votes.csv": all_votes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    results = audit(args.inputs)
    args.output.mkdir()
    for name, rows in results.items():
        with (args.output / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps({name: len(rows) for name, rows in results.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
