"""Reconcile EAC county time-series observations to direct jurisdiction reports."""

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import io
import json
from pathlib import Path
import re
import zipfile
from xml.parsers.expat import ParserCreate

from scripts.participation_intake.contract import encoded, pin


COUNTY = {1: "State Abbreviation", 3: "County Name", 4: "FIPS County Code", 5: "Year",
          6: "Total Registered Voters", 452: "Total Voters Who Cast a Ballot That Was Counted",
          465: "Source of Voter Participation Data, Votes Cast for Highest Office on Ballot"}
JURISDICTION = {1: "FIPSCode", 3: "State_Abbr", 4: "Jurisdiction_Name", 5: "Year",
                6: "regist_tot", 452: "turnout_tot", 465: "source_votescast"}
LOCAL_SOURCE_FLAGS = {462: "source_pollbook", 463: "source_ballots", 464: "source_votehistory",
                      467: "source_oth"}
LOCAL_FIPS = {"CT": "09", "ME": "23", "MA": "25", "NH": "33", "RI": "44", "VT": "50", "WI": "55"}
LOCAL_CSV = "participation-eac-locality-history.csv"
FIELDS = ("state", "year", "county_fips", "county_name", "county_registered", "county_turnout",
          "county_highest_office_flag", "county_workbook_row", "direct_workbook_row",
          "direct_name", "direct_registered", "direct_turnout", "direct_highest_office_flag", "decision",
          "direct_reported_turnout", "same_report_registration_fraction_pct")
INPUT = "data/results-intake/historical-eac-county-facts.json.gz"
CONTRACT = "participation.eac_county_counted_ballot_reconciliation.v1"
SOURCE_ROOT = "https://www.eac.gov/sites/default/files/2026-09/"
SOURCES = {
    "county": SOURCE_ROOT + "EAVS_Time_Series_County_Collapse_2004_2024_Appended_Labels.xlsx",
    "jurisdiction": SOURCE_ROOT + "EAVS_Time_Series_2004_2024.xlsx",
}
GUIDE = SOURCE_ROOT + "EAVS_Time_Series_User_Guide_v2.1.docx"


