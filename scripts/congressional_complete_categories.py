"""Complete official minor/write-in inventories for reviewed category updates."""

import copy
from datetime import datetime
import gzip
import json
from pathlib import Path
import re
from uuid import UUID

from scripts.participation_intake.contract import encoded, pin


VERSION = "20261117-categories-02"
CONTRACT = "participation.congressional_complete_categories.v1"
IDENTITY = "RI-official-house-candidates"
URL = ("https://electionresults.ri.gov/results/public/api/elections/"
       "rhodeisland/2026StatewideGeneralElection/data")
DATA_ROOT = "data/results-intake/analytical-handoff/complete-categories/"
DATA_PATHS = tuple(DATA_ROOT + name for name in (
    "predecessor-review.json.gz", "evidence.json.gz", "independent-native-verification.json"))
MODES = {
    "01000000-59ac-daed-698b-08df1e27c424": "Election Day",
    "01000000-59ac-daed-6316-08df1e27c425": "Early Voting",
    "01000000-59ac-daed-65a2-08df1e27c425": "Mail Ballots",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    require(isinstance(value, list), "Missing native localized identity")
    require(all(isinstance(row, dict) and "text" in row for row in value),
            "Malformed native localized identity")
    values = [row["text"] for row in value if row.get("languageId") == "en"]
    require(len(values) == 1 and isinstance(values[0], str) and values[0].strip(),
            "Ambiguous native English identity")
    return values[0]


def integer(value):
    require(type(value) is int and 0 <= value <= 2**53 - 1,
            "Missing or invalid native candidate count")
    return value


def clock(value):
    require(isinstance(value, str) and value.endswith("Z"), "Missing native UTC count clock")
    normalized = re.sub(r"(\.[0-9]{6})[0-9]+Z$", r"\1Z", value)
    return datetime.fromisoformat(normalized[:-1] + "+00:00")


def identifier(value):
    require(isinstance(value, str) and str(UUID(value)) == value, "Invalid native stable identity")
    return value


def selected_native(document, chamber="house"):
    """Keep the entire selected federal tables, without unrelated publisher material."""
    require(chamber in ("house", "senate"), "Unreviewed federal office")
    prefix = "Representative in Congress" if chamber == "house" else "Senator in Congress"
    election = document["election"]
    fields = ("id", "jurisdictionId", "name", "electionDate", "isProduction",
              "isOfficialResults", "isPrimary", "asOf")
    result = {"election": {key: copy.deepcopy(election[key]) for key in fields}, "ballotItems": []}
    for row in document["ballotItems"]:
        if not text(row["name"]).startswith(prefix):
            continue
        contest = {key: copy.deepcopy(row[key]) for key in (
            "id", "parentId", "publishPublicElectionId", "name", "voteFor",
            "reportingStatus", "voteTotal", "contestType", "rankedChoiceSummaryResults")}
        contest["summaryResults"] = {"ballotOptions": []}
        for candidate in row["summaryResults"]["ballotOptions"]:
            value = {key: copy.deepcopy(candidate[key]) for key in (
                "id", "nativeId", "name", "voteCount", "groupResults", "isWriteIn",
                "isQualifiedWriteIn")}
            value["party"] = {key: copy.deepcopy(candidate["party"][key])
                              for key in ("id", "name", "abbreviation", "standardName")}
            contest["summaryResults"]["ballotOptions"].append(value)
        result["ballotItems"].append(contest)
    return result


def parse(body, chamber="house"):
    from scripts.results_official_congress import CONTRACT as OFFICIAL_CONTRACT

    document = json.loads(body)
    native = selected_native(document, chamber)
    election = native["election"]
    require(election["id"] == "01000000-eac8-8412-859d-08df1e279809"
            and election["jurisdictionId"] == "8ffc83e2-a526-4cb5-9f8f-f87fef52d125"
            and text(election["name"]) == "Statewide General Election"
            and election["electionDate"] == "2026-11-03"
            and election["isProduction"] is True and election["isPrimary"] is False
            and type(election["isOfficialResults"]) is bool,
            "Official publisher, election, production or stage changed")
    clock(election["asOf"])
    races = []
    for row in native["ballotItems"]:
        match = re.fullmatch(
            r"Representative in Congress District ([12])" if chamber == "house"
            else r"Senator in Congress", text(row["name"]))
        require(match is not None and row["parentId"] is None
                and row["publishPublicElectionId"] == "2026StatewideGeneralElection"
                and row["contestType"] == "Candidate"
                and text(row["voteFor"]) == "Vote for 1"
                and row["rankedChoiceSummaryResults"] is None,
                "Unreviewed House district, parent, stage, multiseat or ranked round")
        status = row["reportingStatus"]
        reported, total = integer(status["reportingUnits"]), integer(status["totalUnits"])
        require(total > 0 and reported == total, "Incomplete official House reporting inventory")
        require(status["asOf"] == election["asOf"], "Mixed official contest count clocks")
        candidates = []
        for candidate in row["summaryResults"]["ballotOptions"]:
            party = candidate["party"]
            literal, write_in = text(candidate["name"]), candidate["isWriteIn"]
            require(type(write_in) is bool and candidate["isQualifiedWriteIn"] is False,
                    "Unreviewed named or qualified write-in role")
            abbreviation = party["abbreviation"]
            if write_in:
                require(literal == "Write-in" and all(value is None for value in party.values()),
                        "Generic write-in has a named/affiliated identity")
                name, group = literal, "O"
            else:
                require(abbreviation in ("DEM", "REP", "Ind")
                        and text(party["name"]) == {
                            "DEM": "DEMOCRAT", "REP": "REPUBLICAN", "Ind": "Independent"}[abbreviation]
                        and literal.endswith(" (" + abbreviation + ")"),
                        "Unknown official candidate party or literal suffix")
                identifier(party["id"])
                name = literal[:-(len(abbreviation) + 3)]
                require(bool(name.strip()), "Empty official named candidate")
                group = {"DEM": "D", "REP": "R", "Ind": "O"}[abbreviation]
            modes = candidate["groupResults"]
            require(len(modes) == len(MODES) and {mode["groupId"] for mode in modes} == set(MODES)
                    and all(text(mode["groupName"]) == MODES[mode["groupId"]] for mode in modes),
                    "Changed or duplicate native candidate mode inventory")
            votes = integer(candidate["voteCount"])
            require(candidate["nativeId"] is None or
                    (type(candidate["nativeId"]) in (str, int) and bool(str(candidate["nativeId"]))),
                    "Malformed native candidate identity")
            require(sum(integer(mode["voteCount"]) for mode in modes) == votes,
                    "Native candidate modes do not reconcile")
            candidates.append({
                "candidate_id": identifier(candidate["id"]), "native_id": candidate["nativeId"],
                "name": name, "name_literal": literal, "literal_party": abbreviation,
                "party_group": group, "votes": votes,
                "role": "generic_write_in" if write_in else "named_candidate",
                "native_mode_counts": copy.deepcopy(modes),
            })
        require(len({candidate["candidate_id"] for candidate in candidates}) == len(candidates)
                and len({(candidate["name"], candidate["literal_party"]) for candidate in candidates})
                == len(candidates)
                and sum(candidate["votes"] for candidate in candidates) == integer(row["voteTotal"])
                and sum(candidate["role"] == "generic_write_in" for candidate in candidates) == 1
                and all(sum(candidate["party_group"] == group for candidate in candidates) == 1
                        for group in "DR"),
                "Complete official candidate inventory does not reconcile to its contest control")
        seat = match[1] if chamber == "house" else "2"
        races.append({
            "state_code": "RI", "district": ("RI-0" if chamber == "house" else "RI-S") + seat,
            "seat": seat,
            "native_contest_id": identifier(row["id"]), "native_office_label": text(row["name"]),
            "election_date": "2026-11-03", "stage": "general", "election_kind": "regular",
            "native_status_literal": "Official Results" if election["isOfficialResults"] else "Unofficial Results",
            "source_update_label": election["asOf"], "source_update_timezone": "UTC",
            "reported_units": reported, "total_units": total, "partial_units": 0,
            "complete_reporting": True, "contest_total": row["voteTotal"], "candidates": candidates,
        })
        if chamber == "senate":
            races[-1].update(
                chamber="senate", native_seat_declared=False,
                seat_basis="reviewed_2026_regular_Class_II_cycle_not_a_native_seat_field")
    require((len(races) == 2 and {row["seat"] for row in races} == {"1", "2"})
            if chamber == "house" else (len(races) == 1 and races[0]["seat"] == "2"),
            "Incomplete or duplicate statewide official House district inventory")
    return {
        "contract": OFFICIAL_CONTRACT, "election_date": "2026-11-03",
        "source_updated_at": election["asOf"], "races": sorted(races, key=lambda row: row["seat"]),
        "native_facts": native, "complete_minor_and_generic_write_in_inventory": True,
        "participation_observation_qualified": False, "candidate_votes_are_not_ballots_or_turnout": True,
        "provider_other_equivalence_qualified": False, "conditional_model_eligible": False,
        "holds": ["Evidence alone does not grant model eligibility or combine provider counts."],
    }


def signature(race):
    return {
        "native_contest_id": race["native_contest_id"], "seat": race["seat"],
        "candidates": sorted([row["candidate_id"], row["native_id"], row["name"],
                              row["literal_party"], row["party_group"], row["role"]]
                             for row in race["candidates"]),
    }


def reconcile(previous, query):
    from scripts.congressional_analytical_bridge import name_tokens, review_names
    from scripts.automatic_estimates import _party_group

    require(parse(encoded(query["native_facts"])) == query, "Changed complete official category facts")
    expected = previous["states"]["RI"]["expected_race_ids"]
    require(len(expected) == 2, "Unreviewed provider statewide inventory")
    decisions = {}
    for key in expected:
        reviewed = previous["races"][key]
        frame = reviewed["identity"]
        require(all(frame.get(name) == value for name, value in {
            "state_code": "RI", "chamber": "house", "election_date": "2026-11-03",
            "stage": "general", "election_kind": "regular", "ranked_choice": False,
            "round": "not_ranked"}.items()), "Official and model election/office/stage differ")
        official = next(row for row in query["races"] if row["seat"] == frame["seat"])
        provider = reviewed["accepted_native"]["candidates"]
        named = [row for row in provider if row["role"] == "named_candidate"]
        aggregates = [row for row in provider if row["role"] == "provider_aggregate_other"]
        require(len(aggregates) == 1 and aggregates[0]["party_group"] == "O"
                and len(named) + 1 == len(provider), "Ambiguous provider Other category")
        mapped, legacy_indices, omitted = set(), set(), []
        for row in official["candidates"]:
            options = [candidate for candidate in named
                       if row["role"] == "named_candidate" and candidate["party_group"] == row["party_group"]
                       and review_names(row["name"], candidate["name"])]
            if options:
                require(len(options) == 1 and options[0]["candidate_id"] not in mapped
                        and options[0]["candidate_id"] in reviewed["named_crosswalk"],
                        "Official named provider identity is unresolved or ambiguous")
                mapped.add(options[0]["candidate_id"])
                continue
            require(row["party_group"] == "O", "Official major candidate is absent from provider")
            options = [
                index for index in reviewed["unmatched_legacy_indices"]
                if (name_tokens(previous["legacy_candidates_preserved"][index]["name"]) == ["write", "in"]
                    if row["role"] == "generic_write_in" else
                    review_names(previous["legacy_candidates_preserved"][index]["name"], row["name"]))
                and _party_group(previous["legacy_candidates_preserved"][index]["party"]) == "O"
            ]
            require(len(options) == 1 and options[0] not in legacy_indices,
                    "Official minor/write-in identity differs from retained legacy universe")
            legacy_indices.add(options[0])
            omitted.append(copy.deepcopy(row))
        require(mapped == {row["candidate_id"] for row in named}
                and legacy_indices == set(reviewed["unmatched_legacy_indices"]),
                "Complete official/provider/legacy candidate inventories differ")
        require(sum(row["votes"] for row in omitted) == aggregates[0]["votes"],
                "Provider Other differs from complete official minor/write-in mass")
        decisions[key] = {
            "method": "complete_official_minor_and_write_in_category_inventory",
            "source_id": IDENTITY, "source_url": URL, "official_inventory": signature(official),
            "accepted_source_updated_at": query["source_updated_at"],
            "official_omitted_candidates": omitted,
            "official_omitted_candidate_ids": sorted(row["candidate_id"] for row in omitted),
            "provider_aggregate_id": aggregates[0]["candidate_id"],
            "provider_aggregate_other": copy.deepcopy(aggregates[0]),
            "retained_legacy_indices": sorted(legacy_indices),
            "individual_count_allocated_from_Other": False,
            "provider_counts_not_added_to_official_counts": True,
            "subsequent_updates_require_fresh_complete_official_category_evidence": True,
        }
    return decisions


def successor(previous, value, files):
    from scripts.congressional_category_reconciliation import MASS_HOLD
    from scripts.congressional_filing_identity import VERSION as PREVIOUS_VERSION

    require(previous.get("version") == PREVIOUS_VERSION, "Complete category successor needs full predecessor")
    require(set(value) == {"contract", "source_url", "native_original", "captured_at", "official_house_query"}
            and value["contract"] == CONTRACT and value["source_url"] == URL,
            "Unreviewed complete category evidence")
    original = value["native_original"]
    require(isinstance(original, dict) and set(original) == {"bytes", "sha256"}
            and type(original["bytes"]) is int and original["bytes"] > 0
            and isinstance(original["sha256"], str)
            and re.fullmatch(r"[a-f0-9]{64}", original["sha256"]),
            "Missing complete category original byte pin")
    require(isinstance(value["captured_at"], str), "Missing complete category capture clock")
    require(clock(value["captured_at"].replace("+00:00", "Z")) >=
            clock(value["official_house_query"]["source_updated_at"]),
            "Complete category source clock exceeds capture")
    decisions = reconcile(previous, value["official_house_query"])
    result, resolved = copy.deepcopy(previous), []
    for key, decision in decisions.items():
        race = result["races"][key]
        if MASS_HOLD in race["initial_holds"]:
            race["initial_holds"].remove(MASS_HOLD)
            resolved.append(key)
        race["complete_official_categories"] = decision
    require(bool(resolved), "Complete official categories resolve no guard")
    for state, decision in result["states"].items():
        decision["holds"] = sorted(set(decision["holds"]) - {
            key + ":" + MASS_HOLD for key in resolved if key in decision["expected_race_ids"]})
        decision["automatic_update_reviewed"] = not decision["holds"]
        if decision["automatic_update_reviewed"]:
            require(decision["frozen_scientific_comparison_qualified"]
                    and decision["initial_recorded_comparison_qualified"] and state not in ("HI", "WY"),
                    "Category evidence cannot grant new scientific eligibility")
    result["version"] = VERSION
    result["complete_category_successor"] = {
        "contract": CONTRACT, "version": VERSION, "files": copy.deepcopy(files),
        "predecessor_review_sha256": pin(encoded(previous))["sha256"],
        "evidence_sha256": pin(encoded(value))["sha256"],
        "reviewed_races": sorted(decisions), "resolved_races": sorted(resolved),
        "all_legacy_candidates_and_individual_counts_preserved": True,
    }
    return result


def load_successor(root, review):
    from scripts.congressional_filing_identity import load_successor as load_previous

    require(review.get("version") == VERSION, "Unreviewed complete category successor")
    files = (review.get("complete_category_successor") or {}).get("files") or {}
    require(set(files) == set(DATA_PATHS), "Incomplete complete-category evidence package")
    bodies = {}
    for name in DATA_PATHS:
        body = (Path(root) / name).read_bytes()
        require(pin(body) == files[name], "Changed complete category evidence")
        bodies[name] = body
    previous = json.loads(gzip.decompress(bodies[DATA_PATHS[0]]))
    load_previous(root, previous)
    evidence = json.loads(gzip.decompress(bodies[DATA_PATHS[1]]))
    require(successor(previous, evidence, files) == review, "Complete category decisions do not reproduce")
    return review


def current_hold(congress, key, reviewed, provider):
    policy = reviewed.get("complete_official_categories")
    if policy is None:
        return None
    try:
        entry = congress.get("official_candidate_evidence", {}).get(policy["source_id"], {})
        require(entry.get("status") == "reported", "official_category_source_not_fresh")
        require((entry.get("source") or {}).get("url") == policy["source_url"],
                "official_category_source_URL_changed")
        data = entry["data"]
        require(parse(encoded(data["native_facts"])) == data, "official_category_native_facts_changed")
        require(clock(data["source_updated_at"]) >= clock(policy["accepted_source_updated_at"]),
                "official_category_source_clock_regressed")
        rows = [row for row in data["races"] if row["seat"] == reviewed["identity"]["seat"]]
        require(len(rows) == 1 and signature(rows[0]) == policy["official_inventory"],
                "official_category_candidate_inventory_changed")
        official = rows[0]
        aggregates = [row for row in provider["candidates"]
                      if row["role"] == "provider_aggregate_other"
                      and row["candidate_id"] == policy["provider_aggregate_id"]]
        omitted = [row for row in official["candidates"]
                   if row["candidate_id"] in policy["official_omitted_candidate_ids"]]
        require(len(aggregates) == 1 and sum(row["votes"] for row in omitted) == aggregates[0]["votes"],
                "official_category_Other_mass_differs")
    except (ValueError, KeyError, TypeError, StopIteration) as error:
        return str(error)
    return None
