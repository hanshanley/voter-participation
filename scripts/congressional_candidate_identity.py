"""Reviewed FEC identity evidence; never a ballot-inventory or scientific-eligibility source."""

import copy
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

from scripts.participation_intake.contract import encoded, pin


VERSION = "20261117-identity-01"
CONTRACT = "participation.congressional_fec_identity.v1"
DATA_ROOT = "data/results-intake/analytical-handoff/fec-identity/"
DATA_PATHS = tuple(DATA_ROOT + name for name in (
    "predecessor-review.json.gz", "evidence.json.gz", "independent-native-verification.json"))
FIELDS = {
    "candidates": {
        "candidate_id", "name", "literal_party", "election_year", "office_state",
        "office", "district", "incumbent_challenger", "candidate_status",
    },
    "committees": {
        "committee_id", "name", "designation", "committee_type", "literal_party", "candidate_id",
    },
    "linkages": {
        "candidate_id", "candidate_election_year", "fec_election_year",
        "committee_id", "committee_type", "designation", "linkage_id",
    },
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def tokens(value):
    return re.findall(r"[a-z0-9]+", value.casefold())


class Evidence:
    def __init__(self, value):
        require(value.get("contract") == CONTRACT, "Unreviewed FEC identity evidence")
        require(set(value) == {"contract", "sources", *FIELDS}, "Unexpected FEC evidence fields")
        for label, fields in FIELDS.items():
            require(isinstance(value[label], list), "Missing complete FEC identity table")
            for row in value[label]:
                require(set(row) == fields and all(isinstance(item, str) for item in row.values()),
                        "Unexpected or nonliteral FEC identity field")
        self.candidates = {row["candidate_id"]: row for row in value["candidates"]}
        require(len(self.candidates) == len(value["candidates"]), "Duplicate FEC candidate identity")
        committees = {row["committee_id"]: row for row in value["committees"]}
        require(len(committees) == len(value["committees"]), "Duplicate FEC committee identity")
        self.authorized = defaultdict(list)
        for link in value["linkages"]:
            committee = committees.get(link["committee_id"])
            if (link["candidate_election_year"] == link["fec_election_year"] == "2026"
                    and link["committee_type"] == "H" and link["designation"] in ("P", "A")
                    and committee is not None
                    and committee["candidate_id"] == link["candidate_id"]
                    and committee["committee_type"] == "H"
                    and committee["designation"] == link["designation"]):
                self.authorized[link["candidate_id"]].append((committee, link))
        self.by_frame = defaultdict(list)
        for row in self.candidates.values():
            if row["office"] == "H" and row["election_year"] == "2026":
                frame = (row["office_state"], row["district"], row["literal_party"])
                self.by_frame[frame].append(row)

    def support(self, name, candidate):
        surname, separator, given = candidate["name"].partition(",")
        words, family, first = tokens(name), tokens(surname), tokens(given)
        if not separator or len(words) <= len(family) or words[-len(family):] != family:
            return None
        given_words = words[:-len(family)]
        if first[:len(given_words)] == given_words and len(given_words[0]) > 1:
            return {"method": "literal_FEC_given_prefix_and_full_surname"}
        aliases = re.findall(r"""['"]([^'"]+)['"]""", given)
        if any(tokens(alias) == given_words for alias in aliases):
            return {"method": "explicit_FEC_quoted_given_name_and_full_surname"}
        for committee, linkage in self.authorized[candidate["candidate_id"]]:
            committee_words = tokens(committee["name"])
            if (len(given_words[0]) > 1 and
                    any(committee_words[index:index + len(words)] == words
                        for index in range(len(committee_words) - len(words) + 1))):
                return {"method": "authorized_committee_literal_full_name",
                        "committee_id": committee["committee_id"],
                        "committee_name": committee["name"], "linkage_id": linkage["linkage_id"]}
        return None

    def resolve(self, old, current, race):
        from scripts.automatic_estimates import _party_group

        group = _party_group(old["party"])
        frame = race["identity"]
        if (group not in ("D", "R") or current["party_group"] != group
                or current["role"] != "named_candidate"
                or frame["chamber"] != "house" or frame["election_date"] != "2026-11-03"
                or frame["election_kind"] != "regular"
                or frame["stage"] != "general" or frame["ranked_choice"] is not False
                or old["state_code"] != frame["state_code"] or old["district"] != race["district"]
                or str(old["year"]) != "2026"):
            return None
        district = race["district"].split("-", 1)[1]
        district = "00" if district == "AL" else district.zfill(2)
        candidates = self.by_frame[(frame["state_code"], district, {"D": "DEM", "R": "REP"}[group])]
        matches = []
        for name in (old["name"], current["name"]):
            matches.append([(row, proof) for row in candidates
                            if (proof := self.support(name, row)) is not None])
        if len(matches[0]) != 1 or len(matches[1]) != 1:
            return None
        before, after = matches[0][0], matches[1][0]
        if before[0]["candidate_id"] != after[0]["candidate_id"]:
            return None
        return {"fec_candidate": copy.deepcopy(before[0]),
                "legacy_support": before[1], "provider_support": after[1],
                "ballot_stage_and_counts_qualified_by_FEC": False}


def successor(previous, value, files):
    from scripts.automatic_estimates import _party_group

    require(previous.get("version") == "20261116-01", "Identity review needs its frozen predecessor")
    evidence = Evidence(value)
    review = copy.deepcopy(previous)
    changed = []
    crosswalk = {(row["race_id"], row["legacy_index"]): row for row in review["candidate_crosswalk"]}
    for key, race in review["races"].items():
        if race["district"] is None:
            continue
        candidates = race["accepted_native"]["candidates"]
        proposals = {}
        for index in race["unmatched_legacy_indices"]:
            old = review["legacy_candidates_preserved"][index]
            options = []
            for candidate in candidates:
                if candidate["candidate_id"] not in race["named_crosswalk"]:
                    proof = evidence.resolve(old, candidate, race)
                    if proof is not None:
                        options.append((candidate, proof))
            if len(options) == 1:
                proposals[index] = options[0]
        target_counts = defaultdict(int)
        for candidate, _ in proposals.values():
            target_counts[candidate["candidate_id"]] += 1
        for index, (candidate, proof) in proposals.items():
            if target_counts[candidate["candidate_id"]] != 1:
                continue
            race["named_crosswalk"][candidate["candidate_id"]] = index
            race["unmatched_legacy_indices"].remove(index)
            row = crosswalk[(key, index)]
            row.update(provider_candidate_id=candidate["candidate_id"],
                       provider_literal_name=candidate["name"],
                       provider_literal_party=candidate["literal_party"],
                       decision="reviewed_named_identity", rule="reviewed_FEC_stable_identity",
                       identity_evidence=proof)
            changed.append({"race_id": key, "legacy_index": index,
                            "provider_candidate_id": candidate["candidate_id"], **proof})
        remaining_major = {
            "unmatched_or_ambiguous_named_major_candidate:"
            + review["legacy_candidates_preserved"][index]["name"]
            for index in race["unmatched_legacy_indices"]
            if _party_group(review["legacy_candidates_preserved"][index]["party"]) in ("D", "R")}
        unlisted = any(candidate["candidate_id"] not in race["named_crosswalk"]
                       and candidate["role"] != "provider_aggregate_other" for candidate in candidates)
        race["initial_holds"] = [
            reason for reason in race["initial_holds"]
            if (not reason.startswith("unmatched_or_ambiguous_named_major_candidate:")
                or reason in remaining_major)
            and (reason != "unmatched_new_named_candidate" or unlisted)]
    for state, decision in review["states"].items():
        old_race_holds = {key + ":" + reason for key in decision["expected_race_ids"]
                          for reason in previous["races"][key]["initial_holds"]}
        new_race_holds = {key + ":" + reason for key in decision["expected_race_ids"]
                          for reason in review["races"][key]["initial_holds"]}
        decision["holds"] = sorted((set(decision["holds"]) - old_race_holds) | new_race_holds)
        decision["automatic_update_reviewed"] = not decision["holds"]
        if decision["automatic_update_reviewed"]:
            require(decision["frozen_scientific_comparison_qualified"]
                    and decision["initial_recorded_comparison_qualified"] and state not in ("HI", "WY"),
                    "Candidate identity evidence cannot grant new scientific eligibility")
    review["version"] = VERSION
    review["candidate_identity_successor"] = {
        "contract": CONTRACT, "version": VERSION, "files": copy.deepcopy(files),
        "predecessor_review_sha256": pin(encoded(previous))["sha256"],
        "evidence_sha256": pin(encoded(value))["sha256"],
        "resolved_identities": changed,
        "FEC_is_not_a_complete_ballot_or_stage_inventory": True,
        "all_legacy_candidates_and_unmatched_Other_mass_preserved": True,
        "nickname_dictionary_or_initial_only_aliases_used": False,
    }
    return review


def load_successor(root, review):
    require(review.get("version") == VERSION, "Unreviewed candidate identity successor")
    descriptor = review.get("candidate_identity_successor") or {}
    files = descriptor.get("files") or {}
    require(set(files) == set(DATA_PATHS), "Incomplete candidate identity evidence package")
    bodies = {}
    for name in DATA_PATHS:
        body = (Path(root) / name).read_bytes()
        require(pin(body) == files[name], "Changed complete candidate identity evidence")
        bodies[name] = body
    previous = json.loads(gzip.decompress(bodies[DATA_PATHS[0]]))
    evidence = json.loads(gzip.decompress(bodies[DATA_PATHS[1]]))
    require(successor(previous, evidence, files) == review,
            "Candidate identity decisions do not reproduce from their complete predecessor and evidence")
    return review
