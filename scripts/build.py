"""Normalize historical participation without conflating population denominators."""

import csv
import io
import json
import math
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import openpyxl
import shapefile
import xlrd
from pyproj import CRS, Transformer

from scripts.download import ROOT, atomic_json

OUT = ROOT / "public/data"
RACES = {
    "W": "White", "B": "Black", "A": "Asian", "I": "American Indian / Alaska Native",
    "M": "Two or more races", "P": "Native Hawaiian / Pacific Islander",
    "O": "Other race", "U": "Undesignated race",
}
ETHNICITY = {"HL": "Hispanic / Latino", "NL": "Not Hispanic / Latino", "UN": "Undesignated ethnicity"}
SEX = {"M": "Male", "F": "Female", "U": "Undesignated sex"}
NC_COLUMNS = ["county_desc", "precinct_abbrv", "age", "party_cd", "race_code",
              "ethnic_code", "sex_code", "total_voters", "election_date",
              "stats_type", "update_date", "voting_method", "voted_party_cd"]
META = json.loads((ROOT / "data/sources.json").read_text())
SOURCES = {s["path"]: s for s in META["sources"]}


def workbook(name):
    return list(openpyxl.load_workbook(ROOT / "data/raw/census" / name, data_only=True).active.values)


def numeric(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def warnings_for(year, dimension, basis):
    notes = []
    if basis == "cvap" and year < 1996:
        notes.append("Citizenship measurement before 1996 is not directly comparable with later years.")
    if dimension == "race" and year < 2004:
        notes.append("Race classification differs from 2004 onward; Asian includes Pacific Islanders.")
    if year < 1972:
        notes.append("Voting-age eligibility differs from the later 18+ series; consult workbook notes.")
    if dimension == "education" and year < 1992:
        notes.append("Historical educational attainment categories require caution across the 1992 CPS change.")
    return notes


def election_demographics():
    observations = []
    for spec in META["sources"]:
        if spec["kind"] != "cps_election_table" or spec["table"] != 5:
            continue
        path = ROOT / spec["path"]
        if path.suffix == ".xls":
            sheet = xlrd.open_workbook(path).sheet_by_index(0)
            rows = [sheet.row_values(i) for i in range(sheet.nrows)]
        else:
            rows = list(openpyxl.load_workbook(path, data_only=True).active.values)
        headings = next((row for row in rows[:12]
                         if any(str(v).strip().lower() == "total citizen population" for v in row)), None)
        if headings:
            citizen_col = next(i for i, v in enumerate(headings)
                               if str(v).strip().lower() == "total citizen population")
            voted_col = next(i for i, v in enumerate(headings)
                             if str(v).strip().lower() == "reported voted")
        else:
            if not any(str(row[10]).strip().lower() == "u.s. citizen" for row in rows[:12]):
                raise ValueError(f"Unrecognized citizen-population header: {path}")
            citizen_col, voted_col = None, 6
        label_col = 1 if citizen_col == 3 else 0
        sex, pending = None, ""
        education, sexes = {}, {}
        for row_number, row in enumerate(rows, 1):
            first = str(row[0] or "").strip(" .")
            if re.search(r"margins? of error", first, re.I):
                break
            if sex and re.match(r"\d+.*years", first, re.I):
                break
            if first.lower() in ["both sexes", "male", "female"]:
                sex = first.lower()
                pending = ""
            if sex is None:
                continue
            label = str(row[label_col] or "").strip(" .")
            if not numeric(row[voted_col]):
                if label and label.lower() not in ["both sexes", "male", "female"]:
                    pending += label + " "
                continue
            label = (pending + label).lower()
            pending = ""
            citizen = row[citizen_col] if citizen_col is not None else row[10] + row[11]
            voted = row[voted_col]
            if not numeric(citizen) or not 0 <= voted <= citizen or citizen <= 0:
                raise ValueError(f"Invalid citizen turnout counts: {path}:{row_number}")
            counts = (voted, citizen, row_number)
            if label == "total" and sex in ["male", "female"]:
                sexes[sex.title()] = counts
            if sex == "both sexes":
                for prefix, group in [
                    ("less than 9th", "Less than 9th grade"),
                    ("9th", "9th–12th grade, no diploma"),
                    ("high school", "High school / GED"),
                    ("some college", "Some college / associate's degree"),
                    ("bachelor", "Bachelor"), ("advanced", "Advanced"),
                ]:
                    if label.startswith(prefix):
                        education[group] = counts
                        break
        if len(education) != 6 or len(sexes) != 2:
            raise ValueError(f"Incomplete adult demographic block: {path}")
        grouped = [("education", group, [counts]) for group, counts in education.items()
                   if group not in ["Bachelor", "Advanced"]]
        grouped.append(("education", "Bachelor's degree or more",
                        [education["Bachelor"], education["Advanced"]]))
        grouped.extend(("sex", group, [counts]) for group, counts in sexes.items())
        for dimension, group, parts in grouped:
            voted, citizen = sum(p[0] for p in parts), sum(p[1] for p in parts)
            observations.append({
                "year": spec["year"], "election_type": "presidential" if spec["year"] % 4 == 0 else "midterm",
                "age_group": "All ages", "dimension": dimension, "group": group,
                "denominator": "cvap", "turnout_pct": round(100 * voted / citizen, 3),
                "source": str(path.relative_to(ROOT / "data/raw/census")),
                "source_row": [p[2] for p in parts],
                "warnings": ["Calculated from published thousand-person counts; rounding can differ from published percentages."],
                "participants_thousands": voted, "citizen_population_thousands": citizen,
            })
    return observations


def census_data():
    national, states = [], []
    rows = workbook("hst_vote01.xlsx")
    age = None
    measures = [
        (2, "overall", "All", "vap"), (3, "overall", "All", "cvap"),
        (4, "race", "White", "vap"), (5, "race", "White", "cvap"),
        (6, "race", "White, non-Hispanic", "vap"), (7, "race", "White, non-Hispanic", "cvap"),
        (8, "race", "Black", "vap"), (9, "race", "Black", "cvap"),
        (10, "race", "Asian", "vap"), (11, "race", "Asian", "cvap"),
        (12, "race", "Hispanic, any race", "vap"), (13, "race", "Hispanic, any race", "cvap"),
        (14, "sex", "Male", "vap"), (15, "sex", "Female", "vap"),
    ]
    for row_number, row in enumerate(rows, 1):
        label = str(row[0] or "")
        if "Percent Registered" in label:
            age = None
        elif "Percent Voted" in label:
            age = label.split(", Percent")[0].replace("Total", "All ages")
        if age is None or not isinstance(row[0], int):
            continue
        year = row[0]
        for column, dimension, group, basis in measures:
            if not numeric(row[column]):
                continue
            national.append({
                "year": year, "election_type": "presidential" if year % 4 == 0 else "midterm",
                "age_group": age, "dimension": dimension, "group": group,
                "denominator": basis, "turnout_pct": row[column],
                "source": "hst_vote01.xlsx", "source_row": row_number,
                "warnings": warnings_for(year, dimension, basis),
            })
    for row_number, row in enumerate(workbook("hst_vote02.xlsx"), 1):
        if row[0] == "Registered":
            break
        if not isinstance(row[0], int):
            continue
        for column, group in enumerate([
            "Less than 9th grade", "9th–12th grade, no diploma", "High school / GED",
            "Some college / associate's degree", "Bachelor's degree or more",
        ], 5):
            if numeric(row[column]):
                national.append({
                    "year": row[0], "election_type": "presidential" if row[0] % 4 == 0 else "midterm",
                    "age_group": "All ages", "dimension": "education", "group": group,
                    "denominator": "vap", "turnout_pct": row[column],
                    "source": "hst_vote02.xlsx", "source_row": row_number,
                    "warnings": warnings_for(row[0], "education", "vap"),
                })
    for name in ["a5a.xlsx", "hst_vote03a.xlsx"]:
        rows = workbook(name)
        headings, populations = rows[3], rows[4]
        current_year = None
        columns = []
        for index in range(1, len(headings)):
            if isinstance(headings[index], int):
                current_year = headings[index]
            columns.append((index, current_year, "cvap" if populations[index] == "Citizen" else "vap"))
        for row_number, row in enumerate(rows[5:], 6):
            if not row[0] or not any(numeric(v) for v in row[1:]):
                continue
            state = str(row[0]).strip()
            if state.startswith(("Note", "Source", "Information", '"N"')):
                continue
            for index, year, basis in columns:
                if index < len(row) and numeric(row[index]):
                    states.append({
                        "state": state, "year": year, "denominator": basis,
                        "turnout_pct": row[index], "source": name, "source_row": row_number,
                        "warnings": warnings_for(year, "overall", basis),
                    })
    national.extend(election_demographics())
    for record in national:
        record.setdefault("participants_thousands", None)
        record.setdefault("citizen_population_thousands", None)
    atomic_json(OUT / "national.json", national)
    atomic_json(OUT / "states.json", states)
    write_csv(OUT / "national.csv", national)
    write_csv(OUT / "states.csv", states)
    return national, states


def write_csv(path, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value) if isinstance(value, (list, dict)) else value
                             for key, value in row.items()})


