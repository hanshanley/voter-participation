"""Pair native CPS state voting/registration percentages without inventing populations."""

import argparse
import csv
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import io
import json
from pathlib import Path
import zipfile


STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
POPULATIONS = ("vap", "cvap")
DIAGNOSTIC_FIELDS = (
    "year", "reference_state_code", "population_frame", "study", "weight_field", "positive_weight_n",
    "source_weight", "source_modeled_voter_weight", "source_modeled_nonvoter_weight", "source_unknown_weight",
    "source_modeled_voter_pct", "cps_reported_voted_pct", "cps_reported_registered_pct",
    "cps_marginal_vote_to_registration_ratio_pct", "modeled_minus_cps_marginal_ratio_pp",
    "independent_administrative_validation", "population_transport_validated", "population_count",
    "observed_staying_home", "local_allocation", "native_inference_status",
)
DECISION_FIELDS = ("year", "scope", "dimension", "group", "weight_field", "population_frame", "disposition")
COMPARISON_FIELDS = (
    "from_year", "to_year", "reference_state_code", "election_type", "population_frame",
    "reported_voted_percentage_point_difference", "reported_registered_percentage_point_difference",
    "disposition", "definitions_harmonized", "individual_retention", "local_allocation",
)


def numeric(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and 0 <= result <= 100 else None
    except InvalidOperation:
        return None


def value_text(value):
    return None if value is None else format(value, "f")


def ratio(voted, registered):
    if voted is None or registered is None or not 0 <= voted <= registered or registered <= 0:
        return None
    with localcontext() as context:
        context.prec = 60
        return format(100 * voted / registered, ".18f")


def csv_bytes(rows, empty_fields=()):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else empty_fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def native_cells(workbooks):
    cells, ledger = {}, []
    code_by_name = {name: code for code, name in STATE_NAMES.items()}
    for workbook in workbooks:
        for sheet in workbook["sheets"]:
            rows = sheet["rows"]
            if rows[3][0] != "State":
                raise ValueError("Changed native state header")
            required_measure = "Reported Voting" if workbook["measure"] == "voted" else "Reported Registration"
            required_election = "Presidential Elections" if workbook["election_type"] == "presidential" else "Congressional Elections"
            if required_measure not in rows[1][0] or required_election not in rows[1][0]:
                raise ValueError("Native source title differs from assigned measure or election type")
            year, columns = None, []
            for index in range(1, len(rows[3])):
                label = rows[3][index]
                if label is not None:
                    year = int(label)
                population = rows[4][index]
                if population not in ("Total", "Citizen") or year is None:
                    raise ValueError("Unqualified native population/year column")
                if (year % 4 == 0) != (workbook["election_type"] == "presidential"):
                    raise ValueError("Source title and election type disagree")
                columns.append((index, year, "cvap" if population == "Citizen" else "vap"))
            found = set()
            for ordinal, row in enumerate(rows[5:], start=6):
                name = row[0]
                if name not in code_by_name:
                    continue
                code = code_by_name[name]
                if code in found:
                    raise ValueError("Duplicate native state row")
                found.add(code)
                for index, year, population in columns:
                    key = year, code, population, workbook["measure"]
                    if key in cells:
                        raise ValueError("Duplicate native source percentage")
                    cells[key] = dict(
                        raw_value=row[index], source_row=ordinal, source_column=index + 1,
                        source_name=Path(workbook["path"]).name, source_sheet=sheet["name"],
                        source_url=workbook["url"], source_sha256=workbook["sha256"],
                        source_retrieved_at=workbook["retrieved_at"],
                    )
                    ledger.append(dict(
                        year=year, reference_state_code=code, native_state_name=name, population_frame=population,
                        measure=workbook["measure"], raw_value=row[index],
                        numeric_percentage=value_text(numeric(row[index])),
                        disposition="native_published_percentage" if numeric(row[index]) is not None else "held_native_unavailable",
                        source_name=Path(workbook["path"]).name, source_sheet=sheet["name"],
                        source_row=ordinal, source_column=index + 1,
                    ))
            if found != set(STATE_NAMES):
                raise ValueError("Incomplete native state roster")
    return cells, ledger


def build(workbooks, existing_votes, ap):
    cells, ledger = native_cells(workbooks)
    for source in existing_votes:
        key = int(source["year"]), next(code for code, name in STATE_NAMES.items() if name == source["state"]), source["denominator"], "voted"
        original = cells.get(key)
        if not original or numeric(original["raw_value"]) != Decimal(str(source["turnout_pct"])) or (
                original["source_row"] != source["source_row"] or original["source_name"] != source["source"]):
            raise ValueError("New source binding differs from preserved voter query")
    if len(existing_votes) != sum(numeric(row["raw_value"]) is not None for key, row in cells.items() if key[3] == "voted"):
        raise ValueError("Incomplete preserved voter query")
    years = sorted({key[0] for key in cells})
    pairs = []
    for year in years:
        for state in sorted(STATE_NAMES):
            for population in POPULATIONS:
                vote, registration = cells.get((year, state, population, "voted")), cells.get((year, state, population, "registered"))
                voted = numeric(vote["raw_value"]) if vote else None
                registered = numeric(registration["raw_value"]) if registration else None
                quotient = ratio(voted, registered)
                disposition = ("held_native_population_column_absent" if not vote or not registration else
                               "held_native_unavailability_or_invalid_ratio" if quotient is None else
                               "native_reported_percentage_ratio_not_individual_joint")
                pairs.append(dict(
                    year=year, reference_state_code=state, native_state_name=STATE_NAMES[state],
                    election_type="presidential" if year % 4 == 0 else "midterm",
                    population_frame=population, raw_voted_value=vote["raw_value"] if vote else None,
                    raw_registered_value=registration["raw_value"] if registration else None,
                    reported_voted_pct=value_text(voted), reported_registered_pct=value_text(registered),
                    reported_vote_to_registration_ratio_pct=quotient, disposition=disposition,
                    native_population_columns_present=vote is not None and registration is not None,
                    early_largest_state_reporting_limit=year in (1972, 1974, 1976),
                    citizenship_measurement_pre_1996_caution=population == "cvap" and year < 1996,
                    registered_population_count=None, unknown_response_mass_identified=False,
                    ratio_is_administrative_or_joint_registered_turnout=False, local_allocation=False,
                    eligibility=None, deaths=None, migration=None,
                    voted_source_url=vote["source_url"] if vote else None,
                    registered_source_url=registration["source_url"] if registration else None,
                    voted_source_sha256=vote["source_sha256"] if vote else None,
                    registered_source_sha256=registration["source_sha256"] if registration else None,
                    voted_source_sheet=vote["source_sheet"] if vote else None,
                    registered_source_sheet=registration["source_sheet"] if registration else None,
                    voted_source_row=vote["source_row"] if vote else None,
                    registered_source_row=registration["source_row"] if registration else None,
                    source_column=(vote or registration or {}).get("source_column"),
                ))
    by_frame = {(row["year"], row["reference_state_code"], row["population_frame"]): row for row in pairs}
    comparisons = []
    for current in pairs:
        prior = by_frame.get((current["year"] - 4, current["reference_state_code"], current["population_frame"]))
        if not prior:
            continue
        qualified = all(row["reported_vote_to_registration_ratio_pct"] is not None for row in (prior, current))
        crossed_citizenship = current["population_frame"] == "cvap" and prior["year"] < 1996 <= current["year"]
        comparisons.append(dict(
            from_year=prior["year"], to_year=current["year"], reference_state_code=current["reference_state_code"],
            election_type=current["election_type"], population_frame=current["population_frame"],
            reported_voted_percentage_point_difference=value_text(
                Decimal(current["reported_voted_pct"]) - Decimal(prior["reported_voted_pct"])) if qualified and not crossed_citizenship else None,
            reported_registered_percentage_point_difference=value_text(
                Decimal(current["reported_registered_pct"]) - Decimal(prior["reported_registered_pct"])) if qualified and not crossed_citizenship else None,
            disposition="same_election_type_source_snapshot_not_cohort" if qualified and not crossed_citizenship else "held_missingness_or_native_citizenship_break",
            definitions_harmonized=False, individual_retention=False, local_allocation=False,
        ))
    diagnostics, decisions = [], []
    for source in ap["selected_rows"]:
        for population in POPULATIONS:
            reference = by_frame.get((int(source["year"]), source["scope"], population))
            if source["dimension"] != "overall" or source["group"] != "all":
                disposition = "not_native_whole_state_overall_query"
            elif source["scope"] not in STATE_NAMES or not source["weight_field"].endswith("_STATE_WEIGHT"):
                disposition = "no_native_state_weight_and_CPS_state_frame"
            elif not reference or reference["reported_vote_to_registration_ratio_pct"] is None:
                disposition = "no_qualified_same_year_native_CPS_percentage_pair"
            elif int(source["positive_weight_n"]) < 500:
                disposition = "source_support_hold"
            else:
                disposition = "source_specific_marginal_ratio_diagnostic_not_population_validation"
                with localcontext() as context:
                    context.prec = 60
                    weight = Decimal(source["weight"])
                    voter = Decimal(source["modeled_voter_weight"])
                    nonvoter = Decimal(source["modeled_nonvoter_weight"])
                    unknown = Decimal(source["model_unknown_weight"])
                    if weight <= 0 or min(voter, nonvoter, unknown) < 0 or voter + nonvoter + unknown != weight:
                        raise ValueError("Unreconciled complete survey mass")
                    modeled = 100 * voter / weight
                    diagnostics.append(dict(
                        year=source["year"], reference_state_code=source["scope"], population_frame=population,
                        study="AP VoteCast", weight_field=source["weight_field"],
                        positive_weight_n=source["positive_weight_n"],
                        source_weight=source["weight"], source_modeled_voter_weight=source["modeled_voter_weight"],
                        source_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                        source_unknown_weight=source["model_unknown_weight"],
                        source_modeled_voter_pct=format(modeled, ".18f"),
                        cps_reported_voted_pct=reference["reported_voted_pct"],
                        cps_reported_registered_pct=reference["reported_registered_pct"],
                        cps_marginal_vote_to_registration_ratio_pct=reference["reported_vote_to_registration_ratio_pct"],
                        modeled_minus_cps_marginal_ratio_pp=format(modeled - Decimal(
                            reference["reported_vote_to_registration_ratio_pct"]), ".18f"),
                        independent_administrative_validation=False, population_transport_validated=False,
                        population_count=None, observed_staying_home=False, local_allocation=False,
                        native_inference_status=source["inference_status"],
                    ))
            decisions.append(dict(
                year=source["year"], scope=source["scope"], dimension=source["dimension"], group=source["group"],
                weight_field=source["weight_field"], population_frame=population, disposition=disposition))
    summary = dict(
        native_percentage_cell_rows=len(ledger), complete_state_year_population_pairs=len(pairs),
        known_voting_source_rows=len(existing_votes),
        paired_native_marginal_ratios=sum(row["reported_vote_to_registration_ratio_pct"] is not None for row in pairs),
        missing_native_population_columns=sum(not row["native_population_columns_present"] for row in pairs),
        earliest_year=min(years), latest_year=max(years), states_and_DC=len(STATE_NAMES),
        same_election_type_comparison_rows=len(comparisons), supported_AP_state_diagnostic_rows=len(diagnostics),
        complete_AP_population_frame_decisions=len(decisions), modeled_population_counts=0,
        notes=[
            "Presidential and congressional sources are complementary election types, never old/new copies.",
            "All 51 native state/DC names and every declared year/frame are retained.",
            "Early source N is restricted state reporting, not no voters; absent citizen columns remain absent.",
            "Citizen measurements before 1996 are not uniform; comparisons across that change remain held.",
            "Published percentages and marginal ratios are source-weighted self-report, not administrative turnout.",
            "CPS registration percentages are not population counts; no multiplication by VEP/CVAP or group marginals.",
            "AP source weights/model unknown mass and final/poll-close frames remain separate.",
            "Comparisons are source-specific diagnostics, not independent validation, causal change or original-cohort retention.",
            "No state/group survey propensity allocation to counties/precincts or observed staying-home count.",
        ],
    )
    return {
        "complete-native-percentage-cells.csv": csv_bytes(ledger),
        "complete-state-year-population-pairs.csv": csv_bytes(pairs),
        "complete-same-election-type-comparisons.csv": csv_bytes(comparisons, COMPARISON_FIELDS),
        "complete-AP-state-frame-diagnostics.csv": csv_bytes(diagnostics, DIAGNOSTIC_FIELDS),
        "complete-AP-frame-dispositions.csv": csv_bytes(decisions, DECISION_FIELDS),
        "summary.json": json_bytes(summary),
    }, summary


def read_inputs(inputs):
    source = json.loads((inputs / "source.json").read_bytes())
    workbooks = json.loads((inputs / "workbooks.json").read_bytes())
    expected = {"sources.json", "workbooks.json", "existing-voted-observations.json", "ap-selected-aggregates.json"} | {
        "originals/" + row["path"] for row in workbooks}
    if set(source["files"]) != expected or any(Path(name).is_absolute() or ".." in Path(name).parts for name in (
            expected | {row["path"] for row in workbooks})):
        raise ValueError("Changed or unsafe sufficient-input contract")
    for name, metadata in source["files"].items():
        raw = (inputs / name).read_bytes()
        if len(raw) != metadata["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
            raise ValueError("Frozen input checksum differs: " + name)
    metadata = {row["path"]: row for row in json.loads((inputs / "sources.json").read_bytes())["sources"]}
    if len(workbooks) != 4 or {(row["election_type"], row["measure"]) for row in workbooks} != {
            (election, measure) for election in ("presidential", "midterm") for measure in ("voted", "registered")}:
        raise ValueError("Incomplete native voting/registration source inventory")
    for row in workbooks:
        original = metadata[row["path"]]
        if any(row[field] != original[field] for field in ("url", "sha256", "retrieved_at")):
            raise ValueError("Changed native source identity or clock")
        if hashlib.sha256((inputs / "originals" / row["path"]).read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Changed original workbook")
    return workbooks, json.loads((inputs / "existing-voted-observations.json").read_bytes()), json.loads(
        (inputs / "ap-selected-aggregates.json").read_bytes()), source


def export(inputs, output):
    if output.exists():
        raise ValueError("Refusing to overwrite a prior analysis")
    workbooks, votes, ap, source = read_inputs(inputs)
    files, summary = build(workbooks, votes, ap)
    for name in sorted(set(source["files"]) | {"source.json"}):
        files["inputs/" + name] = (inputs / name).read_bytes()
    files["scripts/cps_state_frames.py"] = Path(__file__).read_bytes()
    files["tests/test_cps_state_frames.py"] = Path(__file__).parents[1].joinpath("tests/test_cps_state_frames.py").read_bytes()
    files["README.txt"] = (
        "Complete native CPS state voting/registration percentages and separate AP diagnostics.\n"
        "All sufficient originals/caches, original voter query, complete outputs, code and tests included.\n"
        "Read summary.json: these ratios are not administrative or joint registered-voter turnout.\n"
        "python3 -m unittest discover -s tests -p test_cps_state_frames.py\n"
        "python3 -m scripts.cps_state_frames --inputs inputs --output reproduced\n"
    ).encode()
    files["checksums.json"] = json_bytes({name: dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
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
