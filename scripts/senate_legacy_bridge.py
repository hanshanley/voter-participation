"""Refresh reviewed D/R-only Senate scenarios, never Senate respondent fits."""

import copy
import gzip
import io
import json
from pathlib import Path
import unicodedata
import zipfile

from scripts import calibrated_swing
from scripts.congressional_analytical_bridge import identity, review_names
from scripts.congressional_candidate_identity import DATA_PATHS as FEC_PATHS, Evidence
from scripts.participation_intake.contract import encoded, pin
from scripts.results_congress import check_revision, compressed, normalize, require


PREVIOUS_VERSION = "20261117-01"
VERSION = "20261117-02"
CONTRACT = "participation.senate_legacy_partial_scenarios.v1"
PREVIOUS_REVIEW_PATH = "data/results-intake/senate-legacy/review.json"
REVIEW_PATH = "data/results-intake/senate-legacy/review-02.json"
SCIENCE_PATH = "data/results-intake/senate-legacy/complete-predecessor.zip"
DATA_PATHS = (PREVIOUS_REVIEW_PATH, REVIEW_PATH, SCIENCE_PATH, *FEC_PATHS)
MODEL_PATH = "senate/legacy-partial-results.json.gz"
SCIENCE_PIN = {
    "bytes": 14943668,
    "sha256": "2377ea253d33b88af3146bad4e2a52c9936d97b178c00a4fa0e3be022aadeae1",
}
IDENTITY_HOLD = "Reported full candidate identity/universe differs; no minor/write-in mass discarded"


def _latin_name(value):
    normalized = "".join(character for character in unicodedata.normalize("NFD", value.casefold())
                         if not unicodedata.combining(character))
    return normalized if all(not character.isalpha() or character.isascii()
                             for character in normalized) else None


def fec_identity(old, current, frame, evidence):
    group = {"Democratic": "D", "Republican": "R"}.get(old["party"])
    if (group not in ("D", "R") or current["party_group"] != group
            or current["role"] != "named_candidate"
            or frame["chamber"] != "senate" or frame["election_date"] != "2026-11-03"
            or frame["election_kind"] != "regular" or frame["stage"] != "general"
            or frame["ranked_choice"] is not False):
        return None
    names = [_latin_name(row["name"]) for row in (old, current)]
    if any(name is None for name in names):
        return None
    candidates = []
    for candidate in evidence.candidates.values():
        if (candidate["office"] == "S" and candidate["election_year"] == "2026"
                and candidate["office_state"] == frame["state_code"]
                and candidate["district"] == "00"
                and candidate["literal_party"] == {"D": "DEM", "R": "REP"}[group]):
            folded = _latin_name(candidate["name"])
            if folded is not None:
                candidates.append((candidate, {**candidate, "name": folded}))
    matches = [
        [(candidate, proof) for candidate, folded in candidates
         if (proof := evidence.support(name, folded)) is not None]
        for name in names]
    if len(matches[0]) != 1 or len(matches[1]) != 1:
        return None
    before, after = matches[0][0], matches[1][0]
    if before[0]["candidate_id"] != after[0]["candidate_id"]:
        return None
    return {
        "fec_candidate": copy.deepcopy(before[0]),
        "legacy_literal_name": old["name"], "provider_literal_name": current["name"],
        "legacy_support": before[1], "provider_support": after[1],
        "name_normalization": "Unicode NFD; remove combining diacritics; casefold; no nickname inference",
        "ballot_inventory_counts_seat_or_stage_qualified_by_FEC": False,
    }


