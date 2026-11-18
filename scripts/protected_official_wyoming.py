"""Complete official Wyoming House choices, separate from ballot accounting."""

import copy
import io
import re
import zipfile

from scripts import native_tabular
from scripts.participation_intake.contract import pin


IDENTITY = "WY-official-house-candidates"
URL = "https://sos.wyo.gov/Elections/Docs/2026/Results/General/2026_Wyoming_General_Results.zip"
FORMAT = "wyoming_general_house_summary_2026.v1"
FACTS_PATH = "data/results-intake/protected-official-house/wy-summary-facts.json.gz"
WORKBOOK = "2026 General Results Summaries - OFFICIAL.xlsx"
MEMBERS = (WORKBOOK, "2026 County General PbP - OFFICIAL.xlsx",
           "2026 County General PbP TBC - OFFICIAL.xlsx")
SHEETS = ("Statewide Total Ballots Cast", "Statewide Candidates", "Statewide Senate Odd",
          "Statewide House", "Statewide Judicial", "Statewide Ballot Issue")
TITLE = "Wyoming General Election - November 3, 2026"
PARTIES = {"R": "Republican", "D": "Democratic",
           "L": "Libertarian", "C": "Constitution"}
COLUMNS = tuple("GHIJKLM")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def count(cell):
    value = cell["value"]
    require(type(value) is int and 0 <= value <= 2**53 - 1
            and cell["storage_type"] == "n"
            and cell["cached_literal"] == str(value),
            "Invalid protected Wyoming native count")
    return value


def selected_table(table, columns):
    rows = []
    for row in table["rows"]:
        cells = [copy.deepcopy(cell) for cell in row["cells"]
                 if re.sub(r"[0-9]+$", "", cell["address"]) in columns]
        if row["row"] <= 28:
            rows.append({"row": row["row"], "cells": cells})
        else:
            require(all(cell["value"] in (None, "") for cell in cells),
                    "Additional Wyoming source rows require review")
    return {"name": table["name"], "member": table["member"], "rows": rows}


