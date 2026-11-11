"""Preserve native CPS group registration, participation and response frames."""

import argparse
import csv
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


HISTORY_COLUMNS = (
    (2, "overall", "Total", "total_population"), (3, "overall", "Total", "citizen_population"),
    (4, "race", "White", "total_population"), (5, "race", "White", "citizen_population"),
    (6, "race", "White non-Hispanic", "total_population"),
    (7, "race", "White non-Hispanic", "citizen_population"),
    (8, "race", "Black", "total_population"), (9, "race", "Black", "citizen_population"),
    (10, "race", "Asian (native era)", "total_population"),
    (11, "race", "Asian (native era)", "citizen_population"),
    (12, "ethnicity", "Hispanic any race", "total_population"),
    (13, "ethnicity", "Hispanic any race", "citizen_population"),
    (14, "sex", "Male", "total_population"), (15, "sex", "Female", "total_population"),
)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def csv_data(rows, empty_fields=()):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else empty_fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def number(value):
    try:
        result = Decimal(str(value).replace(",", "").strip())
        return result if result.is_finite() and result >= 0 else None
    except InvalidOperation:
        return None


def decimal_text(value):
    return None if value is None else format(value, "f")


def quotient(numerator, denominator, scale=100):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    with localcontext() as context:
        context.prec = 60
        return format(Decimal(scale) * numerator / denominator, ".18f")


def label(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" .")


def schema(rows):
    for ordinal, row in enumerate(rows[:20]):
        normalized = [label(value).lower() for value in row]
        if "total citizen population" in normalized:
            def find(prefix):
                prefixes = (prefix,) if isinstance(prefix, str) else prefix
                return next((i for i, value in enumerate(normalized) if value.startswith(prefixes)), None)
            citizen = normalized.index("total citizen population")
            registered, voted = find("reported registered"), find("reported voted")
            population = next((i for previous in rows[max(0, ordinal - 1):ordinal]
                               for i, value in enumerate(previous)
                               if label(value).lower() == "total population" and i < citizen), None)
            return dict(header_row=ordinal + 1, legacy=False, citizen=citizen, population=population,
                        registered=registered, registered_all=None, voted=voted,
                        not_registered=find(("reported not registered", "not registered")),
                        unknown_registered=find("no response to registration"),
                        not_voted=find(("reported not voted", "reported did not vote", "did not vote")),
                        unknown_voted=find("no response to voting"),
                        registered_citizen_not=None, noncitizen=None)
    if any(len(row) > 10 and label(row[10]).lower() == "u.s. citizen" for row in rows[:20]):
        return dict(header_row=None, legacy=True, citizen=None, population=1, registered=10,
                    registered_all=2, voted=6, not_registered=4, unknown_registered=None,
                    not_voted=8, unknown_voted=None, registered_citizen_not=11, noncitizen=12)
    raise ValueError("Unrecognized native registration and voting headers")


