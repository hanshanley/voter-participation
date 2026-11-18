"""Recondition existing Senate scenarios using complete official candidate categories."""

import copy
import gzip
import json
from pathlib import Path

from scripts import calibrated_swing
from scripts.congressional_analytical_bridge import identity, name_tokens, review_names
from scripts.congressional_complete_categories import clock, parse, signature, URL
from scripts.participation_intake.contract import encoded, pin
from scripts.results_congress import check_revision, compressed, normalize, require
from scripts.results_official_congress import SENATE_IDENTITY
from scripts.senate_legacy_bridge import load_review as load_legacy_review


VERSION = "20261118-01"
CONTRACT = "participation.senate_complete_category_scenarios.v1"
REVIEW_CONTRACT = "participation.senate_complete_category_review.v1"
DATA_ROOT = "data/results-intake/senate-complete-categories/"
REVIEW_PATH = DATA_ROOT + "review.json.gz"
EVIDENCE_PATH = DATA_ROOT + "evidence.json.gz"
VERIFICATION_PATH = DATA_ROOT + "independent-native-verification.json"
DATA_PATHS = (REVIEW_PATH, EVIDENCE_PATH, VERIFICATION_PATH)
MODEL_PATH = "senate/legacy-complete-results.json.gz"
SCOPE = "complete_reported_DRO_candidate_universe_not_ballots_or_turnout"


def _official(entry):
    require(isinstance(entry, dict) and entry.get("status") == "reported",
            "Complete official candidate evidence is unavailable or retained")
    source, data = entry.get("source"), entry.get("data")
    require(isinstance(source, dict) and source.get("url") == URL
            and type(source.get("bytes")) is int and source["bytes"] > 0
            and isinstance(source.get("sha256"), str) and len(source["sha256"]) == 64
            and all(value in "0123456789abcdef" for value in source["sha256"]),
            "Complete official Senate source identity or byte pin differs")
    require(isinstance(data, dict) and data == parse(encoded(data["native_facts"]), "senate"),
            "Complete official Senate facts do not reproduce")
    require(len(data["races"]) == 1, "Ambiguous official Senate contest")
    return data["races"][0], data["source_updated_at"]


def _reconcile(data, official, legacy):
    from scripts.automatic_estimates import _party_group

    named = [row for row in data["candidates"] if row["role"] == "named_candidate"]
    aggregate = [row for row in data["candidates"] if row["role"] == "provider_aggregate_other"]
    require(len(aggregate) == 1 and aggregate[0]["party_group"] == "O"
            and len(named) + 1 == len(data["candidates"])
            and sorted(row["party_group"] for row in named) == ["D", "R"],
            "Unreviewed complete provider Senate candidate categories")
    provider_ids, legacy_ids, omitted = set(), set(), []
    for candidate in official["candidates"]:
        old = [row for row in legacy
               if _party_group(row["party"]) == candidate["party_group"]
               and (name_tokens(row["name"]) == ["write", "in"]
                    if candidate["role"] == "generic_write_in"
                    else review_names(row["name"], candidate["name"]))]
        require(len(old) == 1 and old[0]["candidate_id"] not in legacy_ids,
                "Complete official minor/write-in universe differs from the original Senate model")
        legacy_ids.add(old[0]["candidate_id"])
        matched = [row for row in named
                   if candidate["role"] == "named_candidate"
                   and row["party_group"] == candidate["party_group"]
                   and review_names(row["name"], candidate["name"])]
        if matched:
            require(len(matched) == 1 and matched[0]["candidate_id"] not in provider_ids
                    and matched[0]["votes"] == candidate["votes"],
                    "Official and provider named Senate counts or identities differ")
            provider_ids.add(matched[0]["candidate_id"])
        else:
            require(candidate["party_group"] == "O",
                    "Official major Senate candidate is absent from the provider")
            omitted.append(candidate)
    require(legacy_ids == {row["candidate_id"] for row in legacy}
            and len(legacy_ids) == len(legacy)
            and provider_ids == {row["candidate_id"] for row in named}
            and sum(row["votes"] for row in omitted) == aggregate[0]["votes"],
            "Complete Senate candidate inventory or provider Other mass differs")
    return {
        "official_inventory": signature(official),
        "provider_inventory": [
            {key: row[key] for key in ("candidate_id", "name", "literal_party", "party_group", "role")}
            for row in data["candidates"]],
        "omitted_official_candidate_ids": sorted(row["candidate_id"] for row in omitted),
        "retained_legacy_candidate_ids": sorted(legacy_ids),
        "provider_aggregate_id": aggregate[0]["candidate_id"],
        "all_provider_category_counts_reconciled": True,
        "individual_votes_allocated_from_Other": False,
        "provider_and_official_counts_added": False,
    }


