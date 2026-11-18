"""Reviewed whole native frames, independently of incomplete provider categories."""

import copy
import gzip
import json
from pathlib import Path

from scripts import results_native_congress as native
from scripts.congressional_candidate_identity import Evidence, declared_names, tokens
from scripts.participation_intake.contract import encoded, pin


CONTRACT = "participation.native_official_house_review.v1"
VERSION = "20261118-native-01"
ROOT = "data/results-intake/native-official-house/"
REVIEW_PATH = ROOT + "review.json"
FACTS_PATH = ROOT + "accepted-source.json.gz"
DATA_PATHS = (REVIEW_PATH, FACTS_PATH)
PARTIES = {"Democratic": "D", "Republican": "R", "Independent": "I",
           "Libertarian": "L", "Green": "G", "Nonpartisan": None}
MASS_HOLD = "aggregate_other_not_reconciled_to_retained_minor_candidate_mass"
SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def formal_support(name, candidate):
    family, separator, given = candidate["name"].partition(",")
    if not separator:
        return None
    names = tokens(name)
    fec_given = tokens(given)
    suffix = names.pop() if names and names[-1] in SUFFIXES else None
    fec_suffix = fec_given.pop() if fec_given and fec_given[-1] in SUFFIXES else None
    if suffix is not None and fec_suffix is not None and suffix != fec_suffix:
        return None
    fec_given = [word for word in fec_given if word not in ("mr", "mrs", "ms", "dr")]
    surname = tokens(family)
    if not surname or names[-len(surname):] != surname:
        return None
    names = names[:-len(surname)]
    if (not names or not fec_given or names[0] != fec_given[0]
            or len(names) > len(fec_given) or not any(len(word) > 1 for word in names)):
        return None
    if all(left == right or len(left) == 1 and left == right[:1]
           for left, right in zip(names[1:], fec_given[1:])):
        return {"method": "literal_FEC_formal_name_with_nonconflicting_suffix_and_middle_initials",
                "source_name": name, "fec_name": candidate["name"],
                "explicit_suffix": suffix, "fec_suffix": fec_suffix}
    return None


def name_bridge(old, current, race, evidence):
    from scripts.congressional_analytical_bridge import review_names

    before, after = declared_names(old["name"]), declared_names(current["name"])
    if any(review_names(left, right) for left in before for right in after):
        return {"method": "literal_or_explicitly_quoted_name_with_optional_middle_initials"}
    group = current["party_group"]
    if group not in ("D", "R"):
        return None
    frame = race["identity"]
    candidates = evidence.by_frame[(frame["state_code"], frame["seat"].zfill(2),
                                    {"D": "DEM", "R": "REP"}[group])]
    matched = []
    for candidate in candidates:
        supports = []
        for names in (before, after):
            options = [proof for name in names
                       if (proof := evidence.support(name, candidate)
                           or formal_support(name, candidate)) is not None]
            supports.append(options)
        if all(supports):
            matched.append({"fec_candidate": copy.deepcopy(candidate),
                            "legacy_support": supports[0][0], "official_support": supports[1][0],
                            "FEC_establishes_ballot_presence_or_vote_counts": False})
    return matched[0] if len(matched) == 1 else None


