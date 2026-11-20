"""Reconcile Oregon's two published statewide general-election series."""
import io
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

HISTORY = "OR-general-election-turnout-history"
CONTROL = "OR-general-election-returned-ballot-controls"
URLS = {
    HISTORY: "https://sos.oregon.gov/elections/Documents/History/Voter_Turnout_History_General_Election.pdf",
    CONTROL: "https://sos.oregon.gov/elections/Documents/statistics/May-19-2026-Turnout-Statistics.pdf",
}
CSV = "participation-or-general-election-turnout-reconciliation.csv"
NUMBER = r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)"
RATE = r"[0-9]{1,3}\.[0-9]{2}%"


def query(lines, feed):
    rows = []
    stamp = None
    header = " ".join(lines)
    if feed == HISTORY:
        if ("Voter Turnout History" not in header or "for General Elections" not in header
                or "Total Registered Voters Total Votes Cast % of Turnout" not in header
                or "Oregon Secretary of State" not in header):
            raise ValueError("Oregon statewide history publisher or column semantics changed")
        generated = re.findall(r"\bGenerated (\d{2}/\d{2}/\d{4})\b", header)
        if len(generated) != 1:
            raise ValueError("Oregon historical edition stamp missing")
        stamp = datetime.strptime(generated[0], "%m/%d/%Y").date().isoformat()
    elif feed == CONTROL:
        if ("May 19, 2026 Primary Election" not in header or "Official Voter Registration & Turnout Statistics" not in header
                or "Comparative Voter Registration and Participation Statistics General Elections Other Totals "
                "Year Active Ballots Percent Active Ballots Percent Voters Returned Returned Voters Returned Returned"
                not in header):
            raise ValueError("Oregon general-election control table or scope changed")
        stamp = None  # The report's primary election date is not its issue or revision date.
    else:
        raise ValueError("Unknown Oregon history profile")
    for line in lines:
        if not re.match(r"\d{4}\s", line):
            continue
        prefix = "" if feed == HISTORY else rf"{NUMBER} (?:{NUMBER}|N/A) (?:{RATE}|N/A) "
        match = re.fullmatch(rf"(\d{{4}}) {prefix}({NUMBER}) ({NUMBER}) ({RATE})", line)
        if not match:
            raise ValueError("Malformed Oregon historical statewide row")
        year, register, votes, printed = match.groups()
        registered, reported = (int(s.replace(",", "")) for s in (register, votes))
        if not 0 < reported <= registered:
            raise ValueError("Oregon turnout counts are outside their source denominator")
        exact = Decimal(reported) * 100 / registered
        printed_value = Decimal(printed[:-1])
        rows.append({"year": int(year), "registered": registered, "count": reported,
                     "printed_rate": printed, "printed_rate_matches_counts": printed_value == exact.quantize(
                         Decimal(".01"), rounding=ROUND_HALF_UP)})
    years = [r["year"] for r in rows]
    allowed = (list(range(2024, 1959, -2)), list(range(2026, 1959, -2))) if feed == HISTORY else (
        list(range(1960, 2025, 2)),)
    last_election = "2026-11-03" if years and max(years) == 2026 else "2024-11-05"
    if years not in allowed or (stamp is not None and stamp < last_election):
        raise ValueError("Incomplete Oregon general-election history")
    return {"complete_native_query": rows, "native_lines": lines, "date": stamp,
            "participation_observation_qualified": False}


def parse(body, feed):
    from pypdf import PdfReader

    if not 0 < len(body) <= 5_000_000 or not body.startswith(b"%PDF-"):
        raise ValueError("Oregon source is not a bounded PDF")
    pages = PdfReader(io.BytesIO(body), strict=True).pages
    if feed == HISTORY:
        if len(pages) != 1:
            raise ValueError("Oregon statewide summary layout changed")
        page = pages[0]
    else:
        if not 40 <= len(pages) <= 70:
            raise ValueError("Oregon control report layout changed")
        page = pages[39]
    lines = [" ".join(line.split()) for line in page.extract_text(extraction_mode="layout").splitlines() if line.strip()]
    return query(lines, feed)


def collect(collector, feed, *, reuse_checked_week=False):
    old = collector.prior.get(feed) or {}
    day = collector.now.astimezone(timezone.utc).date()
    week = (day - timedelta(days=day.weekday())).isoformat()
    if (reuse_checked_week and not collector.offline and old.get("archive_check_week_utc") == week
            and old.get("status") == "reported" and old.get("data") is not None):
        return old

    def checked(body):
        data = parse(body, feed)
        prior_years = {row["year"] for row in (old.get("data") or {}).get("complete_native_query", ())}
        if (not prior_years <= {row["year"] for row in data["complete_native_query"]}
                or data.get("date") and data["date"] > day.isoformat()):
            raise ValueError("Oregon history is future-dated or lost an edition")
        return data

    entry = collector.capture(feed, URLS[feed], checked, equivalent=lambda before, after: before == after)
    if not collector.offline:
        entry["archive_check_week_utc"] = week
    return entry


def exports(entries):
    from scripts.retained_bulk_turnout import disposition

    by_feed = {}
    for feed, url in URLS.items():
        entry = entries.get(feed, {})
        data = entry.get("data")
        if entry.get("status") not in ("reported", "retained_after_failure") or data is None:
            continue
        if entry["source"]["url"] != url or data != query(data["native_lines"], feed):
            raise ValueError("Oregon historical facts differ from their retained source query")
        by_feed[feed] = {row["year"]: (row, entry) for row in data["complete_native_query"]}
    history, control = (by_feed.get(feed, {}) for feed in (HISTORY, CONTROL))
    for year in sorted(set(history) | set(control), reverse=True):
        h, c = history.get(year), control.get(year)
        agreed = h and c and all(h[0][field] == c[0][field] for field in ("registered", "count"))
        row = {"state_code": "OR", "year": year,
               "election_type": "presidential" if year % 4 == 0 else "midterm",
               "reconciliation": "counts_agree" if agreed else "counts_differ" if h and c else "one_source",
               "matched_returned_ballots_per_active_voter": c[0]["count"] / c[0]["registered"] if agreed else None}
        for prefix, fact in (("history", h), ("control", c)):
            values, entry = fact or ({}, {})
            row.update({f"{prefix}_{name}": values.get(name)
                        for name in ("registered", "count", "printed_rate", "printed_rate_matches_counts")})
            row.update({f"{prefix}_url": entry.get("source", {}).get("url"),
                        f"{prefix}_sha256": entry.get("source", {}).get("sha256"),
                        f"{prefix}_source_status": entry.get("status"),
                        f"{prefix}_generation_date": entry.get("data", {}).get("date"),
                        f"{prefix}_checked_week_utc": entry.get("archive_check_week_utc")})
            row.update({f"{prefix}_{name}": val for name, val in disposition(entry).items()})
        yield row