def parse(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        require(len(archive.namelist()) == len(set(archive.namelist()))
                and set(archive.namelist()) == set(MEMBERS),
                "Protected Wyoming bulk workbook inventory changed")
        require(sum(row.file_size for row in archive.infolist()) < 50_000_000,
                "Protected Wyoming workbook package is oversized")
        tables = native_tabular.xlsx(archive.read(WORKBOOK))
    require(tuple(table["name"] for table in tables) == SHEETS,
            "Protected Wyoming summary sheet inventory changed")
    require(native_tabular.values(tables[1], 3).get("N") == "Governor",
            "Protected Wyoming House column boundary changed")
    facts = {
        "format": FORMAT, "original": pin(body), "workbook": WORKBOOK,
        "tables": [selected_table(tables[0], ("A", "B")),
                   selected_table(tables[1], ("A", *COLUMNS))],
    }
    return from_facts(facts)


def from_facts(facts):
    require(isinstance(facts, dict)
            and set(facts) == {"format", "original", "workbook", "tables"}
            and facts["format"] == FORMAT and facts["workbook"] == WORKBOOK,
            "Protected Wyoming native fact schema changed")
    original = facts["original"]
    require(isinstance(original, dict) and set(original) == {"bytes", "sha256"}
            and type(original["bytes"]) is int and original["bytes"] > 0
            and isinstance(original["sha256"], str)
            and re.fullmatch(r"[a-f0-9]{64}", original["sha256"]) is not None,
            "Protected Wyoming original pin is missing")
    tables = facts["tables"]
    require(isinstance(tables, list) and len(tables) == 2,
            "Protected Wyoming selected tables are incomplete")
    indexed = []
    for index, (table, columns) in enumerate(zip(tables, (("A", "B"), ("A", *COLUMNS)))):
        require(isinstance(table, dict) and set(table) == {"name", "member", "rows"}
                and table["name"] == SHEETS[index]
                and table["member"] == f"xl/worksheets/sheet{index + 1}.xml"
                and isinstance(table["rows"], list),
                "Protected Wyoming worksheet identity changed")
        rows = {}
        for row in table["rows"]:
            require(isinstance(row, dict) and set(row) == {"row", "cells"}
                    and type(row["row"]) is int and 1 <= row["row"] <= 28
                    and row["row"] not in rows and isinstance(row["cells"], list),
                    "Protected Wyoming native row is ambiguous")
            cells = {}
            for cell in row["cells"]:
                require(isinstance(cell, dict)
                        and set(cell) == {"address", "attributes", "storage_type",
                                         "cached_literal", "value", "formula"},
                        "Protected Wyoming native cell schema changed")
                column = re.sub(r"[0-9]+$", "", cell["address"])
                require(column in columns and cell["address"] == column + str(row["row"])
                        and column not in cells,
                        "Protected Wyoming native cell is ambiguous")
                cells[column] = cell
            rows[row["row"]] = cells
        require(set(rows) == set(range(1, 29)),
                "Protected Wyoming worksheet rows are incomplete")
        indexed.append(rows)
    ballots, choices = indexed
    require(ballots[1]["B"]["value"] == "Statewide Total Ballots Cast\n" + TITLE
            and choices[1]["G"]["value"] == "Statewide Candidates Official Summary\n" + TITLE
            and ballots[4]["B"]["value"] == "Total Ballots Cast"
            and choices[3]["G"]["value"] == "United States Representative",
            "Protected Wyoming election, office or ballot measure changed")
    headers = {column: choices[4][column]["value"] for column in COLUMNS}
    require(headers["K"] == "Write-Ins" and headers["L"] == "Overvotes"
            and headers["M"] == "Undervotes",
            "Protected Wyoming write-in or accounting roles changed")
    candidates = []
    for column in "GHIJ":
        name = headers[column]
        require(isinstance(name, str), "Protected Wyoming candidate name is missing")
        match = re.fullmatch(r".+ \(([RDLC])\)", name, re.S)
        require(match is not None, "Unreviewed protected Wyoming candidate party")
        party = match[1]
        candidates.append({
            "candidate_id": column + "4", "name": name, "name_literal": name,
            "literal_party": PARTIES[party], "party_literal": party,
            "native_candidate_sequence": column,
            "party_basis": "Explicit native candidate-name suffix, not provider party allocation.",
            "party_group": party if party in "DR" else "O",
            "votes": count(choices[28][column]),
            "votes_literal": choices[28][column]["cached_literal"], "role": "named_candidate",
        })
    candidates.append({
        "candidate_id": "K4", "name": "Write-Ins", "name_literal": "Write-Ins",
        "literal_party": "", "party_literal": "", "native_candidate_sequence": "K",
        "party_basis": "Native unassigned write-ins; no individual or party allocation.",
        "party_group": "O", "votes": count(choices[28]["K"]),
        "votes_literal": choices[28]["K"]["cached_literal"], "role": "generic_write_in",
    })
    require(len({row["name"] for row in candidates}) == 5
            and sorted(row["literal_party"] for row in candidates) ==
            ["", "Constitution", "Democratic", "Libertarian", "Republican"],
            "Protected Wyoming complete candidate inventory changed")
    counties = []
    for number in range(5, 28):
        name = ballots[number]["A"]["value"]
        require(isinstance(name, str) and name and choices[number]["A"]["value"] == name,
                "Protected Wyoming county identity mismatch")
        vector = {column: count(choices[number][column]) for column in COLUMNS}
        total = count(ballots[number]["B"])
        require(sum(vector.values()) == total,
                "Protected Wyoming county candidate and ballot accounting differs")
        counties.append({"county": name, "physical_row": number, "ballots": total,
                         "house_columns": vector})
    require(len({row["county"] for row in counties}) == 23
            and ballots[28]["A"]["value"] == choices[28]["A"]["value"] == "Total",
            "Protected Wyoming county or state-total inventory changed")
    native_ballots = count(ballots[28]["B"])
    require(sum(row["ballots"] for row in counties) == native_ballots
            and all(sum(row["house_columns"][column] for row in counties) ==
                    count(choices[28][column]) for column in COLUMNS),
            "Protected Wyoming county-to-state controls differ")
    candidate_total = sum(row["votes"] for row in candidates)
    overvotes, undervotes = count(choices[28]["L"]), count(choices[28]["M"])
    require(candidate_total + overvotes + undervotes == native_ballots,
            "Protected Wyoming state ballot accounting differs")
    race = {
        "state_code": "WY", "district": "WY-AL", "seat": "0",
        "native_contest_id": "G3", "native_office_label": "United States Representative",
        "candidate_identity_basis": "Native worksheet cell addresses, not published candidate IDs.",
        "election_date": "2026-11-03", "stage": "general", "election_kind": "regular",
        "native_status_literal": "Official Summary", "source_update_label": None,
        "source_update_timezone": None, "source_updated_at": None,
        "reported_units": None, "total_units": None, "partial_units": None,
        "complete_reporting": None, "candidates": candidates, "contest_total": candidate_total,
        "contest_total_literal": None,
        "contest_total_basis": "Complete named choices plus unassigned write-ins; not total ballots.",
        "native_contest_controls": {"counties": counties, "ballots": native_ballots,
                                    "overvotes": overvotes, "undervotes": undervotes},
    }
    return {
        "contract": "participation.official_congressional_candidate_evidence.v1",
        "election_date": "2026-11-03", "source_updated_at": None,
        "source_clock_supplied": False, "races": [race], "native_facts": copy.deepcopy(facts),
        "participation_observation_qualified": False, "conditional_model_eligible": False,
        "candidate_votes_are_not_ballots_or_turnout": True,
        "provider_other_equivalence_qualified": False,
        "holds": [
            "No native count timestamp, reporting counters or separate certification evidence is supplied.",
            "Official is a literal workbook label, not inferred completed counting.",
            "Unassigned write-ins remain blank-party Other; overvotes and undervotes are separate.",
            "County labels are not FIPS, a precinct crosswalk or demographic allocation.",
        ],
    }


def collect(collector):
    from scripts.protected_official_house import check_revision

    def guarded(body):
        data = parse(body)
        prior = (collector.prior.get(IDENTITY) or {}).get("data") or {}
        check_revision(prior, data)
        return data

    return collector.capture(IDENTITY, URL, guarded)
