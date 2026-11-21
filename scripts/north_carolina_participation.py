"""Election-specific NCSBE voter-history and registration statistics."""

from collections import Counter, defaultdict
import csv
from datetime import date
import io
import json
import re
from zipfile import ZipFile

from scripts.participation_intake.contract import IntakeError, count, digest, pin
from scripts.results_nc_vote_history import AGES, CATALOGS, COUNTY_PIN, HEADERS, report_url
from scripts.results_turnout_history import archive_link, html_tables
from scripts.southeast_turnout import collect_report


FEEDS = {
    f"NC-{year}-general-participation-statistics": date(year, 11, day)
    for year, day in ((2008, 4), (2010, 2), (2012, 6), (2014, 4), (2016, 8),
                      (2018, 6), (2020, 3), (2022, 8), (2024, 5), (2026, 3))
}
COUNTIES = "participation-nc-general-county-history.csv"
GROUPS = "participation-nc-general-state-groups.csv"
PRECINCTS = "participation-nc-general-native-precincts.csv"
FIELDS = {"age": "age", "race": "race_code", "ethnicity": "ethnic_code", "sex": "sex_code"}
MAX_BYTES = 35_000_000
EARLY_VOTER_HEADER = ("county_desc precinct_abbrv {vtd}age party_cd race_code ethnic_code sex_code "
                      "total_voters election_date stats_type update_date")
TRUNCATED_VOTER_EDITIONS = {2012: "Nov  6 201", 2014: "Nov  5 201"}
CONTROLS = {
    year: f"https://www.ncsbe.gov/results-data/voter-turnout/{year}-general-election-turnout"
    for year in (2022, 2024)
}
GROUP_LABELS = {
    "race": ("A", "B", "I", "M", "O", "P", "U", "W"),
    "ethnicity": ("HL", "NL", "UN"),
}
PUBLISHED_LABELS = {
    "race": ("Asian", "Black or African American", "American Indian or Alaska Native", "Two or More Races",
             "Other", "Native Hawaiian or Pacific Islander", "Undesignated", "White"),
    "ethnicity": ("Hispanic or Latino", "Not Hispanic or Latino", "Undesignated"),
}


def extract(body, kind, election):
    fields = HEADERS[kind].split()
    if kind == "voter" and election.year <= 2012:
        fields = EARLY_VOTER_HEADER.format(vtd="vtd_abbrv " if election.year == 2012 else "").split()
    padded = kind == "voter" and election.year <= 2014
    counties, units = Counter(), Counter()
    vtds = defaultdict(set)
    native_codes = {}
    groups = {field: Counter() for field in FIELDS}
    editions = set()
    with ZipFile(io.BytesIO(body)) as archive:
        members = archive.infolist()
        if (len(members) != 1 or members[0].filename != f"{kind}_stats_{election:%Y%m%d}.txt"
                or not 0 < members[0].file_size <= 150_000_000):
            raise ValueError("Unexpected NC aggregate archive inventory")
        with archive.open(members[0]) as data:
            reader = csv.reader(io.TextIOWrapper(data, encoding="utf-8-sig"), delimiter="\t", strict=True)
            if next(reader, None) != fields:
                raise ValueError("NC aggregate schema changed")
            indexes = [fields.index(name) for name in (
                "county_desc", "election_date", "stats_type", "update_date", "total_voters",
                "precinct_abbrv", *FIELDS.values())]
            vtd_index = fields.index("vtd_abbrv") if "vtd_abbrv" in fields else None
            expected_date = election.strftime("%m/%d/%Y")
            for row in reader:
                if len(row) != len(fields):
                    raise ValueError("NC aggregate row width changed")
                county, day, category, updated, raw, precinct, *labels = (row[i] for i in indexes)
                if day != expected_date or category != kind or not re.fullmatch(r"[0-9]+", raw):
                    raise ValueError("NC aggregate election, category or count changed")
                value = count(raw)
                if padded:
                    native = precinct
                    precinct = native.rstrip(" ")
                    if native_codes.setdefault((county, precinct), native) != native:
                        raise ValueError("NC registration precinct padding collapses distinct native keys")
                counties[county] += value
                units[county, precinct] += value
                if vtd_index is not None:
                    vtds[county, precinct].add(row[vtd_index])
                for field, label in zip(FIELDS, labels, strict=True):
                    groups[field][label] += value
                editions.add(updated)
    if (len(counties) != 100 or min(counties.values()) <= 0
            or digest(("\n".join(sorted(counties)) + "\n").encode()) != COUNTY_PIN
            or len(editions) != 1):
        raise ValueError("Incomplete or mixed-edition NC aggregate")
    (native_edition,) = editions
    edition = None
    truncated = kind == "voter" and native_edition == TRUNCATED_VOTER_EDITIONS.get(election.year)
    if native_edition and not truncated:
        month, day, year = (int(value) for value in native_edition.split("/"))
        edition = date(year, month, day)
        if edition < election:
            raise ValueError("NC aggregate edition predates election")
    elif not truncated and (kind != "voter" or election.year not in (2016, 2018)):
        raise ValueError("Missing NC native update edition")
    return {
        "edition": edition.isoformat() if edition else None,
        "counties": dict(sorted(counties.items())),
        "units": [[county, precinct, value, sorted(vtds[county, precinct])]
                  for (county, precinct), value in sorted(units.items())],
        "groups": {field: dict(sorted(totals.items())) for field, totals in groups.items()},
        **({"truncated_edition": native_edition} if truncated else {}),
        **({"native_codes": [[c, p, native] for (c, p), native in sorted(native_codes.items()) if p != native]}
           if padded else {}),
    }


