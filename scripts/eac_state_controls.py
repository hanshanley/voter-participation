"""Compare held EAC state reporting units and separate AP registration-frame scenarios."""

import argparse
import csv
from decimal import Decimal, localcontext
from fractions import Fraction
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile


YEARS = tuple(range(2004, 2025, 2))
STATES = tuple(sorted(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()))
PROVEN_STATE_UNITS = {
    ("AK", "0200000000", "ALASKA"), ("DC", "1100000000", "DISTRICT OF COLUMBIA"),
}
INPUTS = {
    "complete-methods.zip", "local-observations.csv.gz", "native-selections.json",
    "registration-selections.json", "definitions.json", "eac-timeseries-guide.docx",
    "ap-selected-aggregates.json", "2010-registration.xls", "2012-registration.xlsx",
    "earlier-timeseries.xlsx",
}
SCENARIO_FIELDS = (
    "year", "state_code", "study", "weight_field", "n", "positive_weight_n",
    "native_registration_denominator", "registration_basis", "native_active_registered",
    "native_inactive_registered", "source_weight", "source_modeled_voter_weight",
    "source_modeled_nonvoter_weight", "source_unknown_weight", "modeled_voter_share",
    "modeled_nonvoter_share", "model_unknown_share", "conditional_modeled_voter_count",
    "conditional_modeled_nonvoter_count", "conditional_model_unknown_count",
    "native_total_participation", "native_measure_disposition", "conditional_minus_native_participation",
    "conditional_diagnostic_is_independent_validation", "exchangeability_validated",
    "administrative_staying_home_observed", "geographic_allocation", "prior_cohort_count",
    "eligibility", "deaths", "migration", "source_url", "source_sha256", "source_retrieved_at",
    "native_weight_inference_status",
)
TIME_FIELDS = (
    "from_year", "to_year", "state_code", "prior_native_participation", "current_native_participation",
    "native_participation_count_difference", "disposition", "registration_definitions_harmonized",
    "individual_retention_or_switching_inferred", "eligibility", "deaths", "migration",
)


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def csv_bytes(rows, fields=None):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def native_count(value):
    if value is None:
        return None
    text = str(value).strip()
    return int(Decimal(text.replace(",", ""))) if re.fullmatch(
        r"[0-9]+(?:,[0-9]{3})*(?:\.0+)?", text) else None


def reported(row, field):
    flags = [value for key, value in row.items() if key.startswith(field + "_")
             and any(term in key for term in ("notavailable", "notapplicable", "validskip"))]
    if any(str(value or "").strip().lower() not in ("", "0", "0.0", "false", "no") for value in flags):
        return None
    return native_count(row.get(field))


def ratio(value):
    with localcontext() as context:
        context.prec = 60
        return format(Decimal(value.numerator) / Decimal(value.denominator), ".18f")


def instrument_rows(raw):
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    relation_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(node.itertext()) for node in ET.fromstring(
                archive.read("xl/sharedStrings.xml")).findall(namespace + "si")]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = next(node for node in workbook.find(namespace + "sheets")
                     if node.attrib["name"] == "Variables")
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(node.attrib["Target"] for node in relationships
                      if node.attrib["Id"] == sheet.attrib[relation_namespace + "id"])
        path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        rows = {}
        for node in ET.fromstring(archive.read(path)).find(namespace + "sheetData"):
            values = {}
            for cell in node:
                column = re.sub(r"\d+", "", cell.attrib["r"])
                value = cell.find(namespace + "v")
                if cell.attrib.get("t") == "s":
                    values[column] = strings[int(value.text)]
                elif cell.attrib.get("t") == "inlineStr":
                    values[column] = "".join(cell.find(namespace + "is").itertext())
                elif value is not None:
                    values[column] = value.text
            rows[int(node.attrib["r"])] = (values.get("A", "").lower(), values.get("C", ""))
        return rows


def validate_registration(row, definitions):
    if row["registered"] != reported(row["native_fields"], row["field"]):
        raise ValueError("Registration cache differs from native field and unavailable flags")
    for field, component in (("a1b", "active"), ("a1c", "inactive")):
        label = definitions.get(int(row["year"]), {}).get(field, "").lower()
        qualified = int(row["year"]) >= 2018 and re.search(r"\b" + component + r"\b", label)
        expected = reported(row["native_fields"], field) if qualified else None
        if row[component] != expected:
            raise ValueError("Registration component lacks matching native field definition")