def successor(previous, evidence):
    require(evidence.get("contract") == REVIEW_CONTRACT
            and evidence.get("version") == VERSION
            and set(evidence.get("official_entries", {})) == {SENATE_IDENTITY},
            "Unreviewed complete Senate evidence inventory")
    official, source_clock = _official(evidence["official_entries"][SENATE_IDENTITY])
    context = previous["candidate_identity_successor"]["context"]
    decisions = {}
    for key, old in sorted(previous["models"].items()):
        decision = {
            "state_code": old["state_code"], "enabled": False,
            "holds": ["No complete compatible official candidate inventory is registered for this model."],
            "legacy_comparison": copy.deepcopy(old["legacy_comparison"]),
            "legacy_native_control": copy.deepcopy(old["legacy_native_control"]),
        }
        decisions[key] = decision
        if old["state_code"] != official["state_code"]:
            continue
        options = [row for row in context["comparisons"]
                   if row["chamber"] == "senate" and row["state_code"] == old["state_code"]
                   and row["seat"] == official["seat"] and row["qualified_comparison"]
                   and all(row["previous"].get(party) == old["legacy_comparison"]["previous"].get(party)
                           for party in "DRO")]
        require(len(options) == 1, "Complete Senate scenario needs its original same-seat historical endpoints")
        selected = options[0]
        entry = context["races"][selected["id"]]
        data, control = entry["data"], old["legacy_native_control"]
        frame = identity(data)
        require(all(frame.get(name) == value for name, value in {
            "chamber": "senate", "state_code": "RI", "seat": "2",
            "stage": "general", "election_kind": "regular", "ranked_choice": False,
            "round": "not_ranked", "election_date": "2026-11-03"}.items())
            and data == normalize(data["native_facts"], "senate")
            and control["year"] == 2026 and control["office"] == "senate"
            and control["source_election_scope"] == "General",
            "Complete Senate office, seat, election, stage or native frame differs")
        reconciliation = _reconcile(data, official, control["full_candidate_rows"])
        decision.update(
            enabled=True, holds=[], identity=frame, checkpoint=copy.deepcopy(entry),
            official_checkpoint=copy.deepcopy(evidence["official_entries"][SENATE_IDENTITY]),
            accepted_official_clock=source_clock, reconciliation=reconciliation,
            previous={party: selected["previous"][party] for party in "DRO"},
            previous_candidates=copy.deepcopy(selected["previous_candidates"]),
            baseline=copy.deepcopy(selected["baseline"]),
            conditioning_scope=SCOPE,
        )
    require(any(row["enabled"] for row in decisions.values()), "No complete Senate model bridge was qualified")
    return {
        "contract": REVIEW_CONTRACT, "version": VERSION,
        "predecessor_review_pin": pin(encoded(previous)),
        "historical_senate_pin": copy.deepcopy(previous["historical_senate_pin"]),
        "evidence_pin": pin(encoded(evidence)), "models": decisions,
        "prior": copy.deepcopy(previous["prior"]),
        "senate_respondent_model": False, "source_models_refitted": False,
        "current_candidate_counts_are_not_participation": True,
    }


def load_review(root):
    root = Path(root)
    previous = load_legacy_review(root)
    evidence = json.loads(gzip.decompress((root / EVIDENCE_PATH).read_bytes()))
    review = json.loads(gzip.decompress((root / REVIEW_PATH).read_bytes()))
    require(review == successor(previous, evidence),
            "Complete Senate decisions do not reproduce from their original evidence")
    verification = json.loads((root / VERIFICATION_PATH).read_bytes())
    require(verification.get("passed") is True
            and verification.get("evidence_pin") == pin(encoded(evidence))
            and verification.get("complete_native_candidates") == 4,
            "Independent complete Senate native verification is missing or changed")
    return review


