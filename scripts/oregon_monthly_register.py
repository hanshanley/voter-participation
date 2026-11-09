"""Keep Oregon monthly registrations separate from held returned envelopes."""

import argparse
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from .washington_register_control import civic_source, csv_bytes, encoded


BASELINE_SHA = "c8b3b6664507bebea9e8d3fc7cecbe19f8182510d748f298961e787887b68893"
NATIVE_SHA = "ea2b60eba1cd4ca6842c7a3b674cb785800af918ab5c15ba69d078a157459e72"
PDF_SHA = "6ba27dc31ecb4b09d81ef9c9b3258dfa8fd44bdc8f2a1c34aa38d3dc5ab890b9"
RETURN_SHA = "0584cf65ac46bf34096e7c81544c54af97daf761aa050e75842812f36678f8d2"
URL = "https://sos.oregon.gov/elections/Documents/Registration/2026-November.pdf"
RETURN_URL = "https://sos.oregon.gov/elections/Documents/2026-general-election-unofficial-ballot-returns.pdf"
CONTROL = "or-2026-monthly-registration-prepared-20261103"
HELD = "or-2026-returned-envelopes-formal-analysis-warning-held"
MEASURE = "native_monthly_registration_stock_preparation_not_cutoff"
BASIS = "native_November_registration_Total_prepared_20261103_status_and_cutoff_unspecified"
PARTIES = ["Democrat", "Republican", "Non Affiliated", "Independent", "Libertarian",
           "No Labels", "Pacific Green", "Progressive", "Working Families", "Other", "Total"]
COUNTIES = "Baker|Benton|Clackamas|Clatsop|Columbia|Coos|Crook|Curry|Deschutes|Douglas|Gilliam|Grant|Harney|Hood River|Jackson|Jefferson|Josephine|Klamath|Lake|Lane|Lincoln|Linn|Malheur|Marion|Morrow|Multnomah|Polk|Sherman|Tillamook|Umatilla|Union|Wallowa|Wasco|Washington|Wheeler|Yamhill".split("|")


def parse_pages(pages):
    if len(pages) != 7:
        raise ValueError("Incomplete seven-page registration report")
    rows = []
    district = None
    for page_number, text in enumerate(pages, 1):
        normalized = " ".join(text.split())
        title = ("Voter Registration Comparison by County" if page_number == 1 else
                 "Voter Registration by County" if page_number == 2 else
                 "Voter Registration by Congressional District" if page_number in (3, 4) else
                 "Voter Registration by Senate District" if page_number == 5 else
                 "Voter Registration by Representative District")
        if title not in normalized or "November 2026" not in normalized or "11/3/2026" not in normalized:
            raise ValueError("Changed native title, month or preparation date")
        if page_number > 1 and (
                "Democrat Republican Affiliated Independent Libertarian No Labels Green Progressive Families Other Total" not in normalized
                or "Non Pacific Working" not in normalized):
            raise ValueError("Changed native registration-affiliation headers")
        for line in text.splitlines():
            literal = " ".join(line.split())
            if page_number == 1:
                match = re.fullmatch(r"(.+?) (\d[\d,]*) (\d[\d,]*) (-?[\d.]+%) (\d[\d,]*) (-?[\d.]+%)", literal)
                if not match:
                    continue
                label, current, previous, percent, annual, annual_percent = match.groups()
                values = [int(current.replace(",", "")), int(previous.replace(",", "")), percent,
                          int(annual.replace(",", "")), annual_percent]
                rows.append(dict(source_page=page_number, view="monthly_comparison", district=None,
                                 native_label=label, values=values))
                continue
            match = re.fullmatch(r"(.+?) ((?:\d[\d,]* ){10}\d[\d,]*)", literal)
            if not match:
                continue
            label, tail = match.groups()
            values = [int(value.replace(",", "")) for value in tail.split()]
            if page_number in (3, 4):
                start = re.match(r"^([1-6](?:st|nd|rd|th)) (.+)$", label)
                if start:
                    district, label = start.groups()
                view = "congressional"
                row_district = None if label == "Grand Total" else district
                if label != "Grand Total" and row_district is None:
                    raise ValueError("Missing native congressional district scope")
            else:
                view = "county" if page_number == 2 else "senate" if page_number == 5 else "representative"
                row_district = label if label.isdigit() else None
            rows.append(dict(source_page=page_number, view=view, district=row_district,
                             native_label=label, values=values))
    return rows