def prepare_review(analytical, facts, fec):
    from scripts.congressional_analytical_bridge import FRAME_FIELDS, identity

    data = native.normalized(facts)
    state = analytical["states"]["VA"]
    require(state["frozen_scientific_comparison_qualified"]
            and state["initial_recorded_comparison_qualified"],
            "Native official precedence cannot grant scientific or historical eligibility")
    keys = state["expected_race_ids"]
    require(len(keys) == len(data["races"]) == 11, "Unreviewed native official state inventory")
    evidence = Evidence(fec)
    legacy = {i: row for i, row in enumerate(analytical["legacy_candidates_preserved"])
              if row["state_code"] == "VA" and str(row["year"]) == "2026"}
    require(len(legacy) == 47, "Changed retained complete candidate universe")
    decisions, consumed, old_holds = [], set(), set()
    for key in keys:
        race = analytical["races"][key]
        frame = race["identity"]
        require(identity(frame) == {field: frame[field] for field in FRAME_FIELDS}
                and all(frame[field] == value for field, value in {
                    "chamber": "house", "state_code": "VA", "election_date": "2026-11-03",
                    "election_kind": "regular", "stage": "general",
                    "ranked_choice": False, "round": "not_ranked"}.items()),
                "Changed native official office, election, seat or stage")
        official, = [row for row in data["races"] if row["district"] == race["district"]]
        require(official["seat"] == frame["seat"]
                and all(sum(c["party_group"] == p for c in official["candidates"]) == 1 for p in "DR"),
                "Changed native official major-party coverage")
        candidates = {i: row for i, row in legacy.items() if row["district"] == race["district"]}
        for candidate in official["candidates"]:
            matches = []
            for index, old in candidates.items():
                if old["party"] not in PARTIES or PARTIES[old["party"]] != candidate["literal_party"]:
                    continue
                if candidate["role"] == "generic_write_in":
                    proof = {"method": "literal_unassigned_generic_write_in"} if (
                        tokens(old["name"]) == ["write", "in"] and old["party"] == "Nonpartisan") else None
                else:
                    proof = name_bridge(old, candidate, race, evidence)
                if proof:
                    matches.append((index, old, proof))
            require(len(matches) == 1 and matches[0][0] not in consumed,
                    "Unmatched or ambiguous retained/native candidate identity: " + candidate["name"])
            index, old, proof = matches[0]
            consumed.add(index)
            decisions.append({"race_id": key, "district": race["district"], "legacy_index": index,
                              "legacy_literal_name": old["name"], "legacy_literal_party": old["party"],
                              "official_candidate_id": candidate["candidate_id"],
                              "official_literal_name": candidate["name"],
                              "official_literal_party": candidate["literal_party"],
                              "official_role": candidate["role"], "evidence": proof})
        require(len(candidates) == len(official["candidates"]), "Different complete candidate universes")
        for reason in race["initial_holds"]:
            require(reason in (MASS_HOLD, "unmatched_new_named_candidate")
                    or reason.startswith("unmatched_or_ambiguous_named_major_candidate:"),
                    "Unresolved substantive native official model restriction")
            old_holds.add(key + ":" + reason)
    require(consumed == set(legacy) and old_holds == set(state["holds"]),
            "Native official bridge cannot erase an independent state or candidate hold")
    return {
        "contract": CONTRACT, "version": VERSION,
        "policy": "prefer_complete_reviewed_native_official_frame_without_provider_count_mixing",
        "state_code": "VA", "source_id": native.IDENTITY, "parent_source_id": native.PARENT_ID,
        "source_url": native.native.ROOT_URL, "expected_provider_race_ids": sorted(keys),
        "reviewed_previous_counts": copy.deepcopy(state["reviewed_previous_counts"]),
        "reviewed_initial_source_holds": sorted(old_holds),
        "official_inventory": native.inventory(data), "accepted_source_pin": pin(encoded(facts)),
        "analytical_state_pin": pin(encoded(state)),
        "fec_identity_evidence_pin": pin(encoded(fec)), "candidate_crosswalk": decisions,
        "provider_discrepancies_preserved": True,
        "individual_count_allocation_from_Other_allowed": False,
        "new_scientific_eligibility_allowed": False, "respondent_refitting_allowed": False,
    }


def load_review(root, analytical):
    from scripts.congressional_candidate_identity import DATA_PATHS as FEC_PATHS

    root = Path(root)
    facts = json.loads(gzip.decompress((root / FACTS_PATH).read_bytes()))
    fec = json.loads(gzip.decompress((root / FEC_PATHS[1]).read_bytes()))
    expected = prepare_review(analytical, facts, fec)
    require(json.loads((root / REVIEW_PATH).read_bytes()) == expected,
            "Native official candidate/precedence review does not reproduce")
    expected["accepted_native"] = native.normalized(facts)
    return expected


