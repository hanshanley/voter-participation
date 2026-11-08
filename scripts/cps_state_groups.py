"""State demographic participation from already-held public CPS joint cells."""

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
import zipfile


YEARS = (2022, 2024)
STATE_CODES = dict(zip(
    "01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 "
    "30 31 32 33 34 35 36 37 38 39 40 41 42 44 45 46 47 48 49 50 51 53 54 55 56".split(),
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
    "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split(),
))
GROUPS = {
    "age_group": ("18 to 24 Years", "25 to 44 Years", "45 to 64 Years", "65 Years and Over"),
    "sex": ("Female", "Male"),
    "education": ("Less than 9th grade", "9th\u201312th grade, no diploma", "High school / GED",
                  "Some college / associate's degree", "Bachelor's degree or more"),
    "race_ethnicity": ("White, non-Hispanic", "Black, non-Hispanic", "Asian, non-Hispanic",
                       "Hispanic, any race", "Other, non-Hispanic"),
}
OUTCOMES = ("yes", "no", "dont_know", "refused", "no_response",
            "supplement_noninterview", "not_in_universe_response")
INPUTS = {"complete-cps-inputs.zip", "complete-cps-state-references.zip"}


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def weight_units(value):
    amount = Decimal(value) * 10000
    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
        raise ValueError("Cached CPS weight must preserve documented integer PWSSWGT units")
    return int(amount)


def percentage(numerator, denominator):
    if not denominator:
        return None
    with localcontext() as context:
        context.prec = 80
        return str(Decimal(100 * numerator) / denominator)