def _checkpoint(entry, official_entry, decision, saved):
    require(isinstance(entry, dict) and entry.get("status") == "reported"
            and entry.get("advertised") is True and entry.get("freshness") == "source_verified",
            "National Senate source is unavailable or retained")
    data, source = entry.get("data"), entry.get("source")
    require(isinstance(data, dict) and data == normalize(data["native_facts"], "senate")
            and identity(data) == decision["identity"], "Senate native identity, seat or stage changed")
    expected_source = decision["checkpoint"]["source"]
    require(isinstance(source, dict) and source.get("url") == expected_source["url"]
            and type(source.get("bytes")) is int and source["bytes"] > 0
            and isinstance(source.get("sha256"), str) and len(source["sha256"]) == 64
            and all(value in "0123456789abcdef" for value in source["sha256"]),
            "National Senate source URL or pin changed")
    check_revision(saved["native"] if saved else decision["checkpoint"]["data"], data)
    official, official_clock = _official(official_entry)
    before = saved["official_evidence"] if saved else decision["official_checkpoint"]
    _, previous_clock = _official(before)
    require(clock(official_clock) >= clock(previous_clock), "Complete official Senate clock regressed")
    require(official_clock != previous_clock or official_entry["data"] == before["data"],
            "Complete official Senate facts changed without a new native clock")
    require(all(type(row["votes"]) is int and row["votes"] >= 0 for row in data["candidates"])
            and all(row["votes"] > 0 for row in data["candidates"] if row["party_group"] in "DR"),
            "Positive reported Senate major-party counts are required")
    require(_reconcile(data, official, decision["legacy_native_control"]["full_candidate_rows"])
            == decision["reconciliation"], "Reviewed complete Senate inventory changed")
    return data, source


def _estimate(data, source, decision, prior):
    before = decision["previous"]
    current = {row["party_group"]: row["votes"] for row in data["candidates"]}
    comparison = {
        key: copy.deepcopy(decision["legacy_comparison"][key])
        for key in ("status", "baseline_year", "baseline_office", "baseline_stage", "scope")}
    comparison.update(
        previous=copy.deepcopy(before), current=current,
        previous_margin_pp=calibrated_swing.margin(before["D"], before["R"]),
        current_margin_pp=calibrated_swing.margin(current["D"], current["R"]),
        current_native_clock=data["source_updated_at"], current_source_url=source["url"],
        current_stage=data["stage"], current_round=data["native_round"],
        current_percent_reporting=None, current_snapshot=None, current_source_scope=SCOPE,
        qualification="Complete official named/minor/write-in inventory matches the original Senate "
        "model and every national provider category; original same-seat historical endpoints retained.")
    comparison["reported_change_pp"] = comparison["current_margin_pp"] - comparison["previous_margin_pp"]
    model = calibrated_swing.estimate({
        "id": decision["legacy_native_control"]["id"], "office": "senate",
        "state_code": decision["state_code"], "reported_comparison": comparison}, prior)
    model.update(
        separately_versioned_complete_extension=True, current_unreported_other_unknown=False,
        complete_candidate_universe_qualified=True, senate_respondent_model=False,
        source_models_refitted=False,
        limitation="Transported President/House synthetic associations, not a Senate respondent fit, "
        "total turnout, measured staying home or identified individual behavior.")
    return model


