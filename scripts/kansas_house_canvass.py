"""Reconcile Kansas's official House workbook to the published statewide vote totals."""

from collections import Counter
from datetime import timedelta, timezone
from functools import partial
from io import BytesIO
import re
from urllib.parse import urljoin, urlsplit
from zipfile import ZipFile

from scripts.national_turnout_release_watch import Labels
from scripts.participation_intake.contract import pin

INDEX = "https://www.sos.ks.gov/elections/election-results.html"
FEEDS = {f"KS-{year}-official-house-canvass-audit": year for year in (2024, 2026)}
CSV = "congressional-ks-house-canvass-audit.csv"
LIMIT = 6_000_000
DISTRICT = re.compile(r"(?:United States House of Representatives ([1-4])|(?:For )?United States Representative,? ([1-4])(?:st|nd|rd|th) District)")
PARTIES = {"DEM": "D", "REP": "R", "LIB": "L", "IND": "I", "D": "D", "R": "R", "L": "L",
           "I": "I", "Democratic": "D", "Republican": "R", "Libertarian": "L", "Independent": "I"}


def discover(body, *, year):
    parser = Labels()
    if not 0 < len(body) <= LIMIT:
        raise ValueError("Invalid Kansas results index size")
    parser.feed(body.decode("utf-8-sig"))
    links = {}
    prior = False
    for tag, attrs, label in parser.labels:
        if tag != "a":
            continue
        compact = re.sub(r"\s+", "", label)
        if compact == "2024OfficialGeneralElectionResults":
            prior = True
        kind = {"%dOfficialGeneralElectionResults" % year: "control",
                "U.S.HouseofRepresentatives%dGeneralElection" % year: "workbook"}.get(compact)
        if kind is None:
            continue
        url = urljoin(INDEX, attrs.get("href") or "")
        target = urlsplit(url)
        extension = "pdf" if kind == "control" else "xlsx"
        if (target.scheme != "https" or target.netloc != urlsplit(INDEX).netloc or target.query or target.fragment
                or not re.fullmatch(rf"/elections/{year % 100:02d}elec/{year}-General-Election-[\w% -]+\.{extension}",
                                    target.path, re.ASCII) or kind in links):
            raise ValueError("Unexpected or ambiguous Kansas general-election report link")
        links[kind] = url
    if not prior:
        raise ValueError("Kansas archive identity could not be verified")
    return links


def name_key(name):
    if "," in name:
        last, first = name.split(",", 1)
        name = f"{first} {last}"
    return "".join(c for c in name.casefold() if c.isalnum())


def read_control(body, *, year):
    from pypdf import PdfReader

    if not body.startswith(b"%PDF-") or len(body) > LIMIT:
        raise ValueError("Invalid Kansas canvass PDF")
    pdf = PdfReader(BytesIO(body))
    if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 150:
        raise ValueError("Kansas canvass PDF is encrypted or outside reviewed limits")
    lines = [" ".join(line.split()) for page in pdf.pages[:5] for line in page.extract_text().splitlines()]
    if not any(line == f"{year} General Election" for line in lines) or "Kansas Secretary of State" not in lines:
        raise ValueError("Kansas canvass year or issuer differs")
    out, district = [], None
    for line in lines:
        match = DISTRICT.fullmatch(line)
        if match:
            district = int(match[1] or match[2])
            continue
        if not district or line == "Race Candidate Votes Percent":
            continue
        if line.startswith(("Official Vote Totals", "Kansas Secretary of State", f"{year} General Election")):
            continue
        row = re.fullmatch(r"([A-Za-z])-([^%]+?) ([\d,]+) \d+(?:\.\d+)?%", line)
        if not row:
            if re.fullmatch(r"(?:Kansas |State |Governor|Secretary |Attorney |Insurance |Treasurer|Member |Court |District |Constitutional ).*", line):
                district = None
                continue
            raise ValueError("Unrecognized row in Kansas House canvass")
        party = PARTIES.get(row[1].upper())
        if party is None:
            raise ValueError("Unreviewed Kansas House canvass party")
        out.append({"district": district, "candidate": row[2], "party": party,
                    "statewide_votes": int(row[3].replace(",", ""))})
    keys = {(r["district"], r["party"], name_key(r["candidate"])) for r in out}
    if len(keys) != len(out) or {r["district"] for r in out} != {1, 2, 3, 4}:
        raise ValueError("Incomplete Kansas statewide House controls")
    return out