def observation(source, local, registration, definitions):
    year = int(source["year"])
    fields = source["native_fields"]
    prefix = "qf1" if "qf1a" in fields else "f1"
    native = reported(fields, prefix + "a")
    if native != native_count(local["total_participation"]):
        raise ValueError("Native participation differs from frozen local observation")
    key = source["state_code"], source["jurisdiction_id"], source["jurisdiction"]
    proof = key in PROVEN_STATE_UNITS
    supplemental = local["supplemental_unit"] == "True"
    if supplemental:
        scope = "held_supplemental_uocava_only"
    elif not proof:
        scope = "held_state_label_without_qualified_full_electorate_scope"
    else:
        scope = "native_full_state_reporting_unit"
    reg = registration.get((year, *key))
    registered = reg["registered"] if reg else None
    if registered != native_count(local["registered"]):
        raise ValueError("Native registration differs from frozen local observation")
    active = reg.get("active") if reg else None
    inactive = reg.get("inactive") if reg else None
    if active is not None and inactive is not None and registered is not None:
        reg_accounting = "active_plus_inactive_reconciles" if active + inactive == registered else "native_difference_held"
    else:
        reg_accounting = "components_not_qualified"
    basis_fields = {key: value for key, value in fields.items() if key.startswith(("f2", "qf2"))}
    highest = reported(fields, "f2_4") == 1 or any(
        "highest office" in str(value).lower() or "highest-office" in str(value).lower()
        for value in basis_fields.values())
    if highest:
        measure = "held_highest_office_participation_proxy"
    elif supplemental:
        measure = "supplemental_uocava_participation"
    else:
        measure = "native_source_defined_participation_not_cast_ballots"
    qualified = proof and not supplemental and not highest and native is not None
    description = definitions.get(year, {})
    return dict(
        year=year, state_code=source["state_code"], jurisdiction_id=source["jurisdiction_id"],
        jurisdiction=source["jurisdiction"], native_total_participation=native,
        native_registered=registered, native_active_registered=active, native_inactive_registered=inactive,
        registration_accounting=reg_accounting, scope_disposition=scope, measure_disposition=measure,
        qualified_full_state_participation=qualified,
        reported_cast_ballots=None,
        native_participation_per_native_register_pct=(
            ratio(Fraction(100 * native, registered))
            if qualified and registered and native <= registered else None),
        ratio_is_eligible_or_harmonized_turnout=False,
        native_participation_field=prefix + "a", native_participation_definition=description.get("f1a", ""),
        native_registration_field=reg["field"] if reg else None,
        native_registration_definition=description.get("a1a", "") if reg else "",
        registration_basis=("native_total_including_active_inactive"
                            if reg_accounting == "active_plus_inactive_reconciles"
                            else "native_registration_field_frame_not_harmonized"),
        native_participation_basis=json.dumps(basis_fields, sort_keys=True),
        native_source_comments=local["source_details"], native_registration_comments=local["registration_comment"],
        registration_source_url=reg.get("source_url") if reg else None,
        registration_source_sha256=reg.get("source_sha256") if reg else None,
        registration_source_sheet=reg.get("source_sheet") if reg else None,
        registration_source_row=reg.get("source_row") if reg else None,
        source_url=source["source_url"], source_sha256=source["source_sha256"],
        source_sheet=source["source_sheet"], source_row=source["source_row"],
        source_retrieved_at=source["retrieved_at"], source_is_independent_survey_validation=False,
        county_or_precinct_allocation=False, eligibility=None, deaths=None, migration=None,
    )


