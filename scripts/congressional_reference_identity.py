"""Explicit quoted names bound to authorized filings and a primary candidate role."""

import copy
import gzip
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from scripts.congressional_candidate_identity import (
    DATA_PATHS as FEC_PATHS, _apply_evidence, declared_names, full_name_key, require, tokens,
)
from scripts.congressional_complete_categories import VERSION as PREDECESSOR_VERSION
from scripts.congressional_filing_identity import FilingEvidence, filing_name
from scripts.participation_intake.contract import encoded, pin


VERSION = "20261118-01"
CONTRACT = "participation.congressional_explicit_reference_names.v1"
REVIEW_PATH = "data/results-intake/explicit-reference-names/review.json"
DATA_PATHS = (REVIEW_PATH,) + tuple(
    "data/results-intake/explicit-reference-names/" + name
    for name in ("evidence.json.gz", "independent-native-verification.json"))


class ReferenceEvidence(FilingEvidence):
    def __init__(self, fec, value):
        require(isinstance(value, dict) and set(value) == {
            "contract", "authorized_filings", "sources", "declarations"}
            and value["contract"] == CONTRACT, "Unreviewed explicit reference names")
        super().__init__(fec, value["authorized_filings"])
        require(isinstance(value["sources"], list) and isinstance(value["declarations"], list)
                and value["declarations"], "Missing complete name-reference evidence")
        sources = {}
        self.reference_names = {}
        for source in value["sources"]:
            require(isinstance(source, dict) and set(source) == {
                "id", "url", "bytes", "sha256", "checked_at", "kind", "facts"},
                "Unexpected name-reference source fields")
            url = urlsplit(source["url"])
            require(isinstance(source["id"], str) and source["id"]
                    and source["id"] not in sources
                    and url.scheme == "https" and url.hostname
                    and not url.username and not url.password
                    and type(source["bytes"]) is int and source["bytes"] > 0
                    and isinstance(source["sha256"], str)
                    and re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
                    and isinstance(source["checked_at"], str) and source["checked_at"]
                    and source["kind"] in ("candidate_reference", "nominating_party_role")
                    and isinstance(source["facts"], dict),
                    "Unqualified or duplicate name-reference source")
            sources[source["id"]] = source
        filings = value["authorized_filings"]
        filing_sources = {source["id"]: source for source in filings["sources"]}
        for declaration in value["declarations"]:
            require(isinstance(declaration, dict) and set(declaration) == {
                "fec_candidate_id", "filing_source", "reference_source", "party_source"},
                "Unexpected explicit name-reference declaration")
            cid = declaration["fec_candidate_id"]
            candidate = self.candidates.get(cid)
            reference = sources.get(declaration["reference_source"])
            party = sources.get(declaration["party_source"])
            form = filing_sources.get(declaration["filing_source"])
            require(candidate is not None and candidate["office"] == "H"
                    and candidate["election_year"] == "2026"
                    and cid not in self.reference_names
                    and reference is not None and reference["kind"] == "candidate_reference"
                    and party is not None and party["kind"] == "nominating_party_role"
                    and urlsplit(reference["url"]).hostname != urlsplit(party["url"]).hostname
                    and form is not None and form["kind"] == "fec_form1"
                    and len([row for row in filings["filings"]
                             if row["fec_candidate_id"] == cid
                             and row["filing_source"] == form["id"]]) == 1,
                    "Name reference lacks its unique authorized filing and independent party role")
            facts = reference["facts"]
            require(set(facts) == {
                "candidate_label", "fec_candidate_id", "same_native_candidate_cell",
                "election_date", "chamber", "state_code", "district", "literal_party"}
                and facts["fec_candidate_id"] == cid
                and facts["same_native_candidate_cell"] is True
                and facts["election_date"] == "2026-11-03" and facts["chamber"] == "house"
                and facts["state_code"] == candidate["office_state"]
                and facts["district"] == candidate["district"]
                and facts["literal_party"] == {"REP": "Republican", "DEM": "Democratic"}.get(
                    candidate["literal_party"]),
                "Explicit reference has a different candidate, party, seat or election")
            names = declared_names(facts["candidate_label"])
            require(len(names) == 2 and tokens(names[0]) == tokens(filing_name(
                    form["facts"]["candidate_name"]))
                    and full_name_key(names[0]) != full_name_key(names[1]),
                    "Quoted nickname lacks the complete literal candidate-designation name")
            self.check_surname(names[1], candidate)
            primary = party["facts"]
            require(set(primary) == {"name_heading", "role_heading"}
                    and primary["name_heading"] == "Meet " + names[1]
                    and primary["role_heading"] == (
                        f"Candidate for US Congress, {candidate['office_state']} "
                        f"{int(candidate['district'])}"
                        + ("th" if 10 <= int(candidate["district"]) % 100 <= 20 else
                           {1: "st", 2: "nd", 3: "rd"}.get(int(candidate["district"]) % 10, "th"))
                        + " District"),
                    "Primary party declaration does not identify the same literal nickname and seat")
            proof = {
                "method": "explicit_quoted_reference_name_FEC_id_and_authorized_candidate_designation",
                "reference_source": copy.deepcopy(reference), "party_source": copy.deepcopy(party),
                "filing_source_id": form["id"], "literal_names": names,
                "reference_is_not_official_ballot_or_vote_count_evidence": True,
            }
            self.reference_names[cid] = (names[1], proof)

    def support(self, name, candidate):
        ordinary = super().support(name, candidate)
        if ordinary is not None:
            return ordinary
        declared = self.reference_names.get(candidate["candidate_id"])
        if declared and full_name_key(name) == full_name_key(declared[0]):
            return declared[1]
        return None


def successor(previous, value, fec, files):
    require(previous.get("version") == PREDECESSOR_VERSION,
            "Explicit reference names need the complete reviewed predecessor")
    require(pin(encoded(fec))["sha256"] == previous["candidate_identity_successor"]["evidence_sha256"],
            "Explicit reference names need the same complete FEC evidence")
    review, changed = _apply_evidence(
        previous, ReferenceEvidence(fec, value), "reviewed_explicit_reference_and_authorized_filing")
    require(bool(changed), "Explicit reference names resolve no existing identity guard")
    review["explicit_reference_names"] = {
        "contract": CONTRACT, "version": VERSION, "files": copy.deepcopy(files),
        "predecessor_review_sha256": pin(encoded(previous))["sha256"],
        "evidence_sha256": pin(encoded(value))["sha256"], "resolved_identities": changed,
        "only_existing_identity_guards_resolved": True,
        "candidate_counts_parties_and_Other_mass_preserved": True,
        "nickname_dictionary_or_campaign_domain_aliases_used": False,
        "ballot_inventory_counts_and_stage_qualified_by_reference": False,
    }
    return review


def load_optional(root, previous):
    root = Path(root)
    if not (root / REVIEW_PATH).exists():
        return previous
    policy = json.loads((root / REVIEW_PATH).read_bytes())
    files = policy.get("files") or {}
    require(set(files) == set(DATA_PATHS[1:]), "Incomplete explicit reference evidence package")
    bodies = {}
    for name in DATA_PATHS[1:]:
        bodies[name] = (root / name).read_bytes()
        require(pin(bodies[name]) == files[name], "Changed complete explicit reference evidence")
    value = json.loads(gzip.decompress(bodies[DATA_PATHS[1]]))
    fec = json.loads(gzip.decompress((root / FEC_PATHS[1]).read_bytes()))
    result = successor(previous, value, fec, files)
    require(result["explicit_reference_names"] == policy,
            "Explicit reference decisions do not reproduce from complete pinned evidence")
    return result
