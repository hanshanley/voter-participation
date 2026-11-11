"""Prepare independently acquired public CPS survey inputs, not a 2026 nowcast."""

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter, defaultdict

from scripts.download import ROOT, atomic_json, download

YEARS = (2022, 2024)
# One-based inclusive positions checked against each year's attachments 6 and 7.
LAYOUT = {
    "month": (16, 17), "year": (18, 21), "state": (93, 94), "age": (122, 123),
    "sex": (129, 130), "education": (137, 138), "race": (139, 140),
    "hispanic": (157, 158), "person_type": (161, 162), "citizenship": (172, 173),
    "weight": (613, 622), "interview": (1001, 1002), "voted": (1003, 1004),
}
STATES = {1, 2, 4, 5, 6, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21,
          22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38,
          39, 40, 41, 42, 44, 45, 46, 47, 48, 49, 50, 51, 53, 54, 55, 56}
EDUCATION = {
    **dict.fromkeys(range(31, 35), "Less than 9th grade"),
    **dict.fromkeys(range(35, 39), "9th\u201312th grade, no diploma"),
    39: "High school / GED",
    **dict.fromkeys(range(40, 43), "Some college / associate's degree"),
    **dict.fromkeys(range(43, 47), "Bachelor's degree or more"),
}
OUTCOMES = ("yes", "no", "dont_know", "refused", "no_response",
            "supplement_noninterview", "not_in_universe_response")
CELL_FIELDS = ("state_fips", "age_group", "sex", "education", "race_ethnicity")


def acquire():
    path = ROOT / "data/cps-sources.json"
    previous = json.loads(path.read_text()) if path.exists() else {"sources": []}
    existing = {row["path"]: row for row in previous["sources"]}
    results = []
    for year in YEARS:
        base = f"https://www2.census.gov/programs-surveys/cps/datasets/{year}/supp/"
        for name, url, kind in [
            ("catalog.html", base, "cps_microdata_catalog"),
            (f"nov{year % 100}pub.zip", base + f"nov{year % 100}pub.zip", "cps_public_use_survey"),
            (f"cpsnov{year % 100}.pdf",
             f"https://www2.census.gov/programs-surveys/cps/techdocs/cpsnov{year % 100}.pdf",
             "cps_technical_documentation"),
        ]:
            relative = f"data/raw/cps/{year}/{name}"
            result = download({**existing.get(relative, {}), "path": relative,
                               "url": url, "kind": kind, "year": year})
            results.append(result)
            if result["status"] == "failed":
                raise ValueError(f"CPS acquisition failed: {result['error']}")
    atomic_json(path, {"sources": results})


def records(path, year):
    if year not in YEARS:
        raise ValueError("This year's CPS layout has not been assessed")
    with zipfile.ZipFile(path) as archive:
        expected = f"nov{year % 100}pub.dat"
        if archive.namelist() != [expected]:
            raise ValueError("Unexpected CPS ZIP members")
        with archive.open(expected) as stream:
            for number, line in enumerate(stream, 1):
                line = line.rstrip(b"\r\n")
                if len(line) != 1020:
                    raise ValueError(f"CPS record {number}: unexpected width")
                try:
                    row = {name: int(line[start - 1:end]) for name, (start, end) in LAYOUT.items()}
                except ValueError as error:
                    raise ValueError(f"CPS record {number}: invalid numeric field") from error
                if row["year"] != year or row["month"] != 11:
                    raise ValueError("Wrong election year/month in CPS input")
                yield row


def demographics(row):
    age = row["age"]
    if not 18 <= age <= 85 or row["sex"] not in (1, 2):
        raise ValueError("Unexpected age/sex in CPS adult-citizen universe")
    if row["education"] not in EDUCATION or not 1 <= row["race"] <= 26:
        raise ValueError("Unexpected CPS education/race code")
    if row["hispanic"] not in (1, 2) or row["state"] not in STATES:
        raise ValueError("Unexpected CPS Hispanic-origin/state code")
    age_group = ("18 to 24 Years" if age < 25 else "25 to 44 Years" if age < 45
                 else "45 to 64 Years" if age < 65 else "65 Years and Over")
    race = {1: "White", 2: "Black", 4: "Asian"}.get(row["race"], "Other")
    partition = ("Hispanic, any race" if row["hispanic"] == 1
                 else f"{race}, non-Hispanic")
    return (f"{row['state']:02d}", age_group, {1: "Male", 2: "Female"}[row["sex"]],
            EDUCATION[row["education"]], partition)