def conditional(row, survey):
    weight, voter, nonvoter = (Fraction(survey[key])
                              for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
    unknown = Fraction(survey.get("model_unknown_weight", weight - voter - nonvoter))
    if weight <= 0 or min(voter, nonvoter, unknown) < 0 or voter + nonvoter + unknown != weight:
        raise ValueError("Unreconciled full survey mass")
    registered = row["native_registered"]
    return dict(
        year=int(survey["year"]), state_code=survey["scope"], study="AP VoteCast",
        weight_field=survey["weight_field"], n=survey["n"], positive_weight_n=survey["positive_weight_n"],
        native_registration_denominator=registered, registration_basis=row["registration_basis"],
        native_active_registered=row["native_active_registered"], native_inactive_registered=row["native_inactive_registered"],
        source_weight=survey["weight"], source_modeled_voter_weight=survey["modeled_voter_weight"],
        source_modeled_nonvoter_weight=survey["modeled_nonvoter_weight"], source_unknown_weight=str(unknown),
        modeled_voter_share=ratio(voter / weight), modeled_nonvoter_share=ratio(nonvoter / weight),
        model_unknown_share=ratio(unknown / weight),
        conditional_modeled_voter_count=ratio(registered * voter / weight),
        conditional_modeled_nonvoter_count=ratio(registered * nonvoter / weight),
        conditional_model_unknown_count=ratio(registered * unknown / weight),
        native_total_participation=row["native_total_participation"], native_measure_disposition=row["measure_disposition"],
        conditional_minus_native_participation=(
            ratio(registered * voter / weight - row["native_total_participation"])
            if row["qualified_full_state_participation"] else None),
        conditional_diagnostic_is_independent_validation=False, exchangeability_validated=False,
        administrative_staying_home_observed=False, geographic_allocation=False,
        prior_cohort_count=None, eligibility=None, deaths=None, migration=None,
        source_url=row["source_url"], source_sha256=row["source_sha256"],
        source_retrieved_at=row["source_retrieved_at"], native_weight_inference_status=survey["inference_status"],
    )


def build(observations, ap):
    by_state = {}
    for row in observations:
        key = int(row["year"]), row["state_code"]
        if key in by_state:
            raise ValueError("Ambiguous native statewide observation")
        if key[0] not in YEARS or key[1] not in STATES:
            raise ValueError("Unsupported native state/year")
        by_state[key] = row
    controls = []
    for year in YEARS:
        for state in STATES:
            source = by_state.get((year, state))
            selected = source and source["scope_disposition"] == "native_full_state_reporting_unit"
            controls.append(dict(
                year=year, state_code=state, native_observation_present=source is not None,
                source_reference_selected=bool(selected),
                disposition=source["scope_disposition"] if source else "no_qualified_native_state_reporting_row",
                native_total_participation=source["native_total_participation"] if source else None,
                native_registered=source["native_registered"] if source else None,
                native_active_registered=source["native_active_registered"] if source else None,
                native_inactive_registered=source["native_inactive_registered"] if source else None,
                native_measure_disposition=source["measure_disposition"] if source else None,
                qualified_full_state_participation=source["qualified_full_state_participation"] if source else False,
                reported_cast_ballots=None, county_or_precinct_allocation=False,
                source_url=source["source_url"] if source else None,
            ))
    scenarios, decisions = [], []
    for survey in ap["selected_rows"]:
        year = int(survey["year"])
        source = by_state.get((year, survey["scope"]))
        if survey["dimension"] != "overall" or survey["group"] != "all":
            disposition = "not_whole_state_overall"
        elif not survey["weight_field"].endswith("_STATE_WEIGHT"):
            disposition = "not_native_state_weight_frame"
        elif not source or source["scope_disposition"] != "native_full_state_reporting_unit":
            disposition = "no_qualified_native_full_state_register"
        elif int(survey["positive_weight_n"]) < 500:
            disposition = "source_support_hold"
        elif source["registration_accounting"] != "active_plus_inactive_reconciles":
            disposition = "native_register_component_accounting_not_qualified"
        else:
            disposition = "conditional_native_register_exchangeability_unvalidated"
            scenarios.append(conditional(source, survey))
        decisions.append(dict(
            year=year, scope=survey["scope"], dimension=survey["dimension"], group=survey["group"],
            weight_field=survey["weight_field"], disposition=disposition))
    changes = []
    for current in observations:
        prior = by_state.get((int(current["year"]) - 2, current["state_code"]))
        if not prior or (prior["jurisdiction_id"], prior["jurisdiction"]) != (
                current["jurisdiction_id"], current["jurisdiction"]):
            continue
        comparable = prior["qualified_full_state_participation"] and current["qualified_full_state_participation"]
        changes.append(dict(
            from_year=prior["year"], to_year=current["year"], state_code=current["state_code"],
            prior_native_participation=prior["native_total_participation"],
            current_native_participation=current["native_total_participation"],
            native_participation_count_difference=(current["native_total_participation"] - prior["native_total_participation"]
                                                   if comparable else None),
            disposition=("source_defined_snapshot_difference_not_harmonized" if comparable
                         else "held_scope_or_participation_proxy_endpoint"),
            registration_definitions_harmonized=False, individual_retention_or_switching_inferred=False,
            eligibility=None, deaths=None, migration=None))
    summary = dict(
        complete_state_year_rows=len(controls), native_observation_rows=len(observations),
        selected_native_state_references=sum(row["source_reference_selected"] for row in controls),
        qualified_source_defined_participation_references=sum(row["qualified_full_state_participation"] for row in controls),
        conditional_survey_rows=len(scenarios), complete_public_survey_decisions=len(decisions),
        source_defined_time_comparisons=len(changes),
        held_observations=[dict(year=row["year"], state_code=row["state_code"],
                               scope=row["scope_disposition"], measure=row["measure_disposition"])
                           for row in observations if not row["qualified_full_state_participation"]],
        notes=[
            "Only native state reporting rows are considered; local unit sums are not statewide controls.",
            "Alaska native total registrations include active and inactive records; no citizen/eligible denominator is inferred.",
            "EAVS source-defined participation is not automatically ballots cast; changing F1/F2 meanings remain.",
            "Highest-office proxies and statewide UOCAVA-only rows remain held, not corrected or discarded.",
            "AP final/poll-close weights are separate views of the same sample and may already calibrate outcomes.",
            "R*p scenarios assume unvalidated exchangeability to the particular total-register frame.",
            "Unknown model mass remains in the full denominator; model nonvoter is not observed staying home.",
            "No national population count, demographic allocation, individual retention or false confidence interval.",
            "Earlier held native rows with no source qualification remain in the full grid; missing is never zero.",
        ],
    )
    return {
        "complete-state-year-controls.csv": csv_bytes(controls),
        "complete-native-source-observations.csv": csv_bytes(observations),
        "complete-source-weighted-scenarios.csv": csv_bytes(scenarios, SCENARIO_FIELDS),
        "complete-survey-dispositions.csv": csv_bytes(decisions, (
            "year", "scope", "dimension", "group", "weight_field", "disposition")),
        "complete-native-time-comparisons.csv": csv_bytes(changes, TIME_FIELDS),
        "summary.json": json_bytes(summary),
    }, summary


def read_inputs(inputs):
    source = json.loads((inputs / "source.json").read_bytes())
    if set(source["files"]) != INPUTS:
        raise ValueError("Changed frozen sufficient-input contract")
    for name, metadata in source["files"].items():
        raw = (inputs / name).read_bytes()
        if len(raw) != metadata["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
            raise ValueError("Source-bound checksum mismatch: " + name)
    selections = json.loads((inputs / "native-selections.json").read_bytes())
    registration_rows = json.loads((inputs / "registration-selections.json").read_bytes())["rows"]
    definition_input = json.loads((inputs / "definitions.json").read_bytes())
    definitions = {int(year): fields for year, fields in definition_input["definitions"].items()}
    with zipfile.ZipFile(inputs / "complete-methods.zip") as archive:
        index = json.loads(archive.read("index.json"))
        fingerprints = {}

        def archive_sha(name):
            if name not in fingerprints:
                fingerprints[name] = hashlib.sha256(archive.read(name)).hexdigest()
            return fingerprints[name]

        for selected in selections["native_rows"]:
            name = selected["source_name"]
            metadata = index["sources"][name]
            if (archive_sha("originals/" + name) != selected["source_sha256"]
                    or metadata["sha256"] != selected["source_sha256"]
                    or metadata["url"] != selected["source_url"]
                    or metadata["retrieved_at"] != selected["retrieved_at"]):
                raise ValueError("Native row bound to changed original")
        for row in registration_rows:
            name = row["source_name"]
            if name in ("2010-registration.xls", "2012-registration.xlsx"):
                metadata = source["supplemental_registration_metadata"][str(row["year"])]
                digest = source["files"][name]["sha256"]
            else:
                metadata = index["sources"][name]
                digest = archive_sha("originals/" + name)
            if digest != row["source_sha256"] or metadata["sha256"] != digest or metadata["url"] != row["source_url"]:
                raise ValueError("Registration cache bound to changed original")
            validate_registration(row, definitions)
        instruments = {}
        defined_fields = set()
        for row in definition_input["source_bound_native_instrument_rows"]:
            name = row["original_member"]
            if row["sheet"] != "Variables" or archive_sha(name) != row["original_sha256"]:
                raise ValueError("Instrument definition bound to changed original")
            if name not in instruments:
                instruments[name] = instrument_rows(archive.read(name))
            key = int(row["year"]), row["field"]
            if key in defined_fields or instruments[name][row["source_row"]] != (row["field"], row["label"]):
                raise ValueError("Instrument definition differs from native worksheet row")
            if definitions[key[0]][key[1]] != row["label"]:
                raise ValueError("Changed native instrument definition")
            defined_fields.add(key)
        if defined_fields != {(year, field) for year, fields in definitions.items() for field in fields}:
            raise ValueError("Native definition missing original worksheet binding")
    registrations = {}
    for row in registration_rows:
        key = int(row["year"]), row["state_code"], row["jurisdiction_id"], row["jurisdiction"]
        if key in registrations:
            raise ValueError("Duplicate registration source join")
        registrations[key] = row
    local_rows = list(csv.DictReader(io.StringIO(
        gzip.decompress((inputs / "local-observations.csv.gz").read_bytes()).decode())))
    if len(local_rows) != 67525:
        raise ValueError("Incomplete frozen local query")
    local = {(int(row["year"]), row["state_code"], row["jurisdiction_id"], row["jurisdiction"]): row
             for row in local_rows if row["statewide_unit"] == "True"}
    if len(local) != 15 or len(selections["native_rows"]) != 13:
        raise ValueError("Changed complete statewide candidate inventory")
    if source["earlier_source_sha256"] != source["files"]["earlier-timeseries.xlsx"]["sha256"]:
        raise ValueError("Earlier inventory bound to changed time-series original")
    candidate_keys = {(int(row["year"]), row["state_code"], row["jurisdiction_id"], row["jurisdiction"])
                      for row in selections["native_rows"] + selections["omitted_early_rows"]}
    if candidate_keys != set(local) or len(selections["omitted_early_rows"]) != 2:
        raise ValueError("Incomplete native and held source inventory")
    observations = [observation(
        row, local[(int(row["year"]), row["state_code"], row["jurisdiction_id"], row["jurisdiction"])],
        registrations, definitions) for row in selections["native_rows"]]
    for row in selections["omitted_early_rows"]:
        key = int(row["year"]), row["state_code"], row["jurisdiction_id"], row["jurisdiction"]
        if key[0] not in (2004, 2006) or row != local[key]:
            raise ValueError("Earlier inventory differs from frozen local query")
        observations.append(dict(
            observations[0], year=int(row["year"]), state_code=row["state_code"],
            jurisdiction_id=row["jurisdiction_id"], jurisdiction=row["jurisdiction"],
            native_total_participation=native_count(row["total_participation"]),
            native_registered=native_count(row["registered"]), native_active_registered=None,
            native_inactive_registered=None, registration_accounting="components_not_qualified",
            scope_disposition="held_earlier_original_not_qualified_in_this_increment",
            measure_disposition="held_earlier_harmonized_counted_ballot_measure",
            qualified_full_state_participation=False, native_participation_per_native_register_pct=None,
            native_participation_field=json.loads(row["source_details"])["total_field"],
            native_participation_definition="", native_registration_field=row["registration_field"],
            native_registration_definition="", registration_basis=row["registration_basis"],
            native_participation_basis="", native_source_comments=row["source_details"],
            native_registration_comments=row["registration_comment"], source_url=row["source_url"],
            source_sha256=source["earlier_source_sha256"], source_sheet="held_jurisdiction_time_series",
            source_row=json.loads(row["source_details"]).get("source_row"),
            source_retrieved_at="already_held_before_this_increment",
            registration_source_url=row["source_url"], registration_source_sha256=source["earlier_source_sha256"],
            registration_source_sheet="held_jurisdiction_time_series",
            registration_source_row=json.loads(row["source_details"]).get("source_row"),
        ))
    return sorted(observations, key=lambda row: (row["year"], row["state_code"])), json.loads(
        (inputs / "ap-selected-aggregates.json").read_bytes())


def export(inputs, output):
    if output.exists():
        raise ValueError("Refusing to overwrite an existing analysis")
    files, summary = build(*read_inputs(inputs))
    for name in sorted(INPUTS | {"source.json"}):
        files["inputs/" + name] = (inputs / name).read_bytes()
    files["scripts/eac_state_controls.py"] = Path(__file__).read_bytes()
    files["tests/test_eac_state_controls.py"] = Path(__file__).parents[1].joinpath(
        "tests/test_eac_state_controls.py").read_bytes()
    files["README.txt"] = (
        "Complete EAC native-state context and conditional AP register-frame scenarios.\n"
        "Read summary.json: no local-unit statewide extrapolation, cast-ballot relabeling or eligible population.\n"
        "Original aggregate archives/instruments, source-bound selections, full reference inputs, all queries, code and tests included.\n"
        "Two earlier rows retain unqualified source references, not new source approval.\n"
        "Offline reproduction using only Python's standard library:\n"
        "  python3 -m unittest discover -s tests -p test_eac_state_controls.py\n"
        "  python3 -m scripts.eac_state_controls --inputs inputs --output reproduced\n"
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
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