def registration_frame(first, second):
    rows = parse_pages(first)
    if rows != parse_pages(second):
        raise ValueError("Independent full registration readers disagree")
    identity = lambda row: (row["view"], row["district"], row["native_label"])
    if len({identity(row) for row in rows}) != len(rows):
        raise ValueError("Duplicate native geography or parent")
    by_view = {view: [row for row in rows if row["view"] == view]
               for view in ("monthly_comparison", "county", "congressional", "senate", "representative")}
    for view in ("monthly_comparison", "county"):
        if {row["native_label"] for row in by_view[view]} != set(COUNTIES) | {"Total"}:
            raise ValueError("Incomplete native 36-county inventory or explicit Total")
    for view, expected in (("senate", 30), ("representative", 60)):
        if {row["native_label"] for row in by_view[view]} != {str(value) for value in range(1, expected + 1)} | {"Total"}:
            raise ValueError("Incomplete native legislative district inventory")
    congressional = by_view["congressional"]
    if len(congressional) != 56:
        raise ValueError("Incomplete native congressional fragment inventory")
    if {row["district"] for row in congressional if row["native_label"] == "Total"} != {"1st", "2nd", "3rd", "4th", "5th", "6th"}:
        raise ValueError("Missing native six congressional subtotals")
    parents = [row for row in congressional if row["native_label"] == "Grand Total"]
    if len(parents) != 1:
        raise ValueError("Missing explicit congressional Grand Total; no sum fallback")
    if any(row["native_label"] not in set(COUNTIES) | {"Total", "Grand Total"} for row in congressional):
        raise ValueError("Changed native congressional county labels")
    parent = next(row for row in by_view["county"] if row["native_label"] == "Total")
    total = parent["values"][-1]
    if type(total) is not int or total <= 0:
        raise ValueError("Missing explicit positive monthly registration parent")
    diagnostics = []
    def equation(scope, expected, children):
        diagnostics.append(dict(scope=scope, native_parent=expected,
                                observed_child_sum=sum(children), difference=sum(children) - expected))
    for row in rows:
        if row["view"] != "monthly_comparison":
            equation(":".join(str(value) for value in identity(row)), row["values"][-1], row["values"][:-1])
    for view in ("county", "senate", "representative"):
        selected = next(row for row in by_view[view] if row["native_label"] == "Total")
        if selected["values"] != parent["values"]:
            raise ValueError("Repeated native statewide parents disagree")
        for column in range(11):
            equation(view + ":component:" + str(column), selected["values"][column],
                     [row["values"][column] for row in by_view[view] if row["native_label"] != "Total"])
    if parents[0]["values"] != parent["values"]:
        raise ValueError("Native congressional Grand Total differs from county Total")
    for district in ("1st", "2nd", "3rd", "4th", "5th", "6th"):
        selected = next(row for row in congressional if row["district"] == district and row["native_label"] == "Total")
        for column in range(11):
            equation(district + ":component:" + str(column), selected["values"][column],
                     [row["values"][column] for row in congressional
                      if row["district"] == district and row["native_label"] != "Total"])
    for column in range(11):
        equation("congressional:component:" + str(column), parent["values"][column],
                 [row["values"][column] for row in congressional if row["native_label"] == "Total"])
    comparison_parent = next(row for row in by_view["monthly_comparison"] if row["native_label"] == "Total")
    if comparison_parent["values"][0] != total:
        raise ValueError("Native current-month comparison parent differs")
    for column in (0, 1, 3):
        equation("monthly_comparison:" + str(column), comparison_parent["values"][column],
                 [row["values"][column] for row in by_view["monthly_comparison"] if row["native_label"] != "Total"])
    accounting = []
    for row in rows:
        columns = ["This Month", "Last Month", "Native monthly % change", "November 2025",
                   "Native annual % change"] if row["view"] == "monthly_comparison" else PARTIES
        for column, value in zip(columns, row["values"]):
            accounting.append(dict(source_page=row["source_page"], view=row["view"],
                district_literal=row["district"], geography_literal=row["native_label"],
                native_column_label=column, native_value=value,
                native_kind="printed_percentage" if isinstance(value, str) else "observed_count",
                missing_imputed_zero=False, registration_affiliation_not_vote_choice=True))
    return total, accounting, diagnostics


