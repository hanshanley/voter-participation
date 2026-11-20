"""Reconcile Nebraska's printed county registration and voting tables."""

import io
from pathlib import Path
import re

from scripts.participation_intake.contract import count, encoded, pin
from scripts import results_pdf_archive_ocr as scan

INDEX = "https://sos.nebraska.gov/previous-elections"
BASE = "https://sos.nebraska.gov/sites/default/files/doc/elections/"
LIBRARY = "https://govdocs.nebraska.gov/epubs/s1200/"
PAIRED_ELECTION = "2002-11-05"
BLUE_BOOK = "https://govdocs.nebraska.gov/epubs/L3000/D001-200203.pdf"
CURRENT = "2026-11-03"
BOOKS = {
    "2000-11-07": LIBRARY + "S001-2000prim_gen.pdf",
    PAIRED_ELECTION: LIBRARY + "S001-2002prim_gen.pdf",
    "2004-11-02": LIBRARY + "S001-2004prim_gen.pdf",
    "2006-11-07": BASE.removesuffix("elections/") + "2006%20General.pdf",
    "2008-11-04": "2008%20General%20Canvass%20Book.pdf",
    "2010-11-02": "2010%20Gen%20Canvass%20Book%2011-30-Final.pdf",
    "2012-11-06": "2012-general-canvass.pdf",
    "2014-11-04": "2014-General-Canvass-Recount-Final.pdf",
    "2016-11-08": "2016-canvass-book.pdf",
    "2018-11-06": "2018-general-election-official-results.pdf",
    "2020-11-03": "2020-General-Canvass-Book.pdf",
    "2022-11-08": "2022%20General%20Canvass%20Book.pdf",
    "2024-11-05": "2024%20General%20Canvass%20Book.pdf",
    CURRENT: None,
}
CURRENT_FEED = "NE-2026-general-election-canvass"
COUNTIES = (
    "Adams|Antelope|Arthur|Banner|Blaine|Boone|Box Butte|Boyd|Brown|Buffalo|Burt|Butler|Cass|Cedar|Chase|"
    "Cherry|Cheyenne|Clay|Colfax|Cuming|Custer|Dakota|Dawes|Dawson|Deuel|Dixon|Dodge|Douglas|Dundy|"
    "Fillmore|Franklin|Frontier|Furnas|Gage|Garden|Garfield|Gosper|Grant|Greeley|Hall|Hamilton|Harlan|Hayes|"
    "Hitchcock|Holt|Hooker|Howard|Jefferson|Johnson|Kearney|Keith|Keya Paha|Kimball|Knox|Lancaster|Lincoln|"
    "Logan|Loup|Madison|McPherson|Merrick|Morrill|Nance|Nemaha|Nuckolls|Otoe|Pawnee|Perkins|Phelps|Pierce|"
    "Platte|Polk|Red Willow|Richardson|Rock|Saline|Sarpy|Saunders|Scotts Bluff|Seward|Sheridan|Sherman|Sioux|"
    "Stanton|Thayer|Thomas|Thurston|Valley|Washington|Wayne|Webster|Wheeler|York"
).split("|")
CSV = "participation-ne-2026-county-canvass.csv"
MAX_BYTES = 16_000_000
AUTHORITY = ("Official Report", "State Canvassers", "State of Nebraska", "General Election")
SCANS = {
    "2000-11-07": {
        "cover_page": 65,
        "cover_headings": (*AUTHORITY, "November 7, 2000"),
        "native_controls": {"registered": 7},
        "aliases": {"deue": "deuel", "dougias": "douglas", "harian": "harlan", "hoit": "holt",
                    "pawnce": "pawnee", "whceler": "wheeler", "knor": "knox",
                    "greeiey": "greeley", "mofrill": "morrill"},
        "tables": {
            "registered": (
                (67, ("Number of Registered Voters", "Registered Republican Democrat"),
                 ("TOTAL", *COUNTIES[:45]), (60, 82), (163, 175)),
                (68, ("Registered Republican Democrat",), ("TOTAL", *COUNTIES[45:]),
                 (102, 125), (207, 218)),
            ),
            "voted": (
                (69, ("Number of People Voting", "Total Voting"),
                 ("TOTAL", *COUNTIES[:45]), (60, 96), (450, 470)),
                (70, ("Total Voting", "At Polls"), ("TOTAL", *COUNTIES[45:]),
                 (100, 138), (493, 515)),
            ),
        },
    },
    "2004-11-02": {
        "cover_page": 55,
        "cover_headings": (*AUTHORITY, "November 2, 2004"),
        "aliases": {},
        "tables": {
            "registered": (
                (59, ("Number of Registered Voters", "Total Registered"),
                 ("TOTAL", *COUNTIES[:45]), (45, 69), (226, 240)),
                (60, ("County Precincts Total Registered",), COUNTIES[45:], (45, 69), (226, 240)),
            ),
            "voted": (
                (61, ("Total Voters by Location", "Total Voting"),
                 ("TOTAL", *COUNTIES[:45]), (80, 153), (528, 540)),
                (62, ("County At the Polls", "Total Voting"), COUNTIES[45:], (80, 155), (528, 541)),
            ),
        },
    },
    "2006-11-07": {
        "cover_page": 0,
        "cover_headings": (*AUTHORITY, "November 7, 2006"),
        "aliases": {"fumas": "furnas", "mermick": "merrick", "poik": "polk", "morill": "morrill"},
        "tables": {
            "registered": (
                (10, ("Number of Registered Voters", "Nebraska Total"),
                 ("TOTAL", *COUNTIES[:45]), (68, 105), (480, 503)),
                (11, ("Precincts Republican", "Nebraska Total"),
                 COUNTIES[45:], (68, 105), (480, 503)),
            ),
            "voted": (
                (12, ("Total Voting By Location", "Polls Overseas Voting Voting"),
                 ("TOTAL", *COUNTIES[:47]), (48, 105), (262, 298)),
                (12, ("Total Voting By Location", "Polls Overseas Voting Voting"),
                 COUNTIES[47:], (305, 361), (519, 557)),
            ),
        },
    },
}
REGISTRATION = {
    2008: ("County Democrat Green Libertarian Nebraska Nonpartisan Republican Total", 7),
    2010: ("County Republican Democrat Nonpartisan Libertarian Grand Total", 5),
    2012: ("County Republican Democratic Nonpartisan Libertarian Americans Elect Total", 6),
    2014: ("County Precincts Republican Democratic Nonpartisan Libertarian Total", 6),
    2016: ("Precincts Republican Democratic Libertarian Nonpartisan Total", 6),
    2018: ("County Precincts Republican Democratic Libertarian Nonpartisan Total", 6),
    2020: ("County Precincts Republican Democratic Libertarian Nonpartisan Total", 6),
    2022: ("County Precincts Republican Democratic Libertarian NOW Nonpartisan Total", 7),
    2024: ("County Precincts Republican Democratic Libertarian NOW Nebraska Nonpartisan Total", 8),
}
VOTING = {
    2008: ("County At the Polls (EV) Absentees Military/Overseas New/Former Resident Total Voting", 5),
    2010: ("County Voters at the Polls Early Voters Military Early Voters Total Voting", 4),
    2012: ("County At the Polls Early Voters Military New/Former Resident Total Voting", 5),
    2014: ("County At Polls Mail Provisional Early Voting Military/Overseas Total Voting", 6),
    2016: ("Precincts Provisional Early Overseas Resident Total Voting", 7),
    2018: ("County At Polls Precincts Provisional Early Voting Overseas Total Voting", 6),
    2020: ("County At Polls Precincts Provisional Early Voting Overseas Resident Total Voting", 7),
    2022: ("County At Polls Precincts Provisional Early Voting Overseas Total Voting", 6),
    2024: ("County Place Voting Precincts Ballot & Overseas Resident Voting", 7),
}


