"""Reconcile Texas's 2024 House returns against enacted precinct and VTD inventories."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import zipfile

import openpyxl
import xlrd


PINS = {
    "tx-2024-precinct-districts.xlsx": "c726e807c2cb3b15fa789d49b43f784f891ad6ced3e5a88ba686a446cb5ba134",
    "tx-precincts-new-plan.xls": "38c8a22947d5f05b075a29f12c679abdc0b7336784cc80f82effb398f5aafa05",
    "tx-split-precincts-old-plan.xls": "a86bbdc1ec84992ca066a23b51f169d41b452f710a69e9ae4494504839253b00",
    "tx-split-precincts-new-plan.xls": "9689b7d1c86c219ef8b1efcec6eb68832fe88a2dd2740ca2e60c647751bbe77d",
    "tx-old-vtd.xls": "e79fa7dd3fd749134db81517a6bfdc5500e3809eb8b545e674a2137401a94a70",
    "tx-new-vtd.xls": "07d8f96f11b1f4d53d9896201e7b07535e2c8602296e36bfd811027f65b6a8b8",
    "2024_General_Election_Returns.csv": "575746d36c66dfffc16162aaa3bc59ba5fc2286a246bf5943f8a6774ceb6bd72",
    "congress-comparisons.csv": "f3d11c079b907f6a4abf5bdd4ebadb193ff299291435d9a03970277e5b111177",
}
SEATS = set(range(1, 39))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_pinned(root, name):
    body = (root / name).read_bytes()
    require(hashlib.sha256(body).hexdigest() == PINS[name], "Changed Texas audit input: " + name)
    return body


def precinct_points(body):
    workbook = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        rows = workbook["PrecinctPoints24G_CurrentPlansU"].values
        require(next(rows) == ("FIPS", "FENAME", "PREC", "PCTKEY", "PlanC2193",
                               "PlanH2316", "PlanS2168", "PlanE2106"), "Unexpected 2024 precinct schema")
        points, counties = {}, {}
        for fips, county, precinct, key, district, *_ in rows:
            require(re.fullmatch(r"[0-9]{3}", fips) and precinct and county == county.upper()
                    and key == str(int(fips)) + precinct and district in SEATS
                    and (fips, precinct) not in points, "Invalid 2024 precinct identity")
            require(counties.setdefault(county, fips) == fips, "Ambiguous Texas county")
            points[fips, precinct] = {district}
        require(len(points) == 9657 and len(counties) == len(set(counties.values())) == 254,
                "Incomplete 2024 precinct points")
        return points, counties
    finally:
        workbook.close()


def plan_report(body, counties, plan, *, splits):
    with open(os.devnull, "w") as diagnostics:
        workbook = xlrd.open_workbook(file_contents=body, logfile=diagnostics)
    sheet = workbook.sheet_by_name("Red380" if splits else "Red375")
    title = "\n".join(str(cell) for i in range(6) for cell in sheet.row_values(i))
    require("2024 General Election Precincts" in title and f"CONGRESSIONAL DISTRICTS - {plan}" in title,
            "Unexpected plan or precinct vintage")
    col, start = (4, 9) if splits else (3, 7)
    report, starred = defaultdict(set), set()
    district = county = None
    for i in range(start, sheet.nrows):
        seat, area, unit = sheet.row_values(i)[col:col + 3]
        if seat != "":
            require(type(seat) is float and seat.is_integer() and int(seat) in SEATS,
                    "Malformed report seat")
            district = int(seat)
            county = None
        if area:
            county = counties[area.removesuffix(" *").upper()]
        if unit:
            key = county, unit.removeprefix("** ")
            require(county and district and district not in report[key], "Duplicate or unassigned report precinct")
            report[key].add(district)
            if unit.startswith("** "):
                starred.add((key, district))
    if splits:
        match = re.fullmatch(r"Total Splits: ([0-9]+)", sheet.cell_value(6, 8))
        require(match and len(report) == int(match[1]) and all(len(seats) > 1 for seats in report.values()),
                "Incomplete split precinct inventory")
    else:
        require(starred == {(key, seat) for key, seats in report.items() if len(seats) > 1 for seat in seats}
                and {seat for seats in report.values() for seat in seats} == SEATS,
                "Split marker or district inventory differs")
    return dict(report)


def csv_rows(body):
    return csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline=""))


def vtd_report(body, counties, plan):
    with open(os.devnull, "w") as diagnostics:
        workbook = xlrd.open_workbook(file_contents=body, logfile=diagnostics)
    sheet = workbook.sheet_by_name("Red110C")
    require("2024 General Election VTDs" in sheet.cell_value(1, 1)
            and sheet.cell_value(3, 9) == f"CONGRESSIONAL DISTRICTS - {plan}", "Unexpected VTD vintage or plan")
    report, marked, seen_seats = defaultdict(set), set(), set()
    district = county = None
    for i in range(9, sheet.nrows):
        label, fragment, _, measure, _ = sheet.row_values(i)[2:7]
        if not label:
            continue
        if match := re.fullmatch(r"DISTRICT ([0-9]+)", label):
            district = int(match[1])
            require(district not in seen_seats and measure == "Total:", "Duplicate VTD district heading")
            seen_seats.add(district)
            county = None
        elif match := re.fullmatch(r"(.+) \([0-9]+ %\)", label):
            county = counties[match[1].upper()]
        else:
            key = county, label
            require(county and district and measure == "Total:" and district not in report[key],
                    "Malformed VTD report row")
            report[key].add(district)
            if fragment:
                require(re.fullmatch(r"[0-9.]+%", fragment), "Unknown VTD split marker")
                marked.add((key, district))
    require(seen_seats == SEATS and len(report) == 9712
            and marked == {(key, seat) for key, seats in report.items() if len(seats) > 1 for seat in seats},
            "Incomplete VTD inventory or inconsistent split markers")
    return dict(report)


def audit(bodies):
    old, counties = precinct_points(bodies["tx-2024-precinct-districts.xlsx"])
    old_splits = plan_report(bodies["tx-split-precincts-old-plan.xls"], counties, "PLANC2193", splits=True)
    for key, seats in old_splits.items():
        require(key in old and old[key] <= seats, "Old precinct split disagrees with precinct points")
        old[key] = seats
    new = plan_report(bodies["tx-precincts-new-plan.xls"], counties, "PLANC2333", splits=False)
    new_splits = plan_report(bodies["tx-split-precincts-new-plan.xls"], counties, "PLANC2333", splits=True)
    require(new_splits == {key: seats for key, seats in new.items() if len(seats) > 1},
            "New precinct and split reports disagree")
    old_vtd = vtd_report(bodies["tx-old-vtd.xls"], counties, "PLANC2193")
    new_vtd = vtd_report(bodies["tx-new-vtd.xls"], counties, "PLANC2333")
    require(old_vtd.keys() == new_vtd.keys(), "Official VTD rosters differ across plans")

    controls = {}
    for row in csv_rows(bodies["congress-comparisons.csv"]):
        if row["chamber"] == "house" and row["state_code"] == "TX" and row["advertised"] == "True":
            seat = int(row["seat"])
            require(seat not in controls and row["baseline"] and row["previous"], "Texas comparison control differs")
            previous = json.loads(row["previous"])
            controls[seat] = ({p: previous[p] for p in "DRO"}, json.loads(row["comparison_holds"]))
    require(controls.keys() == SEATS, "Missing Texas historical comparison controls")

    returns = csv_rows(bodies["2024_General_Election_Returns.csv"])
    require(returns.fieldnames == ["County", "FIPS", "VTD", "cntyvtd", "vtdkeyvalue",
                                  "Office", "Name", "Party", "Incumbent", "Votes"],
            "Unexpected Texas return schema")
    units, totals, seen, raw = defaultdict(Counter), defaultdict(Counter), set(), []
    for row in returns:
        match = re.fullmatch(r"U\.S\. Rep (\d+)", row["Office"])
        if not match:
            require(not row["Office"].startswith("U.S. Rep"), "Unexpected House office label")
            continue
        seat, precinct, party = int(match[1]), row["VTD"], row["Party"]
        fips = counties.get(row["County"].upper())
        key = fips, precinct
        identity = key, seat, row["Name"], party
        require(fips and row["FIPS"].zfill(3) == fips and precinct
                and row["cntyvtd"] == row["FIPS"] + precinct and seat in SEATS
                and re.fullmatch(r"[DRLIW]", party) and row["Name"] and identity not in seen
                and re.fullmatch(r"[0-9]+", row["Votes"]), "Invalid or duplicate Texas House return")
        seen.add(identity)
        votes = int(row["Votes"])
        units[key][seat] += votes
        totals[seat][party if party in "DR" else "O"] += votes
        raw.append({**row, "old_plan_key_matches_office": seat in old.get(key, ()),
                    "new_plan_key_exact": key in new,
                    "old_plan_vtd_matches_office": seat in old_vtd.get(key, ()),
                    "new_plan_vtd_key_exact": key in new_vtd})

    by_county = {value: name for name, value in counties.items()}
    roster = [{
        "county_fips": "48" + fips, "county": by_county[fips], "source_precinct_key": precinct,
        "old_plan_seats": ";".join(map(str, sorted(old.get((fips, precinct), ())))),
        "new_plan_seats": ";".join(map(str, sorted(new.get((fips, precinct), ())))),
        "house_return_votes_by_old_seat": json.dumps(units.get((fips, precinct), {}), sort_keys=True),
        "exact_join_in_both_plans": (fips, precinct) in old and (fips, precinct) in new,
    } for fips, precinct in sorted(old.keys() | new.keys() | units.keys())]
    vtds = [{
        "county_fips": "48" + fips, "county": by_county[fips], "source_vtd": vtd,
        "old_plan_seats": ";".join(map(str, sorted(old_vtd.get((fips, vtd), ())))),
        "new_plan_seats": ";".join(map(str, sorted(new_vtd.get((fips, vtd), ())))),
        "house_return_votes_by_old_seat": json.dumps(units.get((fips, vtd), {}), sort_keys=True),
        "new_plan_splits_vtd": len(new_vtd.get((fips, vtd), ())) > 1,
        "votes_reallocated": False,
    } for fips, vtd in sorted(new_vtd.keys() | units.keys())]
    districts = []
    for seat in sorted(SEATS):
        control, holds = controls[seat]
        report = totals.get(seat)
        keys = [key for key, seats in new.items() if seat in seats]
        conflicts = [key for key in units if seat in units[key] and seat not in old.get(key, ())]
        no_new_match = [key for key in units if seat in units[key] and key not in new]
        vtd_keys = [key for key, seats in new_vtd.items() if seat in seats]
        vtd_splits = [key for key in vtd_keys if len(new_vtd[key]) > 1]
        vtd_conflicts = [key for key in units if seat in units[key] and seat not in old_vtd.get(key, ())]
        missing_old_contests = sorted({old_seat for key in vtd_keys for old_seat in old_vtd[key]
                                       if old_seat not in totals})
        districts.append({
            "district": f"TX-{seat:02d}", "comparison_holds_before_audit": "; ".join(holds),
            "new_plan_keys": len(keys), "new_plan_split_keys": sum(key in new_splits for key in keys),
            "new_plan_keys_missing_old_exact_match": sum(key not in old for key in keys),
            "old_office_return_present": report is not None,
            "old_office_return_keys_missing_exact_new_key": len(no_new_match),
            "old_office_votes_missing_exact_new_key": sum(units[key][seat] for key in no_new_match),
            "old_office_return_keys_inconsistent_with_old_plan": len(conflicts),
            "old_office_votes_inconsistent_with_old_plan": sum(units[key][seat] for key in conflicts),
            "new_plan_vtd_keys": len(vtd_keys), "new_plan_split_vtd_keys": len(vtd_splits),
            "new_plan_split_vtd_keys_with_positive_house_votes": sum(sum(units.get(key, {}).values()) > 0
                                                                    for key in vtd_splits),
            "old_office_vtd_keys_inconsistent_with_old_plan": len(vtd_conflicts),
            "old_office_vtd_votes_inconsistent_with_old_plan": sum(units[key][seat] for key in vtd_conflicts),
            "incoming_old_offices_missing_from_bulk_returns": ";".join(map(str, missing_old_contests)),
            **{f"historical_control_{p}": control[p] for p in "DRO"},
            **{f"bulk_return_{p}": report[p] if report is not None else None for p in "DRO"},
            "bulk_party_totals_reconcile": report is not None and all(report[p] == control[p] for p in "DRO"),
            "new_swing_qualified_by_audit": False,
        })
    return {"texas-house-district-audit.csv": districts,
            "texas-house-precinct-key-audit.csv": roster, "texas-house-vtd-key-audit.csv": vtds,
            "texas-house-source-votes.csv": raw}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    outputs = audit({name: read_pinned(args.inputs, name) for name in PINS})
    args.output.mkdir()
    for name, rows in outputs.items():
        with (args.output / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps({name: len(rows) for name, rows in outputs.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