def read_workbook(body, *, control):
    from openpyxl import load_workbook

    if not 0 < len(body) <= LIMIT:
        raise ValueError("Invalid Kansas House workbook size")
    with ZipFile(BytesIO(body)) as archive:
        members = archive.infolist()
        if (len(members) > 400 or len({m.filename for m in members}) != len(members)
                or sum(m.file_size for m in members) > 40_000_000 or any(m.flag_bits & 1 for m in members)):
            raise ValueError("Kansas House workbook archive exceeds its reviewed limits")
    workbook = load_workbook(BytesIO(body), read_only=True, data_only=True)
    if not (1 <= len(workbook.worksheets) <= 106) or workbook.sheetnames[0] != "OfficialPrecinctLevelResults":
        raise ValueError("Unrecognized Kansas House workbook sheets")
    if any(not (1 <= (sheet.max_row or 0) <= 40_000 and 1 <= (sheet.max_column or 0) <= 100)
           for sheet in workbook.worksheets):
        raise ValueError("Kansas House workbook sheet dimensions exceed their reviewed limits")
    exact = {(r["district"], r["party"], name_key(r["candidate"])) for r in control}
    sums, seen, counties = Counter(), set(), set()
    blank_rows = 0
    main = iter(workbook.worksheets[0].values)
    if next(main, None) != ("County", "Precinct", "Race", "Candidate", "Party", "Votes", "VTD"):
        raise ValueError("Kansas statewide House worksheet header differs")
    for county, label, race, name, party, votes, vtd in main:
        match = DISTRICT.fullmatch(race or "")
        if not match or not all(isinstance(s, str) and s for s in (county, label, name, party)) or vtd is None:
            raise ValueError("Kansas statewide House worksheet identity differs")
        key = (int(match[1] or match[2]), PARTIES.get(party), name_key(name))
        identity = (county.casefold(), label, str(vtd), key)
        if key not in exact or identity in seen:
            raise ValueError("Duplicate or unknown candidate in Kansas statewide sheet")
        seen.add(identity)
        counties.add(county.casefold())
        if votes is None:
            blank_rows += 1
        elif type(votes) is int and votes >= 0:
            sums[key] += votes
        else:
            raise ValueError("Invalid Kansas statewide worksheet count")
    supplements, uncontrolled = Counter(), []
    for sheet in workbook.worksheets[1:]:
        if not re.fullmatch(r"[A-Z]+", sheet.title) or sheet.title.casefold() in counties:
            raise ValueError("Kansas supplemental sheet overlaps the statewide worksheet")
        counties.add(sheet.title.casefold())
        lines = list(sheet.values)
        if len(lines) < 3 or "COUNTY TOTALS" not in lines[-1]:
            raise ValueError("Missing Kansas supplemental county controls")
        district, columns = None, set()
        for heading, candidate, votes in zip(lines[0], lines[1], lines[-1], strict=True):
            if heading and (match := DISTRICT.fullmatch(str(heading))):
                district = int(match[1] or match[2])
            if candidate is None:
                continue
            if district is None or not isinstance(candidate, str) or type(votes) is not int or votes < 0:
                raise ValueError("Invalid Kansas supplemental county control")
            if candidate.casefold() == "write-in":
                key = (district, None, "writein")
                if key in columns:
                    raise ValueError("Duplicate Kansas supplemental write-in column")
                columns.add(key)
                uncontrolled.append({"district": district, "county": sheet.title, "candidate": candidate,
                                     "workbook_votes": votes})
                continue
            prefix, _, remaining = candidate.partition(" ")
            label = remaining if prefix in PARTIES else candidate
            keys = [k for k in exact if k[0] == district and k[2] == name_key(label)
                    and (prefix not in PARTIES or k[1] == PARTIES[prefix])]
            if len(keys) != 1 or keys[0] in columns:
                raise ValueError("Unmatched or duplicate Kansas supplemental candidate")
            columns.add(keys[0])
            supplements[keys[0]] += votes
    workbook.close()
    if len(counties) != 105:
        raise ValueError("Kansas House workbook does not account for 105 counties")
    return {
        "blank_main_rows": blank_rows, "counties": len(counties),
        "named": [{**r, "main_sheet_votes": sums[k], "supplemental_sheet_votes": supplements[k]}
                  for r in control for k in [(r["district"], r["party"], name_key(r["candidate"]))]],
        "uncontrolled": uncontrolled,
    }


