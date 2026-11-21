"""Export the complete reviewed New Mexico turnout query without collector dependencies."""

import re


URL = "https://electionresults.sos.nm.gov/VoterTurnoutDetails.aspx?map=PREC"
CSV = "participation-nm-2026-native-turnout.csv"
IDENTITY = "NM-registered-e236d453f2e53e42"


def rows(entries):
    entry = entries.get(IDENTITY, {})
    data = entry.get("data")
    if data is None:
        return []
    source, status = entry["source"], entry["status"]
    if (source["url"] != URL or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            or status not in ("reported", "retained_after_failure")
            or data.get("native_measure_not_relabelled_as_ballots") is not True):
        raise ValueError("Unreviewed New Mexico turnout export source")
    facts = data["complete_native_query"]
    levels = ("state", "county", "reporting_unit")
    state, counties, units = ([row for row in facts if row["geography_level"] == level] for level in levels)
    if (len(state) != 1 or len(counties) != 33 or len(units) != 2204
            or len(facts) != 2238 or state[0]["reported_units"] != len(units)
            or state[0]["total_units"] != len(units)):
        raise ValueError("Incomplete New Mexico native turnout export inventory")
    parent = state[0]
    fields = ("count", "registered")
    if (any(row["source_clock"] != parent["source_clock"] or
            any(type(row[k]) is not int or row[k] < 0 for k in fields) for row in facts)
            or any(sum(row[k] for row in counties) != parent[k] for k in fields)):
        raise ValueError("New Mexico statewide turnout counts or clocks differ")
    county_ids = {row["county_id"]: row for row in counties}
    if (len(county_ids) != len(counties) or len({row["county"] for row in counties}) != len(counties)
            or set(county_ids) != {row["county_id"] for row in units}
            or len({(row["county_id"], row["unit"]) for row in units}) != len(units)):
        raise ValueError("Duplicate or incompatible New Mexico turnout identities")
    for county in counties:
        children = [row for row in units if row["county_id"] == county["county_id"]]
        if (len(children) != county["reported_units"] or len(children) != county["total_units"]
                or any(not row["unit"] or row["county"] != county["county"] for row in children)
                or any(sum(row[k] for row in children) != county[k] for k in fields)):
            raise ValueError("New Mexico reporting-unit totals differ from the county")
    provenance = {
        "state_code": "NM", "election_date": "2026-11-03",
        "source_status": status, "source_url": source["url"], "source_sha256": source["sha256"],
        "native_numerator_label": "Ballots Cast (source turnout sign-in measure)",
        "native_denominator_label": "Eligible Voters (source label)",
        "certification_claimed": False, "geographic_match_claimed": False,
    }
    return [{**provenance, **row} for row in sorted(facts, key=lambda row: (
        levels.index(row["geography_level"]), row.get("county", ""), row.get("unit", "")))]
