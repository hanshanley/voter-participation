"""Retain federal candidate tables from a reviewed statewide JSON product."""

import copy
from datetime import datetime, timezone
import json
import re
from uuid import UUID

from scripts.results_official_congress import CONTRACT, require


IDENTITY = "UT-official-house-candidates"
URL = (
    "https://electionresults.utah.gov/results/public/api/elections/Utah/"
    "General11032026/data"
)
FACT_CONTRACT = "participation.statewide_json_federal_candidate_facts.v1"
PROFILE = {
    "state_code": "UT", "name": "Utah", "districts": (1, 2, 3, 4),
    "jurisdiction_id": "a7510980-7b10-4aca-a2d8-ff92951aca1c",
    "election_id": "01000000-3eb9-2098-2ce9-08df22ebab67",
    "public_election_id": "General11032026",
    "office_pattern": r"U\.S\. House District ([1-4])",
}
PARTIES = {
    "Democratic": "D", "Republican": "R", "Libertarian": "O",
    "Unaffiliated": "O", "Independent American": "O", "Constitution": "O",
}
ELECTION_FIELDS = (
    "id", "jurisdictionId", "name", "electionDate", "asOf", "lastUpdated",
    "isPrimary", "isProduction", "isOfficialResults",
)
RACE_FIELDS = (
    "id", "parentId", "name", "voteFor", "contestType", "publishPublicElectionId",
    "rankedChoiceSummaryResults", "reportingStatus", "voteTotal",
)
CANDIDATE_FIELDS = (
    "id", "nativeId", "name", "isWriteIn", "isQualifiedWriteIn", "voteCount", "groupResults",
)


def english(values):
    require(isinstance(values, list), "Missing native JSON language declarations")
    texts = [row.get("text") for row in values
             if isinstance(row, dict) and row.get("languageId") == "en"]
    require(len(texts) == 1 and isinstance(texts[0], str) and bool(texts[0].strip()),
            "Missing or ambiguous native JSON English label")
    return texts[0]


def integer(value):
    require(type(value) is int and 0 <= value <= 2**53 - 1,
            "Missing, negative or unsafe native JSON candidate count")
    return value


def uuid(value):
    require(isinstance(value, str) and str(UUID(value)) == value,
            "Missing or changed native JSON identity")
    return value


def clock(value):
    require(isinstance(value, str) and re.fullmatch(
        r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]{1,7})?Z", value) is not None, "Missing native JSON UTC clock")
    base = value[:-1]
    fraction = ""
    if "." in base:
        prefix, fraction = base.split(".")
        base = prefix + "." + fraction[:6]
    result = datetime.fromisoformat(base + "+00:00")
    require(datetime(2026, 11, 3, tzinfo=timezone.utc) <= result
            < datetime(2027, 2, 1, tzinfo=timezone.utc), "Native JSON clock outside election")
    return result, int(fraction.ljust(7, "0")[-1])


def selected_facts(document):
    races = []
    for race in document["ballotItems"]:
        name = english(race["name"])
        if "House" not in name:
            continue
        if not name.startswith("U.S. House"):
            continue
        require(re.fullmatch(PROFILE["office_pattern"], name) is not None,
                "Unreviewed native JSON federal seat or election stage")
        selected = {key: copy.deepcopy(race[key]) for key in RACE_FIELDS}
        candidates = []
        for candidate in race["summaryResults"]["ballotOptions"]:
            row = {key: copy.deepcopy(candidate[key]) for key in CANDIDATE_FIELDS}
            party = candidate["party"]
            row["party"] = ({key: copy.deepcopy(party[key])
                             for key in ("id", "name", "abbreviation")}
                            if party is not None else None)
            candidates.append(row)
        selected["summaryResults"] = {"ballotOptions": candidates}
        races.append(selected)
    return {
        "contract": FACT_CONTRACT,
        "election": {key: copy.deepcopy(document["election"][key]) for key in ELECTION_FIELDS},
        "jurisdiction": {key: copy.deepcopy(document["jurisdiction"][key])
                         for key in ("id", "name", "shortName")},
        "ballotItems": races,
    }