def collect(collector, feed, *, reuse_checked_week=False):
    year = FEEDS[feed]
    old = collector.prior.get(feed) or {}
    day = collector.now.astimezone(timezone.utc).date()
    week = (day - timedelta(days=day.weekday())).isoformat()
    if reuse_checked_week and not collector.offline and old.get("archive_check_week_utc") == week:
        return old

    def parse(body):
        links = discover(body, year=year)
        result = {"links": links, "participation_observation_qualified": False}
        if set(links) != {"control", "workbook"}:
            if (old.get("data") or {}).get("audit") is not None:
                raise ValueError("Previously advertised Kansas House workbook pair disappeared")
            return result
        control, _ = collector.acquire(links["control"])
        workbook, _ = collector.acquire(links["workbook"])
        facts = read_control(control, year=year)
        result.update(audit=read_workbook(workbook, control=facts), control=facts,
                      originals={k: {"url": links[k], **pin(b)}
                                 for k, b in (("control", control), ("workbook", workbook))})
        return result

    entry = collector.capture(feed, INDEX, parse, equivalent=lambda prior, latest: prior == latest)
    if not collector.offline:
        entry["archive_check_week_utc"] = week
    return entry


def exports(entries):
    for feed, year in FEEDS.items():
        if feed not in entries:
            continue
        entry = entries[feed]
        data = entry.get("data") or {}
        links, audit = data.get("links", {}), data.get("audit")
        originals = data.get("originals", {})
        common = {"state": "KS", "election_year": year, "source_status": entry["status"],
                  "index_url": INDEX, "control_url": links.get("control"), "workbook_url": links.get("workbook"),
                  "index_sha256": (entry.get("source") or {}).get("sha256"),
                  "control_sha256": originals.get("control", {}).get("sha256"),
                  "workbook_sha256": originals.get("workbook", {}).get("sha256"),
                  "counties_in_workbook": audit["counties"] if audit else None,
                  "blank_main_rows": audit["blank_main_rows"] if audit else None,
                  "checked_week_utc": entry.get("archive_check_week_utc"), "scope_complete_for_model": False}
        if not audit:
            yield {**common, "decision": (
                "report_pair_not_verified" if not data else
                "report_pair_incomplete" if links else "report_pair_not_yet_linked")}
            continue
        for candidate in audit["named"]:
            count = candidate["main_sheet_votes"] + candidate["supplemental_sheet_votes"]
            yield {**common, **candidate, "workbook_votes": count, "county": None,
                   "difference": count - candidate["statewide_votes"],
                   "decision": "named_totals_agree" if count == candidate["statewide_votes"] else "named_totals_differ"}
        for write_in in audit["uncontrolled"]:
            yield {**common, **write_in, "decision": "supplemental_write_in_without_statewide_control"}


def original_reports(entries):
    for feed, year in FEEDS.items():
        entry = entries.get(feed) or {}
        if (data := entry.get("data")) is None:
            continue
        yield feed, entry["source"], ".html", LIMIT, entry["source"]["url"] == INDEX, partial(
            discover, year=year), data["links"]
        if data.get("audit") is not None:
            for kind, extension, parse, facts in (
                ("control", ".pdf", partial(read_control, year=year), data["control"]),
                ("workbook", ".xlsx", partial(read_workbook, control=data["control"]), data["audit"]),
            ):
                source = data["originals"][kind]
                yield f"{feed}-{kind}", source, extension, LIMIT, source["url"] == data["links"][kind], parse, facts