def build(cells, references):
    tallies = defaultdict(Counter)
    decisions, identities = [], set()
    for ordinal, row in enumerate(cells):
        year, state = int(row["year"]), row["state_fips"]
        identity = year, state, *(row[field] for field in GROUPS)
        if year not in YEARS or state not in STATE_CODES or identity in identities:
            raise ValueError("Unqualified or duplicate CPS election/state/joint cell")
        identities.add(identity)
        if any(row[field] not in groups for field, groups in GROUPS.items()):
            raise ValueError("Unknown CPS native demographic category")
        n = int(row["sample_n"])
        outcome_n = {outcome: int(row[outcome + "_n"]) for outcome in OUTCOMES}
        units = {outcome: weight_units(row[outcome + "_weighted"]) for outcome in OUTCOMES}
        total = weight_units(row["citizens_weighted"])
        if (n <= 0 or min(outcome_n.values()) < 0 or sum(outcome_n.values()) != n
                or sum(units.values()) != total or total <= 0
                or units["yes"] != weight_units(row["reported_voters_weighted"])
                or units["no"] != weight_units(row["reported_nonvoters_weighted"])
                or total - units["yes"] - units["no"] != weight_units(row["unknown_weighted"])):
            raise ValueError("CPS full-denominator outcome accounting changed")
        for dimension, group in [("overall", "All"), *[(field, row[field]) for field in GROUPS]]:
            tally = tallies[year, state, dimension, group]
            tally["sample_n"] += n
            for outcome in OUTCOMES:
                tally[outcome + "_n"] += outcome_n[outcome]
                tally[outcome + "_units"] += units[outcome]
        decisions.append(dict(
            source_row_ordinal=ordinal, year=year, state_fips=state,
            age_group=row["age_group"], sex=row["sex"], education=row["education"],
            race_ethnicity=row["race_ethnicity"], source_sample_n=n,
            disposition="observed_public_joint_cell_projected_once_per_exclusive_dimension",
            synthetic_joint_or_local_allocation=False,
        ))

    estimates, sensitivity, partitions, comparisons = [], [], [], []
    reference = {(int(row["year"]), row["reference_state_code"]): row for row in references
                 if int(row["year"]) in YEARS and row["population_frame"] == "cvap"}
    selections = [("overall", "All"), *[(dimension, group)
                   for dimension, groups in GROUPS.items() for group in groups]]
    for year in YEARS:
        for state, code in STATE_CODES.items():
            overall = tallies[year, state, "overall", "All"]
            source_reference = reference.get((year, code))
            for dimension in GROUPS:
                for field in ("sample_n", *(outcome + "_n" for outcome in OUTCOMES),
                              *(outcome + "_units" for outcome in OUTCOMES)):
                    child = sum(tallies[year, state, dimension, group][field] for group in GROUPS[dimension])
                    if child != overall[field]:
                        raise ValueError("CPS state demographic partition does not reconcile")
                    partitions.append(dict(
                        year=year, state_fips=state, state_code=code, dimension=dimension,
                        field=field, exclusive_group_sum=child, state_total=overall[field],
                        reconciled=True, sums_across_dimensions_are_not_population_totals=True,
                    ))
            for dimension, group in selections:
                tally = tallies[year, state, dimension, group]
                total = sum(tally[outcome + "_units"] for outcome in OUTCOMES)
                yes, no = tally["yes_units"], tally["no_units"]
                unknown = total - yes - no
                row = dict(
                    year=year, state_fips=state, state_code=code,
                    state_name=source_reference["native_state_name"] if source_reference else None,
                    election_type="midterm" if year == 2022 else "presidential",
                    population_frame="civilian_noninstitutionalized_adult_citizens",
                    dimension=dimension, group=group,
                    disposition="source_weighted_descriptive_estimate" if total else "no_observed_source_cell",
                    sample_n=tally["sample_n"], documented_weight_scale=10000,
                    citizen_weight_units=total, reported_voter_weight_units=yes,
                    reported_nonvoter_weight_units=no, unknown_weight_units=unknown,
                    reported_voting_pct=percentage(yes, total),
                    reported_nonvoting_pct=percentage(no, total), unknown_pct=percentage(unknown, total),
                    known_response_only_voting_pct=percentage(yes, yes + no),
                    raw_case_count_under_30_diagnostic=0 < tally["sample_n"] < 30,
                    design_based_confidence_interval_available=False,
                    administratively_observed_turnout=False, estimated_2026_turnout=False,
                    registered_voter_population_count=None, legal_eligibility=None,
                    observed_staying_home=False, local_allocation=False,
                    **{outcome + "_n": tally[outcome + "_n"] for outcome in OUTCOMES},
                    **{outcome + "_weight_units": tally[outcome + "_units"] for outcome in OUTCOMES},
                )
                estimates.append(row)
                for assignment in (0, 50, 100):
                    sensitivity.append(dict(
                        year=year, state_fips=state, state_code=code, dimension=dimension, group=group,
                        explicit_unknown_assignment_pct=assignment,
                        assigned_reported_vote_weight_units_numerator=100 * yes + assignment * unknown,
                        source_weight_units_denominator=100 * total,
                        assigned_reported_voting_pct=percentage(100 * yes + assignment * unknown, 100 * total),
                        is_confidence_interval_or_actual_turnout_bound=False,
                        repairs_self_report_error_or_missing_population=False,
                    ))
                if dimension == "overall":
                    native_pct = (source_reference.get("reported_voted_pct") if source_reference else None)
                    with localcontext() as context:
                        context.prec = 80
                        difference = (str(Decimal(row["reported_voting_pct"]) - Decimal(native_pct))
                                      if total and native_pct else None)
                    comparisons.append(dict(
                        year=year, state_fips=state, state_code=code,
                        source_weighted_reported_voting_pct=row["reported_voting_pct"],
                        native_published_citizen_voted_pct=native_pct, source_minus_native_pp=difference,
                        native_source_url=source_reference.get("voted_source_url") if source_reference else None,
                        native_source_sha256=source_reference.get("voted_source_sha256") if source_reference else None,
                        native_source_sheet=source_reference.get("voted_source_sheet") if source_reference else None,
                        native_source_row=source_reference.get("voted_source_row") if source_reference else None,
                        comparison_is_independent_population_validation=False,
                        reweighting_or_source_repair=False,
                    ))
    summary = dict(
        status="all_51_jurisdictions_historical_source_weighted_demographic_participation",
        years=list(YEARS), states_and_dc=51, complete_state_group_estimates=len(estimates),
        observed_joint_cell_decisions=len(decisions), complete_unknown_assignments=len(sensitivity),
        exclusive_partition_checks=len(partitions), state_published_reference_comparisons=len(comparisons),
        supported_estimate_rows=sum(row["citizen_weight_units"] > 0 for row in estimates),
        absent_group_rows=sum(not row["citizen_weight_units"] for row in estimates),
        sparse_raw_case_diagnostic_rows=sum(row["raw_case_count_under_30_diagnostic"] for row in estimates),
        notes=[
            "All 50 states and D.C. are queried; historical 2022 midterm and 2024 presidential frames stay separate.",
            "Only actual public joint cells are aggregated, not products of marginal demographic shares.",
            "All adult-citizen positive-weight source cases and explicit unknown/noninterview classes remain.",
            "PWSSWGT integer units are recovered exactly from the held four-decimal cache; no rounding or repair.",
            "Weights describe the source civilian noninstitutionalized adult-citizen frame, not legal eligibility or registrations.",
            "Under-30 raw sample size is a diagnostic, not a precision, privacy or survey-design guarantee.",
            "Unknown assignments are source-response sensitivity, not confidence intervals or actual-turnout bounds.",
            "Published-state comparisons audit source handling; no outcome calibration or independent population certification.",
            "No 2026 prediction, original-cohort retention, observed staying-home or county/precinct allocation.",
        ],
    )
    return {
        "complete-state-demographic-participation.csv": csv_bytes(estimates),
        "complete-source-joint-cell-decisions.csv": csv_bytes(decisions),
        "complete-state-demographic-nonresponse-scenarios.csv": csv_bytes(sensitivity),
        "complete-exclusive-state-partition-checks.csv": csv_bytes(partitions),
        "complete-published-state-comparisons.csv": csv_bytes(comparisons),
        "summary.json": json_bytes(summary),
    }, summary


