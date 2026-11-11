"""Freeze complete factual report grids, excluding app code and contact prose."""

import hashlib
import re
from pathlib import Path


ORIGINALS = {
    "DC-september-registration": "01bb45649cd0c342cfce466b5870754fdef04ba8e7b1f1fff0db8c8ff972b929",
    "DC-early": "6449f9c0b852826fbb240793d3da3613b0521bbee65bcc6bf2ade7c1a7044306",
    "DC-election-day": "2cc8897e680c623fa2d9d230cc747ba9575b320f080e865868920acb2a1ace00",
    "DC-dropbox": "1f3a539145a51103f8755d9f5e77a90f5fef8660031bcef34259f39ea5a4accf",
    "DC-usps": "4ece1fc191586e6dd58bd46d5eb6835f8956dc941d83a04e6e3e35f11baabe8c",
}
SCOPES = {
    "DC-september-registration": ("AS OF SEPTEMBER 30, 2026", "REGISTRATION SUMMARY"),
    "DC-early": ("EARLY VOTE CENTERS - 2026 GENERAL ELECTION",),
    "DC-election-day": ("GENERAL ELECTION 2026", "ELECTION DAY TURNOUT BY VOTE CENTER"),
    "DC-dropbox": ("2026 General Election", "Ballots Received by Drop Box/Ward"),
    "DC-usps": ("GENERAL ELECTION 2026", "BALLOTS RECEIVED BY USPS"),
}


def normalized(value):
    return " ".join(value.split()) if value else None


def comparable(view):
    return [dict(id=report["id"], source_sha256=report["source_sha256"],
                 pages=[dict(page=page["page"], native_scope=page["native_scope"],
                     tables=[[[normalized(cell) for cell in row] for row in table["rows"]]
                             for table in page["tables"]],
                     external=page["external"]) for page in report["pages"]])
            for report in view["reports"]]


def extract(source, engine):
    if engine not in {"mupdf", "pdfplumber"}:
        raise ValueError("Unknown independent PDF reader")
    if engine == "mupdf":
        import fitz
    else:
        import pdfplumber
    reports = []
    for name, digest in ORIGINALS.items():
        path = Path(source) / (name + "-body.bin")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Changed original native PDF")
        document = fitz.open(path) if engine == "mupdf" else pdfplumber.open(path)
        pages = []
        with document:
            for number in range(len(document) if engine == "mupdf" else len(document.pages)):
                page = document[number] if engine == "mupdf" else document.pages[number]
                text = page.get_text() if engine == "mupdf" else page.extract_text()
                plain = " ".join(text.split())
                if any(scope not in plain for scope in SCOPES[name]):
                    raise ValueError("Changed source title/date/measure")
                tables = page.find_tables()
                tables = tables.tables if engine == "mupdf" else tables
                frozen = [dict(bbox=list(table.bbox), rows=table.extract()) for table in tables]
                external = {}
                if name == "DC-september-registration":
                    ward = re.search(r"WARD ([1-8]) REGISTRATION SUMMARY", plain)
                    if ward:
                        external["native_registration_scope"] = "ward"
                        external["native_registration_ward"] = ward.group(1)
                    elif "CITYWIDE REGISTRATION SUMMARY" in plain:
                        external["native_registration_scope"] = "citywide"
                        external["native_registration_ward"] = None
                    else:
                        raise ValueError("Missing explicit native registration ward/citywide header")
                if name == "DC-election-day":
                    match = re.search(r"ELECTION DAY IN-PERSON\s+(\d+)", plain)
                    if not match:
                        raise ValueError("Missing explicit native Election Day parent")
                    external["native_election_day_parent"] = int(match.group(1))
                if name == "DC-early":
                    if len(tables) != 1:
                        raise ValueError("Changed native early-voting grid")
                    table = tables[0]
                    words = page.get_text("words") if engine == "mupdf" else page.extract_words()
                    labels = []
                    for row in table.rows[1:-1]:
                        x0, top, _, bottom = row.cells[0]
                        candidates = []
                        for word in words:
                            left, center, value = ((word[0], (word[1] + word[3]) / 2, word[4])
                                if engine == "mupdf" else
                                (word["x0"], (word["top"] + word["bottom"]) / 2, word["text"]))
                            if x0 - 45 <= left < x0 and top <= center <= bottom and re.fullmatch("[1-8]", value):
                                candidates.append(value)
                        if len(candidates) != 1:
                            raise ValueError("Missing or ambiguous source location-ward label")
                        labels.append(candidates[0])
                    external["native_location_ward_labels"] = labels
                pages.append(dict(page=number + 1, native_scope=list(SCOPES[name]),
                                  tables=frozen, external=external))
        reports.append(dict(id=name, source_sha256=digest, pages=pages))
    return dict(schema="dc-native-factual-grids-v1", reader=engine, reports=reports)