def build(snapshot, seed):
    review = seed["senate_complete_review"]
    require(review.get("contract") == REVIEW_CONTRACT and review.get("version") == VERSION,
            "Unreviewed complete Senate scenario input")
    require(pin(encoded(seed["congressional_analytical_review"]["historical_senate"]))
            == review["historical_senate_pin"], "Complete Senate historical evidence changed")
    previous = seed.get("senate_complete_last_good", {})
    require(isinstance(previous, dict) and set(previous) <= {
        key for key, row in review["models"].items() if row["enabled"]},
        "Unreviewed last-good complete Senate model")
    congress = snapshot.get("congress") or {}
    official_entry = congress.get("official_candidate_evidence", {}).get(SENATE_IDENTITY)
    checkpoints, rows = copy.deepcopy(previous), []
    for key, decision in sorted(review["models"].items()):
        saved = previous.get(key)
        if saved:
            require(saved.get("review_version") == VERSION
                    and saved.get("model_pin") == pin(encoded(saved.get("model"))),
                    "Changed last-good complete Senate scenario")
            data, source = _checkpoint({
                "status": "reported", "advertised": True, "freshness": "source_verified",
                "data": saved["native"], "source": saved["source"]},
                saved["official_evidence"], decision, None)
            require(saved["model"] == _estimate(data, source, decision, review["prior"]),
                    "Last-good complete Senate model differs from its original evidence")
        row = {
            "id": key, "office": "senate", "state_code": decision["state_code"],
            "status": "held_no_compatible_complete_bridge", "holds": copy.deepcopy(decision["holds"]),
            "legacy_source_clock": decision["legacy_comparison"].get("current_native_clock"),
            "model_source_clock": saved["native"]["source_updated_at"] if saved else None,
            "official_evidence_clock": saved["official_evidence"]["data"]["source_updated_at"] if saved else None,
            "official_source": copy.deepcopy(saved["official_evidence"]["source"]) if saved else None,
            "current_identity": copy.deepcopy(decision.get("identity")),
            "model": copy.deepcopy(saved["model"]) if saved else None,
            "conditioning_scope": decision.get("conditioning_scope"),
            "strict_legacy_model_refreshed": False,
        }
        rows.append(row)
        if not decision["enabled"]:
            continue
        try:
            entry = congress.get("races", {}).get(decision["identity"]["id"])
            data, source = _checkpoint(entry, official_entry, decision, saved)
            model = _estimate(data, source, decision, review["prior"])
            status = ("fresh_unchanged_complete_scenario" if saved
                      and saved["native"] == data and saved["source"] == source
                      and saved["official_evidence"] == official_entry else "fresh_complete_scenario")
            checkpoints[key] = {
                "review_version": VERSION, "native": copy.deepcopy(data), "source": copy.deepcopy(source),
                "official_evidence": copy.deepcopy(official_entry),
                "model": model, "model_pin": pin(encoded(model))}
            row.update(status=status, holds=[], model=model, model_source_clock=data["source_updated_at"],
                       official_evidence_clock=official_entry["data"]["source_updated_at"],
                       official_source=copy.deepcopy(official_entry["source"]),
                       strict_legacy_model_refreshed=True)
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            row.update(status="held_retain_last_good_complete_scenario" if saved
                       else "held_no_compatible_complete_bridge", holds=[str(error)])
    fresh = [row for row in rows if row["status"].startswith("fresh_")]
    return {"last_good": checkpoints, "result": {
        "contract": CONTRACT, "review_version": VERSION, "rows": rows,
        "summary": {
            "legacy_fitted_decisions": len(rows), "fresh_complete_scenarios": len(fresh),
            "retained_complete_scenarios": sum(
                row["status"] == "held_retain_last_good_complete_scenario" for row in rows),
            "fresh_sensitivity_fits": sum(len(row["model"]["complete_scenarios"]) for row in fresh),
            "strict_legacy_models_refreshed": len(fresh), "empirical_senate_models_added": 0},
        "source_models_refitted": False, "measured_staying_home": None,
        "confidence_intervals": None, "local_allocation": False,
    }}


def exports(result):
    science = calibrated_swing.result_files({
        "rows": [row["model"] for row in result["rows"] if row["model"] is not None]})
    return {
        "senate/legacy-complete-decisions.csv": calibrated_swing.csv_bytes([
            {key: value for key, value in row.items() if key != "model"} for row in result["rows"]]),
        **{"senate/legacy-complete-" + name + (".gz" if name.endswith(".json") else ""):
           compressed(json.loads(body)) if name.endswith(".json") else body
           for name, body in science.items()},
    }