def outcome(row):
    if row["interview"] not in (1, 2) or row["voted"] not in (1, 2, -1, -2, -3, -9):
        raise ValueError("Unexpected CPS participation response code")
    if row["interview"] == 2:
        if row["voted"] != -1:
            raise ValueError("Noninterview has an incompatible participation response")
        return "supplement_noninterview"
    return {1: "yes", 2: "no", -1: "not_in_universe_response",
            -2: "dont_know", -3: "refused", -9: "no_response"}[row["voted"]]


def add(tally, status, weight):
    tally["sample_n"] += 1
    tally["weight_units"] += weight
    tally["squared_weight_units"] += weight * weight
    tally[f"{status}_n"] += 1
    tally[f"{status}_units"] += weight


def measures(tally):
    total, yes, no = tally["weight_units"], tally["yes_units"], tally["no_units"]
    unknown = total - yes - no
    return {
        "sample_n": tally["sample_n"],
        "citizens_weighted": total / 10000,
        "reported_voters_weighted": yes / 10000,
        "reported_nonvoters_weighted": no / 10000,
        "unknown_weighted": unknown / 10000,
        "reported_voting_pct": 100 * yes / total,
        "unknown_pct": 100 * unknown / total,
        "missing_outcome_upper_pct": 100 * (yes + unknown) / total,
        "respondent_only_voting_pct": 100 * yes / (yes + no) if yes + no else None,
        "weight_only_effective_n": total * total / tally["squared_weight_units"],
        **{f"{status}_n": tally[f"{status}_n"] for status in OUTCOMES},
        **{f"{status}_weighted": tally[f"{status}_units"] / 10000 for status in OUTCOMES},
    }


def aggregate(rows, year):
    joint, marginals, audit = defaultdict(Counter), defaultdict(Counter), Counter()
    for row in rows:
        audit["source_records"] += 1
        if row["age"] < 18 or row["person_type"] != 2 or row["citizenship"] not in (1, 2, 3, 4):
            audit["outside_universe"] += 1
            continue
        if row["weight"] < 0:
            raise ValueError("Negative CPS final weight")
        if row["weight"] == 0:
            audit["zero_weight_records"] += 1
            continue
        key, status, weight = demographics(row), outcome(row), row["weight"]
        add(joint[key], status, weight)
        projections = [("overall", "All"), ("age", key[1]), ("sex", key[2]),
                       ("education", key[3]), ("race_ethnicity", key[4]),
                       ("state", key[0])]
        for code, label in ((1, "White"), (2, "Black"), (4, "Asian")):
            if row["race"] == code:
                projections.append(("race", label))
        if row["hispanic"] == 1:
            projections.append(("race", "Hispanic, any race"))
        elif row["race"] == 1:
            projections.append(("race", "White, non-Hispanic"))
        for projection in projections:
            add(marginals[projection], status, weight)
    if not joint:
        raise ValueError("No usable CPS adult-citizen observations")
    overall = marginals[("overall", "All")]
    for dimension in ("age", "sex", "education", "race_ethnicity", "state"):
        partition = [tally for (field, _), tally in marginals.items() if field == dimension]
        for field in ("sample_n", "weight_units", "yes_units", "no_units"):
            if sum(tally[field] for tally in partition) != overall[field]:
                raise ValueError(f"CPS {dimension} cells do not reconcile")
    if sum(tally["weight_units"] for tally in joint.values()) != overall["weight_units"]:
        raise ValueError("CPS joint cells do not reconcile")
    audit["included_records"] = overall["sample_n"]
    audit["observed_joint_cells"] = len(joint)
    audit["sparse_joint_cells_under_30"] = sum(t["sample_n"] < 30 for t in joint.values())
    return {
        "year": year, "audit": dict(audit), "summary": measures(overall),
        "joint_cells": [{"year": year, **dict(zip(CELL_FIELDS, key)), **measures(tally)}
                        for key, tally in sorted(joint.items())],
        "marginals": [{"year": year, "dimension": dimension, "group": group, **measures(tally)}
                      for (dimension, group), tally in sorted(marginals.items())],
    }


