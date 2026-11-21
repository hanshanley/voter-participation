"""Discover official turnout releases without treating links as observations."""

from datetime import timedelta, timezone
from html.parser import HTMLParser
import re
from urllib.parse import unquote, urljoin, urlsplit

from scripts import connecticut_turnout_history
from scripts.participation_intake.contract import IntakeError


CENSUS = "US-2026-CPS-turnout-release-index"
EAC = "US-2026-EAVS-turnout-release-index"
CT = "CT-2026-general-statement-of-vote-index"
WV = "WV-2026-general-write-in-results-index"
INDEXES = {
    CENSUS: "https://www.census.gov/topics/public-sector/voting/data/tables.html",
    EAC: "https://www.eac.gov/research-and-data/studies-and-reports",
    CT: connecticut_turnout_history.STATEMENT_INDEX,
    WV: "https://sos.wv.gov/elections/election-data/historical-election-results-and-turnout",
}
CSV = "participation-turnout-release-watch.csv"
FEDERAL_CSV = "congressional-write-in-release-watch.csv"


class Labels(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = None
        self.labels = []

    def handle_starttag(self, tag, attrs):
        if tag in {"a", "button", "h1"}:
            self.active = (tag, dict(attrs), [])

    def handle_data(self, data):
        if self.active:
            self.active[2].append(data)

    def handle_endtag(self, tag):
        if self.active and tag == self.active[0]:
            _, attrs, words = self.active
            self.labels.append((tag, attrs, " ".join("".join(words).split())))
            self.active = None


def discover(body, feed, *, year=2026):
    if not 0 < len(body) <= 2_000_000:
        raise IntakeError("release_index_size", "Unexpected national turnout index size")
    parser = Labels()
    parser.feed(body.decode("utf-8"))
    base = INDEXES[feed]

    def local(href):
        url = urlsplit(urljoin(base, href or ""))
        if url.scheme == "https" and url.netloc == urlsplit(base).netloc and not (url.query or url.fragment):
            return url.geturl()
        return ""

    labels = parser.labels
    discovered = set()
    if feed == CENSUS:
        known = set()
        prefix = "Voting and Registration in the Election of November "
        for tag, attrs, text in labels:
            if tag != "a":
                continue
            title = attrs.get("title", text)
            match = re.fullmatch(re.escape(prefix) + r"(\d{4})", title)
            if not match:
                continue
            target = local(attrs.get("href"))
            if re.fullmatch(r"https://www\.census\.gov/data/tables/time-series/demo/voting-and-registration/[^/]+\.html", target):
                known.add(int(match[1]))
                if int(match[1]) == year:
                    discovered.add((target, "detailed_table_index"))
        if not (year in known or year - 2 in known):
            raise IntakeError("release_index_schema", "Expected Census detailed-table series not found")
    elif feed == CT:
        prior_link = False
        for tag, attrs, text in labels:
            if tag != "a":
                continue
            target = urljoin(base, attrs.get("href") or "")
            if connecticut_turnout_history.valid_link(target, year - 2) and text == str(year - 2):
                prior_link = True
            if text == str(year) and connecticut_turnout_history.valid_link(target, year):
                discovered.add((target, "statement_of_vote"))
        if not prior_link or len(discovered) > 1:
            raise IntakeError("release_index_schema", "Expected Connecticut general-election index or unique new link")
    elif feed == WV:
        archive_years = set()
        for tag, attrs, text in labels:
            match = re.fullmatch(r"(\d{4}) General(?: Election)? Write-In Results", text, re.I)
            if tag != "a" or not match:
                continue
            target = urljoin(base, attrs.get("href") or "")
            if not re.fullmatch(r"https://sos\.wv\.gov/media/[1-9]\d*/download(?:\?inline=?)?", target):
                if int(match[1]) == year:
                    raise IntakeError("release_index_schema", "Unexpected West Virginia write-in archive route")
                continue
            archive_years.add(int(match[1]))
            if int(match[1]) == year:
                discovered.add((target, "official_write_in_results"))
        if year - 2 not in archive_years or len(discovered) > 1:
            raise IntakeError("release_index_schema", "Expected West Virginia write-in archive or unique new link")
    elif feed == EAC:
        sections = [(i, text) for i, (tag, attrs, text) in enumerate(labels)
                    if tag == "button" and attrs.get("aria-controls") and re.fullmatch(r"\d{4}", text)]
        keys = [i for i, (_, name) in enumerate(sections) if name == str(year)]
        if len(keys) != 1:
            raise IntakeError("release_index_schema", "Expected EAVS reporting-year section not found")
        key = keys[0]
        start = sections[key][0] + 1
        end = sections[key + 1][0] if key + 1 < len(sections) else len(labels)
        for tag, attrs, label in labels[start:end]:
            if tag != "a":
                continue
            target = local(attrs.get("href"))
            path = unquote(urlsplit(target).path).lower()
            name = path.rsplit("/", 1)[-1]
            if not path.startswith("/sites/default/files/") or str(year) not in name or "eavs" not in name:
                continue
            if ("policy" not in name and "codebook" not in name and
                    (label.casefold() in {"csv", "excel"} or re.search(r"dataset|public.release", name))
                    and name.endswith((".csv", ".xlsx", ".zip"))):
                discovered.add((target, "administrative_dataset"))
            elif "codebook" in name and "policy" not in name and name.endswith((".pdf", ".docx", ".xlsx")):
                discovered.add((target, "administrative_codebook"))
    ready = any(kind in {"detailed_table_index", "administrative_dataset", "statement_of_vote", "official_write_in_results"}
                for _, kind in discovered)
    if feed == EAC:
        ready = ready and any(kind == "administrative_codebook" for _, kind in discovered)
    return {
        "election_year": year, "participation_observation_qualified": False,
        "complete_native_query": {
            "release_status": "candidate_links_require_admission" if ready else
                "incomplete_release_links" if discovered else "not_yet_linked",
            "links": [{"url": url, "kind": kind} for url, kind in sorted(discovered)],
        },
    }


def collect(collector, feed, *, reuse_checked_week=False):
    old = collector.prior.get(feed) or {}
    day = collector.now.astimezone(timezone.utc).date()
    week = (day - timedelta(days=day.weekday())).isoformat()
    if (reuse_checked_week and not collector.offline and old.get("archive_check_week_utc") == week
            and old.get("status") == "reported" and old.get("data") is not None):
        return old
    def parse(body):
        data = discover(body, feed)
        prior = (old.get("data") or {}).get("complete_native_query", {})
        current = data["complete_native_query"]
        if (prior.get("release_status") == "candidate_links_require_admission"
                and current["release_status"] != "candidate_links_require_admission"):
            raise IntakeError("release_index_regressed", "Previously listed release links are no longer available")
        return data

    entry = collector.capture(feed, INDEXES[feed], parse, shared_acquisition=feed == CT,
                              equivalent=lambda previous, latest: previous == latest)
    if not collector.offline:
        entry["archive_check_week_utc"] = week
    return entry


def _exports(entries, feeds):
    for feed in feeds:
        if feed not in entries:
            continue
        index = INDEXES[feed]
        entry = entries[feed]
        data = entry.get("data")
        query = data["complete_native_query"] if data is not None else {
            "release_status": "index_not_verified", "links": []}
        if data is not None and (data["participation_observation_qualified"] is not False
                                 or entry["source"]["url"] != index
                                 or entry["status"] not in {"reported", "retained_after_failure"}):
            raise ValueError("Turnout release watch is not bound to its checked index")
        for link in query["links"] or [{}]:
            url = link.get("url")
            if url is not None:
                target = urlsplit(url)
                if target.scheme != "https" or target.netloc != urlsplit(index).netloc or target.fragment:
                    raise ValueError("Turnout release link is not on its official index domain")
            yield {"source_id": feed, "election_year": (data or {}).get("election_year", 2026),
                   "index_url": index, "source_status": entry["status"],
                   "release_status": query["release_status"], "release_url": url,
                   "release_kind": link.get("kind"), "index_check_week_utc": entry.get("archive_check_week_utc"),
                   "first_observed_at": entry.get("first_observed_at"),
                   "index_sha256": (entry.get("source") or {}).get("sha256"),
                   "error": entry.get("error"), "participation_observation_qualified": False}


def exports(entries):
    return _exports(entries, (CENSUS, EAC, CT))


def federal_exports(entries):
    return _exports(entries, (WV,))