def native_count_rows(workbook):
    observations, decisions = [], []
    for sheet in workbook["sheets"]:
        rows, name = sheet["rows"], sheet["name"]
        title = " ".join(label(row[0]) for row in rows[:4] if row)
        margin_sheet = "margin" in title.lower()
        columns = schema(rows)
        sex, pending = None, ""
        age_scope = "18 years and over"
        margin_section = margin_sheet
        for ordinal, row in enumerate(rows, start=1):
            first = label(row[0]) if row else ""
            if "margin" in first.lower() and "error" in first.lower():
                margin_section = True
            if first.lower() in ("both sexes", "male", "female"):
                sex = first.upper()
                pending = ""
            if workbook["table"] == 5 and re.fullmatch(
                    r"\d+(?:\s+(?:to|and|-)\s+\d+)?\s+years(?:\s+and\s+over)?", first, re.I):
                age_scope, sex, pending = first, None, ""
            count_columns = [value for key, value in columns.items()
                             if key not in ("header_row", "legacy") and value is not None]
            has_counts = any(i < len(row) and number(row[i]) is not None for i in count_columns)
            disposition = "held_margin_of_error_not_population" if margin_section else "header_note_or_unclassified"
            raw_label = label(row[1]) if not columns["legacy"] and len(row) > 1 else first
            if not margin_section and sex and has_counts and raw_label:
                native_label = label(pending + " " + raw_label)
                pending = ""
                def cell(field):
                    index = columns[field]
                    return number(row[index]) if index is not None and index < len(row) else None
                values = {field: cell(field) for field in (
                    "citizen", "population", "registered", "registered_all", "voted",
                    "not_registered", "unknown_registered", "not_voted", "unknown_voted",
                    "registered_citizen_not", "noncitizen")}
                if columns["legacy"]:
                    citizen_parts = values["registered"], values["registered_citizen_not"]
                    values["citizen"] = sum(citizen_parts) if all(v is not None for v in citizen_parts) else None
                citizen, voted, register = values["citizen"], values["voted"], values["registered"]
                universe = "native_total_population" if columns["legacy"] else "native_citizen_population"
                denominator = values["population"] if columns["legacy"] else citizen
                residual = None
                registration_residual = None
                if not columns["legacy"] and all(values[key] is not None for key in (
                        "voted", "not_voted", "unknown_voted", "citizen")):
                    residual = voted + values["not_voted"] + values["unknown_voted"] - citizen
                if not columns["legacy"] and all(values[key] is not None for key in (
                        "registered", "not_registered", "unknown_registered", "citizen")):
                    registration_residual = register + values["not_registered"] + values["unknown_registered"] - citizen
                row_id = f"{workbook['year']}:{workbook['table']}:{name}:{ordinal}"
                record = dict(
                    row_id=row_id, year=workbook["year"], election_type=(
                        "presidential" if workbook["year"] % 4 == 0 else "midterm"),
                    table=workbook["table"], sex=sex, native_age_scope=(
                        native_label if workbook["table"] == 1 else age_scope),
                    native_group=native_label, geographic_frame="CPS United States resident population",
                    native_reported_vote_universe=universe, citizen_population_is_native_sum=columns["legacy"],
                    reported_voting_pct=quotient(voted, denominator),
                    reported_registered_citizen_pct=quotient(register, citizen),
                    native_registered_universe="native_citizen_population",
                    native_not_registered_universe=universe,
                    registration_components_share_population_frame=not columns["legacy"],
                    vote_to_registration_count_ratio_pct=quotient(voted, register),
                    ratio_is_observed_registered_voter_turnout=False,
                    registration_nonresponse_disposition=(
                        "merged_with_native_not_registered" if columns["unknown_registered"] is None else "separately_reported"),
                    voting_nonresponse_disposition=(
                        "merged_with_native_did_not_vote" if columns["unknown_voted"] is None else "separately_reported"),
                    native_voting_accounting_residual_thousands=decimal_text(residual),
                    native_registration_accounting_residual_thousands=decimal_text(registration_residual),
                    accounting_disposition=("not_separately_identified" if residual is None else
                                            "within_published_rounding" if abs(residual) <= 2 else "native_difference_held"),
                    county_precinct_allocation=False, individual_retention=False,
                    native_count_unit="thousands_of_people", source_url=workbook["url"],
                    source_sha256=workbook["sha256"], source_sheet=name, source_row=ordinal,
                    source_retrieved_at=workbook["retrieved_at"],
                )
                record.update({f"native_{key}_thousands": decimal_text(value) for key, value in values.items()})
                observations.append(record)
                disposition = "native_source_group_counts"
            elif not margin_section and sex and raw_label and not has_counts:
                if raw_label.lower() not in ("both sexes", "male", "female") and not raw_label.startswith(
                        ("Note", "Source", "For information", "NOTES", "1 ", "2 ")):
                    pending = label(pending + " " + raw_label)
            decisions.append(dict(source_name=workbook["path"], source_sheet=name, source_row=ordinal,
                                  year=workbook["year"], table=workbook["table"], disposition=disposition))
    return observations, decisions


