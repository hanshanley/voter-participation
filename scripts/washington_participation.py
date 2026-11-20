"""Washington's published general-election aggregate workbook, not a voter file."""
import io
from collections import Counter, defaultdict
from datetime import date, timedelta, timezone
from math import isfinite
from zipfile import ZipFile

FEED = "WA-general-election-age-sex-workbook"
URL = "https://www.sos.wa.gov/sites/default/files/2022-05/VoterParticipation.xlsx"
CSV = "participation-wa-general-election-age-sex.csv"
FIRST = 2005
STATE = "zWashington State"
COUNTIES = (
    "Adams|Asotin|Benton|Chelan|Clallam|Clark|Columbia|Cowlitz|Douglas|Ferry|Franklin|"
    "Garfield|Grant|Grays Harbor|Island|Jefferson|King|Kitsap|Kittitas|Klickitat|Lewis|Lincoln|"
    "Mason|Okanogan|Pacific|Pend Oreille|Pierce|San Juan|Skagit|Skamania|Snohomish|Spokane|"
    "Stevens|Thurston|Wahkiakum|Walla Walla|Whatcom|Whitman|Yakima"
).split("|")
AGES = ("0TOTAL", "18-24", "25-34", "35-44", "45-54", "55-64", "65-")
HEADER = (
    "County", "Year", "Election Type", "Voters Pamphlet", "Target Area (Square, Oval Arrow)", "Vote-By-Mail",
    "Age", "Female Population", "Male Population", "Total Population", "Female Voters", "Male Voters",
    "Unknown Voters", "Total Voters", "Female Ballots", "Male Ballots", "Unknown Ballots", "Total Ballots",
    "Female Registered Population", "Male Registered Population", "Total Registered Population",
    "Female Pop Turnout", "Male Pop Turnout", "Total Pop Turnout", "Female Voter Turnout",
    "Male Voter Turnout", "Total Voter Turnout",
)


def election_date(year):
    nov = date(year, 11, 1)
    return nov + timedelta(days=(7 - nov.weekday()) % 7 + 1)


def numeric(value):
    return type(value) in (int, float) and isfinite(value) and value >= 0


def query(rows):
    editions = defaultdict(list)
    for row in rows:
        if (len(row) != len(HEADER) or row[2] != "General" or type(row[1]) is not int
                or not FIRST <= row[1] <= 2100 or row[0] not in (*COUNTIES, STATE) or row[6] not in AGES):
            raise ValueError("Unexpected Washington general-election workbook roster or columns")
        editions[row[1]].append(row)
    expected = Counter((c, age) for c in (*COUNTIES, STATE) for age in AGES)
    if not editions or sorted(editions) != list(range(FIRST, max(editions) + 1)):
        raise ValueError("Washington workbook edition missing")
    accepted, pending, exceptions = [], [], {}
    for year, block in sorted(editions.items()):
        roster = Counter((row[0], row[6]) for row in block)
        adams = roster != expected and year == 2014
        allowed = expected.copy()
        if adams:
            del allowed["Adams", "45-54"]
            allowed["Adams", "55-64"] = 2
        if roster != allowed:
            raise ValueError(f"Incomplete or ambiguous Washington {year} county-age roster")
        if all(all(v is None for v in row[7:18]) for row in block):
            if year != max(editions):
                raise ValueError("An interior Washington edition was blanked")
            pending.append(year)
            continue
        for row in block:
            if (not all(numeric(row[i]) for i in range(7, 10))
                    or not all(type(row[i]) is int and row[i] >= 0 for i in (10, 11, 13, 14, 15, 17))
                    or not all(row[i] is None or type(row[i]) is int and row[i] >= 0 for i in (12, 16))
                    or any(row[i] > row[i - 4] for i in (14, 15, 17))
                    or row[13] != row[10] + row[11] + (row[12] or 0)
                    or row[17] != row[14] + row[15] + (row[16] or 0)):
                raise ValueError(f"Incomplete Washington workbook counts in {year}")
        grouped = defaultdict(list)
        for row in block:
            grouped[row[0]].append(row)
        totals = {name: next(r for r in group if r[6] == "0TOTAL") for name, group in grouped.items()}
        deltas = []
        for i in range(10, 18):
            for name, group in grouped.items():
                if sum((r[i] or 0) for r in group if r[6] != "0TOTAL") != (totals[name][i] or 0):
                    raise ValueError(f"Washington age categories do not reconcile in {name}, {year}")
            deltas.append((totals[STATE][i] or 0) - sum(totals[c][i] or 0 for c in COUNTIES))
        known = {
            2005: [0, 0, 0, 0, 7, 5, 0, 12],
            2014: [0, 0, 0, 0, 0, 9, -8, 1],
            2024: [0, 0, 0, 0, 12, 11, -23, 0],
        }
        if any(deltas) and deltas != known.get(year):
            raise ValueError(f"Unreviewed Washington state/county count discrepancy for {year}")
        if adams or any(deltas):
            exceptions[str(year)] = {"state_minus_counties": deltas, "adams_age_labels_held": adams}
        accepted.append(year)
    if not accepted or accepted[-1] < 2025:
        raise ValueError("Washington workbook lacks previously reviewed historical scope")
    return {"complete_native_query": rows, "published_years": accepted, "placeholder_years": pending,
            "exceptions": exceptions, "latest_general_year": accepted[-1],
            "participation_observation_qualified": False}


