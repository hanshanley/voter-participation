"""Extract comparable administrative components from the official NJ periodic index."""
from datetime import date, datetime
import re
from urllib.parse import urljoin

from scripts.participation_intake.contract import IntakeError, pin

INDEX = "https://www.nj.gov/state/elections/election-results-information.shtml"
BASE = "https://www.nj.gov/state/elections/assets/pdf/periodic-report/2026/"
COUNTIES = ("Atlantic", "Bergen", "Burlington", "Camden", "Cape May", "Cumberland", "Essex",
            "Gloucester", "Hudson", "Hunterdon", "Mercer", "Middlesex", "Monmouth", "Morris", "Ocean",
            "Passaic", "Salem", "Somerset", "Sussex", "Union", "Warren")
FEEDS = {f"NJ-2026-{name.lower().replace(' ', '')}-periodic-components": name for name in COUNTIES}
REVERSE = {name.lower().replace(" ", ""): name for name in COUNTIES}
ELECTION = date(2026, 11, 3)
CSV = "participation-nj-2026-periodic-county-components.csv"
MAX_BYTES = 8_000_000
ROUTE = re.compile(r"2026-(\d{2})(\d{2})-([a-z]+)-periodic-report\.pdf")
NUMERAL = re.compile(r"((?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+))\s*\*?")
GROUPS = {1: "early voting", 4: "election day", 7: "vote-by-mail", 11: "provisional"}
LABELS = (
    "machines deployed", "machines not included", "votes cast",
    "machines deployed", "machines not included", "votes cast",
    "ballots issued", "received into svrs", "ballots tallied", "ballots to be processed",
    "eligible received", "eligible counted",
)
MEASURES = ("early_votes_cast", "election_day_votes_cast", "mail_ballots_tallied", "eligible_provisionals_counted")
COLUMNS = (3, 6, 9, 12)
STATUS = re.compile(r"(?<![A-Z])(UNOFFICIAL|OFFICIAL)(?![A-Z])")


def report_identity(url, county):
    match = ROUTE.fullmatch(url.removeprefix(BASE)) if url.startswith(BASE) else None
    if not match or REVERSE.get(match[3]) != county:
        raise ValueError("Unexpected New Jersey periodic report route")
    edition = date(2026, int(match[1]), int(match[2]))
    if edition < ELECTION:
        raise ValueError("New Jersey periodic report predates election")
    return edition


def links(body):
    section = re.findall(r"<h3>\s*2026 General Election\s*</h3>(.*?)(?=<h3>|$)", body.decode("utf-8-sig"), re.S)
    if len(section) != 1:
        raise ValueError("Missing or repeated New Jersey general-election section")
    result = {}
    for path in re.findall(r'href="(assets/pdf/periodic-report/2026/2026-\d{4}-[a-z]+-periodic-report\.pdf)"', section[0]):
        url = urljoin(INDEX, path)
        county = REVERSE.get(ROUTE.fullmatch(path.rsplit("/", 1)[1])[3])
        if county is None:
            raise ValueError("Unrecognized New Jersey periodic county")
        edition = report_identity(url, county)
        if county not in result or edition > result[county][0]:
            result[county] = (edition, url)
    return result


def label(value):
    return " ".join((value or "").split()).casefold().rstrip("* ")


def numeric(value):
    match = NUMERAL.fullmatch((value or "").strip())
    return int(match[1].replace(",", "")) if match else None


