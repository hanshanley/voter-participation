"""Direct official-source successors for explicitly protected scientific frames."""

import copy
import csv
import gzip
import io
import json
import re
from pathlib import Path

from scripts.participation_intake.contract import encoded, pin


IDENTITY = "HI-official-house-candidates"
URL = "https://elections.hawaii.gov/wp-content/results/2026%20General/summary.txt"
CONTRACT = "participation.official_congressional_candidate_evidence.v1"
REVIEW_CONTRACT = "participation.protected_official_house_review.v1"
VERSION = "20261118-02"
DATA_ROOT = "data/results-intake/protected-official-house"
REVIEW_PATH = DATA_ROOT + "/review.json.gz"
ORIGINAL_PATH = DATA_ROOT + "/hi-summary.txt"
DATA_PATHS = (REVIEW_PATH, ORIGINAL_PATH)
HEADERS = (
    "#Contest ID", "Contest Title", "Contest Seq Nbr", "Contest Type", "Contest Party",
    "Mail Blank Votes", "In-Person Blank Votes", "Mail Over Votes", "In-Person Over Votes",
    "Mail Invalid Votes", "In-Person Invalid Votes", "Registered Voters", "Total Precincts",
    "Counted Precincts", "Candidate ID", "Candidate Name", "Candidate Seq Nbr", "Candidate Party",
    "Mail Votes", "In-Person Votes", "Total Votes",
)
PARTIES = {"D": "Democratic", "R": "Republican", "G": "Green", "N": "Nonpartisan"}
DISTRICTS = {"U.S. Representative, Dist I": ("HI-01", "1"),
             "U.S. Representative, Dist II": ("HI-02", "2")}
