"""Reviewed, seat-aware Senate references from complete official publications."""

import copy
import re
from collections import Counter, defaultdict
from pathlib import Path

from scripts.participation_intake.contract import pin


CONTRACT = "participation.congressional_historical_baselines.v1"
PARTIES = {
    "D": "D", "DEM": "D", "DFL": "D", "R": "R",
    "DEM/IP/WF": "D", "D/IP/WF": "D", "D/IP": "D", "R/CON": "R",
}
SPECIAL_CLASSES = {2020: {"AZ": "3", "GA": "3"}, 2022: {"CA": "3", "OK": "2"}}
FEC_URL = "https://www.fec.gov/resources/cms-content/documents/federalelections{}.xlsx"
NEBRASKA_URL = (
    "https://sos.nebraska.gov/sites/default/files/doc/elections/2024/"
    "2024%20General%20Canvass%20Book.pdf"
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def count(value):
    return type(value) in (int, float) and value >= 0 and int(value) == value


def fec_records(path, year):
    import openpyxl

    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = [sheet for sheet in book if "US Senate Results by State" in sheet.title]
        require(len(sheets) == 1, "Missing unique FEC Senate worksheet")
        sheet = sheets[0]
        rows = [list(row) for row in sheet.values]
        require(rows[0][1] == "STATE ABBREVIATION" and rows[0][10] == "PARTY"
                and str(rows[0][15]).strip() == "GENERAL VOTES"
                and "RUNOFF" in rows[0][17], "Changed FEC native columns")
        records = []
        for number, row in enumerate(rows[1:], 2):
            if not (isinstance(row[1], str) and row[3] and row[8] and row[10]):
                continue
            office = str(row[3]).upper()
            require(office.startswith("S"), "Wrong office in FEC Senate sheet")
            special = "UNEXPIRED" in office
            seat = SPECIAL_CLASSES[year].get(row[1]) if special else {
                2020: "2", 2022: "3"}[year]
            for column, stage in ((15, "general"), (17, "general_runoff")):
                if not count(row[column]):
                    continue
                records.append({
                    "state_code": row[1], "seat": seat,
                    "election_kind": "special" if special else "regular",
                    "cycle_year": year, "year": 2021 if year == 2020
                    and row[1] == "GA" and stage == "general_runoff" else year,
                    "stage": stage, "round": "not_ranked",
                    "native_office": row[3], "fec_candidate_id": row[4],
                    "candidate": row[8], "literal_party": row[10],
                    "party_group": PARTIES.get(str(row[10]).strip().upper(), "O"),
                    "votes": int(row[column]), "native_row": number,
                    "native_column": column, "native_footnote": row[23],
                    "ranked_choice": year == 2022 and row[1] == "AK",
                    "source_url": FEC_URL.format(year),
                })
        return {
            "source_url": FEC_URL.format(year),
            "original": {"path": "fec-{}.xlsx".format(year), **pin(Path(path).read_bytes())},
            "worksheet": sheet.title, "header": rows[0], "native_rows": rows,
            "candidate_stage_records": records,
        }
    finally:
        book.close()


def nebraska_records(path):
    from pypdf import PdfReader

    pages = []
    records = []
    for number, page in enumerate(PdfReader(path).pages, 1):
        text = page.extract_text() or ""
        if not re.search(
                r"Member of the United States Senate\s*[\u2013-]\s*"
                r"(?:Six|Two) Year Term\s*\n\s*County\s*\n", text):
            continue
        require("General Election" in text and "November 5, 2024" in text,
                "Wrong Nebraska election")
        if "Six Year Term" in text:
            seat, kind = "1", "regular"
            candidates = [("Deb Fischer", "Republican", "R"),
                          ("Dan Osborn", "By Petition", "O"),
                          ("Write-In Scatterings", "Write-In", "O")]
            require(all(label in text for label in
                        ("Deb Fischer", "Dan Osborn", "(Republican)", "(By Petition)")),
                    "Changed Nebraska regular-seat candidate header")
        elif "Two Year Term" in text:
            seat, kind = "2", "special"
            candidates = [("Pete Ricketts", "Republican", "R"),
                          ("Preston Love Jr.", "Democratic", "D")]
            require(all(label in text for label in
                        ("Pete Ricketts", "Preston Love Jr.", "(Republican)", "(Democratic)")),
                    "Changed Nebraska special-seat candidate header")
        else:
            raise ValueError("Unreviewed Nebraska Senate term")
        width = len(candidates)
        lines = []
        for line in text.splitlines():
            match = re.fullmatch(r"\s*([A-Za-z][A-Za-z ]*?)\s+"
                                 + r"\s+".join([r"([0-9][0-9,]*)"] * width) + r"\s*", line)
            if match:
                lines.append({"county": match[1].strip(),
                              "counts": [int(v.replace(",", "")) for v in match.groups()[1:]]})
        totals = [row for row in lines if row["county"] == "Total"]
        counties = [row for row in lines if row["county"] != "Total"]
        require(len(totals) == 1 and len(counties) == 93
                and len({row["county"] for row in counties}) == 93,
                "Incomplete Nebraska statewide/county Senate table")
        require([sum(row["counts"][i] for row in counties) for i in range(width)]
                == totals[0]["counts"], "Nebraska county and native parent counts differ")
        pages.append({"physical_page": number, "seat": seat, "election_kind": kind,
                      "native_rows": lines, "candidate_headers": candidates})
        for index, (name, literal, group) in enumerate(candidates):
            records.append({
                "state_code": "NE", "seat": seat, "election_kind": kind,
                "cycle_year": 2024, "year": 2024, "stage": "general",
                "round": "not_ranked", "ranked_choice": False,
                "candidate": name, "literal_party": literal, "party_group": group,
                "votes": totals[0]["counts"][index], "physical_page": number,
                "source_url": NEBRASKA_URL,
            })
    require(len(pages) == 2, "Both Nebraska Senate contests must be retained")
    return {"source_url": NEBRASKA_URL,
            "original": {"path": "nebraska-2024.pdf", **pin(Path(path).read_bytes())},
            "senate_tables": pages, "candidate_stage_records": records}


def compile_baselines(fec2020, fec2022, nebraska2024):
    datasets = [fec_records(fec2020, 2020), fec_records(fec2022, 2022),
                nebraska_records(nebraska2024)]
    grouped = defaultdict(list)
    for dataset in datasets:
        for row in dataset["candidate_stage_records"]:
            grouped[(row["state_code"], row["seat"], row["cycle_year"],
                     row["election_kind"], row["stage"])].append(row)
    references = []
    for (state, seat, cycle, kind, stage), rows in sorted(
            grouped.items(), key=lambda item: tuple(str(v) for v in item[0])):
        totals = {party: sum(row["votes"] for row in rows if row["party_group"] == party)
                  for party in "DRO"}
        nominees = Counter(row["party_group"] for row in rows)
        references.append({
            "state_code": state, "seat": seat, "cycle_year": cycle,
            "year": rows[0]["year"], "election_kind": kind, "stage": stage,
            "round": "not_ranked", "counts": totals,
            "ranked_choice": any(row["ranked_choice"] for row in rows),
            "major_party_nominees": {party: nominees[party] for party in "DR"},
            "candidate_facts": copy.deepcopy(rows),
            "source_urls": sorted({row["source_url"] for row in rows}),
            "fusion_labels_preserved": True,
            "party_classification": "reviewed_literal_FEC_labels_not_independent_to_major_party",
        })
    return {"contract": CONTRACT, "version": "20261116-01",
            "datasets": datasets, "references": references,
            "class_basis": "FEC Senate races six-year-cycle tables; native special/full-term labels",
            "regular_cycle_classes": {"2020": "2", "2022": "3", "2024": "1"},
            "special_classes": SPECIAL_CLASSES,
            "final_election_comparison_policy": (
                "Use the latest completed same-seat election, including intervening specials. "
                "A decisive general runoff is compared only as explicitly labeled "
                "final-election-to-final-election, never as the preliminary general round."),
            "behavioral_model_eligibility_granted": False}


def select_reference(baselines, state, seat):
    require(baselines.get("contract") == CONTRACT, "Wrong Senate baseline contract")
    rows = [row for row in baselines["references"]
            if row["state_code"] == state and row["seat"] == seat]
    if not rows:
        return None
    latest = max(row["cycle_year"] for row in rows)
    rows = [row for row in rows if row["cycle_year"] == latest]
    runoffs = [row for row in rows if row["stage"] == "general_runoff"]
    selected = runoffs or [row for row in rows if row["stage"] == "general"]
    require(len(selected) == 1, "Ambiguous same-seat historical election")
    return copy.deepcopy(selected[0])
