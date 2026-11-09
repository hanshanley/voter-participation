"""Keep Maryland's dated registers, unofficial cards and model transport separate."""

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

from .extract_maryland_election_frames import COLUMNS, read_cards, read_workbook
from .washington_register_control import csv_bytes, encoded


BASELINE_SHA = "92b66d3881d87b2742309eeec5d0bdd176170ba4e4b64f87cda580ec964b42bb"
NATIVE_SHA = "ea2c98e95e8e708042ae83292f2c07eacd680fa7065ae2be8f6f2ea109027521"
CONTROL = "md-2026-general-oct18-eligible-active-precinct-register"
URL = "https://elections.maryland.gov/press_room/2026_stats/GG26/Eligible%20Active%20Voters%20by%20County%20-%20GG26.xlsx"


def number(value):
    if value is None:
        return None
    with localcontext() as context:
        context.prec = 80
        return str(Decimal(value.numerator) / value.denominator)


def queries(grids, cards, scope):
    if (scope["election_date"] != "2026-11-03" or scope["register_as_of"] != "2026-10-18"
            or scope["card_report_timezone"] is not None
            or scope["registry_frame_transport_validated"] is not False
            or scope["cards_not_certified_unique_voters"] is not True
            or scope["card_report_unofficial"] is not True
            or scope["full_ballot_canvass_certified"] is not False
            or scope["registration_party_counts_not_participation_by_party"] is not True
            or scope["active_and_inactive_kept_separate"] is not True
            or scope["group_or_county_model_allocation"] is not False
            or scope["reporting_counters_not_precinct_records"] is not True):
        raise ValueError("Keep dated registers, unofficial cards, unknown timezone and unvalidated transport separate")
    if cards["run_date"] != scope["card_report_native_run_date"] or cards["run_time"] != scope["card_report_native_run_time"]:
        raise ValueError("Changed native card-report clock; never substitute retrieval time")
    stocks, accounting = [], []
    for status in ("ACTIVE", "INACTIVE"):
        grid = grids[status]
        rows = grid["rows"]
        if (len(rows) != 25 or rows[-1]["native_county_label"] != "TOTAL"
                or len({r["native_county_label"] for r in rows}) != 25):
            raise ValueError("Incomplete or duplicate county/register-parent coverage")
        if (grid["date_label"] != "Election Date: November 3, 2026\n**As of October 18, 2026"
                or grid["election"] != "Election: 2026 Gubernatorial General Election"
                or grid["status"] != status):
            raise ValueError("Changed dated native register or general-election identity")
        for row in rows:
            if set(row["counts"]) != set(COLUMNS):
                raise ValueError("Incomplete native registration-party inventory")
            for party, value in row["counts"].items():
                if type(value) is not int or value < 0:
                    raise ValueError("Missing or invalid native count; never impute zero")
                total = row["counts"]["TOTAL"]
                share = Fraction(100 * value, total) if total > 0 else None
                stocks.append(dict(status=status, native_county_label=row["native_county_label"],
                    source_file=grid["source_file"], source_cell=row["source_cells"][party],
                    native_party_label=party, native_count=value, native_total=total,
                    source_register_share_pct=number(share), register_as_of=scope["register_as_of"],
                    registration_party_not_vote_choice=True, participation_by_party_available=False,
                    model_allocated=False, unknown_imputed_zero=False))
            parts = sum(row["counts"][key] for key in COLUMNS if key != "TOTAL")
            accounting.append(dict(status=status, partition="registration_party",
                native_parent_label=row["native_county_label"], source_measure="TOTAL",
                derived_component_sum=parts, printed_parent=row["counts"]["TOTAL"],
                derived_minus_printed=parts - row["counts"]["TOTAL"]))
        for party in COLUMNS:
            total = sum(row["counts"][party] for row in rows[:-1])
            parent = rows[-1]["counts"][party]
            accounting.append(dict(status=status, partition="county",
                native_parent_label="TOTAL", source_measure=party,
                derived_component_sum=total, printed_parent=parent, derived_minus_printed=total - parent))
    active = {r["native_county_label"]: r["counts"]["TOTAL"] for r in grids["ACTIVE"]["rows"]}
    if [r["native_county_label"] for r in grids["ACTIVE"]["rows"]] != [
            r["native_county_label"] for r in grids["INACTIVE"]["rows"]]:
        raise ValueError("Different native active/inactive county coverage")
    card_rows = cards["rows"]
    if (len(card_rows) != 25 or card_rows[-1]["native_county_label"] != "Total"
            or len({r["native_county_label"] for r in card_rows}) != 25):
        raise ValueError("Incomplete or duplicate card-report county coverage")
    references = []
    for row in card_rows:
        label = row["native_county_label"]
        key = "TOTAL" if label == "Total" else label if label in active else label.removesuffix(" County")
        if key not in active:
            raise ValueError("Unmatched native card county; never guess a geography")
        for field in ("native_cards_cast", "native_eligible_voters"):
            if not isinstance(row[field], str) or not re.fullmatch(r"\d{1,3}(?:,\d{3})*|\d+", row[field]):
                raise ValueError("Missing or invalid native card-reference count")
        if not re.fullmatch(r"\d+\.\d{2}%", row["native_percentage"]):
            raise ValueError("Changed native two-decimal reference percentage")
        count, eligible = (int(row[key].replace(",", "")) for key in ("native_cards_cast", "native_eligible_voters"))
        exact = Fraction(100 * count, eligible) if eligible > 0 else None
        difference = Fraction(row["native_percentage"][:-1]) - exact if exact is not None else None
        references.append(dict(**row, native_register_county_label=key,
            source_cards_cast=count, source_eligible_voters=eligible,
            register_active_reference=active[key], eligible_minus_active=eligible - active[key],
            source_cards_per_eligible_reference_pct=number(exact),
            printed_minus_reference_percentage_points=number(difference),
            two_decimal_rounding_compatible=abs(difference) <= Fraction(1, 200) if difference is not None else None,
            native_run_date=cards["run_date"], native_run_time=cards["run_time"], timezone=None,
            source_reporting_units_not_precinct_records=True, unique_voters_certified=False,
            final_turnout_certified=False, registration_status_of_cards_known=False,
            registration_party_participation_available=False, model_allocated=False))
    for key in ("source_cards_cast", "source_eligible_voters"):
        total, parent = sum(r[key] for r in references[:-1]), references[-1][key]
        accounting.append(dict(status="CARDS_CONTEXT", partition="county",
            native_parent_label="Total", source_measure=key, derived_component_sum=total,
            printed_parent=parent, derived_minus_printed=total - parent))
    return stocks, references, accounting


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "complete-maryland-election-native-inputs.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete native27 baseline or sufficient native inputs")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        checksums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(checksums) | {"checksums.json"}:
            raise ValueError("Changed sufficient native input inventory")
        for name, metadata in checksums.items():
            raw = archive.read(name)
            if hashlib.sha256(raw).hexdigest() != metadata["sha256"] or len(raw) != metadata["bytes"]:
                raise ValueError("Changed sufficient native input bytes")
        originals = {"general-eligible-active.xlsx": "dbfff2b394a662495677de461ae6abe7954e2077085a2e53ac9791ac8bbd2685",
            "general-eligible-inactive.xlsx": "49ca88279c3090cede0f08f2f80baba850842241210c76d4f6f02c1edb675106",
            "general-election-night-turnout.pdf": "f4ac1aa87b06fbde98ebf0114338ef4c1155d3bf34bb7c5a797ec6a5170f5029"}
        if any(hashlib.sha256(archive.read(name)).hexdigest() != digest for name, digest in originals.items()):
            raise ValueError("Changed original election-statistics product")
        grids = {status: read_workbook(archive.read("general-eligible-" + status.lower() + ".xlsx"), status)
                 for status in ("ACTIVE", "INACTIVE")}
        cards = read_cards(archive.read("general-election-night-turnout.pdf"))
        if (grids != json.loads(archive.read("independent-workbook-grids.json"))
                or cards != json.loads(archive.read("independent-card-grid.json"))):
            raise ValueError("Independent XML/coordinate and production native readings disagree")
        scope = json.loads(archive.read("source-scope.json"))
        stocks, references, accounting = queries(grids, cards, scope)
        source = json.loads(archive.read("accepted-civic-maryland-parent.json"))
    if any(r["derived_minus_printed"] for r in accounting) or any(r["eligible_minus_active"] for r in references):
        raise ValueError("Native discrepancy retained; review before selecting a source-frame scenario")
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 51, 33):
        raise ValueError("Changed native27 complete coverage")
    target = next(r for r in states if r["state_code"] == "MD")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate a prior Maryland source-register scenario")
    total = grids["ACTIVE"]["rows"][-1]["counts"]["TOTAL"]
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in
                                  ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if (weight <= 0 or min(voter, nonvoter) < 0 or voter + nonvoter != weight
                or str(source["n"]) != target["civic_source_n"] or source["scope"] != "MD"
                or source["dimension"] != "overall"):
            raise ValueError("Changed full accepted Civic state parent")
        modeled, nonmodeled = total * (voter / weight), total * (nonvoter / weight)
        if abs(modeled + nonmodeled - total) > Decimal("1e-60"):
            raise ValueError("Conditional source-register partition failed")
    time = "register as of October18,2026; November3 General; paired UNOFFICIAL card report run November8,2026 7:44pm; timezone unspecified"
    basis = "printed_statewide_eligible_ACTIVE_precinct_register_asof_2026-10-18_same_agency24_county_corroboration"
    measure = "native_general_eligible_active_register_frame_only_cards_context_separate"
    target.update(control_id=CONTROL, control_measure=measure, control_native_numerator=None,
        control_registered_denominator=total, control_denominator_basis=basis,
        control_native_time=time, control_source_url=URL,
        conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="MD", year=2026, geographic_level="state",
        geography="Maryland statewide", source_family=URL, measure=measure,
        native_measure="Eligible Active Voters on the Precinct Register; printed statewide TOTAL",
        numerator=None, denominator=total, denominator_basis=basis,
        denominator_label="Eligible ACTIVE precinct register as of October18; inactive283680 separate; not election-time total",
        source_time_label=time, source_url=URL,
        native_status="Published general-election roster; paired card report UNOFFICIAL, not certification",
        source_kind="reviewed_official_aggregate_election_register_workbook",
        scope_notes="All24county/state register rows and native registration-party stocks retained. No participation-by-party joint. Cards Cast is not certified unique voters/ballots, includes native MIB2 title despite index/filename. Same-agency corroboration not independent population validation. No inactive/SDR addition, residual staying-home inference, local/group model allocation or eligibility certification.",
        selected_state_reference=False, disposition="active_register_unvalidated_dated_source_frame_transport_cards_separate")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="MD", control_id=CONTROL, control_measure=measure,
        control_native_status="October18,2026 eligible ACTIVE roster, not election-time all-status population",
        native_registered_denominator=total, native_denominator_basis=basis,
        source_time_label=time, source_url=URL, civic_source_n=source["n"],
        civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
        civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
        conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
        reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
        assumption="Unchanged2026 General Civic propensity transported to October18 ACTIVE roster; date/status/registry-frame exchangeability UNVALIDATED; cards not used for fitting or unique-voter validation",
        scenario_units="native_oct18_active_register_units_not_observed_election_people")
    scenarios.append(scenario)
    qualification = dict(native_control_version=28, register_as_of="2026-10-18",
        native_active_register=total, native_inactive_register=grids["INACTIVE"]["rows"][-1]["counts"]["TOTAL"],
        source_cards_cast=references[-1]["source_cards_cast"], native_source_reference_pct=references[-1]["native_percentage"],
        card_report_native_run_date=cards["run_date"], card_report_native_run_time=cards["run_time"], timezone=None,
        source_card_title=cards["title"], source_coverage_includes_named_MIB2=True,
        source_card_count_not_certified_unique_voters_or_ballots=True, card_report_unofficial=True,
        full_ballot_canvass_certified=False, active_frame_transport_validated=False,
        registration_party_counts_not_participation_by_party=True, inactive_and_SDR_not_added=True,
        same_agency_cross_product_match_not_independent_population_validation=True,
        no_source_reporting_unit_records_or_precinct_map=True, no_group_or_local_model_allocation=True,
        no_card_minus_model_or_staying_home_residual=True, design_confidence_interval=None,
        rates_approved=False, maps_approved=False, new_website_view=False,
        all50_other_states_51_controls_33_scenarios_preserved=True,
        stopped_October_monthly_report_not_retried=True)
    return {"complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-maryland-register-stocks.csv": csv_bytes(stocks),
        "complete-maryland-card-references.csv": csv_bytes(references),
        "complete-maryland-native-accounting.csv": csv_bytes(accounting),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=52, conditional_scenarios=34,
            register_stock_queries=len(stocks), card_reference_queries=len(references),
            native_accounting_queries=len(accounting), native_active_register=total,
            native_inactive_register=qualification["native_inactive_register"],
            source_cards_cast=qualification["source_cards_cast"], native_reference_percentage="48.44%",
            conditional_model_participant_source_units=str(modeled),
            conditional_model_nonparticipant_source_units=str(nonmodeled),
            source_reporting_units_not_precinct_records=True, full_ballot_canvass_certified=False,
            all50_other_states_51_controls_33_scenarios_preserved=True))}


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "complete-maryland-election-native-inputs.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("maryland_election_frames.py", "extract_maryland_election_frames.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_maryland_election_frames.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["requirements.txt"] = b"openpyxl==3.1.5\npdfplumber==0.11.8\n"
    files["README.txt"] = (
        "Maryland2026: Oct18 ACTIVE4293322 and INACTIVE283680 registers remain SEPARATE.\n"
        "Native UNOFFICIAL Cards Cast2079801 / eligible ACTIVE4293322; displayed48.44%.\n"
        "Run11/8/2026 7:44pm, timezone unspecified; header names MIB1/early/electionday/MIB2.\n"
        "Index/filename is NOT the actual report cutoff or proof of final canvass.\n"
        "Cards are NOTcertified unique voters/ballots. County reporting counters are NOT precinct records.\n"
        "All350 registration-stock cells,25 card references,66 accounting rows and all51 state queries included.\n"
        "Native party labels describe registration, NOT vote choice or participation by party.\n"
        "One statewide unchanged Civic p x ACTIVE reference scenario has UNVALIDATED frame transport.\n"
        "No inactive/SDR addition, party/local model allocation, legal eligibility, fakeCI or staying-home residual.\n"
        "All50other states/51prior controls/33scenarios preserved; stopped October monthly PDF not retried.\n"
        "Complete native originals, safe receipts, independent grids, accepted Civic parent, baseline27, code/tests/results.\n"
        "python3 -m unittest discover -s tests -p test_maryland_election_frames.py\n"
        "python3 -m scripts.maryland_election_frames --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
        for name, value in sorted(files.items())})
    output.mkdir(parents=True)
    for name, value in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, value in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, value)
    print(files["summary.json"].decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