def historical_rows(workbook):
    values = {}
    for sheet in workbook["sheets"]:
        context, measure = None, None
        for ordinal, row in enumerate(sheet["rows"], start=1):
            first = row[0] if row else None
            if workbook["kind"] == "history_age":
                match = re.fullmatch(r"(.+), Percent (Voted|Registered)", label(first))
                if match:
                    context, measure = match.group(1), match.group(2).lower()
                columns = HISTORY_COLUMNS
            else:
                if first in ("Voted", "Registered"):
                    context, measure = "Population 18 and over", first.lower()
                groups = sheet["rows"][4]
                columns = tuple((i, "region" if i < 5 else "education" if i < 10 else "labor_force",
                                 label(groups[i]), "total_population") for i in range(1, 14))
            year = number(first)
            if year is None or year != int(year) or not 1964 <= year <= 2024 or not context or not measure:
                continue
            for column, dimension, group, population in columns:
                key = int(year), context, dimension, group, population
                if measure in values.setdefault(key, {}):
                    raise ValueError("Duplicate native historical percentage")
                values[key][measure] = dict(value=row[column], source_row=ordinal, source_column=column + 1,
                                           source_sheet=sheet["name"])
    result = []
    for (year, age, dimension, group, population), paired in sorted(values.items()):
        vote, registration = paired.get("voted", {}), paired.get("registered", {})
        voted, registered = number(vote.get("value")), number(registration.get("value"))
        valid = voted is not None and registered is not None and 0 <= voted <= registered <= 100 and registered > 0
        status = "paired_published_percentages_not_individual_joint" if valid else "held_missing_or_invalid_native_percentage"
        caution = []
        if year < 1972:
            caution.append("native_pre_1972_voting_age_exceptions")
        if population == "citizen_population" and year < 1996:
            caution.append("native_pre_1996_citizenship_not_uniform")
        if dimension in ("race", "ethnicity") and year < 2004:
            caution.append("native_pre_2004_race_classification")
        if dimension == "education" and year < 1992:
            caution.append("historical_education_definition_not_harmonized")
        result.append(dict(
            year=year, election_type="presidential" if year % 4 == 0 else "midterm",
            native_age_scope=age, dimension=dimension, native_group=group, population_frame=population,
            native_reported_voted_pct=decimal_text(voted), native_reported_registered_pct=decimal_text(registered),
            raw_native_voted_value=vote.get("value"), raw_native_registered_value=registration.get("value"),
            vote_to_registration_percentage_ratio_pct=quotient(voted, registered) if valid else None,
            disposition=status, native_definition_cautions=json.dumps(caution),
            reported_registered_group_population_count=None, unknown_response_mass_identified=False,
            ratio_is_observed_registered_voter_turnout=False, individual_retention=False, local_allocation=False,
            source_url=workbook["url"], source_sha256=workbook["sha256"],
            voted_source_sheet=vote.get("source_sheet"), voted_source_row=vote.get("source_row"),
            registered_source_sheet=registration.get("source_sheet"),
            registered_source_row=registration.get("source_row"), source_column=(
                vote.get("source_column") or registration.get("source_column")),
        ))
    return result


def response_scenarios(observations):
    rows = []
    for row in observations:
        citizen, voted, unknown = (number(row[key]) for key in (
            "native_citizen_thousands", "native_voted_thousands", "native_unknown_voted_thousands"))
        if row["voting_nonresponse_disposition"] != "separately_reported" or any(
                value is None for value in (citizen, voted, unknown)) or citizen <= 0 or voted + unknown > citizen + 2:
            continue
        for assignment in (0, 1):
            numerator = voted + assignment * unknown
            rows.append(dict(
                source_row_id=row["row_id"], year=row["year"], sex=row["sex"], native_group=row["native_group"],
                native_age_scope=row["native_age_scope"], assigned_voted_fraction_of_unknown=assignment,
                source_citizen_population_thousands=str(citizen), source_reported_voted_thousands=str(voted),
                source_voting_nonresponse_thousands=str(unknown), assigned_reported_voted_thousands=str(numerator),
                response_assignment_pct=quotient(numerator, citizen), reported_register_is_denominator=False,
                published_rounded_counts_not_unrounded_people=True,
                source_accounting_disposition=row["accounting_disposition"],
                administrative_turnout_bound=False, confidence_interval=False, self_report_error_corrected=False,
                legacy_merged_nonresponse_not_split=True, individual_retention=False, local_allocation=False,
            ))
    return rows