def export(inputs, output):
    if output.exists():
        raise ValueError("Refusing to overwrite an existing analysis")
    manifest = json.loads((inputs / "source-manifest.json").read_bytes())
    if set(manifest["inputs"]) != INPUTS or manifest.get("private_individual_records_included") is not False:
        raise ValueError("Unapproved CPS input set")
    native = {}
    for name, receipt in manifest["inputs"].items():
        raw = (inputs / name).read_bytes()
        if len(raw) != receipt["bytes"] or hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
            raise ValueError("Changed frozen complete CPS input")
        native[name] = raw
    with zipfile.ZipFile(io.BytesIO(native["complete-cps-inputs.zip"])) as archive:
        cells = list(csv.DictReader(io.StringIO(archive.read("joint-cells.csv").decode())))
    if {(int(row["year"]), row["state_fips"]) for row in cells} != {
            (year, state) for year in YEARS for state in STATE_CODES}:
        raise ValueError("Complete CPS cache must contain every state and D.C. in both years")
    with zipfile.ZipFile(io.BytesIO(native["complete-cps-state-references.zip"])) as archive:
        references = list(csv.DictReader(io.StringIO(
            archive.read("complete-state-year-population-pairs.csv").decode())))
    selected_references = [row for row in references
                           if int(row["year"]) in YEARS and row["population_frame"] == "cvap"]
    if (len(selected_references) != 102 or {
            (int(row["year"]), row["reference_state_code"]) for row in selected_references} != {
            (year, code) for year in YEARS for code in STATE_CODES.values()}):
        raise ValueError("Missing or duplicate native state references")
    files, summary = build(cells, references)
    files.update({"inputs/" + name: raw for name, raw in native.items()})
    files["inputs/source-manifest.json"] = json_bytes(manifest)
    files["scripts/cps_state_groups.py"] = Path(__file__).read_bytes()
    files["tests/test_cps_state_groups.py"] = Path(__file__).parents[1].joinpath(
        "tests/test_cps_state_groups.py").read_bytes()
    files["README.txt"] = (
        "All-state historical CPS demographic participation, not 2026/admin turnout.\n"
        "Full permitted public inputs, all queries, code and tests are included.\n"
        "python3 -m unittest discover -s tests -p test_cps_state_groups.py\n"
        "python3 -m scripts.cps_state_groups --inputs inputs --output reproduced\n"
        "Read all source-frame, nonresponse, sparse-support and non-CI qualifications in summary.json.\n"
    ).encode()
    files["checksums.json"] = json_bytes({
        name: dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        for name, raw in sorted(files.items())})
    output.mkdir(parents=True)
    for name, raw in files.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, raw)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