def held_context(views, facts):
    for pages in views.values():
        if len(pages) != 5:
            raise ValueError("Incomplete held returned-envelope original")
        overview, definition = (" ".join(pages[index].split()) for index in (0, 4))
        if ("3,117,439 2,028,213 65.06%" not in overview
                or "unofficial and should not be used for official reporting, certification, or formal analysis" not in overview
                or "ballot envelopes marked as returned" not in definition
                or "snapshot as of 10/16/26 at 7 a.m." not in definition):
            raise ValueError("Changed held measure, formal-analysis warning or active snapshot")
        if "11/6/2026 3:36 PM" not in " ".join(" ".join(pages).split()):
            raise ValueError("Changed held report-generated clock")
    if (facts["ballot_envelopes_marked_returned"] != 2028213 or facts["active_voters"] != 3117439
            or facts["report_generated_at"] != "11/6/2026 3:36 PM"
            or facts["active_voters_snapshot_at"] != "2026-10-16 7:00 AM"):
        raise ValueError("Changed held source facts")
    return dict(native_returned_envelopes=2028213, native_active_snapshot=3117439,
                native_active_snapshot_clock="2026-10-16 7:00 AM", native_report_clock="11/6/2026 3:36 PM",
                timezone=None, source_formal_analysis_warning=True,
                used_for_model_or_calibration=False, cast_ballot_equivalence_qualified=False)


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "complete-oregon-monthly-native-inputs.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted version20 baseline or sufficient native inputs")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        sums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(sums) | {"checksums.json"}:
            raise ValueError("Changed complete native input inventory")
        for name, metadata in sums.items():
            body = archive.read(name)
            if len(body) != metadata["bytes"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient native input")
        if hashlib.sha256(archive.read("registration.pdf")).hexdigest() != PDF_SHA or hashlib.sha256(archive.read("returned-envelopes-held.pdf")).hexdigest() != RETURN_SHA:
            raise ValueError("Changed original PDF")
        views = json.loads(archive.read("registration-source-views.json"))
        total, accounting, diagnostics = registration_frame(views["pymupdf"], views["pdfplumber"])
        held = held_context(json.loads(archive.read("held-return-source-views.json")),
                            json.loads(archive.read("held-source-context.json")))
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        state_bytes = archive.read("complete-state-control-query.csv")
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 37, 26):
        raise ValueError("Changed complete version20 coverage")
    state = next(row for row in states if row["state_code"] == "OR")
    if state["control_id"] != "reporting-OR" or state["control_registered_denominator"] != "3109084":
        raise ValueError("Do not overwrite or replace an existing primary Oregon reference")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "OR" and row["dimension"] == "overall")
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or voter + nonvoter != weight or min(voter, nonvoter) < 0 or str(source["n"]) != state["civic_source_n"]:
            raise ValueError("Changed full public Civic overall weights")
        modeled, nonmodeled = total * (voter / weight), total * (nonvoter / weight)
        if abs(modeled + nonmodeled - total) > Decimal("1e-60"):
            raise ValueError("Conditional dated-register partition failed")
    time = "Native November2026 report prepared11/3/2026; registration cutoff/timezone/status unspecified"
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="OR", year=2026, geographic_level="state", geography="Oregon monthly registration",
        source_family=URL, measure=MEASURE, native_measure="Explicit monthly county Total, corroborated by legislative parents",
        numerator=None, denominator=total, denominator_basis=BASIS, denominator_label="Native monthly registration stock; active/inactive status unspecified",
        source_time_label=time, source_url=URL, native_status="Monthly administrative register, not counting/certification",
        source_kind="reviewed_public_monthly_registration_pdf",
        scope_notes="Prepared date is not registration cutoff. All7pages preserved; repeated county/congressional/senate/house margins counted once. No group/local survey allocation or population validation.",
        selected_state_reference=False, disposition="additional_dated_register_scenario_existing_primary_preserved")
    controls.append(control)
    context_control = dict(control)
    context_control.update(id=HELD, source_family=RETURN_URL, source_url=RETURN_URL,
        measure="held_unofficial_returned_envelopes_not_formal_analysis_input",
        native_measure="Ballot envelopes marked as returned; not accepted/counted/unique voters",
        numerator=2028213, denominator=3117439, denominator_basis="native_active_snapshot_20261016_0700_timezone_unknown",
        denominator_label="Held source's October16 active snapshot, not monthly registration parent",
        source_time_label="ReportGenerated11/6/2026 3:36PM; active snapshot10/16/2026 7AM; timezone unknown",
        native_status="Unofficial; source warns against official reporting/certification/formal analysis",
        source_kind="held_context_original_not_model_control",
        scope_notes="Explicit source formal-analysis warning respected: no model/calibration/ballot comparison/rate. Legacy fine-cell blank-to-zero transformations not reused.",
        disposition="held_source_formal_analysis_warning_no_numerical_use")
    controls.append(context_control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="OR", control_id=CONTROL, control_measure=MEASURE,
        control_native_status=control["native_status"], native_registered_denominator=total,
        native_denominator_basis=BASIS, source_time_label=time, source_url=URL,
        civic_source_n=source["n"], civic_weight=source["weight"],
        civic_modeled_voter_weight=source["modeled_voter_weight"], civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
        conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
        reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
        assumption="dated monthly registration stock is exchangeable with statewide source-weighted Civic propensity; unvalidated, not current population or held returned-envelope calibration",
        scenario_units="native_monthly_registration_units_not_administratively_observed_people")
    scenarios.append(scenario)
    comparisons = []
    for identity, measure, count, registered, clock, used in (
        (state["control_id"], state["control_measure"], state["control_native_numerator"], state["control_registered_denominator"], state["control_native_time"], False),
        (CONTROL, MEASURE, None, total, time, True),
        (HELD, context_control["measure"], 2028213, 3117439, context_control["source_time_label"], False),
    ):
        comparisons.append(dict(source_record_id=identity, native_measure=measure, native_numerator=count,
            native_registration_count=registered, native_time=clock,
            used_for_new_conditional_model=used, source_formal_analysis_warning=identity == HELD,
            model_participant_units=str(modeled) if used else None,
            model_nonparticipant_units=str(nonmodeled) if used else None,
            native_numerator_comparison_approved=False, native_minus_model=None,
            same_population_and_cutoff_qualified=False, observed_staying_home=None))
    qualification = dict(native_monthly_registration_parent=total, native_prepared_date="11/3/2026",
        native_registration_cutoff=None, native_timezone=None, active_inactive_status_qualified=False,
        preparation_date_not_promoted_to_registration_cutoff=True, all_seven_pages_and_native_count_zeros_preserved=True,
        missing_imputed_zero=False, repeated_geographic_margins_counted_once=True,
        prior_primary_state_rows_byte_identical=True, prior_37_controls_and_26_scenarios_preserved=True,
        held_return_context=held, held_return_report_used_for_new_model=False,
        legacy_fine_cell_blank_to_zero_parser_not_reused=True,
        native_accounting_checks=diagnostics, native_accounting_discrepancies=[row for row in diagnostics if row["difference"]],
        group_registration_or_monthly_change_not_group_turnout_or_first_time_registration=True,
        matched_party_denominators_qualified=False, source_population_transport_validated=False,
        native_statewide_ballots=None, native_minus_model=None, observed_staying_home=None,
        group_or_local_survey_allocation=False, design_confidence_interval=None,
        rates_approved=False, maps_approved=False, counting_completion_approved=False, certification_approved=False)
    return {
        "complete-state-control-query.csv": state_bytes,
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-native-registration-accounting.csv": csv_bytes(accounting),
        "complete-oregon-source-frame-comparison.csv": csv_bytes(comparisons),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=39, conditional_scenarios=27,
            additional_dated_registration_scenarios=1, held_return_contexts_added=1,
            monthly_registration_parent=total, native_accounting_slots=len(accounting),
            native_accounting_equations=len(diagnostics),
            native_accounting_discrepancies=len(qualification["native_accounting_discrepancies"]),
            all_prior_state_rows_controls_scenarios_unchanged=True, no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "complete-oregon-monthly-native-inputs.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("oregon_monthly_register.py", "extract_oregon_monthly_register.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_oregon_monthly_register.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "Oregon monthly registration stock: native Total 3,112,307, prepared November 3, 2026.\n"
        "Preparation is not an independently qualified registration cutoff; status/timezone unknown.\n"
        "Seven complete pages preserve county/monthly comparisons, congressional fragments,\n"
        "Senate/representative districts, explicit zero counts and all repeated parents counted once.\n"
        "Conditional statewide source-register units assume unvalidated Civic exchangeability.\n"
        "Existing November 7 Oregon primary reference and every earlier query/scenario are unchanged.\n"
        "The separate returned-envelope report warns against formal analysis: held context ONLY.\n"
        "No model/calibration uses its October 16 active snapshot or returned-envelope counts.\n"
        "Returned is not accepted/counted/cast/unique voters; no matched group rates, population\n"
        "validation, staying-home, first-time-registration inference, local allocation or fake intervals.\n"
        "Legacy fine-cell blank-to-zero transformations are not reused. Original PDFs/complete frozen\n"
        "independent views/receipts/baseline/code/tests/allqueries/checksums are included.\n"
        "python3 -m unittest discover -s tests -p test_oregon_monthly_register.py\n"
        "python3 -m scripts.oregon_monthly_register --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
                                     for name, body in sorted(files.items())})
    output.mkdir(parents=True)
    for name, body in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, body in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, body)
    print(files["summary.json"].decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