def cells(workbook, columns):
    """Stream only the selected cells from the two large EAC worksheets."""
    names = {}
    for n in columns:
        key, value = "", n
        while value:
            value, digit = divmod(value - 1, 26)
            key = chr(65 + digit) + key
        names[key] = n
    with zipfile.ZipFile(workbook) as archive:
        import xml.etree.ElementTree as ET

        strings = ["".join(node.text or "" for node in item.iter()
                           if node.tag.endswith("}t"))
                   for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        rows, selected, row, active, text = [], {}, None, None, None

        def start(tag, attrs):
            nonlocal selected, row, active, text
            if tag == "row":
                row = int(attrs["r"])
                selected = {}
            elif tag == "c" and row is not None:
                column = names.get(attrs["r"].rstrip("0123456789"))
                active = (column, attrs.get("t"))
            elif tag == "v" and active and active[0]:
                text = []

        def end(tag):
            nonlocal row, active, text
            if tag == "v" and text is not None:
                value = "".join(text)
                column, kind = active
                if kind == "s":
                    value = strings[int(value)]
                elif kind not in (None, "n"):
                    raise ValueError(f"Unexpected EAC cell encoding at row {row}: {kind}")
                selected[column] = value
                text = None
            elif tag == "c":
                active = None
            elif tag == "row":
                rows.append([row, *(selected.get(n) for n in columns)])
                row = None

        def characters(data):
            if text is not None:
                text.append(data)

        parser = ParserCreate()
        parser.StartElementHandler, parser.EndElementHandler = start, end
        parser.CharacterDataHandler = characters
        with archive.open("xl/worksheets/sheet1.xml") as source:
            parser.ParseFile(source)
    if not rows or rows[0] != [1, *columns.values()]:
        raise ValueError("Unexpected EAC workbook columns")
    return rows[1:]


def integer(raw):
    return int(raw) if isinstance(raw, str) and re.fullmatch(r"[0-9]+", raw) else None


def name_key(raw):
    return re.sub(r"[^A-Z0-9]", "", re.sub(r"\s+(COUNTY|PARISH|BOROUGH)$", "", raw.upper().strip()))


def reconcile(counties, jurisdictions):
    by_county = defaultdict(list)
    for source_row, fips, state, name, year, registered, turnout, highest in jurisdictions:
        if fips and re.fullmatch(r"[0-9]{10}", fips):
            by_county[state, year, fips[:5]].append((source_row, fips, name, registered, turnout, highest))
    identities = Counter((state, year, fips) for _, state, _, fips, year, *_ in counties)
    for row, state, name, fips, year, registered, turnout, highest in counties:
        if not state or integer(year) not in range(2004, 2025, 2):
            raise ValueError(f"Unexpected EAC county identity at row {row}: {(state, name, fips, year)}")
        key = state, year, fips
        county_scope = (name and fips and re.fullmatch(r"[0-9]{5}", fips)
                        and not fips.endswith("000") and not name.upper().startswith("UOCAVA"))
        candidates = by_county.get(key, [])
        direct = [r for r in candidates if r[1] == fips + "00000" and r[2]
                  and name and name_key(r[2]) == name_key(name)]
        native_row, _, native_name, native_registered, native_turnout, native_highest = (
            direct[0] if len(direct) == 1 else (None,) * 6)
        votes, stock = integer(turnout), integer(registered)
        if not county_scope:
            decision = "not_a_county_scope"
        elif identities[key] != 1:
            decision = "ambiguous_county_workbook_identity"
        elif len(direct) != 1 or len(candidates) != 1:
            decision = "no_unambiguous_direct_county_report"
        elif votes is None:
            decision = "county_turnout_missing_or_noninteger"
        elif votes != integer(native_turnout):
            decision = "direct_and_county_turnout_disagree"
        elif any((integer(value) or 0) > 0 for value in (highest, native_highest)):
            decision = "highest_office_source_reported"
        else:
            decision = "reconciled_direct_county_turnout"
        direct_turnout = votes if decision == "reconciled_direct_county_turnout" else None
        fraction = (100 * direct_turnout / stock if direct_turnout is not None and stock
                    and highest == native_highest == "0"
                    and direct_turnout <= stock and stock == integer(native_registered) else None)
        yield dict(zip(FIELDS, (state, year, fips, name, registered, turnout, highest, row, native_row,
                                native_name, native_registered, native_turnout, native_highest, decision,
                                direct_turnout, fraction)))


def compressed(body):
    result = bytearray(gzip.compress(body, mtime=0))
    result[9] = 3
    return bytes(result)


def locality_rows(packet):
    """Keep local source flags and native records, without implying a polygon match."""
    local = packet.get("localities")
    if local is None:
        return []
    prior = {row[0]: row for row in packet["jurisdiction"] if row[2] in LOCAL_FIPS}
    if len(local) != len(prior) or sorted(row[0] for row in local) != sorted(prior):
        raise ValueError("Incomplete EAC local jurisdiction facts")
    identities = Counter((state, year, fips) for _, fips, state, _, year, *_ in local)
    source = packet["sources"]["jurisdiction"]
    result = []
    for row in local:
        number, fips, state, name, year, registration, turnout, highest, pollbook, ballots, history, other = row
        if row[:8] != prior[number] or any(value not in {None, "0", "1", "-66", "-77", "-88", "-99"}
                                           for value in (highest, pollbook, ballots, history, other)):
            raise ValueError("EAC local facts differ from reviewed jurisdiction source or flags")
        n, d = integer(turnout), integer(registration)
        if not (fips and re.fullmatch(LOCAL_FIPS[state] + r"\d{8}", fips)
                and fips[2:5] != "000" and fips[5:] != "00000"):
            hold = "no_county_subdivision_identifier"
        elif identities[state, year, fips] != 1 or not name:
            hold = "ambiguous_jurisdiction_identity"
        elif n is None:
            hold = "missing_count"
        elif highest == "1":
            hold = "highest_office_source_reported"
        elif highest != "0" or ballots != "1":
            hold = "ballot_count_source_not_confirmed"
        else:
            hold = None
        rate_hold = "count_withheld" if hold else "invalid_same_report_registration" if (
            not d or n > d) else None
        result.append({
            "state_code": state, "year": year, "native_name": name, "native_fips": fips,
            "native_row": number, "reported_turnout_literal": turnout, "registered_literal": registration,
            "source_votescast": highest, "source_pollbook": pollbook, "source_ballots": ballots,
            "source_votehistory": history, "source_oth": other, "count_hold": hold, "rate_hold": rate_hold,
            "reported_counted_ballot_participants": None if hold else n,
            "same_report_registration_fraction_pct": None if rate_hold else 100 * n / d,
            "source_url": source["url"], "source_sha256": source["sha256"],
            "geographic_match_claimed": False,
        })
    return result


def exports(body):
    packet = json.loads(gzip.decompress(body))
    if (packet.get("contract") != CONTRACT or set(packet["sources"]) != set(SOURCES)
            or any(packet["sources"][name]["url"] != url for name, url in SOURCES.items())):
        raise ValueError("Invalid reviewed EAC county inputs")
    rows = list(reconcile(packet["county"], packet["jurisdiction"]))
    csv_file = io.StringIO(newline="")
    writer = csv.DictWriter(csv_file, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    queries = compressed(csv_file.getvalue().encode())
    direct = [row for row in rows if row["direct_reported_turnout"] is not None]
    rates = [row for row in direct if row["same_report_registration_fraction_pct"] is not None]
    report = {
        "contract": CONTRACT,
        "county_rows": len(rows),
        "direct_count_rows": len(direct),
        "direct_count_jurisdictions": sorted({row["state"] for row in direct}),
        "same_report_registration_fraction_rows": len(rates),
        "decisions": dict(Counter(row["decision"] for row in rows)),
        "election_years": sorted({int(row["year"]) for row in rows}),
        "inputs": packet["sources"],
        "source_guide": GUIDE,
        "no_county_boundary_equivalence_inferred": True,
        "source_registered_voter_fraction_not_populational_turnout": True,
        "held_rows_are_not_zero": True,
        "historical_not_2026": True,
    }
    files = {"participation/eac-county-year-decisions.csv.gz": queries,
             "participation/eac-county-year-summary.json": encoded(report)}
    return files, {**report, "downloads": {name: {"path": name, **pin(data)} for name, data in files.items()}}


def build(county, jurisdiction, output):
    detailed = cells(jurisdiction, {**JURISDICTION, **LOCAL_SOURCE_FLAGS})
    packet = {"contract": CONTRACT, "county": cells(county, COUNTY),
              "jurisdiction": [row[:1 + len(JURISDICTION)] for row in detailed],
              "localities": [row for row in detailed if row[2] in LOCAL_FIPS],
              "sources": {name: {"url": SOURCES[name], **pin(path.read_bytes())}
                          for name, path in (("county", county), ("jurisdiction", jurisdiction))}}
    body = compressed(encoded(packet))
    files, report = exports(body)
    output.mkdir()
    (output / Path(INPUT).name).write_bytes(body)
    for path, data in files.items():
        (output / Path(path).name).write_bytes(data)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county", type=Path, required=True)
    parser.add_argument("--jurisdiction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.county, args.jurisdiction, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
