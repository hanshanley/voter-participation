#!/usr/bin/env python3
"""Reconcile unchanged survey-model contributions to qualified reported returns."""

import argparse
import copy
import csv
from decimal import Decimal, localcontext
import io
import json
from pathlib import Path
import zipfile

VERSION = "20261110-02"
TERMS = ("switching", "modeled_nonparticipation", "no_prior_contest_vote_entry",
         "other_choice", "unresolved", "denominator", "return_frame_gap")
SENATE_HOLDS = {
    "NE": "The 2024 same-seat special election is not in this verified reference.",
    "OK": "The 2022 same-seat special election is not in this verified reference.",
}


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def count(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a vote count")
    if value is None or value == "":
        return None
    result = Decimal(str(value))
    if not result.is_finite() or result < 0 or result != result.to_integral_value():
        raise ValueError("Invalid literal vote count")
    return int(result)


def margin(votes):
    d, r = count(votes.get("D")), count(votes.get("R"))
    if d is None or r is None or d + r == 0:
        return None
    return Decimal(100) * (d - r) / (d + r)


def unavailable(reason):
    return dict(status="unavailable", reason=reason, reported_change_pp=None,
                baseline_alignment_pp=None, other_and_unallocated_pp=None)


def reconcile(row, control, reference):
    if reference["status"] == "unavailable":
        return reference
    previous, current = reference["previous"], control["current"]
    before, after = margin(previous), margin(current)
    if before is None or after is None:
        return unavailable("A known D/R denominator is unavailable; unknown is not zero.")
    if not all(previous.get(k, 0) > 0 and current.get(k, 0) > 0 for k in ("D", "R")):
        return unavailable("Both periods need a reported D and R contest; no coalition is inferred.")
    if abs(after - Decimal(str(row["current_return_margin_pp"]))) > Decimal("1e-8"):
        raise ValueError("Reported current counts do not match the model return constraint")
    total = after - before
    source_change = Decimal(str(row["source_frame_change_pp"]))
    result = dict(reference, current=current, current_year=control["year"],
                  current_native_clock=control.get("source_native_clock"),
                  current_snapshot=control.get("source_snapshot"),
                  current_percent_reporting=control.get("source_percent_reporting"),
                  current_source_scope=control["source_scope"],
                  current_source_url=control.get("source_url"),
                  current_stage=control.get("source_election_scope"),
                  current_round=control.get("source_round"),
                  previous_margin_pp=float(before), current_margin_pp=float(after),
                  reported_change_pp=float(total),
                  baseline_alignment_pp=float(total - source_change),
                  other_and_unallocated_pp=float(total
                      - Decimal(str(row["components_pp"]["switching"]))
                      - Decimal(str(row["components_pp"]["modeled_nonparticipation"]))),
                  margin_definition="100 * (D - R) / (D + R)",
                  independent_validation=False,
                  remainder_is_not_an_estimate_of_one_mechanism=True)
    if abs(sum(Decimal(str(row["components_pp"][key])) for key in TERMS)
           + Decimal(str(result["baseline_alignment_pp"])) - total) > Decimal("1e-8"):
        raise ValueError("Eight-term reported-return reconciliation failed")
    return result


def county_identities(path):
    with zipfile.ZipFile(path) as archive:
        text = archive.read("2024_Gaz_counties_national.txt").decode("utf-8-sig")
    result = {}
    for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
        result.setdefault(row["USPS"].strip(), set()).add(row["GEOID"].strip())
    return result


def house_reference(control, rows, expected):
    codes = [row["county_fips"] for row in rows]
    if not rows or len(set(codes)) != len(codes) or set(codes) != expected:
        return unavailable("Held county identities do not exactly cover the Census state reference.")
    totals = {year: dict(D=0, R=0, O=0) for year in (2024, 2026)}
    for row in rows:
        for year in totals:
            for party, field in (("D", "d"), ("R", "r"), ("O", "other")):
                value = count(row[f"{year}_{field}_literal_votes"])
                if value is None:
                    return unavailable("At least one county lacks reviewed prior/current candidate counts.")
                totals[year][party] += value
    if control["missing_candidate_control_indices"]:
        return unavailable("Current district controls omit candidate totals; statewide comparison withheld.")
    if totals[2026] != control["current"]:
        return unavailable("Located county totals disagree with native current district controls.")
    return dict(status="reported_source_comparison", previous=totals[2024],
                baseline_year=2024, baseline_office="house", baseline_stage="general",
                baseline_source="Complete held House county panel and its six sufficient originals",
                scope=f"All {len(rows)} Census county identities; source-recorded House candidate votes",
                county_count=len(rows), source_coverage_certified=False,
                competition_or_other_screened_counties=sum(
                    row["passes_known_descriptive_screens"] != "True" for row in rows),
                qualification="Changed competition/boundaries can affect this descriptive aggregate; not a turnout or causal estimate.")


def senate_references(path):
    import openpyxl

    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    candidates = {}
    try:
        for row in book["12. US Senate Results by State"].values:
            if len(row) <= 23 or row[3] not in ("S", "S-FULL TERM") or not row[8] or not row[10]:
                continue
            candidates.setdefault(row[1], []).append(row)
    finally:
        book.close()
    result = {}
    for state, rows in candidates.items():
        if state in SENATE_HOLDS:
            result[state] = unavailable(SENATE_HOLDS[state])
            continue
        runoff = any(isinstance(row[17], (int, float)) for row in rows)
        column = 17 if runoff else 15
        votes, facts = dict(D=0, R=0, O=0), []
        for row in rows:
            if not isinstance(row[column], (int, float)):
                continue
            value = count(row[column])
            # DFL is the literal Minnesota Democratic-Farmer-Labor designation.
            party = "D" if row[10] in ("D", "DFL") else "R" if row[10] == "R" else "O"
            votes[party] += value
            facts.append(dict(candidate=row[8], literal_party=row[10], votes=value,
                              seat=row[3], footnote=row[23], counted_as=party))
        if not facts:
            continue
        result[state] = dict(status="reported_source_comparison", previous=votes,
            baseline_year=2021 if state == "GA" and runoff else 2020,
            baseline_cycle_year=2020, baseline_office="senate",
            baseline_stage="general_runoff" if runoff else "general",
            baseline_source="FEC Federal Elections 2020, worksheet 12",
            baseline_source_url="https://www.fec.gov/resources/cms-content/documents/federalelections2020.xlsx",
            scope="Statewide regular-seat candidate counts; special/unexpired seat rows excluded",
            native_candidate_facts=facts,
            party_rule="Literal D/R, explicit MN DFL=D; independent, fusion and unmapped labels remain Other",
            qualification="2020 regular-seat cycle; Georgia uses the January 2021 full-term runoff, not its other seat.")
    return result


def governor_reference(control):
    rows = control["full_factual_county_rows"]
    ids = [row["fips"] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate governor county identity")
    for year, expected in ((2022, control["previous"]), (2026, control["current"])):
        totals = dict(D=0, R=0)
        for row in rows:
            for party, field in (("D", "dem"), ("R", "rep")):
                value = count(row[f"{field}_{year}"])
                if value is None:
                    return unavailable("The supplied governor frame has an unknown county count.")
                totals[party] += value
        if totals != expected:
            raise ValueError("Governor facts disagree with supplied source control")
    return dict(status="reported_source_comparison", previous=control["previous"],
                baseline_year=control["previous_year"], baseline_office="governor",
                baseline_stage="general", baseline_source=control["source_url"],
                scope=f"Supplied matched {len(rows)}-county frame, not certified complete statewide",
                county_count=len(rows), source_coverage_certified=False,
                qualification="The same supplied county identities are used in both periods; reporting is not necessarily complete.")


def build(inputs):
    original = json.loads((inputs / "original-viewer.json").read_bytes())
    controls = json.loads((inputs / "model-inputs.json").read_bytes())["return_controls"]
    by_id = {control["id"]: control for control in controls}
    if (original["version"] != "20261110-01" or len(by_id) != len(controls)
            or len(controls) != 113 or set(by_id) != {row["id"] for row in original["rows"]}):
        raise ValueError("Unsupported or duplicate original model controls")
    with (inputs / "house-county-panel.csv").open(newline="") as stream:
        house = {}
        for row in csv.DictReader(stream):
            house.setdefault(row["state_code"], []).append(row)
    identities = county_identities(inputs / "gazetteer-counties.zip")
    senate = senate_references(inputs / "fec-2020.xlsx")
    data = copy.deepcopy(original)
    with localcontext() as context:
        context.prec = 70
        for row in data["rows"]:
            if abs(sum(row["components_pp"][key] for key in TERMS) - row["source_frame_change_pp"]) > 1e-8:
                raise ValueError("Original seven-term model does not reconcile")
            control = by_id[row["id"]]
            if row["office"] == "house":
                ref = house_reference(control, house.get(row["state_code"], []),
                                      identities.get(row["state_code"], set()))
            elif row["office"] == "senate":
                ref = senate.get(row["state_code"],
                    unavailable("No qualified prior same-seat general election is in the held FEC reference."))
            else:
                ref = governor_reference(control)
            row["reported_comparison"] = reconcile(row, control, ref)
    data.update(version=VERSION, original_model_version=original["version"],
                reported_baseline="Previous qualified same-office reference; actual year, stage and frame are attached to each row",
                complete_download_url="https://github.com/hanshanley/margin_of_error/releases/download/participation-observed-swing-20261110-02/complete-analysis.zip")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refuse to replace an immutable numerical output")
    args.output.write_bytes(encoded(build(args.inputs)))


if __name__ == "__main__":
    main()
