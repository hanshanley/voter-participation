"""Reconcile official New Mexico historical turnout without repairing native cells."""

from datetime import datetime
from functools import partial
import html
import re

ELECTIONS = {
    2016: ("84", "November 8, 2016", 1492),
    2018: ("2698", "November 6, 2018", 1492),
    2020: ("2782", "November 3, 2020", 1925),
    2022: ("2838", "November 8, 2022", 2163),
    2024: ("2882", "November 5, 2024", 2169),
}
FEEDS = {f"NM-{year}-general-native-turnout-archive": year for year in ELECTIONS}
URLS = {feed: f"https://electionresults.sos.nm.gov/VoterTurnoutDetails.aspx?eid={ELECTIONS[year][0]}&map=PREC"
        for feed, year in FEEDS.items()}
CSV = "participation-nm-historical-native-turnout.csv"
MAX_BYTES = 2_500_000
INTEGER = r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)"
SECTION = re.compile(r'<div class="col turnout-results-box-a">\s*<h1>(.*?)</h1>(.*?)(?='
                     r'<div class="col turnout-results-box-a">|</form>)', re.S)
UNIT = re.compile(r'<div class="county-precinct">(.*?)</div>\s*'
                  r'<div class="county-cast">\s*<span>(' + INTEGER + r')</span>\s*</div>\s*'
                  r'<div class="county-counted">\s*<span>(-?' + INTEGER + r')</span>', re.S)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def label(value):
    return html.unescape(re.sub(r"<[^>]*>", "", value)).strip()


def number(value):
    return int(value.replace(",", ""))


def reconcile(state, counties, expected):
    require(len(counties) == 33 and len({c["id"] for c in counties}) == 33
            and len({c["name"] for c in counties}) == 33, "Incomplete NM county inventory")
    units = [u for c in counties for u in c["units"]]
    require(len(units) == expected
            and all(c["units"] and len({u[0] for u in c["units"]}) == len(c["units"])
                    for c in counties), "Incomplete or duplicate NM reporting-unit inventory")
    require(all(u[0] and type(u[1]) is int and u[1] >= 0 and type(u[2]) is int for u in units)
            and sum(u[1] for u in units) == state[0] and sum(u[2] for u in units) == state[1],
            "NM reporting units disagree with the separate statewide controls")


def parse(body, feed):
    year = FEEDS[feed]
    eid, day, expected = ELECTIONS[year]
    require(0 < len(body) <= MAX_BYTES, "Invalid NM source size")
    text = body.decode("utf-8-sig")
    header = re.search(r'href="Default.aspx\?eid=' + eid + r'"><h1>Official Results</h1><h2>'
                       + str(year) + r' General<br\s*/?>' + re.escape(day) + r'</h2>', text, re.I)
    clock = re.search(r"Results last updated:</span><span>([^<]+)</span>", text)
    parent = re.search(r'header-ballot-number">(' + INTEGER + r')</span><br /><span class="header-voter-text">'
                       r'Eligible Voters</span><span class="header-voter-number">(' + INTEGER + r')</span>', text)
    coverage = re.search(r'header-partial-number">(\d+)</span>.*?header-total-number">(\d+)</span>'
                         r'.*?header-totalprecincts-text">(\d+)</span>', text, re.S)
    require(header and clock and parent and coverage
            and tuple(map(int, coverage.groups())) == (0, expected, expected), "Incorrect NM election or report coverage")
    literal = label(clock[1])
    stamp = datetime.strptime(literal, "%m/%d/%Y %I:%M %p MT")
    election = datetime.strptime(day, "%B %d, %Y")
    require(stamp >= election, "NM source clock predates election")
    counties = []
    for name, section in SECTION.findall(text):
        ids = set(re.findall(r'countyid="(\d+)"', section))
        units = [[label(unit), number(count), number(eligible)] for unit, count, eligible in UNIT.findall(section)]
        require(len(ids) == 1 and len(units) == section.count('<div class="county-precinct">'),
                "Unparsed NM reporting-unit row")
        counties.append({"id": next(iter(ids)), "name": label(name), "units": units})
    counts = [number(value) for value in parent.groups()]
    reconcile(counts, counties, expected)
    return {"date": stamp.isoformat(), "election_date": election.date().isoformat(),
            "source_clock": literal, "state": counts, "counties": counties,
            "participation_observation_qualified": False}


def collect(collector, feed, *, reuse_checked_week=False):
    from scripts.southeast_turnout import collect_report

    def checked(body, identity):
        data = parse(body, identity)
        if datetime.fromisoformat(data["date"]).date() > collector.observation_time().date():
            raise ValueError("NM historical edition is future-dated")
        # Older publishers require an explicit no-op for a scoped source they do not recognize.
        return {**data, "updates": []}

    entry = collect_report(collector, feed, URLS[feed], checked, reuse_checked_week=reuse_checked_week)
    if (data := entry.get("data")) is not None:
        require(data.get("updates", []) == [], "NM historical archive cannot project observations")
        entry = {**entry, "data": {**data, "updates": []}}
    return entry


def valid_rate(count, eligible):
    return 0 <= count <= eligible and eligible > 0


def exports(entries):
    for feed, year in FEEDS.items():
        entry = entries.get(feed) or {}
        if (data := entry.get("data")) is None:
            continue
        source = entry["source"]
        require(entry["status"] in {"reported", "retained_after_failure"}
                and source["url"] == URLS[feed] and re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
                and 0 < source["bytes"] <= MAX_BYTES
                and data["election_date"] == datetime.strptime(ELECTIONS[year][1], "%B %d, %Y").date().isoformat(),
                "NM historical provenance differs")
        reconcile(data["state"], data["counties"], ELECTIONS[year][2])
        def row(level, count, eligible, hold="", county="", county_id="", unit=""):
            hold = hold or ("" if valid_rate(count, eligible) else
                            "negative_source_denominator" if eligible < 0 else
                            "zero_source_denominator" if eligible == 0 else "count_exceeds_source_denominator")
            return {"state_code": "NM", "election_date": data["election_date"], "geography_level": level,
                    "county_id": county_id, "county": county, "unit": unit, "source_reported_count": count,
                    "source_eligible_voters": eligible, "source_eligible_rate_pct": None if hold else 100 * count / eligible,
                    "rate_hold": hold, "native_numerator_label": "Ballots Cast",
                    "native_denominator_label": "Eligible Voters", "source_results_label": "Official Results",
                    "measure_scope": "source_reported_turnout_not_candidate_votes",
                    "source_clock": data["source_clock"], "source_status": entry["status"], "source_url": source["url"],
                    "source_sha256": source["sha256"], "geographic_match_claimed": False}

        yield row("state", *data["state"])
        for county in data["counties"]:
            units = county["units"]
            issue = ("component_denominator_negative_or_below_count"
                     if any(eligible < 0 or count > eligible for _, count, eligible in units) else "")
            yield row("county", sum(u[1] for u in units), sum(u[2] for u in units), issue,
                      county["name"], county["id"])
            for unit, count, eligible in units:
                yield row("reporting_unit", count, eligible, county=county["name"], county_id=county["id"], unit=unit)


def original_reports(entries):
    for feed, url in URLS.items():
        entry = entries.get(feed) or {}
        if (data := entry.get("data")) is not None:
            yield (feed, entry["source"], ".html", MAX_BYTES, entry["source"]["url"] == url,
                   partial(parse, feed=feed), {k: v for k, v in data.items() if k != "updates"})