def fec_successor(previous, controls, context, evidence, files):
    require(previous["contract"] == CONTRACT and previous["version"] == PREVIOUS_VERSION,
            "Senate identity review needs its complete frozen predecessor")
    review, resolved = copy.deepcopy(previous), []
    for key, decision in review["models"].items():
        if decision["enabled"] or decision["holds"] != [IDENTITY_HOLD]:
            continue
        control = controls[key]
        options = [row for row in context["comparisons"]
                   if row["chamber"] == "senate" and row["state_code"] == control["state_code"]
                   and row["qualified_comparison"]
                   and all(row["previous"].get(party) ==
                           context["legacy_comparisons"][key]["previous"].get(party)
                           for party in "DRO")]
        if len(options) != 1:
            continue
        selected = options[0]
        entry = context["races"].get(selected["id"])
        if not entry or not isinstance(entry.get("data"), dict):
            continue
        data, reported = entry["data"], control["full_candidate_rows"]
        if (len(reported) != len(data["candidates"]) or len(reported) != 2
                or data["id"] != selected["id"]
                or sorted(row["party_group"] for row in data["candidates"]) != ["D", "R"]
                or any(row["role"] != "named_candidate" for row in data["candidates"])
                or control["year"] != 2026 or control["office"] != "senate"
                or control["source_election_scope"] != "General"):
            continue
        frame, proofs, matched = identity(data), [], []
        for candidate in data["candidates"]:
            choices = []
            for old in reported:
                if {"Democratic": "D", "Republican": "R"}.get(old["party"]) != candidate["party_group"]:
                    continue
                proof = None if review_names(old["name"], candidate["name"]) else fec_identity(
                    old, candidate, frame, evidence)
                if proof is not None or review_names(old["name"], candidate["name"]):
                    choices.append((old, proof))
            if len(choices) != 1:
                break
            matched.append(choices[0][0]["candidate_id"])
            if choices[0][1] is not None:
                proofs.append({"model_id": key, "provider_candidate_id": candidate["candidate_id"],
                               **choices[0][1]})
        if len(set(matched)) != len(reported) or not proofs:
            continue
        decision.update(
            enabled=True, holds=[], unmatched_legacy_candidates=[], unmatched_current_candidates=[],
            identity=frame, checkpoint=copy.deepcopy(entry),
            previous={party: selected["previous"][party] for party in "DRO"},
            previous_candidates=copy.deepcopy(selected["previous_candidates"]),
            baseline=copy.deepcopy(selected["baseline"]),
            conditioning_scope="reported_DR_only_current_O_unknown",
            candidate_identity_evidence=proofs)
        resolved.extend(proofs)
    review["version"] = VERSION
    review["candidate_identity_successor"] = {
        "contract": "participation.senate_fec_identity.v1",
        "predecessor_review_pin": pin(encoded(previous)), "files": copy.deepcopy(files),
        "context": copy.deepcopy(context), "resolved_identities": resolved,
        "previously_enabled_models": sorted(key for key, row in previous["models"].items() if row["enabled"]),
        "FEC_is_not_a_complete_ballot_or_seat_or_stage_inventory": True,
    }
    return review


def load_review(root):
    root = Path(root)
    review = json.loads((root / REVIEW_PATH).read_bytes())
    body = (root / SCIENCE_PATH).read_bytes()
    require(pin(body) == SCIENCE_PIN, "Changed complete Senate scientific predecessor")
    require(review.get("contract") == CONTRACT and review.get("version") == VERSION,
            "Unreviewed Senate partial-scenario version")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        original = json.loads(archive.read("results/complete-result.json"))
        with zipfile.ZipFile(io.BytesIO(archive.read("inputs/complete-prior-science.zip"))) as prior_zip:
            prior = json.loads(prior_zip.read("complete-scenarios.json"))
        with zipfile.ZipFile(io.BytesIO(archive.read("inputs/complete-observed-science.zip"))) as observed:
            controls = json.loads(observed.read(
                "data/return-attribution/20261110-02/inputs/model-inputs.json"))["return_controls"]
    models = {row["id"]: row for row in original["rows"]
              if row["office"] == "senate" and row["point"] is not None}
    require(len(models) == 26 and set(models) == set(review["models"]),
            "Legacy Senate fit inventory changed")
    require(prior["source_units_are_people"] is False
            and prior["private_joint_cells_reconstructed"] is False,
            "Only existing disclosed synthetic priors are supported")
    source_controls = {row["id"]: row for row in controls}
    previous = json.loads((root / PREVIOUS_REVIEW_PATH).read_bytes())
    successor = review.get("candidate_identity_successor") or {}
    require(successor.get("context", {}).get("legacy_comparisons") == {
        key: row["reported_comparison"] for key, row in models.items()},
        "Changed original Senate historical comparison evidence")
    require(set(successor.get("files", {})) == set(FEC_PATHS),
            "Incomplete Senate FEC identity evidence")
    for path in FEC_PATHS:
        require(pin((root / path).read_bytes()) == successor["files"][path],
                "Changed complete Senate FEC identity evidence")
    evidence = Evidence(json.loads(gzip.decompress((root / FEC_PATHS[1]).read_bytes())))
    require(review == fec_successor(
        previous, source_controls, successor["context"], evidence, successor["files"]),
        "Senate identity decisions do not reproduce from complete pinned evidence")
    approved = []
    for key, decision in review["models"].items():
        old = models[key]
        decision["legacy_comparison"] = copy.deepcopy(old["reported_comparison"])
        decision["state_code"] = old["state_code"]
        decision["legacy_native_control"] = source_controls[key]
        if decision["enabled"]:
            approved.append(key)
            data = decision["checkpoint"]["data"]
            require(not decision["holds"] and data == normalize(data["native_facts"], "senate"),
                    "Unqualified reviewed Senate checkpoint")
            require(identity(data) == decision["identity"], "Reviewed Senate seat/stage changed")
            reported = source_controls[key]["full_candidate_rows"]
            require(len(reported) == len(data["candidates"]), "Different reported candidate universes")
            for candidate in data["candidates"]:
                matches = [row for row in reported if (
                           review_names(row["name"], candidate["name"])
                           or fec_identity(row, candidate, decision["identity"], evidence) is not None)
                           and {"Democratic": "D", "Republican": "R"}.get(row["party"])
                           == candidate["party_group"]]
                require(len(matches) == 1, "Unreviewed cross-provider Senate candidate identity")
            require(decision["previous"] == old["reported_comparison"]["previous"],
                    "Different historical candidate endpoints")
            require(decision["conditioning_scope"] == "reported_DR_only_current_O_unknown",
                    "Unreported Other is not an observed zero")
    require(set(approved) == {
        key for key, row in previous["models"].items() if row["enabled"]
    } | {row["model_id"] for row in successor["resolved_identities"]},
        "Unreviewed Senate partial-scenario extension")
    states = {row["state_code"] for row in models.values()}
    factor = prior["persistence_calibration"]["selected_factor"]
    factors = [value for value in prior["effective_persistence_factors"]
               if any(abs(value - factor * scale) < 1e-10
                      for scale in calibrated_swing.PERSISTENCE_SCALES)]
    review["prior"] = {
        "persistence_calibration": {"selected_factor": factor},
        "effective_persistence_factors": factors,
        "coupling_assumptions": {
            key: value for key, value in prior["coupling_assumptions"].items()
            if key.split("|")[0] in states and float(key.split("|")[1]) in factors},
    }
    return review


