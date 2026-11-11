"""Reconcile native registration snapshots and conditional whole-state survey frames."""

import argparse
from datetime import datetime
from decimal import Decimal, localcontext
from fractions import Fraction
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


COUNTIES = (
    "ALBANY", "BIG HORN", "CAMPBELL", "CARBON", "CONVERSE", "CROOK", "FREMONT",
    "GOSHEN", "HOT SPRINGS", "JOHNSON", "LARAMIE", "LINCOLN", "NATRONA", "NIOBRARA",
    "PARK", "PLATTE", "SHERIDAN", "SUBLETTE", "SWEETWATER", "TETON", "UINTA", "WASHAKIE", "WESTON",
)
PARTIES = ("Constitution", "Democratic", "Libertarian", "Republican", "Unaffiliated", "Other*")
GENERAL_DATES = {2022: "2022-11-08", 2026: "2026-11-03"}
INPUTS = {
    "2022-registration.pdf", "2026-registration.pdf", "registration-extractions.json",
    "state-year-controls.csv", "historical-statistics.csv", "VoterProfile.pdf",
    "ap-selected-aggregates.json", "civic-selected-aggregates.json",
}
SCENARIO_FIELDS = (
    "year", "state_code", "scope", "geographic_level", "study", "weight_field", "source_n",
    "positive_weight_n", "source_weight", "modeled_voter_weight", "modeled_nonvoter_weight",
    "model_unknown_weight", "registration_snapshot_date", "native_registration_snapshot",
    "registration_basis", "modeled_voter_share", "modeled_nonvoter_share", "model_unknown_share",
    "conditional_modeled_voter_count", "conditional_modeled_nonvoter_count", "conditional_model_unknown_count",
    "reported_cast_ballot_snapshot", "ballot_source_time",
    "exchangeability_to_native_registration_snapshot_validated", "source_calibration_independence",
    "administrative_staying_home_observed", "individual_retention_or_switching_inferred",
    "election_time_registered", "eligibility", "deaths", "migration", "county_or_precinct_allocation",
    "native_registration_source",
)


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def csv_bytes(rows, fields=None):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def number(value):
    if not re.fullmatch(r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)", value):
        raise ValueError("Invalid native count, not zero")
    return int(value.replace(",", ""))


def decimal(value):
    with localcontext() as context:
        context.prec = 60
        return format(Decimal(value.numerator) / Decimal(value.denominator), ".18f")


def parse_page(text, source_url, page):
    text = re.sub(r"\s+", " ", text).strip()
    header = "County " + " ".join(PARTIES) + " TOTAL"
    if header not in text or "Wyoming Voter Registration" not in text or "Statewide Summary" not in text:
        raise ValueError("Changed native registration identity or header")
    dates = re.findall(r"State of Wyoming ([0-9]+/[0-9]+/[0-9]{4})", text)
    if len(dates) != 1:
        raise ValueError("Missing or ambiguous native registration date")
    date = datetime.strptime(dates[0], "%m/%d/%Y").date()
    if date.year not in (2022, 2026):
        raise ValueError("Unsupported native registration year")
    labels = [kind for kind in ("General", "Primary") if kind + " Election Day" in text]
    if len(labels) > 1:
        raise ValueError("Ambiguous native election label")
    kind = labels[0].lower() + "_election_day_label" if labels else "monthly_snapshot"
    body = text.split(header, 1)[1].split("* ", 1)[0].strip()
    pattern = re.compile(
        r"(" + "|".join(re.escape(name) for name in (*COUNTIES, "TOTAL")) + r") "
        + r" ".join([r"([0-9][0-9,]*)"] * 7))
    matches = list(pattern.finditer(body))
    if pattern.sub("", body).strip() or sorted(match[1] for match in matches) != sorted((*COUNTIES, "TOTAL")):
        raise ValueError("Incomplete, duplicate or malformed county/state registration rows")
    rows = []
    for match in matches:
        values = [number(value) for value in match.groups()[1:]]
        row = dict(
            snapshot_date=date.isoformat(), year=date.year, state_code="WY", native_unit=match[1],
            geographic_level="state" if match[1] == "TOTAL" else "county", snapshot_kind=kind,
        )
        row.update(zip(PARTIES, values[:6]))
        row.update(
            native_registration_total=values[6], native_party_sum=sum(values[:6]),
            native_party_sum_difference=sum(values[:6]) - values[6],
            native_accounting_disposition="reconciles" if sum(values[:6]) == values[6] else "source_difference_retained",
            active_inactive_definition="not_declared_in_this_pdf",
            election_day_registration_inclusion="not_declared_in_this_pdf",
            election_time_registered=None, registered_voter_turnout_rate=None,
            source_url=source_url, source_page=page,
        )
        rows.append(row)
    state = next(row for row in rows if row["native_unit"] == "TOTAL")
    counties = [row for row in rows if row["geographic_level"] == "county"]
    accounting = [
        dict(snapshot_date=date.isoformat(), native_column=field,
             county_sum=sum(row[field] for row in counties), declared_state_total=state[field],
             difference=sum(row[field] for row in counties) - state[field],
             parent_and_children_added=False)
        for field in (*PARTIES, "native_registration_total")
    ]
    return rows, accounting


