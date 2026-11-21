"""Reproduce the 2022 Virginia aggregate absentee application and receipt series."""

from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
import io
import re
from urllib.parse import urljoin

from scripts.participation_intake.contract import encoded, pin
from scripts.results_turnout_history import (
    VA_LOCALITY_DATE, VA_LOCALITY_ROSTER, VA_LOCALITY_URL, VA_URL, html_tables, integer, parse_virginia,
)


FEED = "VA-2022-absentee-receipts-by-age-and-gender"
CSV = "virginia-2022-absentee-receipts-by-age-and-gender.csv"
REPORT = urljoin(VA_LOCALITY_URL, "Absentee.html")
RAW = urljoin(REPORT, "Absentee.csv")
MAX_BYTES = 3_000_000
HEADER = ("LocalityName", "CongressionalDistrict", "AgeRange", "Gender",
          "Reason", "ApplicationType", "ReceiptType", "TheCount")
AGES = {"18 to 25", "26 to 40", "41 to 60", "61 to 70", "Over 70"}
GENDERS = {"", "F", "M", "U", "X"}
METHODS = {"Designated Representative", "Drop Off", "In Person", "Mail", "Mail (Non-USPS)"}


def controls(body):
    if not 0 < len(body) <= MAX_BYTES:
        raise ValueError("Virginia absentee report exceeds its reviewed size")
    text = body.decode("utf-8-sig")
    clock = re.findall(r'<p class="asOf">Page generated on ([^<]+)</p>', text)
    if (re.findall(r"<title>\s*([^<]+?)\s*</title>", text) != ["2022 November General"]
            or '<h1 class="absentee-stats">Absentee Statistics</h1>' not in text or len(clock) != 1):
        raise ValueError("Virginia absentee report identity differs")
    edition = datetime.strptime(clock[0], "%m/%d/%Y %I:%M %p").isoformat()
    if edition[:10] < VA_LOCALITY_DATE:
        raise ValueError("Virginia absentee report predates election")
    summary = {}
    for label, key in (("Absentee Applications by Application Type", "applications"),
                       ("Absentee Ballots Returned by Method", "receipts")):
        matches = [t for t in html_tables(body) if t and t[0] == (label, "Count")]
        if len(matches) != 1 or any(len(row) != 2 for row in matches[0]):
            raise ValueError("Virginia absentee control table changed")
        facts = {name: integer(number) for name, number in matches[0][1:]}
        if len(facts) != len(matches[0]) - 1 or facts.pop("Total", None) != sum(
                count for name, count in facts.items() if name != "Total"):
            raise ValueError("Virginia absentee control does not reconcile")
        summary[key] = facts
    if set(summary["receipts"]) != METHODS:
        raise ValueError("Virginia absentee receipt methods changed")
    return {"edition": edition, **summary}


def certified(body):
    if not 0 < len(body) <= MAX_BYTES:
        raise ValueError("Virginia certified history exceeds its reviewed size")
    row, = [r for r in parse_virginia(body)["complete_native_query"] if r["year"] == 2022]
    return integer(row["voting_absentee_literal"])


def extract(body, *, control, certified_receipts):
    if not 0 < len(body) <= MAX_BYTES:
        raise ValueError("Virginia aggregate absentee CSV exceeds its reviewed size")
    reader = csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
    if tuple(next(reader, ())) != HEADER:
        raise ValueError("Virginia absentee CSV schema changed")
    application, receipt, by_group = Counter(), Counter(), Counter()
    seen, localities = set(), set()
    for row in reader:
        if len(row) != 8:
            raise ValueError("Malformed Virginia absentee CSV row")
        loc, district, age, gender, reason, app, method, value = row
        key = tuple(row[:-1])
        if (key in seen or not re.fullmatch(r"[A-Z &]+ (?:COUNTY|CITY)", loc)
                or not re.fullmatch(r"(?:0[1-9]|1[01])?", district)
                or age not in AGES or gender not in GENDERS or not reason
                or app not in control["applications"] or (method and method not in METHODS)
                or not re.fullmatch(r"[1-9][0-9]{0,8}", value)):
            raise ValueError("Invalid or duplicate Virginia absentee aggregate row")
        seen.add(key)
        localities.add(loc)
        n = int(value)
        application[app] += n
        if method:
            receipt[method] += n
        by_group[loc, age, gender, method] += n
        by_group["", age, gender, method] += n
    if pin(encoded(sorted(localities)))["sha256"] != VA_LOCALITY_ROSTER:
        raise ValueError("Virginia absentee locality roster differs")
    if (dict(application) != control["applications"] or dict(receipt) != control["receipts"]
            or sum(receipt.values()) != certified_receipts):
        raise ValueError("Virginia absentee CSV differs from published aggregate controls")
    return [[*key, n] for key, n in sorted(by_group.items())]


def collect(collector, *, reuse_checked_week=False):
    old = collector.prior.get(FEED) or {}
    day = collector.now.astimezone(timezone.utc).date()
    week = (day - timedelta(days=day.weekday())).isoformat()
    if reuse_checked_week and not collector.offline and old.get("archive_check_week_utc") == week:
        return old

    def parse(body):
        control = controls(body)
        history, _ = collector.acquire(VA_URL)
        prior = old.get("data") or {}
        if prior and control["edition"] < prior["control"]["edition"]:
            raise ValueError("Virginia absentee control edition regressed")
        n = certified(history)
        raw, _ = collector.acquire(RAW)
        return {"control": control, "certified_receipts": n, "groups": extract(raw, control=control, certified_receipts=n),
                "raw": {"url": RAW, **pin(raw)}, "certified": {"url": VA_URL, **pin(history)},
                "participation_observation_qualified": False}

    entry = collector.capture(FEED, REPORT, parse, equivalent=lambda prior, new: all(
        prior[key] == new[key] for key in ("control", "certified_receipts", "groups", "raw")))
    if not collector.offline:
        entry["archive_check_week_utc"] = week
    return entry


def exports(entries):
    entry = entries.get(FEED) or {}
    data = entry.get("data")
    if data is None:
        return
    if entry["status"] not in {"reported", "retained_after_failure"}:
        raise ValueError("Invalid Virginia absentee source status")
    for loc, age, gender, method, n in data["groups"]:
        yield {
            "state": "VA", "election_date": VA_LOCALITY_DATE, "geography_level": "locality" if loc else "state",
            "locality": loc or None, "native_age_range": age, "native_gender": gender or None,
            "receipt_method": method or None, "measure": "returned_absentee_ballot" if method else
            "application_without_recorded_receipt", "reported_count": n, "turnout_rate": None,
            "source_edition": data["control"]["edition"], "source_status": entry["status"],
            "checked_week_utc": entry.get("archive_check_week_utc"), "source_url": data["raw"]["url"],
            "source_sha256": data["raw"]["sha256"], "control_url": entry["source"]["url"],
            "control_sha256": entry["source"]["sha256"], "certified_url": data["certified"]["url"],
            "certified_sha256": data["certified"]["sha256"],
        }


def original_reports(entries):
    from functools import partial

    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is None:
        return
    source, raw, history = entry["source"], data["raw"], data["certified"]
    yield FEED + "-report", source, ".html", MAX_BYTES, source["url"] == REPORT, controls, data["control"]
    yield FEED + "-raw", raw, ".csv", MAX_BYTES, raw["url"] == RAW, partial(
        extract, control=data["control"], certified_receipts=data["certified_receipts"]), data["groups"]
    yield FEED + "-certified", history, ".html", MAX_BYTES, history["url"] == VA_URL, certified, data["certified_receipts"]