def _checkpoint(entry, decision, prior):
    require(isinstance(entry, dict) and entry.get("status") == "reported"
            and entry.get("advertised") is True and entry.get("freshness") == "source_verified",
            "Source unavailable or retained; keep the model's own last-good clock")
    data = entry.get("data")
    require(isinstance(data, dict) and isinstance(data.get("native_facts"), dict),
            "Missing native Senate result facts")
    require(data == normalize(data["native_facts"], "senate"), "Native/normalized Senate facts differ")
    require(identity(data) == decision["identity"], "Senate office, seat, stage or round changed")
    source = entry.get("source")
    require(isinstance(source, dict) and source.get("url") == decision["checkpoint"]["source"]["url"]
            and type(source.get("bytes")) is int and source["bytes"] > 0
            and isinstance(source.get("sha256"), str) and len(source["sha256"]) == 64
            and all(c in "0123456789abcdef" for c in source["sha256"]),
            "Senate source identity or byte pin differs")
    baseline = prior["native"] if prior else decision["checkpoint"]["data"]
    check_revision(baseline, data)
    expected = decision["checkpoint"]["data"]["candidates"]
    require([{k: row[k] for k in ("candidate_id", "name", "literal_party", "party_group", "role")}
             for row in data["candidates"]] ==
            [{k: row[k] for k in ("candidate_id", "name", "literal_party", "party_group", "role")}
             for row in expected], "Reported candidate inventory or identity changed")
    require(len(data["candidates"]) == 2
            and sorted(row["party_group"] for row in data["candidates"]) == ["D", "R"]
            and all(type(row["votes"]) is int and row["votes"] > 0 for row in data["candidates"]),
            "A positive reported D/R pair is required; zero is retained in returns, not fitted")
    return data, source


def _estimate(data, source, decision, prior):
    comparison = {
        name: copy.deepcopy(decision["legacy_comparison"][name])
        for name in ("status", "baseline_year", "baseline_office", "baseline_stage", "scope")
    }
    current = {candidate["party_group"]: candidate["votes"] for candidate in data["candidates"]}
    before = decision["previous"]
    comparison.update(
        previous=copy.deepcopy(before), current=current,
        previous_margin_pp=calibrated_swing.margin(before["D"], before["R"]),
        current_margin_pp=calibrated_swing.margin(current["D"], current["R"]),
        current_native_clock=data["source_updated_at"], current_source_url=source["url"],
        current_stage=data["stage"], current_round=data["native_round"],
        current_percent_reporting=None, current_snapshot=None,
        current_source_scope="reported_DR_only_not_complete_candidate_or_ballot_universe",
        qualification="Reviewed same-seat/stage historical endpoints and complete reported D/R "
        "candidate identities. Current unreported Other/write-ins remain unknown, not observed zero.")
    comparison["reported_change_pp"] = comparison["current_margin_pp"] - comparison["previous_margin_pp"]
    model = calibrated_swing.estimate({
        "id": decision["legacy_native_control"]["id"], "office": "senate",
        "state_code": decision["state_code"], "reported_comparison": comparison}, prior)
    model.update(
        separately_versioned_partial_extension=True,
        current_unreported_other_unknown=True, complete_candidate_universe_qualified=False,
        senate_respondent_model=False, source_models_refitted=False,
        limitation="Transported President/House synthetic prior; current Other/write-ins "
        "are unknown and prior-assumed. Not total turnout or identified behavior.")
    return model