def normalize_key(value):
    return str(value or "").strip().upper()


def nc_rows(path, audit=None):
    audit = audit if audit is not None else {}
    audit["nul_bytes_removed"] = 0
    with zipfile.ZipFile(path) as archive:
        files = [n for n in archive.namelist() if n.lower().endswith(".txt") and "readme" not in n.lower()]
        if len(files) != 1:
            raise ValueError(f"{path.name}: no unique tabular participation file (source may be unavailable)")
        with archive.open(files[0]) as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8-sig")

            def cleaned_lines():
                for line in text:
                    audit["nul_bytes_removed"] += line.count("\x00")
                    yield line.replace("\x00", "")

            lines = cleaned_lines()
            first = next(lines)
            if first.strip().lower() == "data unavailable":
                raise ValueError(f"{path.name}: no unique tabular participation file (source unavailable)")
            delimiter = "\t" if "\t" in first else ","
            first_values = next(csv.reader([first], delimiter=delimiter))
            has_header = first_values[0].strip('" ').lower() == "county_desc"
            fields = [v.strip().lower() for v in first_values] if has_header else NC_COLUMNS
            reader = csv.DictReader(lines, fieldnames=fields, delimiter=delimiter)
            if not has_header:
                yield dict(zip(fields, first_values))
            yield from reader


