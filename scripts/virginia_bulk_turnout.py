"""Discover and audit the official Virginia bulk turnout report against independent controls."""

import csv
from datetime import timedelta, timezone
from functools import partial
import io
import re
from urllib.parse import quote, urlsplit

from scripts.participation_intake.contract import pin
from scripts.results_native_virginia import _document
from scripts.results_turnout_history import (
    VA_NATIVE_LOCALITY_DATE, VA_NATIVE_LOCALITY_URL, VA_URL, parse_virginia, virginia_native_locality_report,
)
from scripts.virginia_precinct_turnout import PRECINCT


FEED = "VA-2024-native-precinct-turnout-audit"
CSV = "virginia-2024-native-precinct-turnout-audit.csv"
CONTROLS = "virginia-2024-native-precinct-turnout-controls.csv"
LIMIT = 2_000_000
API_LIMIT = 8_000_000
HEADER = ("election", "election_date", "locality", "precinct", "Early Voting", "Election Day",
          "Mailed Absentee", "Provisional", "Post-Election", "TotalVoteTurnout",
          "ActiveRegisteredVoters", "InactiveRegisteredVoters", "TotalRegisteredVoters")
FIELDS = ("early_voting", "election_day", "mailed_absentee", "provisional", "post_election",
          "printed_turnout", "active_registered", "inactive_registered", "total_registered")


def catalog(body):
    profile = virginia_native_locality_report(body)
    document = _document(body)
    reports = [report for category in document["election"]["publicReportCategories"]
               for report in category["reports"] if report["reportName"] == "Election Turnout"]
    if len(reports) != 1 or reports[0].get("county") is not None:
        raise ValueError("Missing or repeated Virginia statewide turnout report")
    blob = reports[0]["blobName"]
    if not re.fullmatch(r"Election Turnout_[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}\.csv", blob):
        raise ValueError("Unexpected Virginia statewide turnout filename")
    url = f"https://{urlsplit(VA_NATIVE_LOCALITY_URL).hostname}/cdn/results/{document['jurisdiction']['id']}/{quote(blob)}"
    return {"edition": profile["edition"], "url": url, "localities": profile["native_rows"]}


def certified(body):
    if not 0 < len(body) <= LIMIT:
        raise ValueError("Virginia certified history exceeds its reviewed size")
    rows = [row for row in parse_virginia(body)["complete_native_query"] if row["year"] == 2024]
    if len(rows) != 1 or rows[0]["rate_qualified"] is not True:
        raise ValueError("Virginia certified 2024 statewide turnout control is absent")
    return rows[0]


def extract(body, *, locality_names):
    if not 0 < len(body) <= LIMIT:
        raise ValueError("Virginia bulk turnout report exceeds its reviewed size")
    reader = csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
    if tuple(next(reader, ())) != HEADER:
        raise ValueError("Virginia bulk turnout header changed")
    rows = []
    seen, units, localities, placeholders = set(), set(), set(), set()
    for row in reader:
        if (len(row) != len(HEADER) or row[:2] != ["2024 November General", "11/05/2024 00:00:00"]
                or row[2] not in locality_names or tuple(row[2:4]) in seen):
            raise ValueError("Virginia bulk turnout row identity changed")
        locality, label = row[2:4]
        seen.add((locality, label))
        values = row[4:]
        if any(value and not re.fullmatch(r"[0-9]{1,9}", value) for value in values):
            raise ValueError("Invalid Virginia bulk turnout measure")
        early, day, mail, provisional, post, total, active, inactive, registered = [
            int(value) if value else None for value in values
        ]
        if sum(value or 0 for value in (early, day, mail, provisional, post)) != (total or 0):
            raise ValueError("Virginia printed turnout does not sum")
        if (active or 0) + (inactive or 0) != (registered or 0):
            raise ValueError("Virginia printed registration does not sum")
        match = PRECINCT.fullmatch(label)
        if match:
            identity = (locality, match[1])
            if identity in units or None in (early, day, mail, total, active, inactive, registered):
                raise ValueError("Duplicate or incomplete Virginia physical precinct")
            units.add(identity)
            localities.add(locality)
        elif label == f"{locality} PROVISIONALS" and all(
                value is None for value in (early, day, mail, post, active, inactive, registered)):
            placeholders.add(locality)
        else:
            raise ValueError("Unrecognized Virginia bulk turnout reporting unit")
        rows.append({"locality": locality, "reporting_unit": label,
                     "precinct_code": match[1] if match else None, **dict(zip(FIELDS, [
                         early, day, mail, provisional, post, total, active, inactive, registered,
                     ], strict=True))})
    if localities != locality_names or placeholders != locality_names:
        raise ValueError("Virginia bulk turnout locality roster differs")
    return rows


