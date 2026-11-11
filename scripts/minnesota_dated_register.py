"""Use registered counts only; keep preregistration and partial turnout separate."""

import argparse
import csv
from decimal import Decimal, localcontext
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import zipfile

from .washington_register_control import civic_source, csv_bytes, encoded


BASELINE_SHA = "b464688086fa16bbde73381932f414f459779efe4c3c509e8216515de226db03"
NATIVE_SHA = "ae0240076fad61d53e6664193f4ffeb1275aa3b803d88db033113e684d86e109"
URL = "https://www.sos.mn.gov/election-administration-campaigns/data-maps/voter-registration-counts/"
CONTROL = "mn-2026-native-registered-only-snapshot-20261102"
MEASURE = "native_dated_registered_voters_preregistered_excluded"
BASIS = "native_Registered_Voters_TOTAL_asof20261102_excluding_separate_PreRegistered_16_17"


class TableReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.cell = [], None, None
        self.caption_parts, self.in_caption = [], False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
        elif tag == "caption":
            self.in_caption = True

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)
        if self.in_caption:
            self.caption_parts.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "caption":
            self.in_caption = False


def registration_frame(body, independent, scope):
    reader = TableReader()
    reader.feed(body.decode())
    caption = " ".join("".join(reader.caption_parts).split())
    if caption != "Voter Counts by County as of November 2, 2026" or scope["native_snapshot_date"] != "2026-11-02":
        raise ValueError("Changed native snapshot caption/date; not workbook or retrieval date")
    if dict(caption=caption, rows=reader.rows) != independent:
        raise ValueError("Independent complete native HTML readers disagree")
    if (scope["preregistered_source_ages"] != [16, 17] or scope["source_activation_age"] != 18
            or scope["preregistered_excluded_from_model_denominator"] is not True
            or scope["active_inactive_status_qualified"] is not False):
        raise ValueError("Changed registered/preregistered universe qualification")
    rows = reader.rows
    if rows[0] != ["County", "Registered Voters", "Pre-Registered Voters"]:
        raise ValueError("Changed registered and preregistered column identity")
    if len(rows) != 89 or any(len(row) != 3 for row in rows):
        raise ValueError("Incomplete native 87-county plus TOTAL table")
    labels = [row[0] for row in rows[1:]]
    if len(set(labels)) != 88 or labels.count("TOTAL") != 1:
        raise ValueError("Missing or duplicate native county/explicit TOTAL")
    counts, accounting = {}, []
    for number, row in enumerate(rows[1:], 2):
        values = []
        for column, literal in zip(rows[0][1:], row[1:]):
            if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)", literal):
                raise ValueError("Missing explicit native count; no zero or county-sum fallback")
            value = int(literal.replace(",", ""))
            values.append(value)
            accounting.append(dict(source_row=number, county_literal=row[0], population_label=column,
                raw_native_count=literal, native_count=value, missing_imputed_zero=False,
                used_for_model_denominator=column == "Registered Voters"))
        counts[row[0]] = values
    if counts["TOTAL"][0] <= 0:
        raise ValueError("Missing positive explicit Registered Voters TOTAL")
    diagnostics = []
    for index, label in enumerate(rows[0][1:]):
        subtotal = sum(values[index] for county, values in counts.items() if county != "TOTAL")
        diagnostics.append(dict(population_label=label, native_parent=counts["TOTAL"][index],
                                observed_county_sum=subtotal, difference=subtotal - counts["TOTAL"][index]))
    return counts["TOTAL"][0], counts["TOTAL"][1], accounting, diagnostics


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "complete-minnesota-dated-native-inputs.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted version22 baseline or sufficient native inputs")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        sums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(sums) | {"checksums.json"}:
            raise ValueError("Changed complete native input inventory")
        for name, metadata in sums.items():
            body = archive.read(name)
            if len(body) != metadata["bytes"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient factual input")
        total, preregistered, accounting, diagnostics = registration_frame(
            archive.read("native-table.html"), json.loads(archive.read("independent-table.json")),
            json.loads(archive.read("source-scope.json")))
        held = json.loads(archive.read("montana-test-observation.json"))
        if held["native_test_marker"] != "TEST" or held["numerical_model_input_qualified"] is not False:
            raise ValueError("Test-labelled Montana source must not become administrative evidence")
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 40, 28):
        raise ValueError("Changed complete version22 coverage")
    target = next(row for row in states if row["state_code"] == "MN")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate a selected Minnesota frame")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "MN" and row["dimension"] == "overall")
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or min(voter, nonvoter) < 0 or voter + nonvoter != weight or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state weights")
        modeled, nonmodeled = total * (voter / weight), total * (nonvoter / weight)
        if abs(modeled + nonmodeled - total) > Decimal("1e-60"):
            raise ValueError("Conditional registered-only partition failed")
    time = "Native county table asofNovember2,2026; exact clock/timezone and active/inactive status unspecified"
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=None,
        control_registered_denominator=total, control_denominator_basis=BASIS,
        control_native_time=time, control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="MN", year=2026, geographic_level="state", geography="Minnesota dated registered-only count",
        source_family=URL, measure=MEASURE, native_measure="Explicit Registered Voters TOTAL, excluding separate Pre-Registered Voters",
        numerator=None, denominator=total, denominator_basis=BASIS, denominator_label="Dated registered-only source total; not combined with pre-registered 16/17-year-olds",
        source_time_label=time, source_url=URL, native_status="Administrative registration snapshot, not election counting/certification",
        source_kind="reviewed_public_official_typed_registration_table",
        scope_notes="All87counties+TOTAL/267cells/176countslots preserved. PreRegistered94621 excluded, not added/age-projected. No legal-eligibility certification, model population validation or local allocation; old partial result observation unchanged.",
        selected_state_reference=False, disposition="dated_registered_only_frame_not_election_time_population_or_ballot_reference")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="MN", control_id=CONTROL, control_measure=MEASURE,
        control_native_status=control["native_status"], native_registered_denominator=total,
        native_denominator_basis=BASIS, source_time_label=time, source_url=URL,
        civic_source_n=source["n"], civic_weight=source["weight"],
        civic_modeled_voter_weight=source["modeled_voter_weight"], civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
        conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
        reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
        assumption="dated registered-only source frame exchangeable with statewide Civic propensity; unvalidated, excludes preregistered adolescents and not election-time or legal-eligibility certification",
        scenario_units="native_dated_registered_only_units_not_administratively_observed_people")
    scenarios.append(scenario)
    qualification = dict(native_snapshot_date="2026-11-02", native_registered_parent=total,
        native_preregistered_parent_excluded=preregistered, native_preregistered_ages=[16, 17],
        preregistered_not_added_or_age_projected_into_model=True, source_activation_age=18,
        native_time=None, native_timezone=None, active_inactive_status_qualified=False,
        independent_legal_eligibility_certification=False, all267_native_cells_and176_counts_preserved=True,
        missing_imputed_zero=False, native_county_codes_not_inferred_fips=True,
        source_population_transport_validated=False, old_partial_election_observation_unchanged=True,
        native_accounting_checks=diagnostics, native_accounting_discrepancies=[row for row in diagnostics if row["difference"]],
        native_statewide_ballots=None, native_minus_model=None, observed_staying_home=None,
        group_or_local_survey_allocation=False, design_confidence_interval=None,
        rates_approved=False, maps_approved=False, counting_completion_approved=False, certification_approved=False,
        montana_results_test_banner_observed=True, montana_results_counts_used_for_model=False,
        montana_registration_403_route_stays_stopped=True,
        full_index_app_code_contacts_session_forms_and_test_counts_not_redistributed=True)
    frame = dict(state_code="MN", native_snapshot_date="2026-11-02", native_registered_parent=total,
        native_preregistered_parent_excluded=preregistered,
        conditional_model_participant_units=str(modeled), conditional_model_nonparticipant_units=str(nonmodeled),
        ballots_linked_to_dated_frame=None, native_minus_model=None, observed_staying_home=None,
        preregistered_added_to_model=False, rate_approved=False, map_approved=False)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-native-registered-preregistered-accounting.csv": csv_bytes(accounting),
        "complete-minnesota-registered-only-frame.csv": csv_bytes([frame]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=41, conditional_scenarios=29,
            native_registered_parent=total, native_preregistered_excluded=preregistered,
            native_raw_cells=267, native_count_slots=176, native_county_rows=87,
            native_accounting_discrepancies=len(qualification["native_accounting_discrepancies"]),
            all50_other_states_40_prior_controls_28_scenarios_preserved=True,
            no_montana_test_counts_selected=True, no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "complete-minnesota-dated-native-inputs.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("minnesota_dated_register.py", "extract_minnesota_dated_register.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_minnesota_dated_register.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "Minnesota native registered-only TOTAL3,927,036 as of November2,2026.\n"
        "Separate PreRegistered94,621 (sourceages16/17) is NOTadded or age-projected into modelR.\n"
        "All87counties+TOTAL/267cells/176counts preserved with independent HTML parsers.\n"
        "SnapshotDATE is explicit; exacttime/TZ/status/independentlegaleligibility unknown.\n"
        "Conditional statewide source-register units assume unvalidated Civic exchangeability.\n"
        "No observedpeople/stayinghome/nativeballots/residual/group/localallocation/fakeCI/rate/map.\n"
        "Old partial MN election observation and all prior controls/scenarios remain untouched.\n"
        "MTdistinctresults page200 hasvisibleTESTbanner: no testcount becomes administrative evidence.\n"
        "MTdeniedregistrationroute staysstopped. No testcounts/appcode/contacts/sessionforms redistributed.\n"
        "Complete factualtable/independentview/age-datefacts/receipts/baseline/code/tests/allqueries/checksums.\n"
        "python3 -m unittest discover -s tests -p test_minnesota_dated_register.py\n"
        "python3 -m scripts.minnesota_dated_register --inputs inputs --output reproduced\n").encode()
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
