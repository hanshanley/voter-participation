import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re


MODES = ("TOTAL", "Election Day", "Mail", "Walk-in Excuse", "Walk-in Early", "Provisional")
HEADER = ("TOTAL", "Election", "Day", "Mail", "Walk-in", "Excuse", "Walk-in", "Early", "Provision", "al")
PREFIX = ("Summary Results Report", "2026 General Election", "November 3, 2026",
          "UNOFFICIAL RESULTS", "Jefferson County")
INTEGER = re.compile(r"(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(literal):
    require(isinstance(literal, str) and INTEGER.fullmatch(literal) is not None,
            "Unqualified native integer: " + repr(literal))
    return int(literal.replace(",", ""))


def lines_of(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def statistics(text, unit_expected):
    lines = lines_of(text)
    require(tuple(lines[:5]) == PREFIX, "Changed native election/county/status header")
    unit = lines[5] if unit_expected else None
    require(not unit_expected or bool(unit and unit != "Statistics"), "Missing literal native unit")
    if "Statistics" not in lines:
        return None
    require(lines.count("Statistics") == 1, "Ambiguous statistics block")
    start = lines.index("Statistics") + 1
    require(tuple(lines[start:start + len(HEADER)]) == HEADER, "Changed native statistics columns")
    result = {"native_unit": unit, "measures": {}, "native_header_tokens": list(HEADER)}
    for label in ("Ballots Cast - Total", "Ballots Cast - Blank"):
        occurrences = [index for index, value in enumerate(lines) if value == label]
        if not occurrences:
            require(label.endswith("Blank"), "Missing native Ballots Cast - Total")
            result["measures"][label] = None
            continue
        require(len(occurrences) == 1, "Ambiguous native participation measure")
        offset = occurrences[0] + 1
        literals = lines[offset:offset + len(MODES)]
        require(len(literals) == len(MODES), "Incomplete native participation vector")
        values = [integer(value) for value in literals]
        require(values[0] == sum(values[1:]), "Native mode accounting does not reconcile")
        result["measures"][label] = {
            mode: {"value": value, "literal": literal, "text_line": offset + index + 1}
            for index, (mode, value, literal) in enumerate(zip(MODES, values, literals))
        }
    total, blank = (result["measures"][label] for label in ("Ballots Cast - Total", "Ballots Cast - Blank"))
    if blank is not None:
        require(all(blank[mode]["value"] <= total[mode]["value"] for mode in MODES),
                "Blank ballots exceed native cast ballots")
    result["native_reporting_tokens"] = lines[start + len(HEADER):lines.index("Ballots Cast - Total")]
    return result


def report_clock(text, label, page_number, total_pages):
    pattern = (re.escape(label) + r" - (.+?)\s+"
               + (r"Page " if label == "Custom Table Report" else "")
               + r"([\d,]+) of ([\d,]+)(?:\n|$)")
    matches = list(re.finditer(pattern, text))
    require(len(matches) == 1, "Missing or ambiguous printed report clock/page")
    match = matches[0]
    require(integer(match[2]) == page_number and integer(match[3]) == total_pages,
            "Native report page sequence differs from the original")
    return {"literal": match[1], "timezone": None,
            "qualification": "native_printed_clock_timezone_not_supplied"}


def sovc_statistics(text):
    marker = "STATIST\nICS\nBallots Cast -\nTotal\n"
    if marker not in text:
        return None
    require(text.count(marker) == 1, "Ambiguous SOVC participation block")
    lines = lines_of(text.split(marker, 1)[1].split("Custom Table Report -", 1)[0])
    rows = []
    while lines:
        unit = lines.pop(0)
        require(bool(lines), "Incomplete SOVC participation row")
        literal = lines.pop(0)
        rows.append({"native_unit": unit, "value": integer(literal), "literal": literal})
        if unit == "Totals":
            break
    require(rows, "Empty SOVC participation block")
    return rows


def joined_statistics(text, unit_expected):
    lines = lines_of(text)
    require(tuple(lines[:5]) == PREFIX, "Changed native election/county/status header")
    if not any(line.startswith("Statistics ") for line in lines):
        return None
    header = re.search(
        r"^Statistics\s+(.+?)\n(?=(?:Election Day Precincts Reporting|"
        r"Absentee/ Early Precincts Reporting|Ballots Cast - Total))", text, re.M | re.S)
    require(header is not None and " ".join(header[1].split()) == " ".join(HEADER),
            "Changed joined native statistics columns")
    native_unit = lines[5] if unit_expected else None
    canonical = [*PREFIX, *([native_unit] if unit_expected else []), "Statistics", *HEADER]
    locations = {}
    for label in ("Ballots Cast - Total", "Ballots Cast - Blank"):
        matches = list(re.finditer(r"^" + re.escape(label) + r"[ \t]+([^\n]+)$", text, re.M))
        if not matches:
            require(label.endswith("Blank"), "Missing native Ballots Cast - Total")
            continue
        require(len(matches) == 1, "Ambiguous joined native participation measure")
        match = matches[0]
        literals = match[1].split()
        require(len(literals) == len(MODES), "Incomplete joined native participation vector")
        canonical.extend([label, *literals])
        locations[label] = text[:match.start()].count("\n") + 1
    result = statistics("\n".join(canonical), unit_expected)
    for label, vector in result["measures"].items():
        if vector is not None:
            for cell in vector.values():
                cell["text_line"] = locations[label]
    result["native_reporting_tokens"] = text[
        header.end():text.index("Ballots Cast - Total")].strip().splitlines()
    result["text_reader"] = "pypdf"
    return result


def joined_sovc_statistics(text):
    marker = "STATIST\nICS\nBallots Cast -\nTotal\n"
    if marker not in text:
        return None
    require(text.count(marker) == 1, "Ambiguous joined SOVC participation block")
    body = text.split(marker, 1)[1].split("Custom Table Report -", 1)[0]
    rows = []
    for line in lines_of(body):
        match = re.fullmatch(r"(.+?)\s+([0-9][0-9,]*)", line)
        require(match is not None, "Ambiguous joined SOVC native unit/value")
        rows.append({"native_unit": match[1], "value": integer(match[2]), "literal": match[2]})
        if match[1] == "Totals":
            break
    require(rows, "Empty joined SOVC participation block")
    return rows


def csv_body(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def build(root, output):
    from pypdf import PdfReader

    require(not output.exists(), "Use a fresh output directory")
    originals = root / "private-originals"
    sources, profiles, page_inventory, sovc_rows = {}, {}, [], []
    declarations = (
        ("summary", "jefferson-2026-general-summary.pdf", "Election Summary", 53),
        ("sovc", "jefferson-2026-general-sovc.pdf", "Custom Table Report", 539),
        ("precinct", "jefferson-2026-general-precinct.pdf", "Precinct Summary", 4773),
    )
    for identity, name, label, expected_pages in declarations:
        receipt = json.loads((root / (name + ".receipt.json")).read_bytes())
        require(receipt["status"] == "acquired" and receipt["response"]["status"] == 200,
                "Unqualified native source receipt")
        original = originals / name
        require({"bytes": original.stat().st_size,
                 "sha256": hashlib.sha256(original.read_bytes()).hexdigest()} == receipt["pin"],
                "Changed pinned native original")
        source_profiles = []
        with original.open("rb") as stream:
            document = PdfReader(stream)
            require(len(document.pages) == expected_pages, "Native page inventory changed")
            sources[identity] = {
                "url": receipt["source"]["url"], "pin": receipt["pin"],
                "retrieved_at_utc": receipt["acquired_at"], "pages": len(document.pages),
                "pdf_creation_metadata": str(document.metadata.get("/CreationDate", "")),
                "pdf_creation_offset_is_not_printed_clock_timezone": True,
                "text_reader": "pypdf",
            }
            for index, page in enumerate(document.pages):
                text = page.extract_text()
                clock = report_clock(text, label, index + 1, len(document.pages))
                lines = lines_of(text)
                if identity == "sovc":
                    require(re.match(
                        r"^2026 General Election\s+November 3, 2026\s+Jefferson County\s+"
                        r"STATEMENT OF VOTES CAST\s*Custom Table Report(?:\n|$)", text) is not None,
                        "Changed native SOVC election/county header")
                    block = joined_sovc_statistics(text)
                    if block is not None:
                        sovc_rows.extend(dict(row, page=index + 1, clock=clock) for row in block)
                    unit = None
                else:
                    require(tuple(lines[:5]) == PREFIX, "Changed native source header")
                    unit = lines[5] if identity == "precinct" else None
                    block = joined_statistics(text, identity == "precinct")
                    if block is not None:
                        source_profiles.append(dict(block, page=index + 1, clock=clock))
                page_inventory.append({
                    "source": identity, "page": index + 1, "native_unit": unit,
                    "participation_statistics": block is not None, "clock": clock["literal"],
                })
        profiles[identity] = source_profiles
    require(len(profiles["summary"]) == 1, "County parent inventory changed")
    units = [row["native_unit"] for row in profiles["precinct"]]
    require(len(units) == len(set(units)), "Duplicate native precinct statistical profiles")
    require(set(units) == {row["native_unit"] for row in page_inventory if row["source"] == "precinct"},
            "A native report unit lacks its own statistics block")
    totals = [row for row in sovc_rows if row["native_unit"] == "Totals"]
    children = [row for row in sovc_rows if row["native_unit"] != "Totals"]
    require(len(totals) == 1 and len(children) == len({row["native_unit"] for row in children}),
            "SOVC native parent or unit identities are ambiguous")
    require(set(units) == {row["native_unit"] for row in children}, "SOVC/precinct unit sets differ")
    by_unit = {row["native_unit"]: row for row in profiles["precinct"]}
    comparisons = []
    for row in children:
        other = by_unit[row["native_unit"]]["measures"]["Ballots Cast - Total"]["TOTAL"]["value"]
        comparisons.append({"scope": "native_unit", "native_unit": row["native_unit"],
                            "mode": "TOTAL", "left_source": "sovc", "left_value": row["value"],
                            "right_source": "precinct", "right_value": other,
                            "difference": other - row["value"]})
    county = profiles["summary"][0]["measures"]["Ballots Cast - Total"]
    for mode in MODES:
        observed = sum(row["measures"]["Ballots Cast - Total"][mode]["value"]
                       for row in profiles["precinct"])
        comparisons.append({"scope": "native_county_mode", "native_unit": None, "mode": mode,
                            "left_source": "summary", "left_value": county[mode]["value"],
                            "right_source": "precinct", "right_value": observed,
                            "difference": observed - county[mode]["value"]})
    require(sum(row["value"] for row in children) == totals[0]["value"], "SOVC parent does not reconcile")
    statistical_rows = []
    for source in ("summary", "precinct"):
        for profile in profiles[source]:
            for measure, vector in profile["measures"].items():
                if vector is None:
                    continue
                statistical_rows.extend({
                    "source": source, "page": profile["page"], "native_unit": profile["native_unit"],
                    "measure": measure, "mode": mode, "literal": cell["literal"], "value": cell["value"],
                    "native_text_line": cell["text_line"], "clock": profile["clock"]["literal"],
                } for mode, cell in vector.items())
    fact = {
        "contract": "participation.jefferson_ky_native_statistics.v1", "state_code": "KY",
        "county": "Jefferson", "native_election_date": "2026-11-03",
        "sources": sources, "profiles": profiles, "sovc_participation": sovc_rows,
        "comparisons": comparisons,
        "scope": {
            "native_ballots_not_candidate_votes": True, "registered_denominator": None,
            "turnout_rate": None, "unique_people": None, "native_mail_is_returned_envelopes": False,
            "precinct_labels_are_election_date_geometry": False, "maps_approved": False,
            "separate_report_clocks_are_common_snapshot": False,
            "source_reporting_completeness_is_certification": False,
            "source_summary_status_literal": "UNOFFICIAL RESULTS",
        },
        "inventory": {
            "source_pages": len(page_inventory), "native_precinct_labels": len(units),
            "summary_statistical_profiles": len(profiles["summary"]),
            "precinct_statistical_profiles": len(profiles["precinct"]),
            "statistical_numeric_cells": len(statistical_rows),
            "statistical_literal_zero_cells": sum(row["literal"] == "0" for row in statistical_rows),
            "sovc_participation_rows_including_parent": len(sovc_rows),
            "nonzero_cross_report_differences": sum(row["difference"] != 0 for row in comparisons),
        },
    }
    output.mkdir()
    bodies = {
        "participation-facts.json": (json.dumps(fact, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        "native-statistical-cells.csv": csv_body(statistical_rows, (
            "source", "page", "native_unit", "measure", "mode", "literal", "value", "native_text_line", "clock")),
        "native-sovc-participation.csv": csv_body([
            dict(native_unit=row["native_unit"], value=row["value"], literal=row["literal"],
                 page=row["page"], clock=row["clock"]["literal"]) for row in sovc_rows],
            ("native_unit", "value", "literal", "page", "clock")),
        "native-page-inventory.csv": csv_body(page_inventory, (
            "source", "page", "native_unit", "participation_statistics", "clock")),
        "native-cross-report-comparisons.csv": csv_body(comparisons, (
            "scope", "native_unit", "mode", "left_source", "left_value",
            "right_source", "right_value", "difference")),
    }
    for name, body in bodies.items():
        with (output / name).open("xb") as stream:
            stream.write(body)
    return fact["inventory"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(build(arguments.root, arguments.output), sort_keys=True))