def groups_for(row):
    race = normalize_key(row.get("race_code"))
    ethnicity = normalize_key(row.get("ethnic_code"))
    sex = normalize_key(row.get("sex_code"))
    return [
        ("overall", "All"),
        ("race", RACES.get(race, "Unknown race (" + race + ")")),
        ("ethnicity", ETHNICITY.get(ethnicity, "Unknown ethnicity (" + ethnicity + ")")),
        ("sex", SEX.get(sex, "Unknown sex (" + sex + ")")),
        ("age", row.get("age", "").strip() or "Unknown age"),
    ]


def aggregate_nc(path, audit=None):
    counts = defaultdict(int)
    total, rows = 0, 0
    for row in nc_rows(path, audit):
        county = normalize_key(row["county_desc"])
        precinct = normalize_key(row["precinct_abbrv"])
        count = int(row["total_voters"])
        if count < 0:
            raise ValueError(f"Negative count in {path}")
        total += count
        rows += 1
        for dimension, group in groups_for(row):
            counts[(county, precinct, dimension, group)] += count
    return counts, total, rows


def rate_record(voted, registered, numerator_available=True):
    issues = []
    if not numerator_available:
        issues.append("participation_unavailable")
    if registered <= 0:
        issues.append("missing_or_zero_denominator")
    if voted > registered:
        issues.append("participation_exceeds_registration")
    return {
        "participants": voted if numerator_available else None,
        "registered": registered,
        "turnout_pct": round(100 * voted / registered, 3) if not issues else None,
        "quality": issues,
    }