def survey_candidates(ap, civic):
    return (
        [dict(row, study="AP VoteCast") for row in ap["selected_rows"]]
        + [dict(row, study="Civic", year=2026, weight_field="source_weight")
           for row in civic["participation"]]
    )


def conditional(snapshot, survey, control):
    weight, voter, nonvoter = (Fraction(survey[key])
                              for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
    unknown = Fraction(survey.get("model_unknown_weight", weight - voter - nonvoter))
    if weight <= 0 or min(voter, nonvoter, unknown) < 0 or voter + nonvoter + unknown != weight:
        raise ValueError("Unreconciled full survey model mass")
    registered = snapshot["native_registration_total"]
    return dict(
        year=snapshot["year"], state_code="WY", scope="WY", geographic_level="state",
        study=survey["study"], weight_field=survey["weight_field"],
        source_n=survey["n"], positive_weight_n=survey.get("positive_weight_n"),
        source_weight=str(survey["weight"]), modeled_voter_weight=str(survey["modeled_voter_weight"]),
        modeled_nonvoter_weight=str(survey["modeled_nonvoter_weight"]), model_unknown_weight=str(unknown),
        registration_snapshot_date=snapshot["snapshot_date"], native_registration_snapshot=registered,
        registration_basis="native_date_labeled_register_not_qualified_election_time_denominator",
        modeled_voter_share=decimal(voter / weight), modeled_nonvoter_share=decimal(nonvoter / weight),
        model_unknown_share=decimal(unknown / weight),
        conditional_modeled_voter_count=decimal(registered * voter / weight),
        conditional_modeled_nonvoter_count=decimal(registered * nonvoter / weight),
        conditional_model_unknown_count=decimal(registered * unknown / weight),
        reported_cast_ballot_snapshot=control["reported_cast_ballots"],
        ballot_source_time=control["source_time_label"],
        exchangeability_to_native_registration_snapshot_validated=False,
        source_calibration_independence="not_established_final_weights_may_use_results",
        administrative_staying_home_observed=False, individual_retention_or_switching_inferred=False,
        election_time_registered=None, eligibility=None, deaths=None, migration=None,
        county_or_precinct_allocation=False, native_registration_source=snapshot["source_url"],
    )


def build(rows, accounting, controls, statistics, ap, civic):
    keys = {(row["snapshot_date"], row["native_unit"]) for row in rows}
    if len(keys) != len(rows):
        raise ValueError("Duplicate registration snapshot/unit")
    snapshots = {
        row["year"]: row for row in rows
        if row["native_unit"] == "TOTAL" and row["snapshot_kind"] == "general_election_day_label"
        and row["snapshot_date"] == GENERAL_DATES.get(row["year"])
    }
    if set(snapshots) != {2022, 2026}:
        raise ValueError("Missing declared general-election registration snapshot")
    control_map = {int(row["year"]): row for row in controls if row["state_code"] == "WY"}
    profile = {(int(row["year"]), row["election_type"]): row for row in statistics}
    comparisons = []
    qualified = {}
    for year, snapshot in sorted(snapshots.items()):
        date = snapshot["snapshot_date"]
        counts = [row for row in rows if row["snapshot_date"] == date]
        sums = [row for row in accounting if row["snapshot_date"] == date]
        qualified[year] = (len(counts) == 24 and len(sums) == 7
                           and all(row["native_party_sum_difference"] == 0 for row in counts)
                           and all(row["difference"] == 0 for row in sums))
        control = control_map.get(year)
        if not control or not control["reported_cast_ballots"]:
            raise ValueError("Missing qualified source-specific general ballot reference")
        previous = profile[(year, "general")]
        prior_registered = previous["native_day_before_registered"]
        comparisons.append(dict(
            year=year, state_code="WY", registration_snapshot_date=date,
            native_registration_snapshot=snapshot["native_registration_total"],
            county_state_registration_accounting_reconciles=qualified[year],
            profile_day_before_registered=prior_registered,
            profile_comparison=("not_reported_in_profile_revision" if not prior_registered else
                                "equal_count_not_independent_or_frame_proof"
                                if int(prior_registered) == snapshot["native_registration_total"]
                                else "source_count_difference_retained"),
            reported_cast_ballot_snapshot=control["reported_cast_ballots"],
            ballot_source_time=control["source_time_label"], ballot_source_url=control["source_url"],
            ballot_snapshot_per_native_register_percent=decimal(Fraction(
                100 * int(control["reported_cast_ballots"]), snapshot["native_registration_total"])),
            ratio_is_registered_voter_turnout=False, election_time_registered=None,
            registration_snapshot_replaced_existing_control=False,
            native_registration_source=snapshot["source_url"],
        ))
    dispositions, scenarios = [], []
    for survey in survey_candidates(ap, civic):
        year = int(survey["year"])
        if survey["scope"] != "WY" or survey["dimension"] != "overall" or survey["group"] != "all":
            disposition = "not_matching_whole_state_overall"
        elif year not in snapshots:
            disposition = "no_same_year_general_registration_snapshot"
        elif survey["study"] == "AP VoteCast" and not survey["weight_field"].endswith("_STATE_WEIGHT"):
            disposition = "not_publisher_state_weight_frame"
        elif int(survey.get("positive_weight_n", survey["n"])) < 500:
            disposition = "whole_state_support_hold"
        elif not qualified[year]:
            disposition = "native_registration_accounting_hold"
        else:
            disposition = "conditional_native_snapshot_exchangeability_unvalidated"
            scenarios.append(conditional(snapshots[year], survey, control_map[year]))
        dispositions.append(dict(
            study=survey["study"], year=year, scope=survey["scope"], dimension=survey["dimension"],
            group=survey["group"], weight_field=survey["weight_field"], disposition=disposition))
    general = {
        (row["year"], row["native_unit"]): row for row in rows
        if row["snapshot_date"] == GENERAL_DATES.get(row["year"])
        and row["snapshot_kind"] == "general_election_day_label"
    }
    changes = [
        dict(state_code="WY", native_unit=unit, geographic_level=general[(2022, unit)]["geographic_level"],
             from_snapshot_date=GENERAL_DATES[2022], to_snapshot_date=GENERAL_DATES[2026],
             prior_registration_snapshot=general[(2022, unit)]["native_registration_total"],
             current_registration_snapshot=general[(2026, unit)]["native_registration_total"],
             native_registration_snapshot_change=(general[(2026, unit)]["native_registration_total"]
                                                  - general[(2022, unit)]["native_registration_total"]),
             original_cohort_change_inferred=False, eligibility=None, deaths=None, migration=None)
        for unit in (*COUNTIES, "TOTAL")
    ]
    summary = dict(
        native_registration_rows=len(rows), snapshot_dates=len({row["snapshot_date"] for row in rows}),
        county_state_accounting_rows=len(accounting), registration_change_rows=len(changes),
        general_source_comparison_rows=len(comparisons), source_weighted_conditional_rows=len(scenarios),
        full_public_survey_dispositions=len(dispositions),
        general_registration_snapshots={year: row["native_registration_total"] for year, row in snapshots.items()},
        all_native_registration_accounting_reconciles=(
            all(row["native_party_sum_difference"] == 0 for row in rows)
            and all(row["difference"] == 0 for row in accounting)),
        existing_election_time_registration_nulls_unchanged=True,
        existing_model_shares_and_scenarios_unchanged=True,
        notes=[
            "Registration-party categories are source accounting, not vote choice or party-specific turnout.",
            "Each state total is compared with, never added to, its 23 county rows.",
            "Native date/election labels do not establish active/inactive or Election Day registration inclusion.",
            "The 2022 general total equals the profile's explicitly pre-election register; equality does not prove a final denominator.",
            "Ballot/register snapshot ratios are arithmetic context, not registered-voter turnout.",
            "R*p scenarios assume unvalidated exchangeability to the exact native registration snapshot.",
            "AP poll-close/final and Civic constructs remain separate; no cross-study model-count change is inferred.",
            "Model nonvoter is not administratively observed staying home; unknown mass stays in the denominator.",
            "No state survey propensity is allocated to counties or precincts; no false confidence interval.",
        ],
    )
    return {
        "complete-native-registration.csv": csv_bytes(rows),
        "complete-county-state-accounting.csv": csv_bytes(accounting),
        "complete-registration-snapshot-changes.csv": csv_bytes(changes),
        "complete-general-source-comparison.csv": csv_bytes(comparisons),
        "complete-source-weighted-conditional-scenarios.csv": csv_bytes(scenarios, SCENARIO_FIELDS),
        "complete-survey-dispositions.csv": csv_bytes(dispositions),
        "summary.json": json_bytes(summary),
    }, summary


def read_inputs(inputs):
    source = json.loads((inputs / "source.json").read_bytes())
    if set(source["files"]) != INPUTS:
        raise ValueError("Changed frozen input contract")
    for name, metadata in source["files"].items():
        raw = (inputs / name).read_bytes()
        if len(raw) != metadata["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
            raise ValueError("Source-bound input checksum mismatch: " + name)
    pages = json.loads((inputs / "registration-extractions.json").read_bytes())
    expected_pages = {("2022-registration.pdf", page) for page in range(1, 15)} | {("2026-registration.pdf", 1)}
    if len(pages) != 15 or {(page["input_pdf"], page["page"]) for page in pages} != expected_pages:
        raise ValueError("Missing or duplicate native PDF pages")
    rows, accounting = [], []
    for page in pages:
        if page["pdf_sha256"] != source["files"][page["input_pdf"]]["sha256"]:
            raise ValueError("Unbound PDF text cache")
        first = parse_page(page["pypdf"], page["source_url"], page["page"])
        if first != parse_page(page["fitz"], page["source_url"], page["page"]):
            raise ValueError("Independent native registration selections differ")
        rows.extend(first[0])
        accounting.extend(first[1])
    csv_input = lambda name: list(csv.DictReader(io.StringIO((inputs / name).read_text(), newline="")))
    controls, statistics = csv_input("state-year-controls.csv"), csv_input("historical-statistics.csv")
    if len(controls) != 255 or len(statistics) != 50:
        raise ValueError("Incomplete selected reference query")
    return (rows, accounting, controls, statistics,
            json.loads((inputs / "ap-selected-aggregates.json").read_bytes()),
            json.loads((inputs / "civic-selected-aggregates.json").read_bytes()))


def export(inputs, output):
    if output.exists():
        raise ValueError("Refusing to overwrite an existing analysis")
    files, summary = build(*read_inputs(inputs))
    for name in sorted(INPUTS | {"source.json"}):
        files["inputs/" + name] = (inputs / name).read_bytes()
    files["scripts/wyoming_registration_controls.py"] = Path(__file__).read_bytes()
    files["tests/test_wyoming_registration_controls.py"] = Path(__file__).parents[1].joinpath(
        "tests/test_wyoming_registration_controls.py").read_bytes()
    files["README.txt"] = (
        "Complete native Wyoming registration snapshots and conditional whole-state scenarios.\n"
        "Read summary.json: these are source-specific registers, NOT final election-time registered denominators.\n"
        "All native party categories are retained only for source accounting, never inferred vote behavior.\n"
        "Complete aggregate PDFs, both source-bound text selections, public survey/reference inputs, all queries, code and tests included.\n"
        "No raw respondents, voter identifiers, county survey allocation or individual staying-home counts.\n"
        "Offline reproduction:\n"
        "  python3 -m unittest discover -s tests -p test_wyoming_registration_controls.py\n"
        "  python3 -m scripts.wyoming_registration_controls --inputs inputs --output reproduced\n"
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