def time_comparisons(history):
    keyed = {(row["year"], row["native_age_scope"], row["dimension"], row["native_group"], row["population_frame"]): row
             for row in history}
    if len(keyed) != len(history):
        raise ValueError("Ambiguous historical group frame")
    result = []
    for key, current in sorted(keyed.items()):
        prior = keyed.get((key[0] - 4, *key[1:]))
        if not prior:
            continue
        breaks = ((prior["year"] < 1972 <= current["year"])
                  or (key[4] == "citizen_population" and prior["year"] < 1996 <= current["year"])
                  or (key[2] in ("race", "ethnicity") and prior["year"] < 2004 <= current["year"])
                  or (key[2] == "education" and prior["year"] < 1992 <= current["year"]))
        complete = all(number(row[field]) is not None for row in (prior, current) for field in (
            "native_reported_voted_pct", "native_reported_registered_pct"))
        complete = complete and all(row["disposition"] == "paired_published_percentages_not_individual_joint"
                                    for row in (prior, current))
        difference = {}
        for field in ("voted", "registered"):
            difference[field] = decimal_text(number(current["native_reported_" + field + "_pct"])
                                            - number(prior["native_reported_" + field + "_pct"])) if complete and not breaks else None
        result.append(dict(
            from_year=prior["year"], to_year=current["year"], election_type=current["election_type"],
            native_age_scope=key[1], dimension=key[2], native_group=key[3], population_frame=key[4],
            reported_voted_percentage_point_difference=difference["voted"],
            reported_registered_percentage_point_difference=difference["registered"],
            disposition="held_native_missingness_or_definition_break" if breaks or not complete
            else "same_election_type_source_snapshots_not_cohort_or_causal_change",
            native_definitions_harmonized=False, cohort_retention_inferred=False, local_allocation=False,
        ))
    return result


def build(workbooks, ap):
    observations, decisions, history = [], [], []
    for workbook in workbooks:
        if workbook["kind"] == "election":
            native, ledger = native_count_rows(workbook)
            observations.extend(native)
            decisions.extend(ledger)
        else:
            history.extend(historical_rows(workbook))
    scenarios = response_scenarios(observations)
    comparisons = time_comparisons(history)
    survey_dispositions = []
    for row in ap["selected_rows"]:
        disposition = ("no_state_group_registration_from_national_CPS_no_allocation" if row["scope"] != "US50_SOURCE"
                       else "held_US50_source_vs_CPS_US_population_frame_and_native_group_mapping")
        weight = Decimal(row["weight"])
        survey_dispositions.append(dict(
            year=row["year"], scope=row["scope"], dimension=row["dimension"], group=row["group"],
            native_labels=row["native_labels"], weight_field=row["weight_field"], disposition=disposition,
            source_weight=row["weight"],
            source_modeled_voter_share=quotient(Decimal(row["modeled_voter_weight"]), weight, 1),
            source_modeled_nonvoter_share=quotient(Decimal(row["modeled_nonvoter_weight"]), weight, 1),
            source_unknown_share=quotient(Decimal(row["model_unknown_weight"]), weight, 1),
            population_scaling_performed=False, native_gender_not_reclassified_as_CPS_sex=True,
            independent_administrative_validation=False,
        ))
    summary = dict(
        native_group_count_rows=len(observations), complete_election_workbook_row_decisions=len(decisions),
        paired_historical_percentage_rows=len(history),
        historical_years=sorted({row["year"] for row in history}),
        native_count_years=sorted({row["year"] for row in observations}),
        response_assignment_scenario_rows=len(scenarios), same_election_type_comparison_rows=len(comparisons),
        complete_public_survey_frame_dispositions=len(survey_dispositions),
        population_scaled_survey_estimates=0, reported_registered_population_is_administrative_register=False,
        notes=[
            "CPS counts are native weighted survey estimates in thousands, not administrative counts.",
            "Whole-source headers, notes, unavailability and margins-of-error sheets are preserved.",
            "Legacy not-registered/did-not-vote includes unknown responses; never split into observed nonvoters.",
            "Modern response assignments vary only unknown voting responses; not actual-turnout bounds or confidence intervals.",
            "Voting/registration ratios of marginals do not establish a joint registered-voter participation probability.",
            "Native age/sex/education categories overlap; no parent-child or marginal-product population sum.",
            "Historical unavailable N stays missing. No percent times national population to invent group registration counts.",
            "Age, citizenship, race and education definition breaks remain in same-election-type comparisons.",
            "AP US50 source/geographic and demographic frames are not qualified to scale CPS national group populations.",
            "No county/precinct allocation, individual switching/retention, observed staying home or new eligibility.",
        ],
    )
    return {
        "complete-native-group-counts.csv": csv_data(observations),
        "complete-workbook-row-dispositions.csv": csv_data(decisions),
        "complete-historical-group-percentages.csv": csv_data(history),
        "complete-response-assignment-scenarios.csv": csv_data(scenarios, ("source_row_id", "response_assignment_pct")),
        "complete-same-election-type-comparisons.csv": csv_data(comparisons),
        "complete-survey-frame-dispositions.csv": csv_data(survey_dispositions),
        "summary.json": encoded(summary),
    }, summary