def nc_data():
    summaries = []
    specs = [s for s in META["sources"] if s["kind"] == "nc_history"]
    for spec in sorted(specs, key=lambda s: s["year"]):
        year = spec["year"]
        path = ROOT / spec["path"]
        registration = next((s for s in META["sources"]
                             if s["kind"] == "nc_registration" and s["year"] == year), None)
        if registration is None:
            continue
        print(f"Aggregating NC {year}", flush=True)
        history_audit, registration_audit = {}, {}
        try:
            participants, total_voted, history_rows = aggregate_nc(path, history_audit)
            registered, total_registered, registration_rows = aggregate_nc(ROOT / registration["path"], registration_audit)
        except ValueError as error:
            summaries.append({"year": year, "status": "source_unavailable", "reason": str(error)})
            continue
        counties_with_history = {k[0] for k, v in participants.items() if k[2] == "overall" and v > 0}
        precincts_with_history = {(k[0], k[1]) for k, v in participants.items()
                                  if k[2] == "overall" and v > 0}
        records = []
        grouped = defaultdict(lambda: [0, 0])
        for county, precinct, dimension, group in sorted(set(participants) | set(registered)):
            key = county, precinct, dimension, group
            voted, reg = participants.get(key, 0), registered.get(key, 0)
            record = {"county": county, "precinct": precinct, "dimension": dimension, "group": group}
            record.update(rate_record(voted, reg, (county, precinct) in precincts_with_history))
            records.append(record)
            grouped[(dimension, group)][0] += voted
            grouped[(dimension, group)][1] += reg
        statewide = [
            {"dimension": dimension, "group": group, **rate_record(voted, reg)}
            for (dimension, group), (voted, reg) in sorted(grouped.items())
        ]
        summary = {
            "year": year, "election_type": "presidential" if year % 4 == 0 else "midterm",
            "status": "aggregated", "participants": total_voted, "registered": total_registered,
            "history_rows": history_rows, "registration_rows": registration_rows,
            "counties_with_history": len(counties_with_history),
            "precincts": sum(r["dimension"] == "overall" for r in records),
            "invalid_rates": sum(bool(r["quality"]) for r in records),
            "unassigned_participants": sum(r["participants"] or 0 for r in records
                                           if r["dimension"] == "overall" and not r["precinct"]),
            "statewide": statewide, "history_source": spec["url"],
            "registration_source": registration["url"],
            "denominator": "registered", "measure": "voter_history_participation",
            "source_cleaning": {"history": history_audit, "registration": registration_audit},
        }
        atomic_json(OUT / f"nc/{year}.json", {"summary": summary, "records": records}, compact=True)
        write_csv(OUT / f"nc/{year}.csv", [{"year": year, **r} for r in records])
        summaries.append(summary)
        print(f"  {total_voted:,} participants / {total_registered:,} registrations; "
              f"{summary['invalid_rates']:,} flagged subgroup rates", flush=True)
    atomic_json(OUT / "nc/summary.json", summaries)
    return summaries


def reconcile_nc(summaries):
    page = ROOT / "data/raw/pages/nc_turnout.html"
    if not page.exists():
        raise ValueError("Missing official NC turnout page for reconciliation")
    official = []
    for table in re.findall(r"<table\b.*?</table>", page.read_text(), re.S)[:2]:
        for row in re.findall(r"<tr\b.*?</tr>", table, re.S):
            cells = [re.sub(r"<[^>]+>", " ", cell).strip()
                     for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, re.S)]
            if len(cells) != 4 or not re.fullmatch(r"\d{4} General", cells[0]):
                continue
            year = int(cells[0][:4])
            registered = int(cells[1].replace(",", ""))
            ballots = int(cells[2].replace(",", ""))
            published_pct = float(cells[3].rstrip("%"))
            source = {
                "year": year, "official_eligible_label_count": registered,
                "official_ballots_cast": ballots, "official_published_turnout_pct": published_pct,
                "official_count_ratio_pct": round(100 * ballots / registered, 3),
                "published_rate_matches_counts": abs(100 * ballots / registered - published_pct) < 0.015,
                "source": "https://www.ncsbe.gov/results-data/voter-turnout",
            }
            summary = next((s for s in summaries if s["year"] == year and s["status"] == "aggregated"), None)
            if summary:
                source.update({
                    "archive_participants": summary["participants"],
                    "archive_registrations": summary["registered"],
                    "participant_minus_official_ballots": summary["participants"] - ballots,
                    "registration_minus_official_eligible": summary["registered"] - registered,
                    "note": "Voter-history entries and official ballots cast are distinct measures; archived snapshots may also differ.",
                })
            official.append(source)
    if len(official) < 20:
        raise ValueError("Official NC turnout table did not parse as expected")
    atomic_json(OUT / "nc/official-reconciliation.json", sorted(official, key=lambda r: r["year"]))
    write_csv(OUT / "nc/official-reconciliation.csv", [
        {key: row.get(key) for key in sorted({k for r in official for k in r})}
        for row in sorted(official, key=lambda r: r["year"])
    ])
    return official