def routes(election):
    year = election[:4]
    root = re.escape(BASE + year + "/")
    filename = BOOKS[election]
    if filename and filename.startswith(LIBRARY):
        return LIBRARY + "s001.html", re.escape(filename)
    if filename and filename.startswith("https://"):
        return INDEX, re.escape(filename)
    return INDEX, root + (re.escape(filename) if filename else r"[^/?#]{1,140}\.pdf")


def scan_query(evidence, election):
    profile = SCANS[election]
    figures = scan.verify(evidence, profile)
    rows = [{"county": name, "registered": figures["registered"][name],
             "ballots_cast": figures["voted"][name], "rate_hold_reason": None}
            for name in (*COUNTIES, "TOTAL")]
    return {"counties": rows[:-1], "total": rows[-1], "scan_evidence": evidence,
            "native_numerator": "total_voters", "registration_basis": "Registered voters in the same canvass book",
            "report_note": "Printed Total Voting and registration columns independently reconcile to statewide controls. "
                           "OCR did not qualify the voting method breakdown.",
            "extraction_method": "two_render_ocr_reconciled_nebraska_county_totals"}


def replay_query(facts, election):
    if election == PAIRED_ELECTION:
        return blue_book_query(facts["native_pages"], facts["canvass_control"])
    return (scan_query(facts["scan_evidence"], election) if election in SCANS
            else query(facts["native_lines"], election))


