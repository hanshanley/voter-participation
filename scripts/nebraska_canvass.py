"""Reconcile Nebraska's printed county registration and voting tables."""

import io
import re

from scripts.participation_intake.contract import count

INDEX = "https://sos.nebraska.gov/previous-elections"
BASE = "https://sos.nebraska.gov/sites/default/files/doc/elections/"
CURRENT = "2026-11-03"
BOOKS = {
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
MAX_BYTES = 8_000_000
REGISTRATION = {
    2016: ("Precincts Republican Democratic Libertarian Nonpartisan Total", 6),
    2018: ("County Precincts Republican Democratic Libertarian Nonpartisan Total", 6),
    2020: ("County Precincts Republican Democratic Libertarian Nonpartisan Total", 6),
    2022: ("County Precincts Republican Democratic Libertarian NOW Nonpartisan Total", 7),
    2024: ("County Precincts Republican Democratic Libertarian NOW Nebraska Nonpartisan Total", 8),
}
VOTING = {
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
    return INDEX, root + (re.escape(filename) if filename else r"[^/?#]{1,140}\.pdf")


def _data(pages, headers, title, *, registration, year):
    label, width = headers
    flattened = [line for page in pages for line in page]
    if title not in pages[0] or label not in pages[0]:
        raise ValueError("Unreviewed Nebraska county table heading")
    number = r"(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)"
    pattern = re.compile(rf"([A-Za-z]+(?: [A-Za-z]+)*) ((?:{number} )+{number})")
    seen = []
    for line in flattened:
        if match := pattern.fullmatch(line):
            name, literal = match.groups()
            name = "TOTAL" if name in ("Total", "Statewide", "Statewide Total") else name
            values = [count(value) for value in literal.split()]
            if len(values) != width and not (year == 2016 and not registration
                                             and name != "TOTAL" and len(values) == width - 1):
                raise ValueError("Unreviewed Nebraska numeric column inventory")
            seen.append((name, values))
    if [name for name, _ in seen] != ["TOTAL", *COUNTIES]:
        raise ValueError("Missing or repeated Nebraska county rows")
    total = seen[0][1][-1]
    if sum(values[-1] for _, values in seen[1:]) != total:
        raise ValueError("Nebraska printed county amounts do not reconcile to the state total")
    if registration and any(sum(values[1:-1]) != values[-1] for _, values in seen):
        raise ValueError("Nebraska native registration components do not reconcile")
    return dict(seen)


def query(pages, election):
    year, _, day = election.split("-")
    date = f"NOVEMBER {int(day)}, {year}"
    if (len(pages) != 5 or date not in " ".join(pages[0])
            or "STATE CANVASSERS" not in " ".join(pages[0])
            or "OFFICIAL REPORT" not in " ".join(pages[0])
            or "GENERAL ELECTION" not in " ".join(pages[0])):
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
    registered = _data(pages[1:3], reg_layout, "Number of Registered Voters", registration=True, year=year)
    voted = _data(pages[3:], vote_layout,
                  "Total Voting by Location" if year == 2016 else "Total Voting by Method",
                  registration=False, year=year)
    rows = []
    for name in registered:
        stock, votes = registered[name][-1], voted[name][-1]
        mode_disagreement = sum(voted[name][:-1]) != votes
        if year != 2018 and mode_disagreement:
            raise ValueError("Nebraska printed voting method components do not reconcile")
        rows.append({"county": name, "registered": stock, "ballots_cast": votes,
                     "rate_hold_reason": "printed_voting_methods_disagree" if mode_disagreement else None})
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

    def lines(page):
        return [" ".join(line.split()) for line in page.extract_text(extraction_mode="layout").splitlines() if line.strip()]

    front = [lines(page) for page in pdf.pages[:15]]
    starts = [i for i, page in enumerate(front[:-3]) if "Number of Registered Voters" in page]
    if len(starts) != 1:
        raise ValueError("No unique Nebraska canvass turnout section")
    index = starts[0]
    cover = front[0] + front[1] if election == "2016-11-08" else front[0]
    return query([cover, *front[index:index + 4]], election)
