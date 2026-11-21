"""Reconcile Virginia's official 2022 turnout detail to the published locality controls."""

import copy
from datetime import timedelta, timezone
from functools import partial
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urljoin

from scripts.participation_intake.contract import IntakeError, pin
from scripts.results_turnout_history import (
    VA_LOCALITY_DATE, VA_LOCALITY_URL, html_tables, integer, virginia_locality_report,
)


FEED = "VA-2022-native-precinct-counts"
CSV = "virginia-2022-native-precinct-counts.csv"
MAX_BYTES = 500_000
DETAIL = re.compile(r"Turnout/[A-Z0-9_&]+\.html")
PRECINCT = re.compile(r"(\d{3})(?:\s*-\s*|\s+)\S.*")
CENTRAL = {
    "# AB - Absentee By Mail": "mail",
    "# EV - Early Voting": "early_voting",
    "# PE - Ballots Processed Post Election***": "post_election_mail",
    "## Provisional": "provisional",
}


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href") or ""
            self.active = (href, []) if DETAIL.fullmatch(href) else None

    def handle_data(self, data):
        if self.active is not None:
            self.active[1].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.active is not None:
            href, text = self.active
            self.links.append(("".join(text).strip(), href))
            self.active = None


def parse_index(body):
    if len(body) > MAX_BYTES:
        raise ValueError("Virginia turnout index exceeds its reviewed size")
    report = virginia_locality_report(body, VA_LOCALITY_DATE)
    parser = _Links()
    parser.feed(body.decode("utf-8-sig"))
    links = dict(parser.links)
    if (len(links) != len(parser.links) or len(set(links.values())) != len(links)
            or set(links) != {row["county"] for row in report["counties"]}):
        raise ValueError("Virginia turnout link roster differs from the locality controls")
    return {"report": report, "links": links}


def reconcile(rows, control):
    seen, totals = set(), dict.fromkeys((*CENTRAL.values(), "election_day"), 0)
    out = []
    for row in rows:
        if len(row) != 2:
            raise ValueError("Unexpected Virginia precinct columns")
        label, value = row
        match = PRECINCT.fullmatch(label)
        kind = CENTRAL.get(label) if match is None else "election_day"
        identity = label if match is None else match[1]
        if kind is None or identity in seen:
            raise ValueError("Unknown or duplicate Virginia reporting unit")
        seen.add(identity)
        ballots = integer(value)
        totals[kind] += ballots
        out.append({"reporting_unit": label, "precinct_code": match[1] if match else None,
                    "unit_kind": "physical_precinct" if match else "central_reporting_unit",
                    "ballot_component": kind, "ballots": ballots})
    if (not set(CENTRAL) <= seen or not any(row["precinct_code"] is not None for row in out)
            or totals["mail"] + totals["post_election_mail"] != control["by_mail"]
            or any(totals[key] != control[key] for key in ("early_voting", "election_day", "provisional"))
            or sum(totals.values()) != control["ballots_cast"]):
        raise ValueError("Virginia precinct detail does not reconcile to the locality turnout modes")
    return out


def parse_detail(body, *, control, clock):
    if len(body) > MAX_BYTES:
        raise ValueError("Virginia precinct detail exceeds its reviewed size")
    text = body.decode("utf-8-sig")
    headings = re.findall(r'<h1 class="turnout-stats">([^<]+)</h1>', text)
    if (re.findall(r"<title>\s*([^<]+?)\s*</title>", text) != ["2022 November General"]
            or re.findall(r'<h2 class="entry-title">([^<]+)</h2>', text) != ["Official Results"]
            or list(map(unescape, headings)) != ["Turnout Statistics - " + control["county"]]
            or re.findall(r'<p class="asOf">Page generated on ([^<]+)</p>', text) != [clock]):
        raise ValueError("Virginia precinct detail edition, stage or locality differs")
    tables = [t for t in html_tables(body) if t and t[0] == ("Precinct Name", "Totals")]
    if len(tables) != 1:
        raise ValueError("Missing or repeated Virginia precinct turnout table")
    rows = [list(row) for row in tables[0][1:]]
    reconcile(rows, control)
    return rows


