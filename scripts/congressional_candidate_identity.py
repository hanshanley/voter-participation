"""Reviewed FEC identity evidence; never a ballot-inventory or scientific-eligibility source."""

import copy
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from scripts.participation_intake.contract import encoded, pin


VERSION = "20261117-identity-01"
CONTRACT = "participation.congressional_fec_identity.v1"
DATA_ROOT = "data/results-intake/analytical-handoff/fec-identity/"
DATA_PATHS = tuple(DATA_ROOT + name for name in (
    "predecessor-review.json.gz", "evidence.json.gz", "independent-native-verification.json"))
DECLARATION_VERSION = "20261117-declarations-01"
DECLARATION_CONTRACT = "participation.congressional_primary_name_declarations.v1"
DECLARATION_PATHS = tuple("data/results-intake/analytical-handoff/name-declarations/" + name
                         for name in ("predecessor-review.json.gz", "evidence.json.gz",
                                      "independent-native-verification.json"))
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


def _apply_evidence(previous, evidence, rule):
    from scripts.automatic_estimates import _party_group

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
                       decision="reviewed_named_identity", rule=rule,
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
    return review, changed


def successor(previous, value, files):
    require(previous.get("version") == "20261116-01", "Identity review needs its frozen predecessor")
    review, changed = _apply_evidence(previous, Evidence(value), "reviewed_FEC_stable_identity")
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


def declared_names(literal):
    quoted = re.fullmatch(r'(.+?)\s+["\u201c]([^"\u201d]+)["\u201d]\s+(.+)', literal)
    if quoted:
        given, alias, family = quoted.groups()
        return [given + " " + family, alias + " " + family]
    return [literal]


def full_name_key(name):
    words = tokens(name)
    return [words[0], *[word for word in words[1:-1] if len(word) > 1], words[-1]] if len(words) >= 2 else []


class DeclaredEvidence(Evidence):
    def __init__(self, fec, value):
        super().__init__(fec)
        require(set(value) == {"contract", "sources", "declarations"}
                and value["contract"] == DECLARATION_CONTRACT, "Unreviewed primary name declarations")
        require(isinstance(value["sources"], list) and isinstance(value["declarations"], list),
                "Missing primary name evidence tables")
        sources = {}
        for source in value["sources"]:
            require(set(source) == {"id", "url", "bytes", "sha256", "checked_at", "kind", "facts"},
                    "Unexpected primary evidence fields")
            url = urlsplit(source["url"])
            require(url.scheme == "https" and url.netloc and not url.username and not url.password
                    and source["kind"] in ("candidate_campaign", "nominating_party")
                    and type(source["bytes"]) is int and source["bytes"] > 0
                    and re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
                    and isinstance(source["checked_at"], str) and source["checked_at"],
                    "Unqualified primary source receipt")
            require(source["id"] not in sources, "Duplicate primary source")
            require(isinstance(source["facts"], dict) and source["facts"]
                    and all(isinstance(key, str) and isinstance(text, str) and text
                            for key, text in source["facts"].items()), "Nonliteral primary name facts")
            sources[source["id"]] = source
        self.declarations = defaultdict(list)
        seen = set()
        for declaration in value["declarations"]:
            require(set(declaration) == {"fec_candidate_id", "state_code", "district", "literal_party",
                                        "election_year", "source_id", "name_facts", "role_fact",
                                        "relationship"}, "Unexpected name declaration fields")
            candidate = self.candidates.get(declaration["fec_candidate_id"])
            source = sources.get(declaration["source_id"])
            require(candidate is not None and source is not None, "Unbound primary declaration")
            require(candidate["office"] == "H" and candidate["election_year"] == "2026"
                    and all(declaration[key] == candidate[other] for key, other in (
                        ("state_code", "office_state"), ("district", "district"),
                        ("literal_party", "literal_party"), ("election_year", "election_year")))
                    and declaration["relationship"] == "same_candidate_biography",
                    "Primary declaration frame differs from FEC identity")
            key = (declaration["fec_candidate_id"], declaration["source_id"])
            require(key not in seen, "Duplicate candidate declaration")
            seen.add(key)
            ids = declaration["name_facts"]
            require(isinstance(ids, list) and ids and len(ids) == len(set(ids))
                    and all(item in source["facts"] for item in ids)
                    and declaration["role_fact"] in source["facts"], "Incomplete declared identity facts")
            role = source["facts"][declaration["role_fact"]]
            require(tokens(role) == ["us", "representative", "district", str(int(candidate["district"]))],
                    "Primary declaration does not identify its congressional district")
            names = [name for item in ids for name in declared_names(source["facts"][item])]
            family = tokens(candidate["name"].partition(",")[0])
            require(len({tuple(full_name_key(name)) for name in names}) >= 2
                    and all(len(tokens(name)) > len(family)
                            and len(tokens(name)[0]) > 1
                            and tokens(name)[-len(family):] == family for name in names)
                    and any(super(DeclaredEvidence, self).support(
                        " ".join(full_name_key(name)), candidate) for name in names),
                    "Declared aliases lack a full-surname FEC anchor")
            self.declarations[candidate["candidate_id"]].append((source, ids, names))

    def support(self, name, candidate):
        ordinary = super().support(name, candidate)
        if ordinary is not None:
            return ordinary
        matches = []
        for source, ids, names in self.declarations[candidate["candidate_id"]]:
            if full_name_key(name) in [full_name_key(item) for item in names]:
                matches.append({
                    "source_id": source["id"], "source_url": source["url"],
                    "source_pin": {key: source[key] for key in ("bytes", "sha256")},
                    "name_facts": {key: source["facts"][key] for key in ids},
                })
        if matches:
            return {"method": "reviewed_explicit_primary_name_declaration", "declarations": matches}
        return None