def collect(collector, *, reuse_checked_week=False):
    old = collector.prior.get(FEED) or {}
    day = collector.now.astimezone(timezone.utc).date()
    week = (day - timedelta(days=day.weekday())).isoformat()
    if reuse_checked_week and not collector.offline and old.get("archive_check_week_utc") == week:
        return old

    def parse(body):
        listing = catalog(body)
        prior = old.get("data") or {}
        if prior and listing["edition"] < prior["catalog"]["edition"]:
            raise ValueError("Virginia bulk report catalog clock regressed")
        turnout, _ = collector.acquire(listing["url"])
        state, _ = collector.acquire(VA_URL)
        rows = extract(turnout, locality_names={row[0] for row in listing["localities"]})
        return {"catalog": listing, "rows": rows, "certified_state": certified(state),
                "participation_observation_qualified": False,
                "report": {"url": listing["url"], **pin(turnout)}, "history": {"url": VA_URL, **pin(state)}}

    def equivalent(prior, new):
        # A change in the rest of the statewide history is not a new 2024 release.
        return all(prior.get(key) == new[key] for key in (
            "catalog", "rows", "certified_state", "report", "participation_observation_qualified"))

    entry = collector.capture(FEED, VA_NATIVE_LOCALITY_URL, parse, equivalent=equivalent)
    if not collector.offline:
        entry["archive_check_week_utc"] = week
    return entry


def exports(entries):
    entry = entries.get(FEED) or {}
    data = entry.get("data")
    if data is None:
        return [], []
    if entry["status"] not in {"reported", "retained_after_failure"}:
        raise ValueError("Invalid Virginia bulk turnout status")
    catalog, state = data["catalog"], data["certified_state"]
    shared = {
        "state": "VA", "election_date": VA_NATIVE_LOCALITY_DATE, "source_status": entry["status"],
        "checked_week_utc": entry.get("archive_check_week_utc"), "catalog_edition": catalog["edition"],
        "first_observed_at": entry["first_observed_at"], "report_url": data["report"]["url"],
        "report_sha256": data["report"]["sha256"], "control_url": entry["source"]["url"],
        "control_sha256": entry["source"]["sha256"], "certified_history_url": data["history"]["url"],
        "certified_history_sha256": data["history"]["sha256"],
    }
    native, sums = [], {}
    for row in data["rows"]:
        values = sums.setdefault(row["locality"], [0, 0, 0])
        values[0] += row["printed_turnout"] or 0
        values[1] += row["total_registered"] or 0
        values[2] += row["precinct_code"] is not None
        native.append({**shared, **row, "precinct_ballots_qualified": False,
                       "rate_qualified": False, "geometry_qualified": False})
    control = []
    for row in catalog["localities"]:
        name, _, _, _, _, locality_ballots, locality_registration, *_ = row
        locality_ballots, locality_registration = int(locality_ballots), int(locality_registration)
        n, d, units = sums[name]
        control.append({
            **shared, "geography_level": "locality", "locality": name, "physical_precincts": units,
            "csv_printed_turnout": n, "csv_printed_registration": d,
            "locality_api_ballots": locality_ballots, "locality_api_registration": locality_registration,
            "certified_state_total_voting": None, "certified_state_registration": None,
            "difference_from_locality_api": n - locality_ballots, "difference_from_certified_state": None,
        })
    n, d, units = map(sum, zip(*sums.values(), strict=True))
    control.append({
        **shared, "geography_level": "state", "locality": None, "physical_precincts": units,
        "csv_printed_turnout": n, "csv_printed_registration": d,
        "locality_api_ballots": sum(row["locality_api_ballots"] for row in control),
        "locality_api_registration": sum(row["locality_api_registration"] for row in control),
        "certified_state_total_voting": state["total_voting"],
        "certified_state_registration": state["registered_voters"],
        "difference_from_locality_api": n - sum(row["locality_api_ballots"] for row in control),
        "difference_from_certified_state": n - state["total_voting"],
    })
    return native, control


def original_reports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is None:
        return
    listing, statewide, report = data["catalog"], data["history"], data["report"]
    yield FEED + "-catalog", entry["source"], ".json", API_LIMIT, (
        entry["source"]["url"] == VA_NATIVE_LOCALITY_URL), catalog, listing
    yield FEED + "-csv", report, ".csv", LIMIT, report["url"] == listing["url"], partial(
        extract, locality_names={r[0] for r in listing["localities"]}), data["rows"]
    yield FEED + "-certified", statewide, ".html", LIMIT, statewide["url"] == VA_URL, certified, data["certified_state"]
