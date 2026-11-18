"""Derive federal candidate evidence from the existing complete locality intake."""

import copy
import re
from collections import Counter

from scripts import results_native_virginia as native
from scripts.participation_intake.contract import encoded, pin


IDENTITY = "VA-official-house-candidates"
PARENT_ID = "VA-registered-1657a8451bae522c"
CONTRACT = "participation.official_congressional_candidate_evidence.v1"
FACT_CONTRACT = "participation.native_locality_congress_facts.v1"
OFFICE = re.compile(
    r"Member, House of Representatives \(([1-9][0-9]*)(?:st|nd|rd|th) District\)")
MODES = {"Early Voting", "Election Day", "Mailed Absentee", "Provisional", "Post-Election"}
PARTIES = {"D": "D", "R": "R", "I": "O", "L": "O", "G": "O"}
ELECTION_FIELDS = (
    "id", "name", "electionDate", "asOf", "lastUpdated", "isProduction",
    "isOfficialResults", "isPrimary",
)
RACE_FIELDS = (
    "id", "parentId", "name", "voteFor", "contestType", "publishPublicElectionId",
    "rankedChoiceSummaryResults", "reportingStatus", "voteTotal", "summaryResults",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    require(type(value) is int and 0 <= value <= 2**53 - 1,
            "Invalid or missing native congressional count")
    return value


def selected_facts(query):
    root = query["root_document"]
    declarations = native._declared_localities(root)

    def document(value):
        races = []
        for race in value["ballotItems"]:
            label = native._english(race["name"])
            if "House of Representatives" in label:
                require(OFFICE.fullmatch(label) is not None, "Unreviewed House office or stage")
                selected = {key: copy.deepcopy(race[key]) for key in RACE_FIELDS}
                selected["summaryResults"] = {"ballotOptions": [
                    {key: copy.deepcopy(candidate[key]) for key in (
                        "id", "nativeId", "name", "party", "isWriteIn",
                        "isQualifiedWriteIn", "voteCount", "groupResults")}
                    for candidate in race["summaryResults"]["ballotOptions"]
                ]}
                for candidate in selected["summaryResults"]["ballotOptions"]:
                    if candidate["party"] is not None:
                        candidate["party"] = {
                            key: candidate["party"][key] for key in ("abbreviation", "name")}
                races.append(selected)
        jurisdiction = value["jurisdiction"]
        return {
            "election": {key: copy.deepcopy(value["election"].get(key)) for key in ELECTION_FIELDS},
            "jurisdiction": {key: copy.deepcopy(jurisdiction[key])
                             for key in ("id", "shortName", "name")},
            "ballotItems": races,
        }

    manifest = copy.deepcopy(query["numerical_input_manifest"])
    require(pin(encoded(manifest)) == query["numerical_input_manifest_pin"],
            "Native congressional input manifest pin differs")
    selected_root = document(root)
    selected_root["localityElections"] = [
        {key: copy.deepcopy(row[key]) for key in ("jurisdictionId", *ELECTION_FIELDS)}
        for row in root["localityElections"]]
    return {
        "contract": FACT_CONTRACT, "root": selected_root,
        "declarations": declarations,
        "localities": {key: document(value) for key, value in query["locality_documents"].items()},
        "numerical_input_manifest": manifest,
        "numerical_input_manifest_pin": copy.deepcopy(query["numerical_input_manifest_pin"]),
    }


def candidate_rows(race):
    result = {}
    uuids = set()
    for candidate in race["summaryResults"]["ballotOptions"]:
        identity = candidate["nativeId"]
        uuid = native._uuid(candidate["id"])
        require(isinstance(identity, str) and identity and identity not in result and uuid not in uuids,
                "Duplicate or missing native congressional candidate identity")
        uuids.add(uuid)
        name = native._english(candidate["name"])
        write_in, qualified = candidate["isWriteIn"], candidate["isQualifiedWriteIn"]
        require(type(write_in) is bool and type(qualified) is bool,
                "Unspecified native write-in role")
        generic = name == "Write-In"
        require(not generic or write_in and not qualified, "Changed generic write-in role")
        require(not write_in or generic or qualified, "Unreviewed named write-in role")
        party = candidate["party"]
        literal = party["abbreviation"] if party is not None else None
        party_name = native._english(party["name"]) if party and party["name"] is not None else None
        require((literal in PARTIES and not generic) or
                (generic and literal is None and party_name is None),
                "Unreviewed native candidate party or write-in classification")
        modes, mode_ids = {}, set()
        for mode in candidate["groupResults"]:
            label = native._english(mode["groupName"])
            mode_id = native._uuid(mode["groupId"])
            require(label in MODES and label not in modes and mode_id not in mode_ids,
                    "Duplicate or unreviewed congressional voting method")
            modes[label] = integer(mode["voteCount"])
            mode_ids.add(mode_id)
        votes = integer(candidate["voteCount"])
        require(set(modes) == MODES and sum(modes.values()) == votes,
                "Congressional candidate methods do not reconcile")
        result[identity] = {
            "candidate_id": identity, "native_candidate_uuid": uuid,
            "name": name, "name_literal": name, "literal_party": literal,
            "party_name": party_name, "party_group": PARTIES.get(literal, "O"),
            "role": "generic_write_in" if generic else "named_candidate",
            "is_write_in": write_in, "is_qualified_write_in": qualified,
            "votes": votes, "modes": modes,
        }
    require(bool(result) and sum(row["votes"] for row in result.values()) == integer(race["voteTotal"]),
            "Native complete candidate inventory does not reconcile to contest total")
    return result


def normalized(facts):
    require(facts["contract"] == FACT_CONTRACT, "Unreviewed native congressional facts")
    root = facts["root"]
    election = native._election(root["election"], native.ELECTION_ID)
    declarations = native._declared_localities(
        {"jurisdiction": {"childLocalities": [
            {"mapFeatureId": row["code"], "shortName": row["short_name"], "id": row["id"],
             "name": [{"languageId": "en", "text": row["name"]}]}
            for row in facts["declarations"]
        ]}})
    localities = facts["localities"]
    require(set(localities) == {row["code"] for row in declarations},
            "Incomplete native congressional locality inventory")
    manifest = facts["numerical_input_manifest"]
    require(pin(encoded(manifest)) == facts["numerical_input_manifest_pin"]
            and manifest["root"]["url"] == native.ROOT_URL,
            "Changed native congressional input lineage")
    lineage = {row["code"]: row for row in manifest["localities"]}
    require(len(manifest["localities"]) == len(lineage) == len(declarations)
            and set(lineage) == set(localities), "Incomplete native congressional source receipts")
    for receipt in (manifest["root"], *lineage.values()):
        require(type(receipt.get("bytes")) is int and receipt["bytes"] > 0
                and isinstance(receipt.get("sha256"), str)
                and re.fullmatch(r"[a-f0-9]{64}", receipt["sha256"]) is not None,
                "Malformed native congressional original receipt")
    summaries = {row["jurisdictionId"]: row for row in root["localityElections"]}
    require(len(summaries) == len(root["localityElections"]) == len(declarations)
            and set(summaries) == {row["id"] for row in declarations},
            "Incomplete native congressional locality election lineage")
    races, fragments = {}, {}

    def check_race(race, parent):
        label = native._english(race["name"])
        match = OFFICE.fullmatch(label)
        require(match is not None and 1 <= int(match[1]) <= 11
                and race["parentId"] == parent and race["contestType"] == "Candidate"
                and race["publishPublicElectionId"] == "2026-November-General"
                and native._english(race["voteFor"]) == "Vote for only one"
                and race["rankedChoiceSummaryResults"] is None,
                "Changed congressional election, seat, stage or vote-for scope")
        native._uuid(race["id"])
        status = race["reportingStatus"]
        require(integer(status["reportingUnits"]) == integer(status["totalUnits"])
                and status["totalUnits"] > 0, "Incomplete native congressional reporting")
        native._clock(status["asOf"])
        return f"VA-{int(match[1]):02d}", candidate_rows(race)

    for race in root["ballotItems"]:
        district, rows = check_race(race, None)
        require(district not in races, "Duplicate native congressional district")
        races[district] = (race, rows)
        fragments[district] = []
    require(set(races) == {f"VA-{number:02d}" for number in range(1, 12)},
            "Incomplete native House district inventory")
    by_uuid = {race["id"]: district for district, (race, _) in races.items()}
    require(len(by_uuid) == len(races), "Duplicate native congressional contest UUID")
    for declaration in declarations:
        code = declaration["code"]
        document = localities[code]
        jurisdiction = document["jurisdiction"]
        require(all(jurisdiction[key] == declaration[target] for key, target in (
            ("id", "id"), ("shortName", "short_name")))
            and native._english(jurisdiction["name"]) == declaration["name"]
            and lineage[code]["url"] == declaration["url"],
            "Changed native congressional locality identity or source URL")
        summary = native._election(summaries[declaration["id"]])
        local_election = native._election(document["election"], summary["id"])
        require(local_election["isOfficialResults"] == summary["isOfficialResults"]
                == election["isOfficialResults"],
                "Native congressional source finality differs")
        seen = set()
        for race in document["ballotItems"]:
            require(race["parentId"] in by_uuid, "Unreviewed locality congressional parent")
            district, rows = check_race(race, race["parentId"])
            require(district == by_uuid[race["parentId"]] and district not in seen,
                    "Duplicate or different locality congressional seat")
            seen.add(district)
            fragments[district].append({
                "locality_code": code, "native_contest_id": race["id"],
                "parent_contest_id": race["parentId"],
                "source_update_label": race["reportingStatus"]["asOf"],
                "contest_total": race["voteTotal"], "candidates": rows,
            })
    output = []
    for district, (race, rows) in sorted(races.items()):
        pieces = fragments[district]
        require(len(pieces) == race["reportingStatus"]["totalUnits"],
                "Congressional locality fragments do not match native reporting inventory")
        totals, modes = Counter(), {key: Counter() for key in rows}
        for piece in pieces:
            require(set(piece["candidates"]) == set(rows), "Changed locality candidate universe")
            for identity, candidate in piece["candidates"].items():
                fields = ("candidate_id", "name", "literal_party", "party_name", "party_group",
                          "role", "is_write_in", "is_qualified_write_in")
                require(all(candidate[key] == rows[identity][key] for key in fields),
                        "Locality candidate name, party or write-in role differs")
                totals[identity] += candidate["votes"]
                modes[identity].update(candidate["modes"])
        require(all(totals[key] == row["votes"] and dict(modes[key]) == row["modes"]
                    for key, row in rows.items()), "Congressional statewide/locality counts differ")
        output.append({
            "state_code": "VA", "district": district, "seat": str(int(district[3:])),
            "native_contest_id": race["id"], "native_office_label": native._english(race["name"]),
            "election_date": "2026-11-03", "stage": "general", "election_kind": "regular",
            "native_status_literal": "official" if election["isOfficialResults"] else "unofficial",
            "source_update_label": race["reportingStatus"]["asOf"], "source_update_timezone": "UTC",
            "reported_units": len(pieces), "total_units": len(pieces), "partial_units": 0,
            "reporting_unit_kind": "locality_contest_fragment_not_precinct",
            "complete_reporting": True, "contest_total": race["voteTotal"],
            "candidates": list(rows.values()), "locality_contests": pieces,
        })
    return {
        "contract": CONTRACT, "election_date": "2026-11-03", "races": output,
        "source_updated_at": election["asOf"], "native_facts": copy.deepcopy(facts),
        "derived_from_native_source_id": PARENT_ID,
        "participation_observation_qualified": False, "candidate_votes_are_not_ballots_or_turnout": True,
        "provider_other_equivalence_qualified": False, "conditional_model_eligible": False,
        "holds": ["Conditional models require a separately reviewed complete-universe and identity bridge."],
    }


def inventory(data):
    def candidates(rows):
        return sorted([
            row["candidate_id"], row["native_candidate_uuid"], row["name"], row["literal_party"],
            row["party_name"], row["party_group"], row["role"],
            row["is_write_in"], row["is_qualified_write_in"], sorted(row["modes"]),
        ] for row in rows)

    races = [
        [race["district"], race["seat"], race["native_contest_id"], race["total_units"],
         candidates(race["candidates"]),
         sorted([piece["locality_code"], piece["native_contest_id"], piece["parent_contest_id"],
                 candidates(piece["candidates"].values())]
                for piece in race["locality_contests"])]
        for race in data["races"]
    ]
    facts = data["native_facts"]
    documents = [("state", facts["root"]), *sorted(facts["localities"].items())]
    return {
        "races": races,
        "elections": [[code, document["election"]["id"]] for code, document in documents],
        "method_identities": [
            [code, race["id"], sorted(
                [candidate["nativeId"], sorted(
                    [native._english(mode["groupName"]), mode["groupId"]]
                    for mode in candidate["groupResults"])]
                for candidate in race["summaryResults"]["ballotOptions"])]
            for code, document in documents for race in document["ballotItems"]],
    }


def clocks(data):
    result = {}
    facts = data["native_facts"]
    for code, document in [("state", facts["root"]), *sorted(facts["localities"].items())]:
        for field in ("asOf", "lastUpdated"):
            result[(code, "election", field)] = document["election"][field]
        for race in document["ballotItems"]:
            result[(code, race["id"], "asOf")] = race["reportingStatus"]["asOf"]
    for summary in facts["root"]["localityElections"]:
        for field in ("asOf", "lastUpdated"):
            result[("locality_summary", summary["id"], field)] = summary[field]
    return result


def compatible_clock(data, previous, observed):
    current = clocks(data)
    require(all(native._clock(value) <= observed for value in current.values()),
            "Native congressional future clock")
    if previous:
        require(inventory(data) == inventory(previous),
                "Native congressional candidate or locality inventory changed")
        old = clocks(previous)
        require(current.keys() == old.keys()
                and all(native._clock(value) >= native._clock(old[key])
                        for key, value in current.items()), "Native congressional source clock regressed")


def derive(feeds):
    result = dict(feeds)
    if PARENT_ID not in feeds:
        return result
    parent = feeds[PARENT_ID]
    previous = feeds.get(IDENTITY) or {}
    entry = {key: copy.deepcopy(value) for key, value in parent.items() if key != "data"}
    entry["adapter"] = "derived_reviewed_native_locality_congress"
    try:
        queries = (parent.get("data") or {}).get("complete_native_query") or []
        require(len(queries) == 1, "Missing complete native congressional query")
        data = normalized(selected_facts(queries[0]))
        require(parent["source"] == data["native_facts"]["numerical_input_manifest"]["root"],
                "Native congressional root receipt differs")
        observed = native._clock(parent["first_observed_at"].replace("+00:00", "Z"))
        compatible_clock(data, previous.get("data"), observed)
        entry["data"] = data
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        entry.update(status="retained_after_failure" if previous.get("data") else "held",
                     error="native_congressional_evidence_incompatible", error_detail=str(error),
                     data=copy.deepcopy(previous.get("data")),
                     source=copy.deepcopy(previous.get("source")),
                     first_observed_at=previous.get("first_observed_at"))
    result[IDENTITY] = entry
    return result