def compare(marginals, published):
    lookups = {(r["year"], r["dimension"], r["group"]): r for r in marginals}
    comparisons = []
    for row in published:
        if row["year"] not in YEARS or row["denominator"] != "cvap":
            continue
        dimension, group = row["dimension"], row["group"]
        if dimension == "overall" and row["age_group"] != "All ages":
            dimension, group = "age", row["age_group"]
        elif row["age_group"] != "All ages":
            continue
        actual = lookups.get((row["year"], dimension, group))
        if actual is None:
            raise ValueError(f"Missing CPS published comparison: {dimension}/{group}")
        difference = actual["reported_voting_pct"] - row["turnout_pct"]
        comparisons.append({
            "year": row["year"], "dimension": dimension, "group": group,
            "microdata_pct": actual["reported_voting_pct"], "published_pct": row["turnout_pct"],
            "difference_pp": difference, "tolerance_pp": .15, "passed": abs(difference) <= .15,
            "published_source": row["source"], "published_source_row": row["source_row"],
        })
    if not comparisons or {r["year"] for r in comparisons} != set(YEARS):
        raise ValueError("Published CPS comparisons missing a required year")
    return comparisons


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v) if isinstance(v, list) else v for k, v in row.items()})


def export(root=ROOT, rebundle=True):
    manifest = json.loads((root / "data/cps-sources.json").read_text())
    for source in manifest["sources"]:
        raw = (root / source["path"]).read_bytes()
        if len(raw) != source["bytes"] or hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError(f"CPS source checksum mismatch: {source['path']}")
    years = []
    for year in YEARS:
        path = root / f"data/raw/cps/{year}/nov{year % 100}pub.zip"
        if not any(r["path"] == str(path.relative_to(root)) for r in manifest["sources"]):
            raise ValueError("Unmanifested CPS survey input")
        years.append(aggregate(records(path, year), year))
    joint = [row for result in years for row in result["joint_cells"]]
    marginals = [row for result in years for row in result["marginals"]]
    published_path = root / "public/data/national.json"
    comparisons = compare(marginals, json.loads(published_path.read_text()))
    result = {
        "status": "historical_inputs_only_not_a_2026_estimate", "years": list(YEARS),
        "universe": "Civilian noninstitutionalized adult citizens, not legal voting eligibility.",
        "weight": "PWSSWGT / 10000, as specified by each year's technical documentation.",
        "layout_one_based_inclusive": LAYOUT,
        "source_manifest": manifest,
        "published_input_sha256": hashlib.sha256(published_path.read_bytes()).hexdigest(),
        "summaries": [{"year": r["year"], **r["summary"], **r["audit"]} for r in years],
        "comparisons": comparisons, "marginals": marginals,
        "published_comparisons_passed": all(row["passed"] for row in comparisons),
        "release_2026_allowed": False,
        "limitations": [
            "This is an independently calculated historical input audit, not a fitted hierarchical model.",
            "PES1 yes/all adult citizens reproduces reported voting; unknowns are never labeled nonvoters.",
            "Unknown includes supplement noninterviews, don't know, refused, no response and in-universe NIU.",
            "The missing-outcome range assigns unknowns no/yes; it is not a confidence interval or a correction for over-reporting.",
            "Respondent-only turnout changes the denominator and is a sensitivity diagnostic, not corrected turnout.",
            "Observed joint cells use actual survey records, never products of demographic marginals.",
            "Sparse cells remain in complete downloads for research, not validated subgroup turnout estimates.",
            "Weight-only effective n is not a complex-survey variance or a margin of error.",
            "Replicate-weight uncertainty, ACS joint population inputs and a new confirmation specification are still required.",
            "Historical CPS self-reports do not establish 2026 participation; the failed first experiment is unchanged.",
        ],
    }
    if not result["published_comparisons_passed"]:
        raise ValueError("CPS inputs do not reconcile with published rates; do not promote")
    output = root / "public/data/cps"
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output / "inputs.json", result)
    write_csv(output / "joint-cells.csv", joint)
    write_csv(output / "marginals.csv", marginals)
    write_csv(output / "published-comparisons.csv", comparisons)
    with zipfile.ZipFile(output / "complete-inputs.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("inputs.json", "joint-cells.csv", "marginals.csv", "published-comparisons.csv"):
            archive.write(output / name, name)
        for source in manifest["sources"]:
            archive.write(root / source["path"], source["path"])
        archive.write(published_path, "inputs/national.json")
        archive.write(root / "public/data/sources.json", "inputs/sources.json")
        archive.write(root / "METHODOLOGY.md", "METHODOLOGY.md")
    if rebundle:
        from scripts.current import update_downloads
        update_downloads(root)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Acquire documented public CPS originals")
    args = parser.parse_args()
    if args.download:
        acquire()
    result = export()
    print(json.dumps({key: result[key] for key in
                      ("status", "summaries", "published_comparisons_passed", "release_2026_allowed")}, indent=2))
