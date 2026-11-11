"""Preserve Wyoming's primary/general statistics and distinct denominator frames."""

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


SOURCE_URL = "https://sos.wyo.gov/Elections/Docs/VoterProfile.pdf"
YEARS = tuple(range(1978, 2027, 2))
INPUT_FILES = {"VoterProfile.pdf", "profile-pypdf.txt", "profile-fitz.txt", "historical-controls.csv"}


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def percentage(numerator, denominator):
    if numerator is None:
        return None
    with localcontext() as context:
        context.prec = 38
        return format(Decimal(numerator) * 100 / Decimal(denominator), ".12f")


def percentage_check(numerator, denominator, printed):
    if numerator is None:
        return "not_reported"
    digits = len(printed.partition(".")[2])
    difference = abs(Fraction(100 * numerator, denominator) - Fraction(printed))
    return "within_printed_precision" if difference <= Fraction(1, 2 * 10**digits) else "source_disagreement"


def native_count(value):
    if not re.fullmatch(r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)", value):
        raise ValueError("Invalid native count")
    return int(value.replace(",", ""))


def native_percentage(value):
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%", value):
        raise ValueError("Invalid native percentage")
    return value[:-1]


def parse_profile(text):
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"([0-9]+)\. +([0-9]+)%", r"\1.\2%", text)
    required = (
        "Wyoming Voter Registration and Voter Turnout Statistics",
        "Primary Election", "General Election", "* Voting Age Population figures",
        "close of business on the day before the Primary and General Elections",
        "does not include election day registrations",
    )
    if not all(value in text for value in required):
        raise ValueError("Changed source identity or denominator qualification")
    revisions = re.findall(r"Revised: ([0-9]{2}/[0-9]{4})", text)
    if len(revisions) != 1:
        raise ValueError("Missing or ambiguous source revision")
    table = text.split("* Voting Age Population figures", 1)[0]
    starts = list(re.finditer(r"\b((?:19|20)[0-9]{2}) (?=[0-9]{1,3}(?:,[0-9]{3})+\b)", table))
    years = [int(match[1]) for match in starts]
    if sorted(years) != list(YEARS):
        raise ValueError("Missing, duplicate or unsupported source years")
    rows = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(table)
        values = table[match.start():end].split()
        year = int(values[0])
        if len(values) != (6 if year == 2026 else 10):
            raise ValueError("Partial or changed primary/general table row")
        vap = native_count(values[1])
        if not vap:
            raise ValueError("Missing voting-age population")
        for election, offset in (("primary", 2), ("general", 6)):
            registered = native_count(values[offset]) if offset < len(values) else None
            printed_registered = native_percentage(values[offset + 1]) if registered is not None else None
            turnout = native_count(values[offset + 2]) if registered is not None else None
            printed_turnout = native_percentage(values[offset + 3]) if registered is not None else None
            rows.append(dict(
                year=year, state_code="WY", election_type=election,
                source_revision=revisions[0], voting_age_population=vap,
                native_day_before_registered=registered,
                native_registered_percent_of_vap=printed_registered,
                native_voter_turnout=turnout, native_turnout_percent_of_vap=printed_turnout,
                calculated_registration_percent_of_vap=percentage(registered, vap),
                calculated_turnout_percent_of_vap=percentage(turnout, vap),
                registration_percentage_check=percentage_check(registered, vap, printed_registered),
                turnout_percentage_check=percentage_check(turnout, vap, printed_turnout),
                registration_basis="day_before_election_excludes_election_day_registrations",
                turnout_measure="native_Voter_Turnout_not_automatically_cast_ballots",
                election_time_registered=None, registered_voter_turnout_rate=None,
                eligible_citizen_turnout_rate=None, demographic_allocation=None,
                source_url=SOURCE_URL,
            ))
    return sorted(rows, key=lambda row: (row["year"], row["election_type"]))