INTEGERS = tuple(name for name in HEADERS if name not in (
    "Contest Title", "Contest Type", "Contest Party", "Candidate Name", "Candidate Party"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    require(isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]*", value) is not None,
            "Invalid protected official candidate integer")
    number = int(value)
    require(number <= 2**53 - 1, "Unsafe protected official candidate integer")
    return number


def signature(races):
    return sorted([
        [race["district"], race["native_contest_id"], candidate["candidate_id"],
         candidate["name"], candidate["literal_party"], candidate["native_candidate_sequence"]]
        for race in races for candidate in race["candidates"]
    ])


def parse(body):
    lines = body.decode("utf-8-sig").splitlines()
    require(bool(lines) and lines[0].split("\t") == ["#FormatVersion 1"] + [""] * (len(HEADERS) - 1),
            "Protected official summary format changed")
    reader = csv.DictReader(lines[1:], delimiter="\t")
    require(reader.fieldnames == list(HEADERS), "Protected official summary columns changed")
    selected, races = [], {}
    for row in reader:
        require(None not in row and None not in row.values(), "Malformed official source row")
        title = row["Contest Title"]
        if not title.startswith("U.S. Representative"):
            continue
        require(title in DISTRICTS and row["Contest Type"] == "OF"
                and row["Contest Party"] == row["Candidate Party"] == "",
                "Unreviewed protected House office, stage or native party column")
        numbers = {name: integer(row[name]) for name in INTEGERS}
        require(numbers["Mail Votes"] + numbers["In-Person Votes"] == numbers["Total Votes"],
                "Protected candidate mode counts do not reconcile")
        require(0 <= numbers["Counted Precincts"] <= numbers["Total Precincts"]
                and numbers["Total Precincts"] > 0,
                "Invalid protected reporting coverage")
        require(numbers["#Contest ID"] > 0 and numbers["Candidate ID"] > 0
                and numbers["Candidate Seq Nbr"] > 0 and numbers["Contest Seq Nbr"] > 0,
                "Missing protected native identity")
        name = row["Candidate Name"]
        match = re.fullmatch(r"\(([A-Z])\) .+", name)
        require(match is not None and match[1] in PARTIES,
                "Unreviewed protected candidate or write-in party")
        party = PARTIES[match[1]]
        district, seat = DISTRICTS[title]
        controls = {name: row[name] for name in HEADERS[:14]}
        if district not in races:
            races[district] = {
                "state_code": "HI", "district": district, "seat": seat,
                "native_contest_id": row["#Contest ID"], "native_office_label": title,
                "election_date": "2026-11-03", "stage": "general", "election_kind": "regular",
                "election_identity_basis": "Reviewed official 2026 General directory, not an election-date field in this file.",
                "native_status_literal": None, "source_update_label": None,
                "source_update_timezone": None, "source_updated_at": None,
                "reported_units": numbers["Counted Precincts"], "total_units": numbers["Total Precincts"],
                "partial_units": None, "complete_reporting": numbers["Counted Precincts"] == numbers["Total Precincts"],
                "native_contest_controls": controls, "candidates": [],
            }
        race = races[district]
        require(race["native_contest_controls"] == controls,
                "Protected contest controls differ across candidates")
        race["candidates"].append({
            "candidate_id": row["Candidate ID"], "name": name, "name_literal": name,
            "literal_party": party, "party_literal": row["Candidate Party"],
            "native_candidate_sequence": row["Candidate Seq Nbr"],
            "party_basis": "Explicit native candidate-name prefix; native Candidate Party column is blank.",
            "party_group": match[1] if match[1] in "DR" else "O",
            "votes": numbers["Total Votes"], "votes_literal": row["Total Votes"],
            "role": "named_candidate",
            "native_mode_votes": {"mail": numbers["Mail Votes"], "in_person": numbers["In-Person Votes"]},
        })
        selected.append(row)
    require(set(races) == {"HI-01", "HI-02"}, "Protected statewide district inventory changed")
    for district, race in races.items():
        candidates = race["candidates"]
        require(len(candidates) == (4 if district == "HI-01" else 2)
                and len({row["candidate_id"] for row in candidates}) == len(candidates)
                and len({row["name"] for row in candidates}) == len(candidates)
                and len({row["native_candidate_sequence"] for row in candidates}) == len(candidates),
                "Protected complete candidate inventory missing or duplicated")
        require(sum(row["party_group"] == "D" for row in candidates) == 1
                and sum(row["party_group"] == "R" for row in candidates) == 1,
                "Protected major-party coverage changed")
        race["contest_total"] = sum(row["votes"] for row in candidates)
        race["contest_total_literal"] = None
        race["contest_total_basis"] = "Derived sum of the complete named-candidate rows, not native ballots."
    return {
        "contract": CONTRACT, "election_date": "2026-11-03", "source_updated_at": None,
        "source_clock_supplied": False, "races": [races[key] for key in sorted(races)],
        "native_facts": {"format": lines[0], "headers": list(HEADERS), "rows": selected},
        "participation_observation_qualified": False, "conditional_model_eligible": False,
        "candidate_votes_are_not_ballots_or_turnout": True,
        "provider_other_equivalence_qualified": False,
        "holds": [
            "No native count timestamp or certification status is supplied.",
            "Election and general-stage identity depend on the reviewed official source directory.",
            "Generic write-in or changed candidate inventory requires a separately reviewed successor.",
            "Blank, overvote and invalid-vote controls are retained separately, not candidate Other or turnout.",
            "The latest successful retrieved edition is used; equal reporting counters cannot establish chronological order without a native clock.",
        ],
    }


def from_facts(facts):
    require(isinstance(facts, dict) and set(facts) == {"format", "headers", "rows"}
            and facts["headers"] == list(HEADERS) and isinstance(facts["rows"], list),
            "Changed protected official native facts")
    output = io.StringIO(newline="")
    output.write(facts["format"] + "\n")
    writer = csv.DictWriter(output, fieldnames=HEADERS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(facts["rows"])
    return parse(output.getvalue().encode())


def check_revision(previous, current):
    require(isinstance(current, dict) and from_facts(current.get("native_facts")) == current,
            "Protected official normalization differs from native facts")
    if not previous:
        return
    require(isinstance(previous, dict) and from_facts(previous.get("native_facts")) == previous,
            "Protected previous official normalization differs from native facts")
    require(signature(previous["races"]) == signature(current["races"]),
            "Protected official candidate identity changed")
    old = {row["district"]: row for row in previous["races"]}
    for row in current["races"]:
        prior = old[row["district"]]
        require(row["total_units"] == prior["total_units"]
                and row["reported_units"] >= prior["reported_units"],
                "Protected official reporting coverage regressed or changed")


def collect(collector):
    def guarded(body):
        data = parse(body)
        prior = (collector.prior.get(IDENTITY) or {}).get("data") or {}
        check_revision(prior, data)
        return data
    return collector.capture(IDENTITY, URL, guarded)


def prepare_review(seed, original):
    data = parse(original)
    guard = copy.deepcopy(seed["official_source_guards"]["HI"])
    candidates = sorted([race["district"], row["name"], row["literal_party"], str(row["votes"])]
                        for race in data["races"] for row in race["candidates"])
    require(candidates == guard["candidates"], "Protected native original differs from accepted scientific frame")
    require(guard["state_code"] == "HI" and guard["source_election_scope"] == "general"
            and guard["districts"] == ["HI-01", "HI-02"],
            "Protected original source scope changed")
    return {
        "contract": REVIEW_CONTRACT, "version": VERSION,
        "states": {"HI": {
            "source_id": IDENTITY, "source_url": URL, "accepted_guard": guard,
            "candidate_inventory": signature(data["races"]), "accepted_native": data,
            "original": pin(original), "missing_count_clock_preserved": True,
            "provider_substitution_allowed": False,
        }},
        "source_model_refitting_allowed": False, "new_scientific_eligibility_allowed": False,
    }


def load_review(root, seed=None):
    original = (Path(root) / ORIGINAL_PATH).read_bytes()
    review = json.loads(gzip.decompress((Path(root) / REVIEW_PATH).read_bytes()))
    require(review.get("contract") == REVIEW_CONTRACT and review.get("version") == VERSION
            and set(review.get("states", {})) == {"HI"}, "Unreviewed protected official review")
    if seed is None:
        seed = {"official_source_guards": {"HI": review["states"]["HI"]["accepted_guard"]}}
    require(review == prepare_review(seed, original), "Protected official source review does not reproduce")
    return review


def validate_review(review, seed):
    require(isinstance(review, dict) and review.get("contract") == REVIEW_CONTRACT
            and review.get("version") == VERSION and isinstance(review.get("states"), dict)
            and set(review["states"]) == {"HI"}
            and review.get("source_model_refitting_allowed") is False
            and review.get("new_scientific_eligibility_allowed") is False,
            "Unreviewed protected official successor")
    policy = review["states"]["HI"]
    require(isinstance(policy, dict) and policy.get("source_id") == IDENTITY
            and policy.get("source_url") == URL
            and policy.get("accepted_guard") == seed["official_source_guards"]["HI"]
            and policy.get("missing_count_clock_preserved") is True
            and policy.get("provider_substitution_allowed") is False,
            "Protected original source guard changed")
    data = policy.get("accepted_native")
    check_revision(None, data)
    require(policy.get("candidate_inventory") == signature(data["races"]),
            "Protected original candidate inventory changed")
    require(sorted([race["district"], row["name"], row["literal_party"], str(row["votes"])]
                   for race in data["races"] for row in race["candidates"])
            == policy["accepted_guard"]["candidates"],
            "Protected original counts differ from the accepted scientific frame")


def current(entry, policy, previous=None):
    require(entry.get("status") == "reported", "protected_official_source_not_fresh")
    require((entry.get("source") or {}).get("url") == policy["source_url"],
            "protected_official_source_URL_changed")
    data = entry.get("data")
    check_revision(previous or policy["accepted_native"], data)
    require(signature(data["races"]) == policy["candidate_inventory"],
            "protected_official_candidate_inventory_changed")
    return data


def project_snapshot(snapshot, seed):
    review = seed.get("protected_official_house_review")
    if review is None:
        return snapshot
    validate_review(review, seed)
    result = copy.deepcopy(snapshot)
    for state, policy in review["states"].items():
        require(policy["accepted_guard"] == seed["official_source_guards"][state],
                "Protected original source guard changed")
        entry = snapshot.get("congress", {}).get("official_candidate_evidence", {}).get(policy["source_id"], {})
        try:
            data = current(entry, policy, seed.get("protected_official_house_last_good", {}).get(state))
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        fresh = {(race["district"], row["name"], row["literal_party"]): row
                 for race in data["races"] for row in race["candidates"]}
        accepted = [row for row in seed["accepted_candidates"] if row["state_code"] == state]
        require(set(fresh) == {(row["district"], row["name"], row["party"]) for row in accepted},
                "Protected scientific candidate identities changed")
        projected = []
        for row in accepted:
            item = copy.deepcopy(row)
            item.update(
                votes=str(fresh[(row["district"], row["name"], row["party"])]["votes"]),
                status="reported", source_update_label=None,
                source={**copy.deepcopy(entry["source"]),
                        "automatic_estimates_official_scope": policy["accepted_guard"]["guard_sha256"]},
            )
            projected.append(item)
        result["house_candidates"] = [row for row in result["house_candidates"]
                                      if row["state_code"] != state] + projected
    return result


def evaluate(snapshot, seed, handoff):
    review = seed.get("protected_official_house_review")
    if review is None:
        return handoff
    validate_review(review, seed)
    result = copy.deepcopy(handoff)
    previous = seed.get("protected_official_house_last_good", {})
    models = {row["state_code"]: row for row in seed["scenarios"][
        "original/accepted_ridge_multinomial"]["accepted_result"]["rows"]}
    checkpoints = copy.deepcopy(previous)
    for state, policy in review["states"].items():
        original = seed["congressional_analytical_review"]["states"][state]
        require(policy["accepted_guard"] == seed["official_source_guards"][state]
                and original["frozen_scientific_comparison_qualified"]
                and models[state]["reported_comparison"]["previous"] == original["reviewed_previous_counts"],
                "Protected original scientific qualification or historical endpoint changed")
        entry = snapshot.get("congress", {}).get("official_candidate_evidence", {}).get(policy["source_id"], {})
        data, reasons = entry.get("data"), []
        counts = None
        try:
            data = current(entry, policy, previous.get(state))
            counts = {party: sum(row["votes"] for race in data["races"]
                                 for row in race["candidates"] if row["party_group"] == party)
                      for party in "DRO"}
            require(counts["D"] > 0 and counts["R"] > 0, "protected_official_nonpositive_major_endpoint")
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            reasons.append(str(error))
        active = not reasons
        old = models[state]["reported_comparison"]["current"]
        result["states"][state].update(
            automatic_update_eligible=active,
            decision="fresh_compatible_conditioning" if active else "frozen_dated_result",
            holds=reasons, counts=counts if active else None,
            changed=bool(active and counts != old), last_good_model_counts=copy.deepcopy(old),
            current_district_counts={
                race["district"]: {party: sum(row["votes"] for row in race["candidates"]
                                             if row["party_group"] == party) for party in "DRO"}
                for race in data["races"]} if active else None,
            current_stages=["general"] if active else [], current_rounds=["not_ranked"] if active else [],
            source_update_labels=[], source_urls=[policy["source_url"]],
            official_direct_source=True, official_source_clock_supplied=False,
            protected_official_guard_sha256=policy["accepted_guard"]["guard_sha256"],
            national_provider_replacement_allowed=False,
            chronological_count_order_qualified=False,
            source_revision_policy="Latest successfully retrieved reviewed official edition; reporting progress may not regress. No native clock is invented.",
        )
        if active:
            checkpoints[state] = copy.deepcopy(data)
    result["protected_official_last_good"] = checkpoints
    result["protected_official_review_version"] = review["version"]
    return result