def _published_control(tables, year, number, dimension, labels, codes):
    title = f"Table {number}: North Carolina Voter Turnout by {dimension} in the {year} General Election"
    matches = [rows for caption, rows in tables if caption == title]
    if (len(matches) != 1 or any(len(row) != 3 for row in matches[0])
            or [row[0] for row in matches[0]] != [dimension, *labels]
            or matches[0][0] != (dimension, "Voters Who Voted", "Turnout (%)")):
        raise ValueError(f"NC published {dimension} control has changed schema")
    result = {}
    for code, (_, n, percent) in zip(codes, matches[0][1:], strict=True):
        if not re.fullmatch(r"[0-9][0-9,]*", n) or not re.fullmatch(r"\d{1,3}(?:\.\d)?%", percent):
            raise ValueError(f"NC {dimension} control count or percentage changed format")
        places = int("." in percent)
        if dimension == "Age Group" and places != 1:
            raise ValueError("NC age control is not printed to one decimal place")
        result[code] = [count(n.replace(",", "")), int(percent[:-1].replace(".", ""))]
        if dimension != "Age Group":
            result[code].append(places)
    return result


def age_control(body, year):
    return _published_control(html_tables(body, with_captions=True), year, 3, "Age Group",
                              ("Age 18\u201325", "Age 26\u201340", "Age 41\u201365", "Age 66+"), AGES)


def demographic_control(body, year):
    tables = html_tables(body, with_captions=True)
    return {dimension: _published_control(tables, year, number, dimension.title(),
                                           PUBLISHED_LABELS[dimension], GROUP_LABELS[dimension])
            for number, dimension in ((4, "race"), (5, "ethnicity"))}


def published_controls(body, year):
    return {"facts": age_control(body, year), "group_facts": demographic_control(body, year)}


def collect(collector, feed, *, reuse_checked_week=False):
    election = FEEDS[feed]
    prior = (collector.prior.get(feed) or {}).get("data") or {}
    if election.year in CONTROLS and "group_facts" not in (prior.get("age_control") or {}):
        reuse_checked_week = False

    def parse(index, _):
        pair = {}
        for kind, catalog in CATALOGS.items():
            path = report_url(kind, election)
            if not archive_link(index if kind == "history" else collector.acquire(catalog)[0],
                                catalog, re.escape(path)):
                raise IntakeError("report_not_linked", f"NCSBE has not linked the {election} {kind} statistics")
            body, _ = collector.acquire(path)
            if not 0 < len(body) <= MAX_BYTES:
                raise ValueError("Unexpected NC aggregate download size")
            source = {"url": path, **pin(body)}
            previous = (prior.get("pair") or {}).get(kind)
            facts = (previous["facts"] if previous and previous["source"] == source
                     else extract(body, kind, election))
            if previous and previous["facts"]["edition"] and (
                    not facts["edition"] or facts["edition"] < previous["facts"]["edition"]):
                raise ValueError("NC archive edition regressed")
            pair[kind] = {"source": source, "facts": facts}
        control = None
        if url := CONTROLS.get(election.year):
            body, _ = collector.acquire(url)
            control = {"source": {"url": url, **pin(body)}, **published_controls(body, election.year)}
            if (previous := prior.get("age_control")) and all(
                    control[key] == previous.get(key) for key in ("facts", "group_facts")):
                control = previous
        return {"election_date": election.isoformat(), "pair": pair, "age_control": control,
                "participation_observation_qualified": False}

    return collect_report(collector, feed, CATALOGS["history"], parse,
                          reuse_checked_week=reuse_checked_week, shared_acquisition=True)


