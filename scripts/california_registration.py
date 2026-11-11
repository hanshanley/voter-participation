"""Dated native registration evidence; no demographic turnout or population repair."""

import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile


NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
BASELINE_SHA = "99bad46c6c8142c8a92dd0a60f1863929b9ecaf930b290a0aec9fd3f3d3ae101"
SOURCE_URL = "https://www.sos.ca.gov/elections/report-registration/15day-general-2026"
BOOKS = ("county.xlsx", "age.xlsx", "pre-reg.xlsx")
HEADERS = {
    "county.xlsx": ("County", "Eligible", "Total Registered", "Democratic", "Republican",
                   "American Independent", "Green", "Libertarian", "Peace and Freedom",
                   "Unknown", "Other", "No Party Preference"),
    "age.xlsx": ("County", "Total Registered", "17.5* - 25", "26 - 35", "36 - 45",
                "46 - 55", "56 - 65", "66+"),
    "pre-reg.xlsx": ("County", "Total \nPre-Registered1", "Democratic", "Republican",
                    "American Independent", "Green", "Libertarian", "Peace and Freedom",
                    "Unknown", "Other", "No Party Preference"),
}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def workbook(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if [name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")
                and name.endswith(".xml")] != ["xl/worksheets/sheet1.xml"]:
            raise ValueError("Changed native single-sheet workbook")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(node.itertext()) for node in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows = []
    for source in root.findall("s:sheetData/s:row", NS):
        cells = {}
        for cell in source.findall("s:c", NS):
            value = cell.find("s:v", NS)
            inline = cell.find("s:is", NS)
            text = value.text if value is not None else "".join(inline.itertext()) if inline is not None else ""
            if cell.get("t") == "s":
                text = strings[int(text)]
            if text:
                cells[cell.attrib["r"]] = text
        if cells:
            rows.append(cells)
    return rows


def tables(books):
    counts, cells, identities = {}, [], []
    for name in BOOKS:
        rows = books[name]
        if tuple(rows[0].values()) != HEADERS[name]:
            raise ValueError("Changed native header or age/registration frame")
        counties = {}
        for row in rows[1:]:
            label = next(iter(row.values()))
            for reference, value in row.items():
                cells.append(dict(source_file=name, source_cell=reference, native_value=value))
            if label == "Percent":
                continue
            values = list(row.values())
            if len(values) != len(HEADERS[name]) or label in counties:
                raise ValueError("Missing, duplicate or nonrectangular native county")
            numbers = {}
            for header, value in zip(HEADERS[name][1:], values[1:]):
                amount = Decimal(value)
                if not amount.is_finite() or amount != amount.to_integral_value() or amount < 0:
                    raise ValueError("Invalid native registration count")
                numbers[header] = int(amount)
            counties[label] = numbers
        if len(counties) != 59 or "State Total" not in counties:
            raise ValueError("Incomplete 58-county and separate state query")
        identities.append(set(counties))
        total = counties["State Total"]
        for column in total:
            if sum(row[column] for county, row in counties.items() if county != "State Total") != total[column]:
                raise ValueError("Native county sums disagree with separate statewide counts")
        total_column = HEADERS[name][2] if name == "county.xlsx" else HEADERS[name][1]
        parts = HEADERS[name][3:] if name == "county.xlsx" else HEADERS[name][2:]
        for row in counties.values():
            if sum(row[column] for column in parts) != row[total_column]:
                raise ValueError("Native age or registration accounting disagrees")
        counts[name] = counties
    if not identities[0] == identities[1] == identities[2]:
        raise ValueError("Different native county identities across source tables")
    for county in identities[0]:
        if counts["county.xlsx"][county]["Total Registered"] != counts["age.xlsx"][county]["Total Registered"]:
            raise ValueError("Native age and county registration populations differ")
    return counts, cells


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def build(inputs):
    native = {name: (inputs / name).read_bytes() for name in BOOKS}
    counts, cells = tables({name: workbook(body) for name, body in native.items()})
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA:
        raise ValueError("Changed accepted complete all-state baseline")
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        retained = {name: archive.read(name) for name in (
            "complete-state-control-query.csv", "complete-conditional-registered-scenarios.csv",
            "complete-native-control-dispositions.csv")}
    states = list(csv.DictReader(io.StringIO(retained["complete-state-control-query.csv"].decode())))
    scenarios = list(csv.DictReader(io.StringIO(retained["complete-conditional-registered-scenarios.csv"].decode())))
    if len(states) != 51 or len({row["state_code"] for row in states}) != 51 or len(scenarios) != 9:
        raise ValueError("Changed complete state coverage or existing scenarios")
    total = counts["county.xlsx"]["State Total"]["Total Registered"]
    query = []
    for row in states:
        ca = row["state_code"] == "CA"
        original = int(row["control_registered_denominator"]) if row["control_registered_denominator"] else None
        query.append(dict(
            state_code=row["state_code"], year=2026,
            existing_control_id=row["control_id"], existing_registered_denominator=original,
            additional_native_registered_reference=total if ca else None,
            additional_reference_date="2026-10-19" if ca else None,
            existing_minus_additional_registered=(original - total) if ca and original is not None else None,
            disposition="dated_native_count_corroboration_not_lineage_or_model_validation" if ca else "no_new_reference_in_this_increment",
            source_url=SOURCE_URL if ca else None,
            reported_group_participation=None, same_population_and_cutoff_proved=False,
            conditional_model_estimates_changed=False, local_allocation=False))
    for name, counties in counts.items():
        rows = [dict(state_code="CA", source_date="2026-10-19", native_county=county, **values)
                for county, values in counties.items()]
        retained["complete-native-" + name.removesuffix(".xlsx") + "-registration.csv"] = csv_bytes(rows)
    retained["complete-registered-reference-query.csv"] = csv_bytes(query)
    retained["complete-native-workbook-cells.csv"] = csv_bytes(cells)
    retained["source-qualification.json"] = encoded(dict(
        source_url=SOURCE_URL, source_date="2026-10-19", native_counties=58,
        native_registered=total, native_preregistered=counts["pre-reg.xlsx"]["State Total"][HEADERS["pre-reg.xlsx"][1]],
        native_eligible_estimate=counts["county.xlsx"]["State Total"]["Eligible"],
        eligible_estimate_is_unofficial_and_not_registration=True,
        native_youngest_age="17.5* - 25",
        activated_17_year_olds_for_an_upcoming_election_retained=True,
        native_preregistration_report_overlaps_active_registration=True,
        preregistration_not_added_to_registration=True,
        civic_age_bins_incompatible_no_splitting=True, party_columns_are_registration_accounting_not_behavior=True,
        reported_group_participation=None, observed_staying_home=None,
        source_count_agreement_does_not_prove_results_system_lineage=True,
        population_transport_or_model_validation=False, local_allocation=False))
    retained["summary.json"] = encoded(dict(
        jurisdictions=51, native_counties=58, native_registered=total,
        native_preregistered=counts["pre-reg.xlsx"]["State Total"][HEADERS["pre-reg.xlsx"][1]],
        native_workbook_cells=len(cells), native_age_groups=6,
        existing_states_and_nine_scenarios_byte_identical=True, new_or_duplicate_scenarios=0,
        changed_model_estimates=0, observed_demographic_turnout=False,
        native_registered_count_matches_prior_ca_denominator=next(row for row in query if row["state_code"] == "CA")[
            "existing_minus_additional_registered"] == 0))
    return retained


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite an existing complete analysis")
    files = build(inputs)
    receipts = json.loads((inputs / "native-originals-receipts.json").read_bytes())
    expected = {"complete-ror.pdf", "historical-reg-stats.pdf", "county.xlsx", "county.pdf",
                "age.xlsx", "age.pdf", "pre-reg.xlsx", "pre-reg.pdf"}
    if len(receipts) != len(expected) or {row["file"] for row in receipts} != expected:
        raise ValueError("Changed complete native input set")
    for receipt in receipts:
        name = receipt["file"]
        content = (inputs / name).read_bytes()
        if (receipt["url"] != "https://elections.cdn.sos.ca.gov/ror/15day-gen-2026/" + name
                or receipt["status"] != 200 or len(content) != receipt["bytes"]
                or hashlib.sha256(content).hexdigest() != receipt["sha256"]):
            raise ValueError("Changed sufficient original input")
        files["inputs/" + name] = content
    files["inputs/native-originals-receipts.json"] = (inputs / "native-originals-receipts.json").read_bytes()
    files["inputs/baseline-complete-analysis.zip"] = (inputs / "baseline-complete-analysis.zip").read_bytes()
    files["scripts/california_registration.py"] = Path(__file__).read_bytes()
    files["tests/test_california_registration.py"] = Path(__file__).parents[1].joinpath("tests/test_california_registration.py").read_bytes()
    files["README.txt"] = (
        "Dated native California registration evidence, not demographic turnout.\n"
        "Complete51-state query and nine prior scenarios retained byte-identically.\n"
        "Age bins and separately preregistered people are never reallocated.\n"
        "python3 -m unittest discover -s tests -p test_california_registration.py\n"
        "python3 -m scripts.california_registration --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
                                      for name, body in sorted(files.items())})
    output.mkdir(parents=True)
    for name, body in files.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
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
