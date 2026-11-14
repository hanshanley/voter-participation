"""Source-identity-checked House returns, independent of county map eligibility."""

import re

from scripts.nationwide import STATES


HOUSE_STATES = set(STATES) - {"DC"}
API = "https://civicapi.org/api/v2/race/"
NATIONAL_URL = API + "87524"


def election_scope(data, state):
    if (data.get("test_data") is not False or data.get("country") != "US"
            or data.get("province") != state
            or str(data.get("election_date", ""))[:10] != "2026-11-03"
            or data.get("election_type") != "House of Representatives"
            or data.get("election_scope") != "General"):
        raise ValueError("Wrong election, state, office, stage or test-data flag")


def districts(data):
    election_scope(data, "US")
    regions = data.get("region_results")
    if not isinstance(regions, dict):
        raise ValueError("Missing declared House district inventory")
    output, identities = {}, set()
    for key, row in regions.items():
        match = re.fullmatch(r"([a-z]{2})-(al|0[1-9]|[1-4][0-9]|5[0-3])", key)
        source_id = row.get("election_id")
        if (not match or match[1].upper() not in HOUSE_STATES
                or row.get("type") != "Congressional District"
                or type(source_id) is not int or source_id <= 0 or source_id in identities):
            raise ValueError("Duplicate or unknown declared district/source identity")
        identities.add(source_id)
        output[key.upper()] = {
            "state_code": match[1].upper(), "district": key.upper(),
            "source_id": source_id, "url": API + str(source_id),
        }
    if len(output) != 435 or {r["state_code"] for r in output.values()} != HOUSE_STATES:
        raise ValueError("The declaration must cover all 435 districts and 50 states")
    return output


def candidate_results(data, declared):
    election_scope(data, declared["state_code"])
    if data.get("district") != declared["district"]:
        raise ValueError("Native district differs from its declared identity")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Missing candidate counts")
    seen, rows = set(), []
    for row in candidates:
        name, party, votes = (row.get(key) for key in ("name", "party", "votes"))
        if (not isinstance(name, str) or not name.strip()
                or not isinstance(party, str) or not party.strip()
                or type(votes) is not int or votes < 0 or (name, party) in seen):
            raise ValueError("Invalid/duplicate literal candidate, party or integer count")
        seen.add((name, party))
        rows.append({"name": name, "party": party, "votes": votes})
    return {
        "state_code": declared["state_code"], "district": declared["district"],
        "candidates": rows, "source_update_label": data.get("last_updated"),
        "native_reporting": {key: data[key] for key in (
            "percent_reporting", "precincts_reporting", "precincts_total",
            "is_official", "is_certified", "round") if key in data},
        "certification_qualified": False,
        "county_reconciliation_or_map_join_claimed": False,
        "candidate_votes_are_ballots": False,
    }


def state_totals(entries, declared):
    result = []
    for state, name in STATES.items():
        expected = sorted(key for key, row in declared.items() if row["state_code"] == state)
        available = [entries[key] for key in expected if entries.get(key, {}).get("data") is not None]
        complete = state != "DC" and bool(expected) and len(available) == len(expected)
        totals = {}
        if complete:
            for entry in available:
                for row in entry["data"]["candidates"]:
                    totals[row["party"]] = totals.get(row["party"], 0) + row["votes"]
        result.append({
            "state_code": state, "state": name,
            "status": "not_applicable_no_voting_house_seat" if state == "DC" else (
                "all_district_snapshots_available" if complete else "incomplete_district_inventory"),
            "expected_districts": len(expected), "available_districts": len(available),
            "retained_districts": sum(row["status"] != "reported" for row in available),
            "party_votes": totals if complete else None,
            "certification_qualified": False, "ballots": None,
            "different_district_source_clocks_preserved": True,
        })
    return result
