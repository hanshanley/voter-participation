"""Pinned candidate-designation evidence, not FEC ballot-presence inference."""

import copy
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from scripts.congressional_candidate_identity import (
    DATA_PATHS as FEC_PATHS, OFFICIAL_DECLARATION_VERSION, Evidence, _apply_evidence,
    full_name_key, load_official_declaration_successor, require, tokens,
)
from scripts.participation_intake.contract import encoded, pin

VERSION = "20261117-declarations-03"
CONTRACT = "participation.congressional_authorized_filing_names.v1"
DATA_PATHS = tuple(
    "data/results-intake/analytical-handoff/filing-name-declarations/" + name
    for name in ("predecessor-review.json.gz", "evidence.json.gz",
                 "independent-native-verification.json"))


def filing_name(value):
    require(isinstance(value, str), "Missing literal filing candidate name")
    parts = value.split(",")
    require(len(parts) >= 2 and parts[0].strip() and parts[1].strip(),
            "Filing needs its literal candidate-designation name")
    return " ".join(part.strip() for part in parts[1:3] + parts[:1] if part.strip())


def campaign_host(value):
    require(isinstance(value, str) and value and not any(char.isspace() for char in value),
            "Missing literal authorized campaign website")
    url = urlsplit(value if "://" in value else "https://" + value)
    require(url.scheme in ("https", "http") and url.hostname and "." in url.hostname
            and url.netloc.casefold() == url.hostname and url.path in ("", "/")
            and not url.query and not url.fragment,
            "Campaign declaration is not an unambiguous website host")
    return url.hostname


class FilingEvidence(Evidence):
    def __init__(self, fec, value):
        super().__init__(fec)
        require(isinstance(value, dict) and set(value) == {"contract", "sources", "filings"}
                and value["contract"] == CONTRACT
                and isinstance(value["sources"], list) and isinstance(value["filings"], list),
                "Unreviewed authorized filing evidence")
        sources = {}
        kinds = {"fec_candidate", "fec_committee", "fec_committee_about", "fec_form1",
                 "nominating_party"}
        for source in value["sources"]:
            require(isinstance(source, dict) and set(source) == {
                "id", "url", "bytes", "sha256", "checked_at", "kind", "facts"},
                "Unexpected filing source fields")
            url = urlsplit(source["url"])
            require(isinstance(source["id"], str) and source["id"]
                    and source["id"] not in sources and url.scheme == "https"
                    and url.hostname and not url.username and not url.password
                    and type(source["bytes"]) is int and source["bytes"] > 0
                    and isinstance(source["sha256"], str)
                    and re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
                    and isinstance(source["checked_at"], str) and source["checked_at"]
                    and source["kind"] in kinds and isinstance(source["facts"], dict),
                    "Unqualified or duplicate filing source receipt")
            sources[source["id"]] = source
        self.filing_names = defaultdict(list)
        domains = defaultdict(set)
        party_records = []
        seen = set()
        for record in value["filings"]:
            require(isinstance(record, dict) and set(record) == {
                "fec_candidate_id", "committee_id", "candidate_source", "committee_source",
                "committee_about_source", "filing_source", "party_source"},
                "Unexpected authorized filing fields")
            candidate = self.candidates.get(record["fec_candidate_id"])
            require(candidate is not None and candidate["office"] == "H"
                    and candidate["election_year"] == "2026",
                    "Filing candidate is outside the reviewed House cycle")
            cid, committee_id = candidate["candidate_id"], record["committee_id"]
            require((cid, committee_id) not in seen, "Duplicate authorized filing identity")
            seen.add((cid, committee_id))
            authorized = [(committee, link) for committee, link in self.authorized[cid]
                          if committee["committee_id"] == committee_id
                          and committee["literal_party"] == candidate["literal_party"]]
            require(len(authorized) == 1, "Filing lacks its unique current authorized FEC linkage")
            committee, linkage = authorized[0]
            chain = []
            for field, kind in (
                    ("candidate_source", "fec_candidate"), ("committee_source", "fec_committee"),
                    ("committee_about_source", "fec_committee_about"), ("filing_source", "fec_form1")):
                source = sources.get(record[field])
                require(source is not None and source["kind"] == kind,
                        "Missing declared candidate-to-filing chain")
                chain.append(source)
            candidate_page, committee_page, about, form = chain
            candidate_url = f"https://www.fec.gov/data/candidate/{cid}/?cycle=2026&tab=about-candidate"
            committee_url = f"https://www.fec.gov/data/committee/{committee_id}/?cycle=2026"
            about_url = committee_url + "&tab=about-committee#section-2"
            require(candidate_page["url"] == candidate_url
                    and candidate_page["facts"] == {"committee_url": committee_url}
                    and committee_page["url"] == committee_url
                    and committee_page["facts"] == {"about_url": about_url}
                    and about["url"] == about_url
                    and about["facts"] == {"filing_url": form["url"]}
                    and re.fullmatch(
                        r"https://docquery\.fec\.gov/pdf/\d+/(\d+)/\1\.pdf", form["url"]),
                    "Filing declaration chain does not match the authorized committee")
            facts = form["facts"]
            require(set(facts) == {
                "committee_id", "committee_id_page", "candidate_name", "state", "district",
                "literal_party", "office", "designation", "physical_page", "section",
                "field_role", "campaign_website"},
                "Unexpected candidate-designation facts")
            require(facts["committee_id"] == committee_id and facts["committee_id_page"] == 1
                    and facts["physical_page"] == 2 and facts["section"] == "5"
                    and facts["field_role"] == "Name of Candidate"
                    and facts["designation"] == committee["designation"]
                    and facts["office"] == "H"
                    and facts["state"] == candidate["office_state"]
                    and facts["district"] == candidate["district"]
                    and facts["literal_party"] == candidate["literal_party"],
                    "Form 1 is not the matching authorized candidate-designation section")
            name = filing_name(facts["candidate_name"])
            self.check_surname(name, candidate)
            proof = {
                "method": "explicit_authorized_Form1_candidate_designation",
                "committee_id": committee_id, "linkage_id": linkage["linkage_id"],
                "source_id": form["id"], "source_url": form["url"],
                "source_pin": {key: form[key] for key in ("bytes", "sha256")},
                "physical_page": 2, "field_role": facts["field_role"],
                "literal_candidate_designation": facts["candidate_name"],
                "declaration_chain_sources": [item["id"] for item in chain],
            }
            self.filing_names[cid].append((name, proof))
            host = campaign_host(facts["campaign_website"])
            domains[host].add(cid)
            if record["party_source"] is not None:
                party = sources.get(record["party_source"])
                require(party is not None and party["kind"] == "nominating_party",
                        "Missing independent party candidate declaration")
                party_records.append((candidate, party, host, proof, name))
        for candidate, source, host, proof, designation_name in party_records:
            facts = source["facts"]
            require(set(facts) == {"anchor_label", "href", "candidate_anchor_labels", "election_year"},
                    "Unexpected party candidate-link facts")
            anchor = re.fullmatch(r"(.+) \| CD(\d{1,2})", facts["anchor_label"])
            require(anchor is not None and int(anchor[2]) == int(candidate["district"])
                    and facts["election_year"] == "2026"
                    and facts["candidate_anchor_labels"] == [facts["anchor_label"]]
                    and domains[host] == {candidate["candidate_id"]}
                    and urlsplit(facts["href"]).scheme == "https"
                    and campaign_host(facts["href"]) == host,
                    "Party anchor is ambiguous or differs from the authorized campaign website")
            self.check_surname(anchor[1], candidate)
            require(Evidence.support(self, designation_name, candidate) is not None,
                    "Party-link filing name lacks its formal FEC candidate anchor")
            self.filing_names[candidate["candidate_id"]].append((anchor[1], {
                **proof, "method": "explicit_party_candidate_link_to_authorized_campaign",
                "party_source_id": source["id"], "party_source_url": source["url"],
                "party_source_pin": {key: source[key] for key in ("bytes", "sha256")},
                "literal_party_anchor": facts["anchor_label"], "campaign_href": facts["href"],
                "literal_authorized_campaign_host": host,
            }))

    @staticmethod
    def check_surname(name, candidate):
        words, family = tokens(name), tokens(candidate["name"].partition(",")[0])
        require(bool(family) and len(words) > len(family) and len(words[0]) > 1
                and words[-len(family):] == family, "Filing declaration lacks the full FEC surname")

    def support(self, name, candidate):
        ordinary = super().support(name, candidate)
        if ordinary is not None:
            return ordinary
        matches = [proof for declared, proof in self.filing_names[candidate["candidate_id"]]
                   if full_name_key(declared) == full_name_key(name)]
        return {"method": "reviewed_authorized_filing_name", "declarations": matches} if matches else None