def build(rows, controls):
    controls = {(int(row["year"]), row["state_code"]): row for row in controls}
    comparisons = []
    for row in rows:
        control = controls.get((row["year"], "WY")) if row["election_type"] == "general" else None
        qualified = control.get("reported_cast_ballots") if control else None
        if row["election_type"] == "primary":
            disposition = "primary_not_compared_to_general_control"
        elif row["native_voter_turnout"] is None:
            disposition = "general_not_reported_in_this_source_revision"
        elif not qualified:
            disposition = "no_qualified_selected_cast_ballot_control"
        else:
            disposition = ("equal_counts_separate_source_meanings_not_independent_validation"
                           if row["native_voter_turnout"] == int(qualified)
                           else "source_count_difference_retained")
        comparisons.append(dict(
            year=row["year"], state_code="WY", election_type=row["election_type"],
            native_statistics_turnout=row["native_voter_turnout"],
            selected_control_id=control.get("control_id") if control else None,
            selected_reported_cast_ballots=qualified or None,
            selected_control_registered=(control.get("native_registered") or None) if control else None,
            selected_source_time=control.get("source_time_label") if control else None,
            disposition=disposition, registration_denominator_replaced=False,
            independent_outcome_validation=False,
        ))
    lookup = {(row["year"], row["election_type"]): row for row in rows}
    changes = []
    for row in rows:
        previous = lookup.get((row["year"] - 2, row["election_type"]))
        if previous is None:
            continue
        current_count, previous_count = row["native_voter_turnout"], previous["native_voter_turnout"]
        missing = current_count is None or previous_count is None
        changes.append(dict(
            from_year=previous["year"], to_year=row["year"], election_type=row["election_type"],
            previous_native_turnout=previous_count, current_native_turnout=current_count,
            native_turnout_count_change=None if missing else current_count - previous_count,
            voting_age_population_rate_change_pp=None if missing else percentage(
                current_count * previous["voting_age_population"] - previous_count * row["voting_age_population"],
                row["voting_age_population"] * previous["voting_age_population"]),
            disposition="missing_native_endpoint" if missing else "same_election_type_native_snapshot_difference",
            individual_retention_or_switching_inferred=False,
            demographic_participation_change_inferred=False,
        ))
    summary = dict(
        source_url=SOURCE_URL, native_source_revision=rows[0]["source_revision"],
        complete_primary_general_rows=len(rows), complete_source_comparison_rows=len(comparisons),
        complete_same_type_change_rows=len(changes),
        source_percentage_disagreements=[
            dict(year=row["year"], election_type=row["election_type"], field=field)
            for row in rows for field in ("registration_percentage_check", "turnout_percentage_check")
            if row[field] == "source_disagreement"],
        native_unreported_elections=[dict(year=row["year"], election_type=row["election_type"])
                                    for row in rows if row["native_voter_turnout"] is None],
        registered_voter_turnout_estimated=False, modeled_shares_or_scenarios_changed=False,
        notes=[
            "VAP is source-estimated voting-age population, not citizen VAP or eligible voters.",
            "Registration excludes Election Day registrants; no election-time registration denominator is supplied.",
            "Native turnout is not automatically qualified cast ballots; primary and general elections remain distinct.",
            "Blank 2026 general cells remain unknown; no current votes are copied into this older source revision.",
            "Computed percentages are arithmetic ratios, not confidence intervals or demographic estimates.",
            "Equal state totals from the same producer do not provide independent validation.",
        ],
    )
    return {
        "complete-primary-general-statistics.csv": csv_bytes(rows),
        "complete-selected-control-comparison.csv": csv_bytes(comparisons),
        "complete-same-election-type-changes.csv": csv_bytes(changes),
        "summary.json": json_bytes(summary),
    }, summary


def read_inputs(inputs):
    source = json.loads((inputs / "source.json").read_bytes())
    if source["source_url"] != SOURCE_URL or set(source["files"]) != INPUT_FILES:
        raise ValueError("Changed frozen source contract")
    for name, metadata in source["files"].items():
        raw = (inputs / name).read_bytes()
        if len(raw) != metadata["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
            raise ValueError("Source-bound input checksum mismatch: " + name)
    first = parse_profile((inputs / "profile-pypdf.txt").read_text())
    second = parse_profile((inputs / "profile-fitz.txt").read_text())
    if first != second:
        raise ValueError("Independent native PDF text selections differ")
    controls = list(csv.DictReader(io.StringIO((inputs / "historical-controls.csv").read_text(), newline="")))
    if len(controls) != 255 or len({(row["year"], row["state_code"]) for row in controls}) != 255:
        raise ValueError("Incomplete selected state/year reference query")
    return first, controls


def export(inputs, output):
    if output.exists():
        raise ValueError("Refusing to overwrite an existing analysis")
    files, summary = build(*read_inputs(inputs))
    for name in sorted(INPUT_FILES | {"source.json"}):
        files["inputs/" + name] = (inputs / name).read_bytes()
    files["scripts/wyoming_participation_statistics.py"] = Path(__file__).read_bytes()
    files["tests/test_wyoming_participation_statistics.py"] = Path(__file__).parents[1].joinpath(
        "tests/test_wyoming_participation_statistics.py").read_bytes()
    files["README.txt"] = (
        "Complete native Wyoming primary/general statistics, 1978-2026.\n"
        "Read summary.json: registration excludes Election Day registrations; 2026 general is unreported.\n"
        "Native printed percentage disagreements remain; neither VAP nor pre-election R is an eligible-citizen denominator.\n"
        "Original aggregate PDF, both source-bound text extractions, all queries, source receipts, code and tests included.\n"
        "No raw voters/respondents, demographic allocation, modeled participation or registered-turnout estimates.\n"
        "Offline reproduction:\n"
        "  python3 -m unittest discover -s tests -p test_wyoming_participation_statistics.py\n"
        "  python3 -m scripts.wyoming_participation_statistics --inputs inputs --output reproduced\n"
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