def read_inputs(inputs):
    source = json.loads((inputs / "source.json").read_bytes())
    workbooks = json.loads((inputs / "workbooks.json").read_bytes())
    expected = {"sources.json", "workbooks.json", "ap-selected-aggregates.json"} | {
        "originals/" + row["path"] for row in workbooks}
    if set(source["files"]) != expected or any(
            Path(name).is_absolute() or ".." in Path(name).parts
            for name in expected | {row["path"] for row in workbooks}):
        raise ValueError("Changed or unsafe complete sufficient-input contract")
    for name, metadata in source["files"].items():
        raw = (inputs / name).read_bytes()
        if len(raw) != metadata["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
            raise ValueError("Frozen source checksum differs: " + name)
    if len(workbooks) != 28 or {(row["year"], row["table"]) for row in workbooks if row["kind"] == "election"} != {
            (year, table) for year in range(2000, 2025, 2) for table in (1, 5)}:
        raise ValueError("Incomplete held native workbook inventory")
    native_index = json.loads((inputs / "sources.json").read_bytes())["sources"]
    for row in workbooks:
        native = next(item for item in native_index if item["path"] == row["path"])
        raw = (inputs / "originals" / row["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["sha256"] or native["sha256"] != row["sha256"] or native["url"] != row["url"]:
            raise ValueError("Workbook cache bound to changed original")
        if native["retrieved_at"] != row["retrieved_at"] or row["kind"] == "election" and (
                native["year"], native["table"]) != (row["year"], row["table"]):
            raise ValueError("Changed native source year, table or acquisition clock")
    if {row["kind"] for row in workbooks} != {"election", "history_age", "history_education"}:
        raise ValueError("Changed native historical workbook inventory")
    return workbooks, json.loads((inputs / "ap-selected-aggregates.json").read_bytes()), source


def export(inputs, output):
    if output.exists():
        raise ValueError("Refusing to overwrite a prior analysis")
    workbooks, ap, source = read_inputs(inputs)
    files, summary = build(workbooks, ap)
    for name in sorted(set(source["files"]) | {"source.json"}):
        files["inputs/" + name] = (inputs / name).read_bytes()
    files["scripts/cps_group_frames.py"] = Path(__file__).read_bytes()
    files["tests/test_cps_group_frames.py"] = Path(__file__).parents[1].joinpath("tests/test_cps_group_frames.py").read_bytes()
    files["README.txt"] = (
        "Complete native CPS group registration/participation and response-frame queries.\n"
        "All permitted original workbooks, complete source caches, queries, decisions, code and tests included.\n"
        "Read summary.json. Marginal ratios and unknown-response assignments are not administrative turnout.\n"
        "python3 -m unittest discover -s tests -p test_cps_group_frames.py\n"
        "python3 -m scripts.cps_group_frames --inputs inputs --output reproduced\n"
    ).encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                                     for name, raw in sorted(files.items())})
    output.mkdir(parents=True)
    for name, raw in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    with zipfile.ZipFile(output / "complete-analysis.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
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