def collect(collector, *, reuse_checked_week=False):
    from scripts.results_intake import source_error

    old = collector.prior.get(FEED) or {}
    day = collector.now.astimezone(timezone.utc).date()
    week = (day - timedelta(days=day.weekday())).isoformat()
    if reuse_checked_week and not collector.offline and old.get("archive_check_week_utc") == week:
        return old
    stage, url = "index_acquisition", VA_LOCALITY_URL
    try:
        body, _ = collector.acquire(url)
        stage = "index_validation"
        index = parse_index(body)
        source = {"url": url, **pin(body)}
        report = index["report"]
        prior = old.get("data") or {}
        if prior and report["edition"] < prior["index"]["report"]["edition"]:
            raise ValueError("Virginia precinct turnout edition regressed")
        details = {}
        for control in report["counties"]:
            name = control["county"]
            stage, url = "detail_acquisition", urljoin(VA_LOCALITY_URL, index["links"][name])
            body, _ = collector.acquire(url)
            stage = "detail_validation"
            details[name] = {"source": {"url": url, **pin(body)},
                             "rows": parse_detail(body, control=control, clock=report["native_clock"])}
        data = {"index": index, "details": details, "participation_observation_qualified": False}
        same_rows = bool(prior) and all(
            detail["rows"] == prior["details"][name]["rows"] for name, detail in details.items())
        if prior and report["edition"] == prior["index"]["report"]["edition"] and (
                report != prior["index"]["report"] or not same_rows):
            raise ValueError("Virginia precinct counts changed without a new report edition")
        # Publisher HTML can change in transport without changing any accepted source facts.
        equivalent = (same_rows and prior["index"] == index
                      and prior.get("participation_observation_qualified") is False
                      and all(detail["source"]["url"] == prior["details"][name]["source"]["url"]
                              for name, detail in details.items()))
        entry = copy.deepcopy(old) if equivalent else {
            "data": data, "source": source, "first_observed_at": collector.observation_time().isoformat(),
        }
        entry.update(status="reported", error=None, error_stage=None, error_detail=None)
    except Exception as exc:
        code = source_error(exc)
        entry = copy.deepcopy(old) if old.get("data") is not None else {
            "data": None, "source": None, "first_observed_at": None,
        }
        entry.update(status="retained_after_failure" if entry["data"] is not None else code,
                     error=code, error_stage=stage,
                     error_detail=str(exc) if isinstance(exc, (ValueError, IntakeError)) else None)
    entry["attempted_source_url"] = url if entry["error"] else VA_LOCALITY_URL
    if not collector.offline:
        entry["archive_check_week_utc"] = week
    collector.attempts.append({"id": FEED, "url": entry["attempted_source_url"], "status": entry["status"]})
    return entry


def exports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is None:
        return
    if entry["status"] not in {"reported", "retained_after_failure"}:
        raise ValueError("Invalid Virginia precinct source status")
    index = data["index"]
    report = index["report"]
    for control in report["counties"]:
        name = control["county"]
        detail = data["details"][name]
        for row in reconcile(detail["rows"], control):
            yield {
                "state": "VA", "election_date": VA_LOCALITY_DATE, "locality": name, **row,
                "locality_ballots_control": control["ballots_cast"], "source_edition": report["edition"],
                "source_url": detail["source"]["url"], "source_sha256": detail["source"]["sha256"],
                "control_url": entry["source"]["url"], "control_sha256": entry["source"]["sha256"],
                "source_status": entry["status"], "checked_week_utc": entry.get("archive_check_week_utc"),
                "first_observed_at": entry["first_observed_at"], "registration_denominator": None,
                "turnout_rate": None, "geometry_qualified": False,
            }


def original_reports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is None:
        return
    index = data["index"]
    source = entry["source"]
    yield FEED, source, ".html", MAX_BYTES, source["url"] == VA_LOCALITY_URL, parse_index, index
    for pos, control in enumerate(index["report"]["counties"], 1):
        name = control["county"]
        detail = data["details"][name]
        source = detail["source"]
        link = index["links"][name]
        yield (f"{FEED}-locality-{pos:03d}", source, ".html", MAX_BYTES,
               bool(DETAIL.fullmatch(link)) and source["url"] == urljoin(VA_LOCALITY_URL, link),
               partial(parse_detail, control=control, clock=index["report"]["native_clock"]), detail["rows"])