def simplify(points, tolerance=0.0007):
    if len(points) < 4:
        return points
    start, end = points[0], points[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = dx * dx + dy * dy
    maximum, split = 0, 0
    for i, point in enumerate(points[1:-1], 1):
        t = max(0, min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length)) if length else 0
        distance = (point[0] - start[0] - t * dx) ** 2 + (point[1] - start[1] - t * dy) ** 2
        if distance > maximum:
            maximum, split = distance, i
    if maximum > tolerance * tolerance:
        return simplify(points[:split + 1], tolerance)[:-1] + simplify(points[split:], tolerance)
    return [start, end]


def geometry_data():
    state_geometry = json.loads((ROOT / "data/raw/geometry/states.geojson").read_text())
    if state_geometry.get("type") != "FeatureCollection":
        raise ValueError("State geometry is not valid GeoJSON")
    atomic_json(OUT / "states.geojson", state_geometry)
    audit = []
    for spec in [s for s in META["sources"] if s["kind"] == "nc_geometry"]:
        year = spec["year"]
        print(f"Converting NC {year} boundaries", flush=True)
        with zipfile.ZipFile(ROOT / spec["path"]) as archive:
            shp = next(n for n in archive.namelist() if n.lower().endswith(".shp"))
            base = shp[:-4]
            reader = shapefile.Reader(shp=io.BytesIO(archive.read(shp)),
                                      dbf=io.BytesIO(archive.read(base + ".dbf")),
                                      shx=io.BytesIO(archive.read(base + ".shx")),
                                      encoding="latin1")
            crs = CRS.from_wkt(archive.read(base + ".prj").decode())
            transformer = Transformer.from_crs(crs, 4326, always_xy=True)
            features = []
            seen = set()
            for item in reader.iterShapeRecords():
                attrs = {k.lower(): v for k, v in item.record.as_dict().items()}
                county = normalize_key(attrs.get("county_nam", attrs.get("county")))
                precinct = normalize_key(attrs.get("prec_id", attrs.get("seims_code")))
                if not county or not precinct:
                    continue
                seen.add((county, precinct))
                raw = item.shape.__geo_interface__

                def ring(points):
                    xs, ys = transformer.transform(*zip(*[(p[0], p[1]) for p in points]))
                    original = [[round(x, 5), round(y, 5)] for x, y in zip(xs, ys)]
                    simplified = simplify(original)
                    return simplified if len(simplified) >= 4 else original

                polygons = raw["coordinates"] if raw["type"] == "MultiPolygon" else [raw["coordinates"]]
                converted = [[ring(points) for points in polygon] for polygon in polygons]
                features.append({
                    "type": "Feature",
                    "properties": {"county": county, "precinct": precinct,
                                   "label": str(attrs.get("enr_desc", attrs.get("seims_desc", precinct)))},
                    "geometry": {"type": "MultiPolygon", "coordinates": converted},
                })
        atomic_json(OUT / f"nc/geometry-{year}.geojson", {
            "type": "FeatureCollection", "features": features,
            "source": spec["url"], "vintage": spec["vintage"],
            "note": "Published pre-election snapshot; ID joins checked, boundary changes not independently certified.",
        }, compact=True)
        data = json.loads((OUT / f"nc/{year}.json").read_text())
        overall = [r for r in data["records"] if r["dimension"] == "overall"]
        matched = [r for r in overall if (r["county"], r["precinct"]) in seen]
        summary = data["summary"]
        audit.append({
            "year": year, "vintage": spec["vintage"], "source": spec["url"],
            "polygons": len(features), "unique_geometry_keys": len(seen),
            "data_precincts": len(overall), "matched_precincts": len(matched),
            "matched_participants": sum(r["participants"] or 0 for r in matched),
            "total_participants": summary["participants"],
            "participant_match_pct": round(100 * sum(r["participants"] or 0 for r in matched)
                                         / summary["participants"], 3),
            "unmatched_data_keys": [{"county": r["county"], "precinct": r["precinct"],
                                     "participants": r["participants"], "registered": r["registered"]}
                                    for r in overall if (r["county"], r["precinct"]) not in seen],
        })
    atomic_json(OUT / "geometry-audit.json", sorted(audit, key=lambda a: a["year"]))
    return audit


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    national, states = census_data()
    nc = nc_data()
    reconciliation = reconcile_nc(nc)
    geometry = geometry_data()
    state_names = sorted({r["state"] for r in states})
    audit = []
    for state in state_names:
        for year in range(2004, 2025, 2):
            summary = next((s for s in nc if s["year"] == year), None) if state == "North Carolina" else None
            shape = next((g for g in geometry if g["year"] == year), None) if state == "North Carolina" else None
            audit.append({
                "state": state, "year": year,
                "state_cps": any(r["state"] == state and r["year"] == year and r["denominator"] == "cvap" for r in states),
                "precinct_counts": "downloaded_and_aggregated" if summary and summary["status"] == "aggregated" else "not_assessed",
                "demographic_participation": "race_ethnicity_sex_age" if summary and summary["status"] == "aggregated" else "not_assessed",
                "education_participation": "not_available_in_nc_source" if summary else "not_assessed",
                "geometry": shape["vintage"] if shape else "not_validated",
                "participant_geometry_match_pct": shape["participant_match_pct"] if shape else None,
                "note": "No claim of nationwide precinct completeness; not assessed does not mean unavailable.",
            })
    atomic_json(OUT / "coverage.json", audit)
    write_csv(OUT / "coverage.csv", audit)
    atomic_json(OUT / "sources.json", META)
    notes = {
        "denominators": {
            "cvap": "Civilian noninstitutionalized adult citizens (CPS survey); not legal voting-eligible population.",
            "vap": "Civilian noninstitutionalized adult residents, including noncitizens (CPS survey).",
            "registered": "Election-time NC active and inactive registrations; not all adult citizens.",
        },
        "limitations": [
            "National and state CPS estimates are self-reported, not validated participation.",
            "CPS state estimates have sampling uncertainty; margins of error are not supplied by these historical tables.",
            "Do not interpret precinct demographics as an individual's participation or candidate preference.",
            "NC records are public aggregate participation and registration counts, not ballots cast totals.",
            "Race and ethnicity categories overlap; age bands differ between CPS and NC.",
            "Rates above 100%, zero denominators, and precincts lacking participation records are flagged, never clipped or assigned zero turnout.",
            "Published precinct snapshots are not a fixed-boundary panel; no precinct trend claim across changing boundaries.",
            "A matching precinct identifier is not proof of an unchanged or election-certified boundary.",
            "Some NC participants have blank or unmatched precincts; counts remain in the downloadable analysis.",
            "2000 NC history source contains 'Data Unavailable'; no participation rate is inferred.",
            "Historical education and sex VAP series remain separate from 2000–2024 CVAP rates calculated using election-specific Census citizen counts.",
            "Archived NC history/registration totals differ from official ballots/eligible counts in some years; see the reconciliation download.",
            "Historical trend series end in 2024. Separate 2026 NC snapshots are unofficial and incomplete; they are never spliced into historical demographic turnout.",
        ],
    }
    atomic_json(OUT / "methodology.json", notes)
    report = {
        "national_rows": len(national), "state_rows": len(states),
        "national_years": sorted({r["year"] for r in national}),
        "state_years": sorted({r["year"] for r in states}),
        "nc_years": [s["year"] for s in nc if s["status"] == "aggregated"],
        "precinct_map_years": sorted(g["year"] for g in geometry),
        "nc_summaries": nc, "geometry_audit": geometry,
        "official_reconciliation": reconciliation,
        "coverage": {"state_years": len(audit), "precinct_states": ["North Carolina"],
                     "other_states": "not_assessed"},
        "deployment": "Not authorized; local-only.",
    }
    if (OUT / "current/latest.json").exists():
        report["current_snapshot"] = json.loads((OUT / "current/latest.json").read_text())
    atomic_json(OUT / "analysis.json", report)
    from scripts.current import update_downloads
    update_downloads(ROOT)
    print(json.dumps({k: v for k, v in report.items() if k not in ["nc_summaries", "geometry_audit", "official_reconciliation"]}, indent=2))


if __name__ == "__main__":
    build()
