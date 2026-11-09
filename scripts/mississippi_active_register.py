"""Separate an October active-registration frame from observed election participation."""

import argparse
import csv
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from .extract_mississippi_active_register import read_pdf
from .washington_register_control import civic_source, csv_bytes, encoded


BASELINE_SHA = "32d68a849e97d834272e3813a736c2bdbb2157bfe3d62e960d7195acd643772e"
NATIVE_SHA = "bcdeef5c5c1f84f8885c802e15e44e8e9e187fe7b8c3b4dbbf9eea44610afd5b"
URL = "https://www.sos.ms.gov/sites/default/files/active-voter-count-reports/2026October%20Voter%20Count%20Red.pdf"
CONTROL = "ms-2026-october-active-register-all82-county-sum"


def number(value):
    with localcontext() as context:
        context.prec = 80
        return str(Decimal(value.numerator) / value.denominator)


def registration_frame(grid, independent, scope):
    if (scope["report_month"] != "2026-10" or scope["native_registration_status"] != "ACTIVE"
            or scope["exact_registration_cutoff_date"] is not None
            or scope["printed_statewide_total_present"] is not False
            or scope["registration_frame_transport_validated"] is not False
            or scope["cvap_not_used_as_model_denominator"] is not True
            or scope["native_percentages_not_turnout"] is not True):
        raise ValueError("Keep October active scope, unknown cutoff, derived sum and unvalidated transport separate")
    if (grid["pages"] != 3 or grid["headers"] != independent["headers"]
            or grid["pages"] != independent["pages"] or grid["rows"] != independent["rows"]):
        raise ValueError("Independent complete native rows or column meanings disagree")
    rows = grid["rows"]
    if (len(rows) != 82 or [row["native_county_label"][:2] for row in rows] !=
            [f"{i:02}" for i in range(1, 83)] or len({row["native_county_label"] for row in rows}) != 82):
        raise ValueError("Incomplete or duplicate native 82-county coverage")
    contexts, percentages = [], []

    def count(value):
        if value is None:
            return None
        if not isinstance(value, str) or not re.fullmatch(r"\d+", value):
            raise ValueError("Invalid literal count; no coercion, imputation or renormalization")
        return int(value)

    for row in rows:
        active, cvap = (count(row[field]) for field in ("native_active_voters", "native_cvap_estimate"))
        raw = row["native_percentage"]
        if raw is not None and (not isinstance(raw, str) or not re.fullmatch(r"\d+\.\d{3}%", raw)):
            raise ValueError("Changed native three-decimal percentage")
        displayed = Fraction(raw[:-1]) if raw is not None else None
        exact = Fraction(active * 100, cvap) if active is not None and cvap is not None and cvap > 0 else None
        difference = displayed - exact if displayed is not None and exact is not None else None
        asterisk = row["native_county_label"].endswith("*")
        contexts.append(dict(**row, native_active_count=active, native_cvap_count=cvap,
            native_cvap_asterisk=asterisk,
            native_cvap_source_basis="2020_Census_CVAP" if asterisk else "2023_ACS_5year_CVAP",
            report_month="2026-10", exact_registration_cutoff_date=None, exact_clock=None, timezone=None,
            registration_status="ACTIVE", missing_imputed_zero=False,
            cvap_used_as_model_denominator=False, percentage_is_turnout=False,
            independent_legal_eligibility_certification=False, county_model_allocated=False))
        percentages.append(dict(native_county_label=row["native_county_label"], source_page=row["page"],
            source_percentage=raw, exact_active_per_source_cvap_pct=number(exact) if exact is not None else None,
            source_display_minus_exact_percentage_points=number(difference) if difference is not None else None,
            three_decimal_rounding_compatible=abs(difference) <= Fraction(1, 2000) if difference is not None else None,
            source_display_over100=displayed > 100 if displayed is not None else None,
            clipped_or_repaired=False, percentage_is_turnout=False, design_confidence_interval=None))
    accounting = []
    for page in (1, 2, 3, None):
        selected = [row for row in contexts if page is None or row["page"] == page]
        for field in ("native_active_count", "native_cvap_count"):
            missing = sum(row[field] is None for row in selected)
            accounting.append(dict(scope="all82_counties" if page is None else "page" + str(page),
                source_measure=field, native_county_rows=len(selected), missing_count_slots=missing,
                derived_county_sum=sum(row[field] for row in selected) if not missing else None,
                complete=not missing, printed_parent=None, native_parent_discrepancy=None,
                derived_sum_not_printed_parent=True, missing_imputed_zero=False,
                used_as_model_denominator=field == "native_active_count" and page is None))
    total = next(row["derived_county_sum"] for row in accounting
                 if row["scope"] == "all82_counties" and row["source_measure"] == "native_active_count")
    return total, contexts, percentages, accounting


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "complete-mississippi-active-native-inputs.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete version26 baseline or sufficient native inputs")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        checksums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(checksums) | {"checksums.json"}:
            raise ValueError("Changed complete native input inventory")
        for name, metadata in checksums.items():
            value = archive.read(name)
            if len(value) != metadata["bytes"] or hashlib.sha256(value).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient factual input")
        total, contexts, percentages, accounting = registration_frame(
            read_pdf(archive.read("MS-2026-October-active-voter-count.pdf")),
            json.loads(archive.read("independent-pdf-rows.json")),
            json.loads(archive.read("source-scope.json")))
    if total is None or total <= 0:
        raise ValueError("No complete positive active frame; never replace unknown counts by zero")
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 50, 32):
        raise ValueError("Changed complete version26 coverage")
    target = next(row for row in states if row["state_code"] == "MS")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate a prior Mississippi source-register scenario")
    source = next(row for row in civic_source(baseline)["participation"]
                  if row["scope"] == "MS" and row["dimension"] == "overall")
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[field]) for field in
                                  ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or min(voter, nonvoter) < 0 or voter + nonvoter != weight or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state weights")
        modeled, nonmodeled = total * (voter / weight), total * (nonvoter / weight)
        if abs(modeled + nonmodeled - total) > Decimal("1e-60"):
            raise ValueError("Conditional source-register partition failed")
    time = "October2026 official index label; actual cutoff/day/clock/timezone unknown; NOTNovember election-time stock"
    basis = "derived_sum_all82_native_county_ACTIVE_counts_not_printed_statewide_parent_not_CVAP"
    measure = "native_october_active_register_county_sum_frame_only"
    target.update(control_id=CONTROL, control_measure=measure, control_native_numerator=None,
        control_registered_denominator=total, control_denominator_basis=basis,
        control_native_time=time, control_source_url=URL,
        conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="MS", year=2026, geographic_level="state",
        geography="Mississippi all82 source counties", source_family=URL, measure=measure,
        native_measure="Number of Active Voters; derived all82-county sum",
        numerator=None, denominator=total, denominator_basis=basis,
        denominator_label="October ACTIVE registrations, derived complete county sum; NOTCVAP or printed state parent",
        source_time_label=time, source_url=URL,
        native_status="Published monthly ACTIVE register, not general-election counting/certification",
        source_kind="reviewed_official_aggregate_county_register_pdf",
        scope_notes="All82 native county rows retained. State sum is DERIVED, not printed or independently benchmarked. CVAP mixes native2023ACS5year and13asterisk2020Census references; percentages are registration comparisons, NOTturnout or fraud/eligibility evidence. Active-stock transport unvalidated; no matched ballot residual, local/group allocation or legal/population certification.",
        selected_state_reference=False, disposition="active_register_unvalidated_dated_source_frame_transport")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="MS", control_id=CONTROL, control_measure=measure,
        control_native_status="October2026 ACTIVE county-sum register frame, not November election-time population",
        native_registered_denominator=total, native_denominator_basis=basis,
        source_time_label=time, source_url=URL, civic_source_n=source["n"],
        civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
        civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
        conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
        reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
        assumption="2026 General Civic source propensity transported to October ACTIVE register; date/status/registry-frame exchangeability UNVALIDATED; derived county sum, not November population, CVAP or legal-eligibility certification",
        scenario_units="native_october_active_register_units_not_observed_election_people")
    scenarios.append(scenario)
    frame = dict(state_code="MS", report_month="2026-10", exact_registration_cutoff_date=None,
        registration_status="ACTIVE", source_county_rows=82, derived_active_register=total,
        printed_statewide_total=None, aggregate_is_derived_not_printed=True,
        conditional_model_participant_units=str(modeled), conditional_model_nonparticipant_units=str(nonmodeled),
        active_register_transport_validated=False, cvap_used_as_denominator=False,
        native_general_ballots=None, native_minus_model=None, observed_staying_home=None,
        group_or_local_allocation=False, design_confidence_interval=None, rate_approved=False, map_approved=False)
    qualification = dict(report_month="2026-10", native_status="ACTIVE",
        exact_registration_cutoff_date=None, exact_clock=None, timezone=None,
        derived_all82_county_active_register=total, printed_statewide_total=None,
        aggregate_is_derived_not_printed_or_independently_benchmarked=True,
        native_pages=3, native_county_rows=82, native_factual_cells=328, native_count_cells=164,
        native_cvap_asterisk_counties=sum(row["native_cvap_asterisk"] for row in contexts),
        cvap_source_vintages_mixed=True, cvap_used_as_model_denominator=False,
        source_percentages_not_turnout_fraud_or_legal_eligibility_evidence=True,
        percentages_over100_preserved=sum(row["source_display_over100"] is True for row in percentages),
        native_percentage_rounding_disagreements=[row for row in percentages if row["three_decimal_rounding_compatible"] is False],
        active_registry_frame_transport_validated=False, missing_imputed_zero=False,
        native_general_ballots=None, native_minus_model=None, observed_staying_home=None,
        group_or_local_allocation=False, design_confidence_interval=None,
        rates_approved=False, maps_approved=False, new_website_view=False,
        all50_other_states_50_prior_controls_32_scenarios_preserved=True,
        illinois_http200_application_error_not403=True, new_hampshire_http403_route_stopped=True)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-mississippi-native-county-counts.csv": csv_bytes(contexts),
        "complete-mississippi-native-percent-diagnostics.csv": csv_bytes(percentages),
        "complete-mississippi-derived-accounting.csv": csv_bytes(accounting),
        "complete-mississippi-active-register-frame.csv": csv_bytes([frame]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=51, conditional_scenarios=33,
            native_county_rows=82, native_factual_cells=328, native_count_cells=164, native_percentage_cells=82,
            native_unknown_count_cells=sum(row[field] is None for row in contexts
                for field in ("native_active_count", "native_cvap_count")),
            native_observed_zero_count_cells=sum(row[field] == 0 for row in contexts
                for field in ("native_active_count", "native_cvap_count")),
            derived_all82_county_active_register=total, printed_statewide_total=None,
            native_cvap_asterisk_counties=qualification["native_cvap_asterisk_counties"],
            percentages_over100_preserved=qualification["percentages_over100_preserved"],
            native_percentage_rounding_disagreements=len(qualification["native_percentage_rounding_disagreements"]),
            all50_other_states_50_prior_controls_32_scenarios_preserved=True,
            no_observed_turnout_calibration_group_local_allocation_or_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "complete-mississippi-active-native-inputs.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("mississippi_active_register.py", "extract_mississippi_active_register.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_mississippi_active_register.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "October2026 Mississippi ACTIVE registrations: DERIVED sum of all82 county counts, NOT a printed statewide parent.\n"
        "Month comes from the exact official index label; cutoff/day/clock/timezone remain unknown.\n"
        "One conditional General Civic propensity xOctober ACTIVE register scenario is UNVALIDATED frame transport.\n"
        "Conditional source units are NOTobserved people, staying home, general ballots or legal-eligibility certification.\n"
        "All3pages/82native county rows/328factual cells/164counts/82percentages and13asterisks are preserved.\n"
        "CVAP mixes2023ACS5year and13asterisk2020Census references; NOTthe model denominator or turnout.\n"
        "Three source percentages over100 remain unclipped; not evidence of illegal voting or fraud.\n"
        "No missing-zero, partychoice, group/localallocation, fakeCI, linked ballot residual, rate/map/website view.\n"
        "IL200applicationerror is NOT403; NH403route stopped. No bypass/cache/mirror/guessedparameters or worldabsence.\n"
        "Complete originalPDF/independent coordinate cells/scope/receipts/baseline26/code/tests/everyquery/checksums.\n"
        "Requires existing pypdf; original sources/independent reductions are included, no network acquisition required.\n"
        "python3 -m unittest discover -s tests -p test_mississippi_active_register.py\n"
        "python3 -m scripts.mississippi_active_register --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
                                     for name, value in sorted(files.items())})
    output.mkdir(parents=True)
    for name, value in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, value in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, value)
    print(files["summary.json"].decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
