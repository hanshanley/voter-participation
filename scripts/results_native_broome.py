"""Discover and retain Broome's explicitly contest-scoped ballot statistics."""

import copy
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from html.parser import HTMLParser
import io
import json
import re
from urllib.parse import quote, urljoin

from scripts.participation_intake.contract import count, digest, encoded, pin


IDENTITY = "NY-broome-governor-report-ballots-2026"
AUTHORITY_URL = "https://www.broomevotes.com/results"
DASHBOARD = (
    "https://app.enhancedvoting.com/results/public/"
    "broome-county-ny/GE2026_20261028105146"
)
ORIGIN = "https://app.enhancedvoting.com"
API_URL = (
    ORIGIN + "/results/public/api/elections/"
    "broome-county-ny/GE2026_20261028105146"
)
REPORT_NAME = "Municipality, Ward, & District Results with Total Ballots Cast"
SUMMARY_NAME = "Summary Results by Contest with Contest-Level Details"
CONTEXT = "Governor and Lieutenant Governor"
QUERY_CONTRACT = "participation.broome_contest_ballots.v1"
UNIT_INVENTORY = "ba631003a34710c7ffc6b7923fea9007f9a7a05f3deda44221c798d511a10b50"
PARENT_INVENTORY = "c626ffd6c41fa74884783bd557a1ce32c12bc32ddf9ec55958deff6b1ba2ebc0"
COUNT_ROW = re.compile(
    r"^(.*?) ((?:[0-9][0-9,]* ){9}[0-9][0-9,]*)"
    r"(?: ([0-9]+\.[0-9]{2}) %)?$"
)
UUID = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"
EDITION_FIELDS = ("asOf", "lastUpdated", "publishDate", "publishVersionId")
HELD = {
    "whole_election_count_qualified": False,
    "unique_voter_count_qualified": False,
    "analytical_denominator_qualified": False,
    "rate_qualified": False,
    "geographic_join_qualified": False,
    "cross_year_identity_qualified": False,
    "estimate_update_qualified": False,
}


class Declarations(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.links, self.scripts = base, [], []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "base" and values.get("href"):
            self.base = urljoin(self.base, values["href"])
        if tag == "a" and values.get("href"):
            self.links.append(urljoin(self.base, values["href"]))
        if tag == "script" and values.get("src"):
            self.scripts.append(urljoin(self.base, values["src"]))


def _one(values, label):
    values = set(values)
    if len(values) != 1:
        raise ValueError("Missing or ambiguous declared " + label)
    return values.pop()


def _timestamp(value):
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,7}))?Z",
        value if isinstance(value, str) else "",
    )
    if not match:
        raise ValueError("Missing native UTC publication-edition clock")
    try:
        result = datetime.strptime(match[1], "%Y-%m-%dT%H:%M:%S")
    except ValueError as error:
        raise ValueError("Invalid native publication-edition clock") from error
    if result < datetime(2026, 11, 3) or result.year > 2027:
        raise ValueError("Wrong Broome publication-edition year")
    return result, Decimal("0." + (match[2] or "0"))


def election_metadata(value):
    if (not isinstance(value, dict)
            or value.get("name") != [{"languageId": "en", "text": "2026 General Election"}]
            or value.get("dateText") != [{"languageId": "en", "text": "November 3, 2026"}]
            or value.get("electionDate") != "2026-11-03"
            or value.get("isProduction") is not True
            or value.get("isPrimary") is not False
            or type(value.get("isOfficialResults")) is not bool
            or value.get("jurisdictionId") != "2c8df89e-6490-4c32-ac48-a75f7ffc1911"
            or value.get("id") != "01000000-3ae7-e8bb-faa6-08df2fb19018"
            or value.get("precinctResultsProtected") is not True
            or value.get("redactingPrecinctCountGroups") is not False):
        raise ValueError("Changed Broome election identity, production or protection scope")
    for key in EDITION_FIELDS[:3]:
        _timestamp(value.get(key))
    if not re.fullmatch(UUID, value.get("publishVersionId", "")):
        raise ValueError("Missing Broome publication edition identity")
    return {
        "id": value["id"],
        "jurisdictionId": value["jurisdictionId"],
        "electionDate": value["electionDate"],
        "isOfficialResults": value["isOfficialResults"],
        "precinctResultsProtected": True,
        "redactingPrecinctCountGroups": False,
        **{key: value[key] for key in EDITION_FIELDS},
    }