def current(entry, policy, previous):
    require(entry.get("status") == "reported" and entry.get("advertised", True) is True,
            "native_official_source_not_fresh")
    require((entry.get("source") or {}).get("url") == policy["source_url"],
            "native_official_source_URL_changed")
    data = entry["data"]
    require(native.normalized(data["native_facts"]) == data
            and native.inventory(data) == policy["official_inventory"]
            and entry["source"] == data["native_facts"]["numerical_input_manifest"]["root"],
            "native_official_source_inventory_or_lineage_changed")
    native.compatible_clock(data, previous or policy["accepted_native"],
                            native.native._clock(entry["first_observed_at"].replace("+00:00", "Z")))
    return data


def evaluate(snapshot, seed, handoff):
    review = seed["congressional_analytical_review"]
    policy = review.get("native_official_house")
    if policy is None:
        return handoff
    require(policy.get("contract") == CONTRACT and policy.get("version") == VERSION
            and policy.get("state_code") == "VA", "Unreviewed native official House policy")
    state = policy["state_code"]
    original = review["states"][state]
    require(pin(encoded(original)) == policy["analytical_state_pin"]
            and original["frozen_scientific_comparison_qualified"]
            and original["initial_recorded_comparison_qualified"],
            "Native official scientific or retained state guards changed")
    result = copy.deepcopy(handoff)
    row = result["states"][state]
    models = {r["state_code"]: r for r in seed["scenarios"][
        "original/accepted_ridge_multinomial"]["accepted_result"]["rows"]}
    model = models[state]["reported_comparison"]
    require(model["previous"] == policy["reviewed_previous_counts"],
            "Native official historical endpoint changed")
    previous = seed.get("native_official_house_last_good", {})
    checkpoints = copy.deepcopy(previous)
    entry = snapshot.get("congress", {}).get("official_candidate_evidence", {}).get(policy["source_id"], {})
    data, reasons, counts = None, [], None
    try:
        data = current(entry, policy, previous.get(state))
        counts = {p: sum(c["votes"] for r in data["races"] for c in r["candidates"]
                         if c["party_group"] == p) for p in "DRO"}
        require(counts["D"] > 0 and counts["R"] > 0, "native_official_nonpositive_major_endpoint")
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        reasons.append(str(error))
    active = not reasons
    providers = {}
    for key in policy["expected_provider_race_ids"]:
        entry = snapshot.get("congress", {}).get("races", {}).get(key, {})
        providers[key] = {"status": entry.get("status"),
                          "source_updated_at": (entry.get("data") or {}).get("source_updated_at"),
                          "compatibility_holds": copy.deepcopy(result["races"][key]["holds"]),
                          "candidates": copy.deepcopy((entry.get("data") or {}).get("candidates", []))}
    row.update(
        automatic_update_eligible=active,
        decision="fresh_compatible_conditioning" if active else "frozen_dated_result",
        holds=reasons, counts=counts if active else None,
        changed=bool(active and counts != model["current"]),
        last_good_model_counts=copy.deepcopy(model["current"]),
        current_district_counts={
            r["district"]: {p: sum(c["votes"] for c in r["candidates"] if c["party_group"] == p)
                            for p in "DRO"} for r in data["races"]} if active else None,
        current_stages=["general"] if active else [],
        current_rounds=["not_ranked"] if active else [],
        source_update_labels=[data["source_updated_at"]] if active else [],
        source_urls=[policy["source_url"]], official_direct_source=True,
        official_source_clock_supplied=True, direct_official_review_version=VERSION,
        source_revision_policy=policy["policy"], national_provider_frames=providers,
        accepted_candidate_seed_update_allowed=False,
        provider_fallback_on_official_failure_allowed=False,
        provider_counts_added_to_official_counts=False,
    )
    if active:
        checkpoints[state] = copy.deepcopy(data)
    result["native_official_house_last_good"] = checkpoints
    result["native_official_house_review_version"] = VERSION
    return result