def successor(previous, value, fec, files):
    require(previous.get("version") == OFFICIAL_DECLARATION_VERSION,
            "Filing names need their complete official-declaration predecessor")
    require(pin(encoded(fec))["sha256"] == previous["candidate_identity_successor"]["evidence_sha256"],
            "Filing names need the same complete FEC evidence")
    review, changed = _apply_evidence(previous, FilingEvidence(fec, value),
                                     "reviewed_authorized_filing_and_FEC_stable_identity")
    require(bool(changed), "Authorized filing declarations resolve no existing identity guard")
    review["version"] = VERSION
    review["authorized_filing_names"] = {
        "contract": CONTRACT, "version": VERSION, "files": copy.deepcopy(files),
        "predecessor_review_sha256": pin(encoded(previous))["sha256"],
        "evidence_sha256": pin(encoded(value))["sha256"], "resolved_identities": changed,
        "candidate_designation_not_treasurer_name": True,
        "nickname_dictionary_or_domain_aliases_used": False,
        "ballot_inventory_counts_and_stage_qualified_by_FEC": False,
        "all_legacy_candidates_and_unmatched_Other_mass_preserved": True,
    }
    return review


def load_successor(root, review):
    require(review.get("version") == VERSION, "Unreviewed authorized filing successor")
    files = (review.get("authorized_filing_names") or {}).get("files") or {}
    require(set(files) == set(DATA_PATHS), "Incomplete authorized filing evidence package")
    bodies = {}
    for name in DATA_PATHS:
        body = (Path(root) / name).read_bytes()
        require(pin(body) == files[name], "Changed complete authorized filing evidence")
        bodies[name] = body
    previous = json.loads(gzip.decompress(bodies[DATA_PATHS[0]]))
    load_official_declaration_successor(root, previous)
    value = json.loads(gzip.decompress(bodies[DATA_PATHS[1]]))
    fec = json.loads(gzip.decompress((Path(root) / FEC_PATHS[1]).read_bytes()))
    require(successor(previous, value, fec, files) == review,
            "Authorized filing decisions do not reproduce from complete pinned evidence")
    return review