def native_clock(value):
    text = " ".join((value or "").strip().split())
    for fmt in ("%m/%d/%y %I:%M %p", "%m/%d/%Y %I:%M %p"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    raise ValueError("Unrecognized New Jersey county report clock")


def controls(tables, county, edition):
    selectors = {label(f"{county} County"): "county", "congressional totals": "congressional",
                 "municipality totals": "municipal"}
    frames = {}
    for table in tables:
        heading = table["heading"]
        second = table["columns"]
        column_roles = tuple(label(value).replace("deployed machines not included", "machines not included")
                             for value in second[1:13])
        if (column_roles != LABELS or any(label(heading[i]) != group for i, group in GROUPS.items())):
            raise ValueError("New Jersey periodic component order changed")
        when = native_clock(heading[0])
        if not ELECTION <= when.date() <= edition:
            raise ValueError("New Jersey report clock disagrees with official issue")
        status = table["status"]
        if status not in {"OFFICIAL", "UNOFFICIAL"}:
            raise ValueError("Unrecognized New Jersey county report status")
        previous_status, frame = frames.setdefault(when, (status, {}))
        if previous_status != status:
            raise ValueError("Conflicting New Jersey periodic report status")
        for row in table["rows"]:
            key = selectors.get(label(row[0]))
            if key is not None:
                literals = [row[i] for i in COLUMNS]
                if key in frame and [numeric(v) for v in frame[key]] != [numeric(v) for v in literals]:
                    raise ValueError("Conflicting repeated New Jersey periodic controls")
                frame[key] = literals
    if not frames:
        raise ValueError("New Jersey periodic administrative grid not found")
    when = max(frames)
    status, frame = frames[when]
    if "county" not in frame:
        raise ValueError("Latest New Jersey periodic table omits its county identity")
    return when, status, frame


def parse(body, *, county, url):
    import pymupdf

    edition = report_identity(url, county)
    if not body.startswith(b"%PDF-") or len(body) > MAX_BYTES:
        raise ValueError("New Jersey report is not a bounded PDF")
    tables, seen = [], set()
    with pymupdf.open(stream=body, filetype="pdf") as report:
        if report.needs_pass or not report.permissions & pymupdf.PDF_PERM_COPY or not 1 <= len(report) <= 100:
            raise ValueError("Unexpected New Jersey periodic PDF permissions or page inventory")
        for page_number in range(min(4, len(report))):
            page = report[page_number]
            for table in page.find_tables().tables:
                if table.col_count < 13:
                    continue
                rows = [list(row[:13]) for row in table.extract()]
                for i, row in enumerate(rows[:-1]):
                    if not all(label(row[col]) == name for col, name in GROUPS.items()):
                        continue
                    top = [line for line in page.get_text(sort=True).splitlines() if line.strip()][:3]
                    statuses = set(STATUS.findall(" ".join(top))) or set(STATUS.findall(page.get_text()))
                    if len(statuses) != 1:
                        raise ValueError("New Jersey periodic table lacks a unique source status label")
                    native = {"heading": row, "columns": rows[i + 1], "rows": rows[i + 2:],
                              "status": statuses.pop()}
                    key = repr(native)
                    if key not in seen:
                        seen.add(key)
                        tables.append({"page": page_number + 1, **native})
                    break
    clock, _, _ = controls(tables, county, edition)
    return {"date": clock.isoformat(), "posted_edition": edition.isoformat(), "county": county,
            "complete_native_query": tables, "participation_observation_qualified": False}


def collect(collector, feed):
    county = FEEDS[feed]

    def checked(index):
        found = links(index).get(county)
        if found is None:
            raise IntakeError("report_not_linked", "No compatible New Jersey periodic report linked for " + county)
        edition, url = found
        original, _ = collector.acquire(url)
        source = {"url": url, **pin(original)}
        previous = (collector.prior.get(feed) or {}).get("data") or {}
        if previous.get("report") == source:
            return previous
        if previous and edition.isoformat() < previous["posted_edition"]:
            raise ValueError("New Jersey periodic edition regressed")
        return {**parse(original, county=county, url=url), "report": source}

    return collector.capture(feed, INDEX, checked, shared_acquisition=True, equivalent=lambda a, b: a == b)


def exports(entries):
    for feed, county in FEEDS.items():
        entry = entries.get(feed) or {}
        if (data := entry.get("data")) is None:
            continue
        report = data["report"]
        edition = report_identity(report["url"], county)
        when, status, frame = controls(data["complete_native_query"], county, edition)
        if (data["county"] != county or data["date"] != when.isoformat() or data["posted_edition"] != edition.isoformat()
                or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])
                or type(report["bytes"]) is not int or not 0 < report["bytes"] <= MAX_BYTES
                or entry["status"] not in ("reported", "retained_after_failure")):
            raise ValueError("Changed New Jersey periodic query provenance")
        for i, measure in enumerate(MEASURES):
            literals = {key: row[i] for key, row in frame.items()}
            seen = set()
            for literal in literals.values():
                if (value := numeric(literal)) is not None:
                    seen.add(value)
            n = next(iter(seen)) if len(seen) == 1 and sum(numeric(v) is not None for v in literals.values()) >= 2 else None
            hold = ("" if n is not None else "printed_component_controls_disagree" if len(seen) > 1
                    else "fewer_than_two_reported_component_controls")
            yield {"state_code": "NJ", "election_date": ELECTION.isoformat(), "county": county, "measure": measure,
                   "reported_component": n, "hold_reason": hold, "native_control_literals": literals,
                   "source_status": entry["status"], "source_url": report["url"], "source_sha256": report["sha256"],
                   "posted_edition": edition.isoformat(), "source_local_clock": when.isoformat(),
                   "source_status_literal": status, "not_all_mode_ballots_or_turnout_rate": True}