def parse(body):
    from openpyxl import load_workbook

    with ZipFile(io.BytesIO(body)) as archive:
        if len(body) > 10_000_000 or sum(p.file_size for p in archive.infolist()) > 75_000_000:
            raise ValueError("Washington workbook exceeds reviewed size bounds")
    book = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        notes = " ".join(str(r[0]) for r in book["README"].values if r and r[0])
        if not all(s in notes for s in ("postcensal estimates",
                                       "Registered voter data is estimated from the election period",
                                       "Population data is estimated from April 1st")):
            raise ValueError("Washington workbook denominator definitions changed")
        table = iter(book["Table"].values)
        if next(table, None) != HEADER:
            raise ValueError("Washington workbook column definitions changed")
        rows = [list(row) + [None] * (len(HEADER) - len(row)) for row in table if len(row) >= 3
                and row[2] == "General" and
                (type(row[1]) is not int or row[1] >= FIRST)]
        return query(rows)
    finally:
        book.close()


def collect(collector, *, reuse_checked_week=False):
    old = collector.prior.get(FEED) or {}
    day = collector.now.astimezone(timezone.utc).date()
    week = (day - timedelta(days=day.weekday())).isoformat()
    if (reuse_checked_week and not collector.offline and old.get("archive_check_week_utc") == week
            and old.get("status") == "reported" and old.get("data") is not None):
        return old

    def checked(body):
        data = parse(body)
        previous = (old.get("data") or {}).get("published_years", ())
        if (not set(previous) <= set(data["published_years"])
                or election_date(data["latest_general_year"]) > day):
            raise ValueError("Washington workbook lost a published edition or reports a future election")
        return data

    entry = collector.capture(FEED, URL, checked, equivalent=lambda before, after: before == after)
    if not collector.offline:
        entry["archive_check_week_utc"] = week
    return entry


def exports(entries):
    entry = entries.get(FEED, {})
    if entry.get("status") not in ("reported", "retained_after_failure"):
        return []
    data = entry["data"]
    if entry["source"]["url"] != URL or data != query(data["complete_native_query"]):
        raise ValueError("Washington participation export differs from the retained native query")
    occurrences = Counter()
    output = []
    for row in data["complete_native_query"]:
        county, year, _, _, _, _, age = row[:7]
        occurrences[county, year, age] += 1
        notes = data["exceptions"].get(str(year), {})
        held = notes.get("adams_age_labels_held") and county == "Adams" and age != "0TOTAL"
        status = ("workbook_placeholder" if year in data["placeholder_years"] else
                  "held_ambiguous_age_label" if held else "reported_workbook_aggregate")
        # A county sum and a published state total are different observations.
        delta = (notes["state_minus_counties"][7] if notes and county == STATE and age == "0TOTAL"
                 else None)
        ratios = {}
        for sex, count, registered, population in (
            ("female", 14, 10, 7), ("male", 15, 11, 8), ("total", 17, 13, 9),
        ):
            for name, i in (("registration_estimate", registered), ("april_vap_estimate", population)):
                ratios[f"{sex}_ballots_per_{name}"] = (
                    row[count] / row[i] if status == "reported_workbook_aggregate"
                    and row[i] and row[count] <= row[i] else None
                )
        output.append({
            "state_code": "WA", "geography": "Washington" if county == STATE else county,
            "geography_level": "state" if county == STATE else "county", "election_date": election_date(year),
            "election_type": "presidential" if year % 4 == 0 else "midterm" if year % 2 == 0 else "odd_year",
            "age_group": age, "source_occurrence": occurrences[county, year, age],
            "observation_status": status, "collection_status": entry["status"],
            "last_checked_week_utc": entry.get("archive_check_week_utc"),
            "state_ballots_minus_sum_of_counties": delta,
            **ratios,
            **dict(zip((
                "female_april_vap_estimate", "male_april_vap_estimate", "total_april_vap_estimate",
                "female_registration_estimate", "male_registration_estimate", "unknown_sex_registration_estimate",
                "total_registration_estimate", "female_ballots", "male_ballots", "unknown_sex_ballots", "total_ballots",
            ), row[7:18])),
            "source_first_observed_at": entry.get("first_observed_at"), "source_url": URL,
            "source_sha256": entry["source"]["sha256"],
        })
    return output
