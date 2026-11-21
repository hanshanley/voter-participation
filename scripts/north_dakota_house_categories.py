"""Reconcile North Dakota's complete official House slate with the provider frame."""

import re

from scripts import results_native_north_dakota as nd
from scripts.participation_intake.contract import pin

IDENTITY = "ND-official-house-candidates"
URL = nd.FULL_RESULTS_URL
RACE = "npr:house:ND:1:regular:general:not_ranked"
MASS_HOLD = "aggregate_other_not_reconciled_to_retained_minor_candidate_mass"
DATE = "2026-11-03"
PARTIES = {"DEM": "D", "REP": "R", "IND": "O", "NON": "O"}
REVIEWED_CANDIDATE_IDS = frozenset(("37665", "37763", "37935", "37939", "9901"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse(body, metadata):
    from scripts.results_official_congress import CONTRACT

    full = nd._document(body, "full-results")
    meta = nd._authority(nd._document(metadata, "election"), "election")
    election = meta["response"]
    require(election["id"] == "348" and election["name"] == "2026 General Election"
            and election["date"] == DATE + "T00:00:00" and full["ElectionData"]["ElectionID"] == "348"
            and meta["isOfficial"] is full["ElectionData"]["IsOfficial"] is True,
            "North Dakota official election identity or status differs")
    contests = [row for row in full["ContestData"] if row["ContestName"] == "Representative in Congress"]
    require(len(contests) == 1, "Ambiguous North Dakota House contest")
    contest, = contests
    expected_counties = election["districts"]["counties"]
    units = nd._integer(contest["TotalPrecincts"], "House reporting-unit inventory")
    require(contest["ContestID"] == "22055" and contest["DistrictID"] == ""
            and contest["HasLocationResults"] is True and contest["WriteinChoices"] == []
            and contest["Recounts"] == [] and units > 0 and contest["PrecinctsReporting"] == units
            and len(expected_counties) == nd.EXPECTED_COUNTIES
            and set(contest["Locations"]) == set(expected_counties),
            "North Dakota House stage, reporting coverage or separate write-in inventory differs")

    def choices(row):
        candidates = {}
        for item in row["Choices"]:
            key, label, party = item["ChoiceID"], item["Name"], item["PartyID"]
            name = " ".join(label.split())
            write_in = key == "9901"
            require(re.fullmatch(r"[0-9]+", key) and key not in candidates and name and party in PARTIES
                    and write_in == (party == "NON") == (name.casefold() == "write-in"),
                    "Unreviewed North Dakota candidate or write-in row")
            candidates[key] = {"candidate_id": key, "name": name, "name_literal": label,
                               "literal_party": party, "party_group": PARTIES[party],
                               "role": "generic_write_in" if write_in else "named_candidate",
                               "votes": nd._choice_total(item)}
        require(sum(candidate["votes"] for candidate in candidates.values()) == row["TotalVotes"],
                "North Dakota candidate counts disagree with the contest total")
        return candidates

    statewide = choices(contest)
    require("9901" in statewide and all(sum(row["party_group"] == party for row in statewide.values()) == 1
                                      for party in "DR"), "Incomplete North Dakota statewide category roster")
    totals = dict.fromkeys(statewide, 0)
    county_queries = []
    reported_units = 0
    for key, row in sorted(contest["Locations"].items()):
        county_units = nd._integer(row["TotalPrecincts"], "county House reporting-unit inventory")
        require(row["LocationID"] == key and row["ContestID"] == contest["ContestID"] and
                row["PrecinctsReporting"] == county_units and not row["WriteinChoices"],
                "Incomplete North Dakota county House contest")
        candidates = choices(row)
        require(candidates.keys() == statewide.keys(), "North Dakota county candidate roster differs")
        for candidate_id, candidate in candidates.items():
            require(all(candidate[field] == statewide[candidate_id][field] for field in ("name", "literal_party", "role")),
                    "North Dakota candidate identity differs by county")
            totals[candidate_id] += candidate["votes"]
        reported_units += county_units
        county_queries.append({"county_id": key, "county": row["LocationName"], "reporting_units": county_units,
                               "contest_total": row["TotalVotes"], "candidates": list(candidates.values())})
    require(reported_units == units and all(totals[key] == row["votes"] for key, row in statewide.items()),
            "North Dakota county candidate totals do not reconcile to the statewide slate")
    return {
        "contract": CONTRACT, "election_date": DATE, "source_updated_at": meta["lastUpdated"],
        "metadata_source": {"url": nd.ELECTION_URL, **pin(metadata)}, "source_version": meta["versionID"],
        "participation_observation_qualified": False, "candidate_votes_are_not_ballots_or_turnout": True,
        "provider_other_equivalence_qualified": False, "conditional_model_eligible": False,
        "races": [{"state_code": "ND", "chamber": "house", "district": "ND-AL", "seat": "1",
                   "native_contest_id": contest["ContestID"], "native_office_label": contest["ContestName"],
                   "election_date": DATE, "election_kind": "regular", "stage": "general",
                   "native_status_literal": "IsOfficial=true", "source_update_label": meta["lastUpdated"],
                   "source_update_timezone": "UTC", "reported_units": units, "total_units": units,
                   "complete_reporting": True, "contest_total": contest["TotalVotes"],
                   "candidates": list(statewide.values())}],
        "complete_county_candidate_query": county_queries,
    }


def collect(collector):
    def checked(body):
        metadata, _ = collector.acquire(nd.ELECTION_URL)
        data = parse(body, metadata)
        prior = (collector.prior.get(IDENTITY) or {}).get("data") or {}
        clock = nd._clock(data["source_updated_at"])
        require(clock <= collector.observation_time() and (
            not prior or clock >= nd._clock(prior["source_updated_at"])), "North Dakota House source clock differs")
        if prior and clock == nd._clock(prior["source_updated_at"]):
            require(prior["races"] == data["races"]
                    and prior["complete_county_candidate_query"] == data["complete_county_candidate_query"],
                    "North Dakota House facts changed without a source clock revision")
        return data

    return collector.capture(IDENTITY, URL, checked, shared_acquisition=True)


def reconcile(congress, review, reviewed, provider):
    from scripts.automatic_estimates import _party_group
    from scripts.congressional_analytical_bridge import name_tokens, review_names

    entry = congress.get("official_candidate_evidence", {}).get(IDENTITY, {})
    require(entry.get("status") == "reported" and (entry.get("source") or {}).get("url") == URL,
            "North Dakota official category source is not freshly verified")
    data = entry["data"]
    official, = data["races"]
    require(all(official[key] == reviewed["identity"][key] for key in
                ("state_code", "chamber", "seat", "stage", "election_date", "election_kind"))
            and official["native_contest_id"] == "22055" and official["complete_reporting"] is True,
            "North Dakota official and reviewed model contest identities differ")
    named = [row for row in provider["candidates"] if row["role"] == "named_candidate"]
    other = [row for row in provider["candidates"] if row["role"] == "provider_aggregate_other"]
    require(len(named) == 2 and {row["party_group"] for row in named} == {"D", "R"}
            and len(other) == 1 and other[0]["party_group"] == "O" and len(provider["candidates"]) == 3
            and {row["candidate_id"] for row in official["candidates"]} == REVIEWED_CANDIDATE_IDS
            and len(official["candidates"]) == len(REVIEWED_CANDIDATE_IDS),
            "North Dakota provider category roster differs")
    unmatched = set(reviewed["unmatched_legacy_indices"])
    matched, omitted = set(), []
    for row in official["candidates"]:
        if row["party_group"] in "DR":
            matches = [item for item in named if item["party_group"] == row["party_group"]
                       and review_names(item["name"], row["name"])]
            require(len(matches) == 1 and matches[0]["candidate_id"] in reviewed["named_crosswalk"]
                    and matches[0]["votes"] == row["votes"] and matches[0]["candidate_id"] not in matched,
                    "North Dakota provider and official named controls differ")
            matched.add(matches[0]["candidate_id"])
        else:
            matches = [index for index in unmatched if
                       _party_group(review["legacy_candidates_preserved"][index]["party"]) == "O"
                       and (name_tokens(review["legacy_candidates_preserved"][index]["name"]) == ["write", "in"]
                            if row["role"] == "generic_write_in" else
                            review_names(review["legacy_candidates_preserved"][index]["name"], row["name"]))]
            require(len(matches) == 1, "North Dakota official minor/write-in and retained slate differ")
            unmatched.remove(matches[0])
            omitted.append({**row, "legacy_index": matches[0]})
    require(not unmatched and len(matched) == 2 and sum(row["votes"] for row in omitted) == other[0]["votes"]
            and sum(row["votes"] for row in provider["candidates"]) == official["contest_total"],
            "North Dakota provider Other does not equal the complete official minor/write-in total")
    return {"source_id": IDENTITY, "source": entry["source"], "metadata_source": data["metadata_source"],
            "source_updated_at": data["source_updated_at"], "official_omitted_candidates": omitted,
            "provider_other": other[0]["votes"], "individual_counts_allocated_from_Other": False,
            "synchronized_snapshot_claimed": False, "new_scientific_eligibility_granted": False}