def report_url(election, name):
    categories = election.get("publicReportCategories")
    if not isinstance(categories, list):
        raise ValueError("Missing native Broome report declarations")
    selected = []
    for category in categories:
        if not isinstance(category, dict) or not isinstance(category.get("reports"), list):
            raise ValueError("Changed native Broome report category")
        for report in category["reports"]:
            if not isinstance(report, dict):
                raise ValueError("Malformed native Broome report")
            if report.get("reportName") == name:
                selected.append(report.get("blobName"))
    blob = _one(selected, name)
    if (not isinstance(blob, str) or "/" in blob or "\\" in blob
            or not blob.endswith(".PDF") or ".." in blob
            or not re.fullmatch(r"[A-Za-z0-9 ,&()_-]+\.PDF", blob)):
        raise ValueError("Unsafe or changed declared Broome report path")
    return ORIGIN + "/cdn/results/" + election["jurisdictionId"] + "/" + quote(blob, safe="")


def parse_report_pages(pages):
    if not isinstance(pages, list) or not pages:
        raise ValueError("Missing Broome ballot report pages")
    rows = []
    for page_number, text in enumerate(pages, 1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        required = ("Broome County", "2026 General Election", "November 03, 2026",
                    "Results by Municipality, Ward, and District", CONTEXT, "** Protected")
        if any(header not in lines for header in required):
            raise ValueError("Changed Broome statistical report election/context header")
        if ("Vote For 1" not in lines or not re.search(
                r"Write-in\s+Under Votes\s+Over Votes\s+Whole Number\s*"
                r"\(Ballots Cast\)\s*Eligible Voters\s+Turnout \(%\)", text)):
            raise ValueError("Changed Broome physical statistical-column order")
        for line in lines:
            match = COUNT_ROW.fullmatch(line)
            if match:
                label, literals, printed = match.groups()
                values = literals.split()
                rows.append({
                    "native_label": label,
                    "page": page_number,
                    "ballots_cast_literal": values[-2],
                    "eligible_voters_literal": values[-1],
                    "ballots_cast": count(values[-2]),
                    "eligible_voters": count(values[-1]),
                    "printed_pct": printed,
                    "kind": "control" if label.endswith("Total") else "reporting_unit",
                })
                if label == "Contest Total":
                    return rows
            elif re.match(r"^(?:City Binghamton|[A-Za-z][A-Za-z ]* \d+|.* Total)\s", line):
                raise ValueError("Unknown, protected or malformed Broome statistical row")
        if page_number >= 7:
            break
    raise ValueError("Missing complete Broome governor-context control")


def parse_summary_pages(pages):
    if not pages:
        raise ValueError("Missing Broome summary")
    lines = [line.strip() for line in pages[0].splitlines() if line.strip()]
    for header in ("Broome County", "2026 General Election", "November 03, 2026",
                   "Summary Results Report", CONTEXT, "Comptroller"):
        if header not in lines:
            raise ValueError("Changed Broome summary election or contest scope")
    section = lines[lines.index(CONTEXT) + 1:lines.index("Comptroller")]
    if "Vote for 1" not in section:
        raise ValueError("Changed Broome governor vote-for scope")
    districts = [re.fullmatch(r"Election Districts Reported (\d+) of (\d+)", line)
                 for line in section]
    districts = [match.groups() for match in districts if match]
    if districts != [("126", "126")]:
        raise ValueError("Missing Broome native governor reporting inventory")
    totals = [re.fullmatch(r"Total Ballots Cast ([0-9,]+)", line) for line in section]
    totals = [count(match[1]) for match in totals if match]
    if len(totals) != 1:
        raise ValueError("Missing literal Broome summary Total Ballots Cast")
    clock = re.search(r"\bLast Updated: (\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})", pages[0])
    if not clock:
        raise ValueError("Missing Broome summary's own update clock")
    datetime.strptime(clock[1], "%m/%d/%Y %H:%M:%S")
    return {
        "context": CONTEXT, "total_ballots_cast": totals[0],
        "reported_units": 126, "total_units": 126,
        "source_clock": {"literal": clock[1], "timezone": None},
    }


def validate_query(query):
    if (not isinstance(query, dict) or query.get("contract") != QUERY_CONTRACT
            or query.get("context") != CONTEXT or query.get("qualification") != HELD
            or query.get("source_clock") != {"literal": None, "timezone": None}
            or query.get("protection_notice") != "** Protected"):
        raise ValueError("Changed Broome contest-count qualification")
    metadata = query.get("publisher_edition")
    if not isinstance(metadata, dict):
        raise ValueError("Missing Broome publisher edition")
    if (metadata.get("id") != "01000000-3ae7-e8bb-faa6-08df2fb19018"
            or metadata.get("jurisdictionId") != "2c8df89e-6490-4c32-ac48-a75f7ffc1911"
            or metadata.get("electionDate") != "2026-11-03"
            or type(metadata.get("isOfficialResults")) is not bool
            or metadata.get("precinctResultsProtected") is not True
            or metadata.get("redactingPrecinctCountGroups") is not False
            or not re.fullmatch(UUID, str(metadata.get("publishVersionId", "")))):
        raise ValueError("Changed Broome native query election/protection identity")
    for key in EDITION_FIELDS[:3]:
        _timestamp(metadata.get(key))
    rows = query.get("rows")
    if not isinstance(rows, list) or len(rows) != 144:
        raise ValueError("Incomplete Broome statistical row inventory")
    units = [row for row in rows if row.get("kind") == "reporting_unit"]
    controls = [row for row in rows if row.get("kind") == "control"]
    if (len(units) != 126 or len(controls) != 18
            or digest(encoded(sorted(row["native_label"] for row in units))) != UNIT_INVENTORY
            or digest(encoded(sorted(row["native_label"] for row in controls))) != PARENT_INVENTORY
            or rows[-1]["native_label"] != "Contest Total"):
        raise ValueError("Changed or duplicated Broome native unit/control identities")
    pending = []
    parent_totals = []
    for row in rows:
        if (type(row.get("ballots_cast")) is not int
                or type(row.get("eligible_voters")) is not int
                or count(row.get("ballots_cast_literal")) != row["ballots_cast"]
                or count(row.get("eligible_voters_literal")) != row["eligible_voters"]
                or type(row.get("page")) is not int or not 1 <= row["page"] <= 7):
            raise ValueError("Invalid Broome native statistical count or physical page")
        numerator, stock = row["ballots_cast"], row["eligible_voters"]
        expected = (str((Decimal(numerator) * 100 / Decimal(stock)).quantize(
            Decimal(".01"), rounding=ROUND_HALF_UP)) if stock else None)
        if row.get("printed_pct") != expected:
            raise ValueError("Changed or contradictory Broome printed fraction")
        if row["kind"] == "reporting_unit":
            pending.append(row)
        elif row["native_label"] != "Contest Total":
            if (not pending or sum(item["ballots_cast"] for item in pending) != numerator
                    or sum(item["eligible_voters"] for item in pending) != stock):
                raise ValueError("Broome municipality control does not reconcile")
            parent_totals.append(row)
            pending = []
        elif (pending or sum(item["ballots_cast"] for item in parent_totals) != numerator
              or sum(item["eligible_voters"] for item in parent_totals) != stock):
            raise ValueError("Broome contest control does not reconcile")
    summary = query.get("summary_control", {})
    clock = summary.get("source_clock")
    if (summary.get("context") != CONTEXT
            or summary.get("total_ballots_cast") != rows[-1]["ballots_cast"]
            or summary.get("reported_units") != 126 or summary.get("total_units") != 126
            or not isinstance(clock, dict) or clock.get("timezone") is not None
            or not isinstance(clock.get("literal"), str)):
        raise ValueError("Broome separate summary control differs")
    datetime.strptime(clock["literal"], "%m/%d/%Y %H:%M:%S")
    for key in ("report_source", "summary_source"):
        source = query.get(key, {})
        if (not str(source.get("url", "")).startswith(ORIGIN + "/cdn/results/"
                "2c8df89e-6490-4c32-ac48-a75f7ffc1911/")
                or type(source.get("bytes")) is not int or source["bytes"] <= 0
                or not re.fullmatch(r"[a-f0-9]{64}", str(source.get("sha256", "")))):
            raise ValueError("Missing complete Broome report pin")
    return query


def edition_guard(query, previous):
    validate_query(query)
    if previous is None:
        return
    validate_query(previous)
    current, old = query["publisher_edition"], previous["publisher_edition"]
    for key in EDITION_FIELDS[:3]:
        if _timestamp(current[key]) < _timestamp(old[key]):
            raise ValueError("Broome publication edition moved backwards")
    if (current == old and any(query[key] != previous[key] for key in
            ("rows", "report_source", "summary_source", "summary_control"))):
        raise ValueError("Broome statistical report changed without a new publication edition")
    if (old.get("isOfficialResults") is True
            and current.get("isOfficialResults") is not True):
        raise ValueError("Broome official status moved backwards")


def pdf_pages(body, limit):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(body), strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 200:
        raise ValueError("Unqualified Broome PDF page inventory or encryption")
    return [page.extract_text() for page in reader.pages[:limit]]


def collect_statistics(collector):
    """Use only the official link and download templates in its declared client."""
    prior = collector.prior.get(IDENTITY)

    def parse(authority_body):
        authority = authority_body.decode("utf-8")
        declaration = Declarations(AUTHORITY_URL)
        declaration.feed(authority)
        if (DASHBOARD not in declaration.links or "2026" not in authority
                or "General" not in authority):
            raise ValueError("Missing official Broome general-election dashboard declaration")
        provenance = [{"role": "authority", "url": AUTHORITY_URL, **pin(authority_body)}]

        def acquire(url, role):
            body, _ = collector.acquire(url)
            provenance.append({"role": role, "url": url, **pin(body)})
            return body

        dashboard = acquire(DASHBOARD, "dashboard")
        declared = Declarations(DASHBOARD)
        declared.feed(dashboard.decode("utf-8"))
        client_url = _one([url for url in declared.scripts if re.fullmatch(
            re.escape(ORIGIN) + r"/results/public/main-[A-Z0-9]+\.js", url)], "main client")
        client = acquire(client_url, "declared_main_client").decode("utf-8")
        templates = (
            'api:{endpoint:"/results/public/api"',
            'getElection(a,p){return this.http.get(`${this.baseUrl}/elections/${a}/${p}`)',
            'g=a.paramMap.get("name"),p=a.paramMap.get("id")',
            "this.appService.loadElection(g,p)",
            "this.electionService.getElection(o.jurisdictionName,o.electionId)",
            'imageCdn:"/cdn/results/"',
        )
        if any(template not in client for template in templates):
            raise ValueError("Changed Broome declared API/route/download template")
        reports = _one(re.findall(
            r'path:"reports",loadComponent:\(\)=>import\("(\./chunk-[A-Z0-9]+\.js)"\)',
            client), "report component")
        report_client = acquire(urljoin(client_url, reports),
                                "declared_report_client").decode("utf-8")
        for template in ("this.toCategoryView(h,i.id,o,m)", 'blobName:i+"/"+e.blobName',
                         "o.baseImageCdn+o.report.blobName"):
            if template not in report_client:
                raise ValueError("Changed Broome native report-download declaration")
        election = json.loads(acquire(API_URL, "election"))
        metadata = election_metadata(election)
        report = report_url(election, REPORT_NAME)
        summary = report_url(election, SUMMARY_NAME)
        report_body = acquire(report, "contest_ballot_report")
        summary_body = acquire(summary, "separate_contest_summary")
        query = {
            "contract": QUERY_CONTRACT, "context": CONTEXT,
            "publisher_edition": metadata,
            "report_source": {"url": report, **pin(report_body)},
            "summary_source": {"url": summary, **pin(summary_body)},
            "rows": parse_report_pages(pdf_pages(report_body, 7)),
            "summary_control": parse_summary_pages(pdf_pages(summary_body, 1)),
            "qualification": copy.deepcopy(HELD),
            "source_clock": {"literal": None, "timezone": None},
            "protection_notice": "** Protected",
        }
        old_query = (prior or {}).get("data", {}).get("complete_native_query") if (
            isinstance((prior or {}).get("data"), dict)) else None
        edition_guard(query, old_query)
        return {
            "updates": [],
            "numerical_data_qualified": False,
            "complete_native_query": query,
            "source_provenance": provenance,
            "canonical_onboarding_status": "held_contest_scoped_not_whole_election",
            "geographic_joins_changed": False,
        }

    return collector.capture(IDENTITY, AUTHORITY_URL, parse)