def reviewed_age_rate(voted, registered, published):
    if published is None:
        return None, "no_published_age_control"
    if voted != published[0]:
        return None, "published_history_count_differs"
    if not registered or not 0 < voted <= registered:
        return None, "incompatible_registration_count"
    # Compare at the precision actually printed by NCSBE.
    places = published[2] if len(published) == 3 else 1
    if (voted * 200 * 10**places + registered) // (2 * registered) != published[1]:
        return None, "published_age_rate_differs"
    return 100 * voted / registered, None


def exports(entries):
    county_rows, group_rows, precinct_rows = [], [], []
    for feed, election in FEEDS.items():
        entry = entries.get(feed) or {}
        if (data := entry.get("data")) is None:
            continue
        pair = data["pair"]
        if (entry["status"] not in ("reported", "retained_after_failure")
                or data["election_date"] != election.isoformat()
                or any(pair[kind]["source"]["url"] != report_url(kind, election) for kind in CATALOGS)):
            raise ValueError("Incompatible NC archive evidence")
        history, voter = (pair[kind]["facts"] for kind in CATALOGS)
        control = data["age_control"]
        if control and control["source"]["url"] != CONTROLS.get(election.year):
            raise ValueError("Incompatible NC published age control")
        context = {
            "state_code": "NC", "election_date": election.isoformat(), "source_status": entry["status"],
            "checked_week_utc": entry.get("archive_check_week_utc"),
            **{f"{kind}_{field}": pair[kind]["source"][field] for kind in CATALOGS for field in ("url", "sha256")},
            **{f"{kind}_edition": pair[kind]["facts"]["edition"] for kind in CATALOGS},
            "voter_unparsed_edition": voter.get("truncated_edition"),
        }
        for name in ["", *history["counties"]]:
            county_rows.append({
                **context, "geography_level": "county" if name else "state", "native_county": name,
                "voters_with_history": history["counties"][name] if name else sum(history["counties"].values()),
                "registered_voter_statistics": voter["counties"][name] if name else sum(voter["counties"].values()),
                "rate_hold": "no_county_denominator_control" if name else "no_overall_archive_rate_control",
            })
        for dimension in FIELDS:
            h, v = (source["groups"][dimension] for source in (history, voter))
            for label in sorted(h.keys() | v.keys()):
                published = ((control["facts"] if dimension == "age"
                              else control.get("group_facts", {}).get(dimension, {})).get(label)
                             if control else None)
                rate, hold = reviewed_age_rate(h.get(label), v.get(label), published)
                if dimension != "age" and hold == "published_age_rate_differs":
                    hold = "published_group_rate_differs"
                places = (published[2] if len(published) == 3 else 1) if published else None
                group_rows.append({
                    **context, "dimension": dimension, "native_group": label,
                    "voters_with_history": h.get(label), "registered_voter_statistics": v.get(label),
                    "source_defined_rate_pct": rate,
                    "rate_hold": hold if dimension == "age" or published else "no_group_rate_control",
                    "published_control_count": published[0] if published else None,
                    "published_control_rate_pct": published[1] / 10**places if published else None,
                    "published_control_decimal_places": places,
                    "published_control_url": control["source"]["url"] if published else None,
                    "published_control_sha256": control["source"]["sha256"] if published else None,
                })
        h, v = ({(c, p): (value, districts) for c, p, value, districts in source["units"]}
                for source in (history, voter))
        raw_voter_code = {(c, p): raw for c, p, raw in voter.get("native_codes", [])}
        for county, precinct in sorted(h.keys() | v.keys()):
            counts, hvtd = h.get((county, precinct), (None, []))
            stock, vvtd = v.get((county, precinct), (None, []))
            precinct_rows.append({
                **context, "native_county": county, "native_precinct_code": precinct,
                "voter_precinct_code_as_printed": raw_voter_code.get((county, precinct), precinct)
                if stock is not None else None,
                "voters_with_history": counts, "registered_voter_statistics": stock,
                "history_native_vtd_codes": json.dumps(hvtd), "voter_native_vtd_codes": json.dumps(vvtd),
                "geometry_hold": "election_effective_precinct_identity_not_verified",
                "rate_hold": "precinct_denominator_and_geometry_not_verified",
            })
    return county_rows, group_rows, precinct_rows
