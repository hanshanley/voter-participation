"""Pair published North Carolina aggregate archives without exporting fine cells."""

import csv
from datetime import date
import io
import re
from zipfile import ZipFile

from scripts.participation_intake.contract import IntakeError, count, digest, pin
from scripts.results_turnout_history import archive_link


FEED = "NC-2026-general-vote-history"
ELECTION = date(2026, 11, 3)
CATALOGS = {
    "history": "https://www.ncsbe.gov/results-data/voter-history-data",
    "voter": "https://www.ncsbe.gov/results-data/voter-registration-data",
}
BASE = "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/"
AGES = ("Age 18 - 25", "Age 26 - 40", "Age 41 - 65", "Age Over 66")
COUNTY_PIN = "bd1ee4825fb7de37c7c1efd80d0ca28d45e9e3c4b65bb79d0fac9cd38248849c"
HEADERS = {
    "history": ("county_desc precinct_abbrv vtd_abbrv age party_cd race_code ethnic_code sex_code "
                "total_voters election_date stats_type update_date voting_method voting_method_desc voted_party_cd"),
    "voter": ("county_desc election_date stats_type precinct_abbrv vtd_abbrv party_cd race_code "
              "ethnic_code sex_code age total_voters update_date"),
}


def report_url(kind, election):
    return f"{BASE}{election:%Y_%m_%d}/{kind}_stats_{election:%Y%m%d}.zip"


def extract(body, kind, election):
    member = f"{kind}_stats_{election:%Y%m%d}.txt"
    expected_date = election.strftime("%m/%d/%Y")
    ages = dict.fromkeys(AGES, 0)
    counties, editions = set(), set()
    with ZipFile(io.BytesIO(body)) as archive:
        contents = archive.infolist()
        if (len(contents) != 1 or contents[0].filename != member
                or not 0 < contents[0].file_size <= 150_000_000):
            raise ValueError("Unexpected North Carolina aggregate archive inventory")
        with archive.open(contents[0]) as data:
            reader = csv.reader(io.TextIOWrapper(data, encoding="utf-8-sig"), delimiter="\t", strict=True)
            fields = HEADERS[kind].split()
            if next(reader, None) != fields:
                raise ValueError("North Carolina aggregate fields changed")
            indexes = [fields.index(name) for name in
                       ("county_desc", "election_date", "stats_type", "update_date", "age", "total_voters")]
            for native in reader:
                if len(native) != len(fields):
                    raise ValueError("North Carolina aggregate row length changed")
                county, day, category, updated, age, value = (native[i] for i in indexes)
                if (day != expected_date or category != kind or age not in ages
                        or not re.fullmatch(r"[0-9]+", value)):
                    raise ValueError("North Carolina aggregate scope or count changed")
                ages[age] += count(value)
                counties.add(county)
                editions.add(updated)
    if (len(counties) != 100
            or digest(("\n".join(sorted(counties)) + "\n").encode()) != COUNTY_PIN
            or len(editions) != 1 or min(ages.values()) <= 0):
        raise ValueError("Incomplete or mixed-edition North Carolina aggregate")
    month, day, year = (int(part) for part in next(iter(editions)).split("/"))
    edition = date(year, month, day)
    if edition < election:
        raise ValueError("North Carolina aggregate predates its election")
    return {"edition": edition.isoformat(), "statewide_by_age": ages,
            "county_inventory_sha256": COUNTY_PIN, "source": {"url": report_url(kind, election), **pin(body)}}


def collect(collector):
    def parse(history_index):
        history = archive_link(history_index, CATALOGS["history"], re.escape(report_url("history", ELECTION)))
        if not history:
            raise IntakeError("report_not_linked", "North Carolina has not linked the November 2026 voter-history archive")
        voter = archive_link(collector.acquire(CATALOGS["voter"])[0], CATALOGS["voter"],
                             re.escape(report_url("voter", ELECTION)))
        if not voter:
            raise IntakeError("report_not_linked", "North Carolina has not linked the November 2026 registration archive")
        prior = (collector.prior.get(FEED) or {}).get("data") or {}
        pair = {}
        for kind, url in (("history", history), ("voter", voter)):
            body, _ = collector.acquire(url)
            source = {"url": url, **pin(body)}
            previous = (prior.get("pair") or {}).get(kind)
            pair[kind] = previous if previous and previous["source"] == source else extract(body, kind, ELECTION)
            if previous and pair[kind]["edition"] < previous["edition"]:
                raise ValueError("North Carolina aggregate edition regressed")
        return {"election_date": ELECTION.isoformat(), "pair": pair,
                "participation_observation_qualified": False}

    return collector.capture(FEED, CATALOGS["history"], parse, equivalent=lambda old, new: old == new)


def rows(entries):
    entry = entries.get(FEED, {})
    data = entry.get("data")
    if not data:
        return []
    pair = data["pair"]
    if (data["election_date"] != ELECTION.isoformat()
            or entry["status"] not in ("reported", "retained_after_failure")
            or any(pair[kind]["source"]["url"] != report_url(kind, ELECTION)
                   or not re.fullmatch(r"[a-f0-9]{64}", pair[kind]["source"]["sha256"])
                   or date.fromisoformat(pair[kind]["edition"]) < ELECTION
                   or pair[kind]["county_inventory_sha256"] != COUNTY_PIN
                   or set(pair[kind]["statewide_by_age"]) != set(AGES)
                   or any(type(value) is not int or value <= 0
                          for value in pair[kind]["statewide_by_age"].values())
                   for kind in CATALOGS)):
        raise ValueError("Incompatible North Carolina paired aggregate evidence")
    result = []
    for age in AGES:
        voted = pair["history"]["statewide_by_age"][age]
        registered = pair["voter"]["statewide_by_age"][age]
        result.append({
            "state_code": "NC", "election_date": data["election_date"], "geography_level": "state",
            "native_age_label": age, "status": entry["status"], "voters_with_history": voted,
            "active_and_inactive_registered_voters": registered,
            "source_defined_rate_pct": 100 * voted / registered if 0 < voted <= registered else None,
            "history_source": pair["history"]["source"]["url"],
            "registration_source": pair["voter"]["source"]["url"],
            "history_sha256": pair["history"]["source"]["sha256"],
            "registration_sha256": pair["voter"]["source"]["sha256"],
            "history_edition": pair["history"]["edition"], "registration_edition": pair["voter"]["edition"],
            "rate_hold": "History count exceeds the registration count" if voted > registered else None,
            "not_a_ballot_count_or_population_turnout_rate": True,
            "reporting_completeness_or_certification_established": False,
        })
    return result
