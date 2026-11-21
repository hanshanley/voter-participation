"""Reconcile Maryland's all-mode unofficial card-count report."""

from datetime import datetime
from fractions import Fraction

from scripts.maryland_precinct_history import COUNTIES


FEED = "MD-2026-unofficial-cards-by-county"
URL = ("https://elections.maryland.gov/press_room/2026_stats/GG26/"
       "2026-general_election_night_unofficial_turnout.pdf")
CSV = "participation-md-2026-unofficial-cards.csv"
TITLE = "Unofficial Early Voting, Election Day, MIB1, MIB2, and Provisional Turnout"
MAX_BYTES = 2_000_000


def parse(body):
    from scripts.extract_maryland_election_frames import read_cards

    if not 0 < len(body) <= MAX_BYTES:
        raise ValueError("Unexpected Maryland card-report size")
    report = read_cards(body, title=TITLE)
    clock = datetime.strptime(report["run_date"] + " " + report["run_time"], "%m/%d/%Y %I:%M %p")
    if clock.date().isoformat() < "2026-11-03":
        raise ValueError("Maryland report predates election")
    query(report)
    return {"date": clock.isoformat(), "report": report, "participation_observation_qualified": False}


def query(report):
    roster = {name if name in {"Baltimore City", "Baltimore County"} else name + " County"
              for name in COUNTIES}
    source = report["rows"]
    if (len(source) != 25 or {r["native_county_label"] for r in source[:-1]} != roster
            or source[-1]["native_county_label"] != "Total"):
        raise ValueError("Incomplete Maryland county roster")
    rows = []
    for row in source:
        cards, eligible = [int(row[k].replace(",", "")) for k in ("native_cards_cast", "native_eligible_voters")]
        printed = Fraction(row["native_percentage"].removesuffix("%"))
        if not 0 <= cards <= eligible or not eligible or abs(100 * Fraction(cards, eligible) - printed) > Fraction(1, 200):
            raise ValueError("Maryland reported cards fraction does not reconcile")
        observed, expected = (row["reported_source_units"], row["expected_source_units"])
        state = row["native_county_label"] == "Total"
        if (state and (observed is not None or expected is not None)
                or not state and (type(expected) is not int or expected <= 0 or observed != expected)):
            raise ValueError("Maryland reporting-unit coverage is incomplete")
        rows.append({"geography_level": "state" if state else "county",
                     "county": row["native_county_label"], "reported_cards_cast": cards,
                     "reported_eligible_voters": eligible, "printed_cards_per_eligible_pct": float(printed),
                     "reported_source_units": observed, "expected_source_units": expected})
    for key in ("reported_cards_cast", "reported_eligible_voters"):
        if sum(row[key] for row in rows[:-1]) != rows[-1][key]:
            raise ValueError("Maryland county totals differ from the printed statewide report")
    return rows


def collect(collector):
    return collector.capture(FEED, URL, parse, equivalent=lambda old, new: old == new)


def exports(entries):
    entry = entries.get(FEED, {})
    if (data := entry.get("data")) is None:
        return []
    if entry["source"]["url"] != URL or entry["status"] not in ("reported", "retained_after_failure"):
        raise ValueError("Incompatible Maryland cards evidence")
    return [{"state_code": "MD", "election_date": "2026-11-03", **row,
             "reporting_status": "unofficial", "source_status": entry["status"],
             "native_run_time_timezone_not_supplied": data["date"], "source_url": URL,
             "source_sha256": entry["source"]["sha256"], "certified_unique_voter_rate": False}
            for row in query(data["report"])]