def blue_book_query(pages, control):
    n = r"[0-9][0-9,]*"
    row_pattern = re.compile(rf"([A-Za-z ]+?)([1-3])?\s*\.{{2,}}\s+((?:{n}\s+){{10}}{n})")
    control_match = re.fullmatch(rf"-- November 5, 2002 ({n}) ({n})", control)
    if len(pages) != 3 or not control_match:
        raise ValueError("Unexpected 2002 canvass title or turnout control")
    rows = {}
    for lines in pages:
        title = " ".join(lines)
        if not all(term in title for term in (
                "Nebraska General Election Statistics", "November 5, 2002", "Abstract of Votes",
                "Number of People Voting", "Number of Persons Voting", "Registered Voters")):
            raise ValueError("Unexpected 2002 Blue Book participation heading")
        for line in lines:
            match = row_pattern.fullmatch(line)
            if not match:
                continue
            name, marker, numbers = match.groups()
            name = name.strip()
            if name in rows or marker != {"Douglas": "1", "Johnson": "2", "Sarpy": "3"}.get(name):
                raise ValueError("Unexpected or duplicate 2002 county identity")
            rows[name] = list(map(count, numbers.split()))
    if list(rows) != [*COUNTIES, "TOTAL"]:
        raise ValueError("Incomplete 2002 county roster")
    if any(sum(row[7:10]) != row[10] for row in rows.values()):
        raise ValueError("2002 voting methods do not reconcile to printed totals")
    statewide_voters, statewide_registered = map(count, control_match.groups())
    if (sum(rows[name][6] for name in COUNTIES) != rows["TOTAL"][6] or rows["TOTAL"][6] != statewide_registered
            or sum(rows[name][10] for name in COUNTIES) != statewide_voters):
        raise ValueError("2002 Blue Book county totals disagree with the official canvass control")
    return {
        "counties": [{"county": name, "registered": rows[name][6], "ballots_cast": rows[name][10],
                      "rate_hold_reason": None} for name in COUNTIES],
        "total": {"county": "TOTAL", "registered": statewide_registered, "ballots_cast": statewide_voters,
                  "rate_hold_reason": None},
        "native_pages": pages, "canvass_control": control,
        "blue_book_printed_statewide_voters": rows["TOTAL"][10],
        "native_numerator": "total_voters",
        "registration_basis": "Blue Book county registration; official canvass statewide registration",
        "report_note": f"Blue Book county totals reconcile to the official canvass ({statewide_voters:,}); "
                       f"the Blue Book's conflicting printed state total ({rows['TOTAL'][10]:,}) is retained.",
        "extraction_method": "paired_nebraska_blue_book_counties_with_canvass_state_control",
    }


