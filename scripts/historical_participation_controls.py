"""Reconcile held historical ballot controls and compare source-specific survey frames."""

import argparse
from collections import defaultdict
import csv
from decimal import Decimal, localcontext
import gzip
import hashlib
import io
import itertools
import json
from pathlib import Path
import re
import zipfile


YEARS = (2018, 2020, 2022, 2024, 2026)
STATES = tuple(sorted(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()))
ANCHORS = {2018: "U.S. Senator", 2020: "President and Vice President",
           2022: "U.S. Senator", 2024: "President and Vice President"}
DATES = {2018: "November 6, 2018", 2020: "November 3, 2020",
         2022: "November 8, 2022", 2024: "November 5, 2024"}
INPUTS = {
    "current-state-controls.csv", "current-native-controls.csv", "ap-selected-aggregates.json",
    "civic-selected-aggregates.json", "hawaii-historical-sources.zip", "wyoming-2022-sources.zip",
}
PRIMARY_INPUT = "wyoming-2022-primary-statewide.json"


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def csv_bytes(rows):
    if not rows:
        raise ValueError("Missing complete output query")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def read_csv(raw):
    return list(csv.DictReader(io.StringIO(raw.decode(), newline="")))


def count(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        return int(value)
    raise ValueError("Missing or invalid native count, not zero")


def hawaii(year, summary, layout, pdf_text, source_url):
    if year not in ANCHORS or f"GENERAL ELECTION {year}" not in pdf_text or DATES[year] not in pdf_text:
        raise ValueError("Wrong Hawaii native PDF election identity")
    rows = list(csv.reader(io.StringIO(summary.decode(layout["encoding"]), newline=""),
                           delimiter=layout["delimiter"]))
    if layout["source_format_metadata"] == "Format#1":
        if rows.pop(0) != ["Format#1"]:
            raise ValueError("Changed Hawaii native format preamble")
    header = rows.pop(0)
    if header != layout["native_header"]:
        raise ValueError("Changed Hawaii historical header")
    records = []
    for row in rows:
        if layout["data_trailing_empty_field_absent_from_header"]:
            if len(row) != len(header)+1 or row[-1] != "":
                raise ValueError("Changed Hawaii trailing source field")
            row = row[:-1]
        if len(row) != len(header):
            raise ValueError("Malformed Hawaii historical source record")
        records.append(dict(zip(header, row)))
    selected = [r for r in records if r["Contest Title"] == ANCHORS[year]]
    if not selected or len({r["Candidate ID"] for r in selected}) != len(selected):
        raise ValueError("Missing or duplicate Hawaii statewide anchor")
    modes = [field.removesuffix(" Votes") for field in header
             if field.endswith(" Votes") and field not in {"Total Votes"}
             and not any(field.endswith(kind + " Votes") for kind in ("Blank", "Over", "Invalid"))]
    registration = {count(r["Registered Voters"]) for r in selected}
    if len(registration) != 1:
        raise ValueError("Inconsistent repeated Hawaii state registration")
    registered = registration.pop()
    ballot_modes = []
    for mode in modes:
        fields = [mode + " " + category + " Votes" for category in ("Blank", "Over", "Invalid")
                  if mode + " " + category + " Votes" in header]
        accounting = {tuple(count(r[field]) for field in fields) for r in selected}
        if len(accounting) != 1:
            raise ValueError("Inconsistent repeated Hawaii contest accounting")
        value = sum(count(r[mode + " Votes"]) for r in selected) + sum(next(iter(accounting)))
        ballot_modes.append(dict(year=year, state_code="HI", source_family="native_summary_csv",
                                 native_mode=mode, ballots=value, cross_year_mode_harmonized=False))
    for row in selected:
        if sum(count(row[m + " Votes"]) for m in modes) != count(row["Total Votes"]):
            raise ValueError("Hawaii candidate mode sum differs from native total")
    ballots = sum(r["ballots"] for r in ballot_modes)
    for label, expected in (("TOTAL REGISTRATION", registered), ("TOTAL TURNOUT", ballots)):
        values = {int(v.replace(",", "")) for v in re.findall(
            re.escape(label) + r"\s+([0-9][0-9,]*)", pdf_text)}
        if values != {expected}:
            raise ValueError("Hawaii historical PDF/text totals do not reconcile")
    clock = re.findall(r"Printed on:\s*([0-9/]+ at [0-9:]+ [ap]m)", pdf_text)
    if len(set(clock)) != 1 or not re.search(r"(?i)\bFINAL\b", pdf_text):
        raise ValueError("Missing native Hawaii final-report label or print clock")
    for label in ("PRECINCT", "ABSENTEE", "MAIL", "IN-PERSON"):
        values = {int(v.replace(",", "")) for v in re.findall(
            r"(?<![A-Z-])" + re.escape(label) + r" TURNOUT\s+([0-9][0-9,]*)", pdf_text)}
        if values:
            if len(values) != 1:
                raise ValueError("Conflicting PDF mode counts")
            ballot_modes.append(dict(year=year, state_code="HI", source_family="native_state_pdf",
                                     native_mode=label, ballots=values.pop(), cross_year_mode_harmonized=False))
    pdf_modes = [r["ballots"] for r in ballot_modes if r["source_family"] == "native_state_pdf"]
    if not pdf_modes or sum(pdf_modes) != ballots:
        raise ValueError("Hawaii PDF turnout modes do not reconcile")
    return dict(
        year=year, state_code="HI", control_id=f"hi-native-general-{year}",
        control_measure="reported_cast_ballots", native_measure="TOTAL TURNOUT",
        native_numerator=ballots, reported_cast_ballots=ballots, registered=registered,
        registration_basis="native_TOTAL_REGISTRATION_active_inactive_definition_unqualified",
        source_time_label="Printed on: " + clock[0], source_url=source_url,
        source_report_status="source_labeled_final_not_independent_certification",
        source_labeled_final=True, native_total_units=count(selected[0]["Total Precincts"]),
        native_counted_units=count(selected[0]["Counted Precincts"]),
        counted_field_not_used_to_infer_zero_ballots=True,
    ), ballot_modes


def wyoming(rows, audit):
    counties, seen = defaultdict(int), set()
    for row in rows:
        key = row["county"], row["precinct"]
        if (row["year"] != "2022" or row["state_code"] != "WY" or key in seen
                or row["registered_voters"] or row["turnout_rate"]
                or count(row["ballots"]) != sum(count(row[f]) for f in audit["category_labels"])):
            raise ValueError("Changed Wyoming 2022 native ballot or registration contract")
        seen.add(key)
        counties[row["county"]] += count(row["ballots"])
    if (len(counties) != 23 or len(rows) != audit["units"]
            or sum(counties.values()) != audit["statewide_ballots"]
            or audit["ballot_approval"] not in {"approved", "withheld"}):
        raise ValueError("Wyoming historical native ballot reconciliation changed")
    qualified = audit["ballot_approval"] == "approved" and not audit["printed_ballot_conflicts"]
    return dict(
        year=2022, state_code="WY", control_id="wy-native-general-2022",
        control_measure=("reported_cast_ballots" if qualified else
                         "native_workbook_ballot_sum_printed_conflict_held"),
        native_measure="separate native workbook ballot sum",
        native_numerator=sum(counties.values()),
        reported_cast_ballots=sum(counties.values()) if qualified else None, registered=None,
        registration_basis="registered_denominator_not_supplied",
        source_time_label="Native county/workbook clocks retained; no common statewide clock qualified",
        source_url="https://sos.wyo.gov/Elections/Docs/2022/2022GeneralResults.aspx",
        source_report_status="reviewed_native_counts_certification_not_independently_qualified",
        source_labeled_final=False, native_total_units=len(rows), native_counted_units=None,
        counted_field_not_used_to_infer_zero_ballots=True,
        source_scope_notes=json.dumps(dict(
            ballot_approval=audit["ballot_approval"], printed_ballot_conflicts=audit["printed_ballot_conflicts"]),
            sort_keys=True),
    )


def wyoming_statewide(primary, held):
    if (primary["year"] != 2022 or primary["state_code"] != "WY"
            or "Wyoming General Election - November 8, 2022" not in primary["native_pdf_text"]):
        raise ValueError("Wrong direct Wyoming statewide source identity")
    counties = primary["workbook_counties"]
    total = primary["workbook_total"]
    if (len(counties) != 23 or any(type(v) is not int or v < 0 for v in counties.values())
            or sum(counties.values()) != total or total != held["native_numerator"]):
        raise ValueError("Direct statewide and retained native sums differ")
    extracted = {int(v.replace(",", "")) for v in re.findall(
        r"(?m)^\s*([0-9][0-9,]*)\s*Total\s*$", primary["native_pdf_text"])}
    if extracted != {total}:
        raise ValueError("Direct statewide PDF total differs")
    for county, value in counties.items():
        values = {int(v.replace(",", "")) for v in re.findall(
            re.escape(county) + r"\s+([0-9][0-9,]*)", primary["native_pdf_text"])}
        if values != {value}:
            raise ValueError("Direct statewide PDF county vector differs")
    notes = primary["native_ballot_issue_notes"]
    if (len(notes) != 2 or any(
            f"The total ballots cast is {total:,}." not in note or
            f"{total//2+1:,}" not in note for note in notes)):
        raise ValueError("Direct statewide ballot-issue notes differ")
    return dict(
        year=2022, state_code="WY", control_id="wy-native-general-2022-statewide",
        control_measure="reported_cast_ballots", native_measure="Total Ballots Cast: native statewide summary",
        native_numerator=total, reported_cast_ballots=total, registered=None,
        registration_basis="registered_denominator_not_supplied",
        source_time_label="2022 native statewide summary; no print/update clock supplied",
        source_url=primary["source_pdf_url"],
        source_report_status="native_statewide_summary_no_independent_certification",
        source_labeled_final=False, native_total_units=23, native_counted_units=None,
        counted_field_not_used_to_infer_zero_ballots=True,
        source_scope_notes="Explicit statewide PDF and summary workbook totals; all 23 county values match. "
                           "The separately held unit aggregate and Natrona printed county conflict remain unchanged.",
        selected_state_reference=True,
        selection_disposition="separate_primary_statewide_summary_selected_not_county_conflict_repair",
    )


def build(current, native, historical, modes, ap, civic):
    if len(current) != 51 or {r["state_code"] for r in current} != set(STATES):
        raise ValueError("Changed complete current state/DC query")
    observations = {r["id"]: r for r in native}
    selected = [r for r in historical if r.get("selected_state_reference", True)]
    controls = {(r["state_code"], int(r["year"])): r for r in selected}
    if len(controls) != len(selected):
        raise ValueError("Duplicate historical state-year")
    for row in current:
        if not row["control_id"]:
            continue
        source = observations[row["control_id"]]
        controls[row["state_code"], 2026] = dict(
            year=2026, state_code=row["state_code"], control_id=row["control_id"],
            control_measure=row["control_measure"], native_measure=source["native_measure"],
            native_numerator=count(source["numerator"]),
            reported_cast_ballots=int(row["reported_cast_ballots"]) if row["reported_cast_ballots"] else None,
            registered=int(row["control_registered_denominator"]) if row["control_registered_denominator"] else None,
            registration_basis=row["control_denominator_basis"],
            source_time_label=row["control_native_time"], source_url=row["control_source_url"],
            source_report_status=source["native_status"], source_labeled_final=False,
            native_total_units=None, native_counted_units=None, counted_field_not_used_to_infer_zero_ballots=True,
            source_scope_notes=source.get("scope_notes", ""))
    survey = []
    for row in ap["selected_rows"]:
        if row["scope"] == "DC":
            raise ValueError("No approved D.C. survey aggregate")
        if row["scope"] not in STATES or row["dimension"] != "overall":
            continue
        if "_STATE_" not in row["weight_field"] or row["group"] != "all" or int(row["positive_weight_n"]) < 500:
            raise ValueError("Unapproved historical state survey aggregate")
        survey.append(dict(
            year=int(row["year"]), state_code=row["scope"], study="AP VoteCast",
            weight_field=row["weight_field"], n=row["n"], weight=row["weight"],
            voter=row["modeled_voter_weight"], nonvoter=row["modeled_nonvoter_weight"],
            unknown=row["model_unknown_weight"], inference_status=row["inference_status"]))
    civic_overall = [r for r in civic["participation"]
                     if r["dimension"] == "overall" and r["scope"] != "POOLED_SOURCE"]
    if len(civic_overall) != 50 or {r["scope"] for r in civic_overall} != set(STATES)-{"DC"}:
        raise ValueError("Changed Civic state-only sample coverage")
    for row in civic_overall:
        if row["dimension"] == "overall" and row["scope"] != "POOLED_SOURCE":
            survey.append(dict(
                year=2026, state_code=row["scope"], study="Civic",
                weight_field="source_variable_not_supplied_in_public_selection",
                n=row["n"], weight=row["weight"], voter=row["modeled_voter_weight"],
                nonvoter=row["modeled_nonvoter_weight"], unknown="0",
                inference_status="conditional_source_weighted_target_and_field_period_unqualified"))
    keys = [(r["year"], r["state_code"], r["study"], r["weight_field"]) for r in survey]
    if len(keys) != len(set(keys)) or any(r["year"] not in YEARS or r["state_code"] not in STATES for r in survey):
        raise ValueError("Duplicate or unknown survey year/state/frame")
    state_query, comparison, transitions = [], [], []
    with localcontext() as context:
        context.prec = 80
        for year in YEARS:
            for state in STATES:
                control = controls.get((state, year))
                ballots = control["reported_cast_ballots"] if control else None
                registered = control["registered"] if control else None
                rate = str(100 * Decimal(ballots) / registered) if ballots is not None and registered else None
                state_query.append(dict(
                    year=year, state_code=state, control_present=bool(control),
                    control_id=control["control_id"] if control else None,
                    control_measure=control["control_measure"] if control else None,
                    native_measure=control["native_measure"] if control else None,
                    native_control_numerator=control["native_numerator"] if control else None,
                    reported_cast_ballots=ballots, native_registered=registered,
                    native_ballots_per_registered_pct=rate,
                    registration_basis=control["registration_basis"] if control else None,
                    source_time_label=control["source_time_label"] if control else None,
                    source_url=control["source_url"] if control else None,
                    source_report_status=control["source_report_status"] if control else None,
                    source_scope_notes=control.get("source_scope_notes", "") if control else None,
                    source_labeled_final=control["source_labeled_final"] if control else None,
                    native_total_units=control["native_total_units"] if control else None,
                    native_counted_units=control["native_counted_units"] if control else None,
                    registration_definition_harmonized=False,
                    original_cohort_participation=None, eligibility=None, deaths=None, migration=None))
        for row in sorted(survey, key=lambda r: (r["year"], r["state_code"], r["study"], r["weight_field"])):
            total = Decimal(row["weight"])
            mass = [Decimal(row[f]) for f in ("voter", "nonvoter", "unknown")]
            if total <= 0 or min(mass) < 0 or sum(mass) != total:
                raise ValueError("Changed complete survey model denominator")
            proportions = [value / total for value in mass]
            control = controls.get((row["state_code"], row["year"]))
            registered = control["registered"] if control else None
            ballots = control["reported_cast_ballots"] if control else None
            expected = [registered * value for value in proportions] if registered else [None]*3
            if registered and abs(sum(expected)-registered) > Decimal("1e-60"):
                raise ValueError("Conditional full model partition failed")
            comparison.append(dict(
                year=row["year"], state_code=row["state_code"], study=row["study"],
                weight_field=row["weight_field"], source_n=row["n"], source_weight=row["weight"],
                source_modeled_voter_weight=row["voter"], source_modeled_nonvoter_weight=row["nonvoter"],
                source_model_unknown_weight=row["unknown"],
                modeled_voter_pct=str(100*proportions[0]),
                modeled_nonvoter_pct=str(100*proportions[1]),
                model_unknown_pct=str(100*proportions[2]), inference_status=row["inference_status"],
                control_id=control["control_id"] if control else None,
                control_measure=control["control_measure"] if control else None,
                native_control_numerator=control["native_numerator"] if control else None,
                native_registered=registered, reported_cast_ballots=ballots,
                conditional_modeled_voter_count=str(expected[0]) if registered else None,
                conditional_modeled_nonvoter_count=str(expected[1]) if registered else None,
                conditional_model_unknown_count=str(expected[2]) if registered else None,
                cast_minus_conditional_modeled_voters=(
                    str(Decimal(ballots)-expected[0]) if registered and ballots is not None else None),
                exchangeability_assumption_validated=False,
                source_weights_outcome_independence_qualified=False,
                field_period_and_native_cutoff_match_qualified=False,
                cross_study_model_construct_harmonized=False,
                model_nonvoter_is_administrative_staying_home=False,
                original_cohort_participation=None, eligibility=None, deaths=None, migration=None))
        for state in STATES:
            available = [r for r in state_query if r["state_code"] == state and r["control_measure"] in {
                "reported_cast_ballots", "native_workbook_ballot_sum_printed_conflict_held"}]
            for old, new in itertools.combinations(available, 2):
                before, after = old["native_control_numerator"], new["native_control_numerator"]
                held = old["reported_cast_ballots"] is None or new["reported_cast_ballots"] is None
                transitions.append(dict(
                    state_code=state, from_year=old["year"], to_year=new["year"],
                    from_control_measure=old["control_measure"], to_control_measure=new["control_measure"],
                    from_native_ballot_numerator=before, to_native_ballot_numerator=after,
                    native_ballot_count_change=after-before,
                    native_ballot_count_change_pct=str(100*Decimal(after-before)/before) if before else None,
                    qualified_cast_ballot_snapshot_change=None if held else after-before,
                    includes_held_native_ballot_measure=held,
                    from_registered=old["native_registered"], to_registered=new["native_registered"],
                    native_registered_change=(new["native_registered"]-old["native_registered"]
                        if old["native_registered"] is not None and new["native_registered"] is not None else None),
                    native_reported_fraction_change_pp=(
                        str(Decimal(new["native_ballots_per_registered_pct"]) -
                            Decimal(old["native_ballots_per_registered_pct"]))
                        if old["native_ballots_per_registered_pct"] is not None and
                        new["native_ballots_per_registered_pct"] is not None else None),
                    same_presidential_midterm_cycle=(old["year"] % 4 == new["year"] % 4),
                    both_source_labeled_final=bool(old["source_labeled_final"] and new["source_labeled_final"]),
                    from_source_clock=old["source_time_label"], to_source_clock=new["source_time_label"],
                    same_registration_definition_independently_verified=False,
                    individual_retention_or_switching_inferred=False,
                    eligibility=None, deaths=None, migration=None))
    source_selection = []
    if any("selected_state_reference" in r for r in historical):
        for row in native:
            source_selection.append(dict(
                observation_id=row["id"], year=int(row["year"]), state_code=row["state_code"],
                geographic_level=row["geographic_level"], measure=row["measure"],
                native_numerator=count(row["numerator"]),
                native_denominator=count(row["denominator"]) if row["denominator"] else None,
                selected_state_reference=row["selected_state_reference"] == "True",
                disposition=row["disposition"], native_aggregate_ballot_approval=None,
                source_url=row["source_url"], source_time_label=row["source_time_label"],
                scope_notes=row["scope_notes"]))
        for row in historical:
            source_selection.append(dict(
                observation_id=row["control_id"], year=row["year"], state_code=row["state_code"],
                geographic_level=("state_native_unit_aggregate" if
                                  row["control_measure"] == "native_workbook_ballot_sum_printed_conflict_held"
                                  else "state"),
                measure=row["control_measure"], native_numerator=row["native_numerator"],
                native_denominator=row["registered"],
                selected_state_reference=row.get("selected_state_reference", True),
                disposition=row.get("selection_disposition", "historical_native_state_summary_selected"),
                native_aggregate_ballot_approval=(
                    "withheld" if row["control_measure"] == "native_workbook_ballot_sum_printed_conflict_held"
                    else None),
                source_url=row["source_url"], source_time_label=row["source_time_label"],
                scope_notes=row.get("source_scope_notes", "")))
    summary = dict(
        state_year_query_rows=len(state_query), years=list(YEARS),
        state_year_controls=sum(r["control_present"] for r in state_query),
        qualified_cast_state_year_controls=sum(r["reported_cast_ballots"] is not None for r in state_query),
        held_native_ballot_references=sum(
            r["control_measure"] == "native_workbook_ballot_sum_printed_conflict_held" for r in state_query),
        source_specific_survey_rows=len(comparison),
        survey_rows_with_control=sum(r["control_id"] is not None for r in comparison),
        conditional_registered_frame_rows=sum(r["native_registered"] is not None for r in comparison),
        administrative_time_comparison_rows=len(transitions), native_mode_rows=len(modes),
        status="descriptive_native_snapshots_and_unvalidated_source_specific_registration_scenarios",
        notes=[
            "All 51 jurisdictions and five years remain in the full query; missing controls remain null.",
            "Historical Hawaii native statewide summaries reconcile to separate PDFs; repeated registrations are not added.",
            "Native CSV and PDF mode labels are retained separately, never harmonized or added across source families.",
            "Hawaii 2022 Counted Precincts=0 does not turn its positive final-report counts into zero or missing votes.",
            "Historical source-labeled final does not establish independent certification.",
            "Wyoming 2022 and 2026 registrations remain null; no VEP or candidate sum replaces ballots or registration.",
            ("Wyoming 2022 native unit aggregate stays held; the separate primary statewide summary "
             "is selected without repairing county prints, registration or geography."
             if source_selection else
             "Wyoming 2022 native workbook sum remains held for the Natrona printed-total conflict; its native change is not an approved cast-ballot change."),
            "2026 controls are held unofficial snapshots, not final-count turnout declines versus historical finals.",
            "Raw registration-frame fractions are source-defined, not harmonized eligibility rates.",
            "AP poll-close/final state weights remain separate and may already use outcome calibration; no independent prediction validation.",
            "AP/Civic model constructs, field periods and registration-frame exchangeability remain unqualified.",
            "Conditional registered-frame units are not measured staying home or original-cohort people.",
            "No cross-study model-share change, individual transition, partisan fitting, causal turnout decomposition or confidence interval.",
            "Eligibility, death and migration remain unknown, not zero.",
        ])
    files = {
        "complete-state-year-controls.csv": csv_bytes(state_query),
        "complete-source-specific-survey-comparison.csv": csv_bytes(comparison),
        "complete-administrative-time-comparisons.csv": csv_bytes(transitions),
        "complete-native-mode-accounting.csv": csv_bytes(modes),
        "summary.json": json_bytes(summary),
    }
    if source_selection:
        summary["complete_native_source_observations"] = len(source_selection)
        summary["retained_held_native_unit_observations"] = sum(
            r["native_aggregate_ballot_approval"] == "withheld" for r in source_selection)
        files["complete-native-source-selection.csv"] = csv_bytes(source_selection)
        files["summary.json"] = json_bytes(summary)
    return files, summary


def export(inputs, output):
    if output.exists():
        raise ValueError("Refusing to overwrite an existing analysis")
    manifest = json.loads((inputs / "source-manifest.json").read_bytes())
    if (set(manifest["inputs"]) not in (INPUTS, INPUTS | {PRIMARY_INPUT})
            or manifest["raw_individual_records_included"] is not False):
        raise ValueError("Unapproved historical sufficient-input set")
    native = {}
    for name, receipt in manifest["inputs"].items():
        content = (inputs / name).read_bytes()
        if len(content) != receipt["bytes"] or hashlib.sha256(content).hexdigest() != receipt["sha256"]:
            raise ValueError("Changed frozen historical aggregate input")
        native[name] = content
    historical, modes = [], []
    with zipfile.ZipFile(io.BytesIO(native["hawaii-historical-sources.zip"])) as archive:
        metadata = json.loads(archive.read("acquisition.json"))
        receipts = json.loads(archive.read("source-receipts.json"))
        for year in ANCHORS:
            row, accounting = hawaii(
                year, gzip.decompress(archive.read(f"originals/{year}/summary.txt.gz")),
                metadata["elections"][str(year)]["text_formats"]["summary.txt"],
                gzip.decompress(archive.read(f"pdf-text/{year}.txt.gz")).decode(),
                receipts[f"{year}/histatewide.pdf"]["url"])
            historical.append(row)
            modes.extend(accounting)
    with zipfile.ZipFile(io.BytesIO(native["wyoming-2022-sources.zip"])) as archive:
        held = wyoming(read_csv(archive.read("precinct-counts.csv")),
                       json.loads(archive.read("counts-review.json")))
        if PRIMARY_INPUT in native:
            primary = json.loads(native[PRIMARY_INPUT])
            pdf = gzip.decompress(archive.read(
                "originals/2022/2022_General_Statewide_Total_Ballots_Cast_Summary.pdf.gz"))
            workbook_zip = gzip.decompress(archive.read("originals/2022/2022_Wyoming_General_Results.zip.gz"))
            with zipfile.ZipFile(io.BytesIO(workbook_zip)) as workbooks:
                workbook = workbooks.read("2022_General_Summaries_Results.xlsx")
            if (hashlib.sha256(pdf).hexdigest() != primary["source_pdf_sha256"]
                    or hashlib.sha256(workbook).hexdigest() != primary["source_workbook_sha256"]):
                raise ValueError("Changed original statewide Wyoming source bytes")
            state = wyoming_statewide(primary, held)
            held["selected_state_reference"] = False
            held["selection_disposition"] = "original_held_native_unit_aggregate_retained_not_promoted"
            historical.append(state)
        historical.append(held)
    files, summary = build(
        read_csv(native["current-state-controls.csv"]), read_csv(native["current-native-controls.csv"]),
        historical, modes, json.loads(native["ap-selected-aggregates.json"]),
        json.loads(native["civic-selected-aggregates.json"]))
    files.update({"inputs/" + name: content for name, content in native.items()})
    files["inputs/source-manifest.json"] = json_bytes(manifest)
    files["scripts/historical_participation_controls.py"] = Path(__file__).read_bytes()
    files["tests/test_historical_participation_controls.py"] = Path(__file__).parents[1].joinpath(
        "tests/test_historical_participation_controls.py").read_bytes()
    files["README.txt"] = (
        "Native historical participation snapshots and conditional registration-frame scenarios.\n"
        "Complete aggregate originals, sufficient inputs, all queries, code and tests included.\n"
        "Hawaii historical PDF text is source-bound to the included original PDFs; no PDF packages are needed for reproduction.\n"
        "No raw respondents, voter identifiers, original-cohort counts or geographic allocation.\n"
        "Offline reproduction from the unpacked complete archive:\n"
        "  python3 -m unittest discover -s tests -p test_historical_participation_controls.py\n"
        "  python3 -m scripts.historical_participation_controls --inputs inputs --output reproduced\n"
        "Read summary.json and every source-frame, reporting-status and unknown-value qualifier.\n"
    ).encode()
    files["checksums.json"] = json_bytes({
        name: dict(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
        for name, content in sorted(files.items())})
    output.mkdir(parents=True)
    for name, content in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    with zipfile.ZipFile(output / "complete-analysis.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    print(json.dumps({key: value for key, value in summary.items() if key != "notes"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