def build(snapshot, seed):
    review = seed["senate_legacy_review"]
    require(review["contract"] == CONTRACT and review["version"] == VERSION,
            "Unreviewed Senate partial-scenario input")
    require(pin(encoded(seed["congressional_analytical_review"]["historical_senate"])) ==
            review["historical_senate_pin"], "Reviewed Senate historical seat/stage evidence changed")
    previous = seed.get("senate_legacy_last_good", {})
    require(isinstance(previous, dict) and set(previous) <= {
        key for key, row in review["models"].items() if row["enabled"]},
        "Unknown last-good Senate model identity")
    checkpoints, rows = copy.deepcopy(previous), []
    races = (snapshot.get("congress") or {}).get("races", {})
    for key, decision in sorted(review["models"].items()):
        saved = previous.get(key)
        if saved is not None:
            allowed_versions = {VERSION}
            if key in review["candidate_identity_successor"]["previously_enabled_models"]:
                allowed_versions.add(PREVIOUS_VERSION)
            require(saved.get("review_version") in allowed_versions
                    and saved.get("model_pin") == pin(encoded(saved.get("model")))
                    and saved["model"]["id"] == key,
                    "Changed last-good Senate model")
            native, source = _checkpoint({
                "status": "reported", "advertised": True, "freshness": "source_verified",
                "data": saved["native"], "source": saved["source"]}, decision, None)
            require(saved["model"] == _estimate(native, source, decision, review["prior"]),
                    "Last-good Senate model differs from its reviewed native evidence")
        row = {
            "id": key, "state_code": decision["state_code"], "office": "senate",
            "status": "held_no_compatible_partial_bridge", "holds": copy.deepcopy(decision["holds"]),
            "legacy_source_clock": decision["legacy_comparison"].get("current_native_clock"),
            "model_source_clock": saved["native"]["source_updated_at"] if saved else None,
            "model": copy.deepcopy(saved["model"]) if saved else None,
            "conditioning_scope": decision.get("conditioning_scope"),
            "strict_legacy_model_refreshed": False,
        }
        if not decision["enabled"]:
            rows.append(row)
            continue
        try:
            data, source = _checkpoint(races.get(decision["identity"]["id"]), decision, saved)
            model = _estimate(data, source, decision, review["prior"])
            if saved and saved["native"] == data and saved["source"] == source:
                require(model == saved["model"], "Unchanged Senate input changed its scenario")
                action = "fresh_unchanged_partial_scenario"
            else:
                action = "fresh_partial_scenario"
            checkpoints[key] = {
                "review_version": VERSION, "native": copy.deepcopy(data), "source": copy.deepcopy(source),
                "model": model, "model_pin": pin(encoded(model))}
            row.update(status=action, holds=[], model=model, model_source_clock=data["source_updated_at"])
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            row.update(status="held_retain_last_good_partial_scenario" if saved
                       else "held_no_compatible_partial_bridge", holds=[str(error)])
        rows.append(row)
    result = {
        "contract": CONTRACT, "review_version": VERSION, "rows": rows,
        "summary": {
            "legacy_fitted_decisions": len(rows),
            "fresh_partial_scenarios": sum(row["status"].startswith("fresh_") for row in rows),
            "retained_partial_scenarios": sum(row["status"] == "held_retain_last_good_partial_scenario"
                                             for row in rows),
            "fresh_sensitivity_fits": sum(len(row["model"]["complete_scenarios"]) for row in rows
                                          if row["status"].startswith("fresh_")),
            "empirical_senate_models_added": 0, "strict_legacy_models_refreshed": 0,
        },
        "source_models_refitted": False, "measured_staying_home": None,
        "confidence_intervals": None, "local_allocation": False,
        "complete_candidate_universe_qualified": False,
    }
    return {"result": result, "last_good": checkpoints}


def exports(result):
    models = [row["model"] for row in result["rows"] if row["model"] is not None]
    science = calibrated_swing.result_files({"rows": models})
    return {
        "senate/legacy-partial-decisions.csv": calibrated_swing.csv_bytes([
            {key: value for key, value in row.items() if key != "model"} for row in result["rows"]]),
        **{"senate/legacy-partial-" + name + (".gz" if name.endswith(".json") else ""):
           compressed(json.loads(body))
           if name.endswith(".json") else body
           for name, body in science.items()},
    }