def normalized(facts):
    require(isinstance(facts, dict) and facts.get("contract") == FACT_CONTRACT,
            "Unreviewed native JSON congressional facts")
    election, jurisdiction = facts["election"], facts["jurisdiction"]
    require(jurisdiction["id"] == election["jurisdictionId"] == PROFILE["jurisdiction_id"]
            and english(jurisdiction["name"]) == jurisdiction["shortName"] == PROFILE["name"]
            and election["id"] == PROFILE["election_id"]
            and english(election["name"]) == "2026 General Election"
            and election["electionDate"] == "2026-11-03"
            and election["isPrimary"] is False and election["isProduction"] is True
            and type(election["isOfficialResults"]) is bool,
            "Changed native JSON publisher or general-election identity")
    clock(election["asOf"])
    clock(election["lastUpdated"])
    races = []
    for race in facts["ballotItems"]:
        label = english(race["name"])
        match = re.fullmatch(PROFILE["office_pattern"], label)
        require(match is not None and race["parentId"] is None
                and race["contestType"] == "Candidate"
                and race["publishPublicElectionId"] == PROFILE["public_election_id"]
                and race["voteFor"] == [] and race["rankedChoiceSummaryResults"] is None,
                "Changed native JSON federal office or vote-for declaration")
        status = race["reportingStatus"]
        reported, total = integer(status["reportingUnits"]), integer(status["totalUnits"])
        require(total > 0 and reported <= total, "Invalid native JSON reporting fragments")
        clock(status["asOf"])
        candidates = []
        for candidate in race["summaryResults"]["ballotOptions"]:
            native_id, literal_name = candidate["nativeId"], english(candidate["name"])
            require(isinstance(native_id, str) and bool(native_id.strip())
                    and type(candidate["isWriteIn"]) is bool
                    and type(candidate["isQualifiedWriteIn"]) is bool
                    and candidate["groupResults"] is None,
                    "Changed native JSON candidate identity, write-in role or method scope")
            generic = literal_name in ("Write-In", "Write-in", "Write-ins")
            require(not candidate["isQualifiedWriteIn"] or candidate["isWriteIn"],
                    "Qualified write-in lacks native write-in flag")
            require(not generic or candidate["isWriteIn"] and not candidate["isQualifiedWriteIn"],
                    "Changed generic native JSON write-in role")
            require(not candidate["isWriteIn"] or generic or candidate["isQualifiedWriteIn"],
                    "Unreviewed named native JSON write-in role")
            party = candidate["party"]
            if party is None:
                party_id = party_name = abbreviation = None
            else:
                party_id, party_name = uuid(party["id"]), english(party["name"])
                abbreviation = party["abbreviation"]
                require(abbreviation is None or isinstance(abbreviation, str),
                        "Changed native JSON party abbreviation")
            candidates.append({
                "candidate_id": native_id, "native_candidate_uuid": uuid(candidate["id"]),
                "name": literal_name.strip(), "name_literal": literal_name,
                "literal_party": party_name, "party_name": party_name,
                "native_party_uuid": party_id, "native_party_abbreviation": abbreviation,
                "party_group": PARTIES.get(party_name, "U"),
                "role": "generic_write_in" if generic else "named_candidate",
                "is_write_in": candidate["isWriteIn"],
                "is_qualified_write_in": candidate["isQualifiedWriteIn"],
                "votes": integer(candidate["voteCount"]),
            })
        require(bool(candidates)
                and len({c["candidate_id"] for c in candidates}) == len(candidates)
                and len({c["native_candidate_uuid"] for c in candidates}) == len(candidates)
                and sum(c["votes"] for c in candidates) == integer(race["voteTotal"]),
                "Native JSON candidate inventory does not reconcile to contest total")
        seat = int(match[1])
        races.append({
            "state_code": PROFILE["state_code"], "district": f"UT-{seat:02d}", "seat": str(seat),
            "native_contest_id": uuid(race["id"]), "native_office_label": label,
            "election_date": "2026-11-03", "stage": "general", "election_kind": "regular",
            "native_status_literal": "official" if election["isOfficialResults"] else "unofficial",
            "source_update_label": status["asOf"], "source_update_timezone": "UTC",
            "reported_units": reported, "total_units": total, "partial_units": None,
            "reporting_unit_kind": "native_reporting_fragment_not_certified_precinct",
            "complete_reporting": reported == total, "contest_total": race["voteTotal"],
            "candidates": candidates,
        })
    require(len(races) == len(PROFILE["districts"])
            and {int(r["seat"]) for r in races} == set(PROFILE["districts"])
            and len({r["native_contest_id"] for r in races}) == len(races),
            "Incomplete or duplicate statewide JSON House inventory")
    return {
        "contract": CONTRACT, "election_date": "2026-11-03",
        "source_updated_at": election["asOf"], "native_facts": copy.deepcopy(facts),
        "races": sorted(races, key=lambda row: row["seat"]),
        "exhaustive_write_in_universe_qualified": False,
        "participation_observation_qualified": False, "candidate_votes_are_not_ballots_or_turnout": True,
        "provider_other_equivalence_qualified": False, "conditional_model_eligible": False,
        "holds": [
            "Named write-ins do not resolve unmatched generic provider write-ins.",
            "Reporting fragments are not certification or proof of an exhaustive ballot universe.",
            "Candidate counts supply neither participation numerators nor model equivalence.",
        ],
    }


def parse(body):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate native JSON property")
            result[key] = value
        return result
    return normalized(selected_facts(json.loads(body, object_pairs_hook=unique)))


def clocks(data):
    facts = data["native_facts"]
    return {
        "election_as_of": facts["election"]["asOf"],
        "election_last_updated": facts["election"]["lastUpdated"],
        **{r["district"]: r["source_update_label"] for r in data["races"]},
    }


def collect(collector):
    def guarded(body):
        data = parse(body)
        times = clocks(data)
        require(all(clock(value) <= (collector.observation_time(), 0) for value in times.values()),
                "Official JSON congressional clock is in the future")
        previous = (collector.prior.get(IDENTITY) or {}).get("data")
        if previous is not None:
            require(normalized(previous.get("native_facts")) == previous,
                    "Prior official JSON congressional evidence changed")
            old_times = clocks(previous)
            require(times.keys() == old_times.keys()
                    and all(clock(value) >= clock(old_times[key]) for key, value in times.items()),
                    "Official JSON congressional clock regressed")
            old_races = {r["district"]: r for r in previous["races"]}
            for race in data["races"]:
                old = old_races[race["district"]]
                require(old["native_contest_id"] == race["native_contest_id"]
                        and not (old["native_status_literal"] == "official"
                                 and race["native_status_literal"] != "official"),
                        "Official JSON contest identity or finality regressed")
                old_candidates = {c["candidate_id"]: c for c in old["candidates"]}
                new_candidates = {c["candidate_id"]: c for c in race["candidates"]}
                require(set(old_candidates) <= set(new_candidates)
                        and all({k: v for k, v in candidate.items() if k != "votes"} ==
                                {k: v for k, v in new_candidates[key].items() if k != "votes"}
                                for key, candidate in old_candidates.items()),
                        "Official JSON candidate inventory lost or changed an identity")
        return data
    return collector.capture(IDENTITY, URL, guarded)