def declaration_successor(previous, value, fec, files):
    require(previous.get("version") == VERSION, "Name declarations need the reviewed FEC predecessor")
    require(pin(encoded(fec))["sha256"] == previous["candidate_identity_successor"]["evidence_sha256"],
            "Name declarations need the same complete FEC evidence")
    review, changed = _apply_evidence(previous, DeclaredEvidence(fec, value),
                                    "reviewed_primary_declaration_and_FEC_stable_identity")
    review["version"] = DECLARATION_VERSION
    review["candidate_name_declarations"] = {
        "contract": DECLARATION_CONTRACT, "version": DECLARATION_VERSION,
        "files": copy.deepcopy(files), "predecessor_review_sha256": pin(encoded(previous))["sha256"],
        "evidence_sha256": pin(encoded(value))["sha256"], "resolved_identities": changed,
        "declarations_do_not_establish_ballot_inventory_or_stage": True,
        "all_legacy_candidates_and_unmatched_Other_mass_preserved": True,
        "nickname_dictionary_or_initial_only_aliases_used": False,
    }
    return review


def load_declaration_successor(root, review):
    require(review.get("version") == DECLARATION_VERSION, "Unreviewed primary declaration successor")
    files = (review.get("candidate_name_declarations") or {}).get("files") or {}
    require(set(files) == set(DECLARATION_PATHS), "Incomplete primary declaration evidence package")
    bodies = {}
    for name in DECLARATION_PATHS:
        body = (Path(root) / name).read_bytes()
        require(pin(body) == files[name], "Changed complete primary declaration evidence")
        bodies[name] = body
    previous = json.loads(gzip.decompress(bodies[DECLARATION_PATHS[0]]))
    load_successor(root, previous)
    value = json.loads(gzip.decompress(bodies[DECLARATION_PATHS[1]]))
    fec = json.loads(gzip.decompress((Path(root) / DATA_PATHS[1]).read_bytes()))
    require(declaration_successor(previous, value, fec, files) == review,
            "Primary declaration decisions do not reproduce from complete pinned evidence")
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