def parse_blue_book(body, canvass):
    from pypdf import PdfReader

    book = PdfReader(io.BytesIO(body), strict=False)
    official = PdfReader(io.BytesIO(canvass), strict=False)
    if not 854 <= len(book.pages) <= 1000 or not 80 <= len(official.pages) <= 200:
        raise ValueError("Unreviewed 2002 turnout report pagination")
    lines = [" ".join(line.split()) for line in official.pages[-1].extract_text(
        extraction_mode="layout").splitlines()]
    if not any("OFFICIAL TABULATION OF VOTES CAST IN NEBRASKA" in line for line in lines):
        raise ValueError("Missing official 2002 historical turnout tabulation")
    controls = [line for line in lines if line.startswith("-- November 5, 2002 ")]
    if len(controls) != 1:
        raise ValueError("Missing or ambiguous 2002 canvass turnout control")
    pages = [[" ".join(line.split()) for line in book.pages[i].extract_text().splitlines()]
             for i in range(851, 854)]
    return blue_book_query(pages, controls[0])


def scan_policy(election):
    from importlib.metadata import version

    return pin(encoded({
        "profile": SCANS[election],
        "code": [pin(Path(file).read_bytes()) for file in (
            __file__, scan.__file__, Path(scan.__file__).with_name("results_pdf_ocr.py"))],
        "versions": {package: version(package) for package in (
            "pypdf", "PyMuPDF", "rapidocr-onnxruntime", "onnxruntime")},
    }))["sha256"]


def _data(pages, headers, title, *, registration, year):
    label, width = headers
    flattened = [line for page in pages for line in page]
    if title not in pages[0] or label not in pages[0]:
        raise ValueError("Unreviewed Nebraska county table heading")
    number = r"(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)"
    pattern = re.compile(rf"([A-Za-z]+(?: [A-Za-z]+)*) ((?:{number} )+{number})")
    seen = []
    malformed = set()
    for line in flattened:
        if (year == 2008 and not registration
                and line == "Lancaster 98,900 2,9192 517 12 128,621"):
            # Keep the printed total, not a reconstruction of the malformed component.
            seen.append(("Lancaster", [None, 128621]))
            malformed.add("Lancaster")
            continue
        if match := pattern.fullmatch(line):
            name, literal = match.groups()
            name = "TOTAL" if name.casefold() in ("total", "totals", "grand total",
                                                   "statewide", "statewide total") else name
            values = [count(value) for value in literal.split()]
            blank_component = ((registration and year == 2010) or
                               (not registration and year in (2012, 2016)))
            if len(values) != width and not (blank_component and name != "TOTAL" and len(values) == width - 1):
                raise ValueError("Unreviewed Nebraska numeric column inventory")
            seen.append((name, values))
    expected_order = [*COUNTIES, "TOTAL"] if year in (2010, 2014) else ["TOTAL", *COUNTIES]
    if [name for name, _ in seen] != expected_order:
        raise ValueError("Missing or repeated Nebraska county rows")
    indexed = dict(seen)
    if sum(indexed[name][-1] for name in COUNTIES) != indexed["TOTAL"][-1]:
        raise ValueError("Nebraska printed county amounts do not reconcile to the state total")
    offset = 0 if year in (2008, 2010, 2012) else 1
    if registration and any(sum(values[offset:-1]) != values[-1] for _, values in seen):
        raise ValueError("Nebraska native registration components do not reconcile")
    return indexed, malformed


def query(pages, election):
    year, _, day = election.split("-")
    date = f"NOVEMBER {int(day)}, {year}"
    cover = " ".join(" ".join(pages[0]).replace("\ufffd", "").upper().split())
    authority = ("OFFICIAL RESULTS OF NEBRASKA GENERAL ELECTION" in cover if year in ("2008", "2012")
                 else "STATE CANVASSERS" in cover and "OFFICIAL REPORT" in cover)
    if len(pages) != 5 or date not in cover or not authority or "GENERAL ELECTION" not in cover:
        raise ValueError("Unreviewed Nebraska report authority or election date")
    year = int(year)
    if year in REGISTRATION:
        choices = [(REGISTRATION[year], VOTING[year])]
    else:
        reg_line = next((line for line in pages[1] if line.startswith("County Precincts Republican Democratic Libertarian ")
                         and line.endswith(" Nonpartisan Total")), None)
        if not reg_line:
            raise ValueError("Unreviewed Nebraska registration heading")
        # Party columns can change between elections, but must remain explicit and exhaustive.
        between = reg_line.removeprefix("County Precincts Republican Democratic Libertarian ").removesuffix(" Total")
        if not re.fullmatch(r"(?:(?:NOW|Nebraska|People|First) )*Nonpartisan", between):
            raise ValueError("Unreviewed Nebraska registration party columns")
        reg = (reg_line, len(between.split()) + 5)
        choices = [(reg, VOTING[2024]), (reg, VOTING[2022]), (reg, VOTING[2020])]
    candidates = [(reg, vote) for reg, vote in choices if vote[0] in pages[3]]
    if len(candidates) != 1:
        raise ValueError("Unreviewed Nebraska turnout heading")
    reg_layout, vote_layout = candidates[0]
    title = ("Total Voting By Location" if year in (2008, 2010, 2012) else "Total Voting By Method"
             if year == 2014 else "Total Voting by Location" if year == 2016 else "Total Voting by Method")
    registered, _ = _data(pages[1:3], reg_layout, "Number of Registered Voters", registration=True, year=year)
    voted, malformed = _data(pages[3:], vote_layout, title, registration=False, year=year)
    rows = []
    for name in ["TOTAL", *COUNTIES]:
        stock, votes = registered[name][-1], voted[name][-1]
        mode_disagreement = name not in malformed and sum(voted[name][:-1]) != votes
        if year != 2018 and mode_disagreement:
            raise ValueError("Nebraska printed voting method components do not reconcile")
        rows.append({"county": name, "registered": stock, "ballots_cast": votes,
                     "rate_hold_reason": ("malformed_printed_voting_method" if name in malformed else
                                          "printed_voting_methods_disagree" if mode_disagreement else None)})
    return {"counties": rows[1:], "total": rows[0], "native_lines": pages,
            "native_numerator": "total_voters", "registration_basis": "Registered voters in the same canvass book",
            "report_note": "Total Voting is the canvass book's measure; it is not a candidate vote sum.",
            "extraction_method": "pdf_reviewed_nebraska_county_canvass_tables"}


def parse(body, election):
    from pypdf import PdfReader

    if not body.startswith(b"%PDF-") or len(body) > MAX_BYTES:
        raise ValueError("Invalid Nebraska canvass PDF")
    pdf = PdfReader(io.BytesIO(body), strict=True)
    if not 10 <= len(pdf.pages) <= 200:
        raise ValueError("Unreviewed Nebraska canvass pagination")
    if election in SCANS:
        _, evidence = scan.parse(body, SCANS[election], lambda page: pdf.pages[page].extract_text())
        return scan_query(evidence, election)

    def lines(page):
        return [" ".join(line.split()) for line in page.extract_text(extraction_mode="layout").splitlines() if line.strip()]

    front = [lines(page) for page in pdf.pages[:15]]
    starts = [i for i, page in enumerate(front[:-3]) if "Number of Registered Voters" in page]
    if len(starts) != 1:
        raise ValueError("No unique Nebraska canvass turnout section")
    index = starts[0]
    cover = front[0] + front[1] if election == "2016-11-08" else front[0]
    return query([cover, *front[index:index + 4]], election)
