"""Refresh reviewed D/R-only Senate scenarios, never Senate respondent fits."""

import copy
import io
import json
from pathlib import Path
import zipfile

from scripts import calibrated_swing
from scripts.congressional_analytical_bridge import identity, review_names
from scripts.participation_intake.contract import encoded, pin
from scripts.results_congress import check_revision, compressed, normalize, require


VERSION = "20261117-01"
CONTRACT = "participation.senate_legacy_partial_scenarios.v1"
REVIEW_PATH = "data/results-intake/senate-legacy/review.json"
SCIENCE_PATH = "data/results-intake/senate-legacy/complete-predecessor.zip"
DATA_PATHS = (REVIEW_PATH, SCIENCE_PATH)
MODEL_PATH = "senate/legacy-partial-results.json.gz"
SCIENCE_PIN = {
    "bytes": 14943668,
    "sha256": "2377ea253d33b88af3146bad4e2a52c9936d97b178c00a4fa0e3be022aadeae1",
}


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
                matches = [row for row in reported if review_names(row["name"], candidate["name"])
                           and {"Democratic": "D", "Republican": "R"}.get(row["party"])
                           == candidate["party_group"]]
                require(len(matches) == 1, "Unreviewed cross-provider Senate candidate identity")
            require(decision["previous"] == old["reported_comparison"]["previous"],
                    "Different historical candidate endpoints")
            require(decision["conditioning_scope"] == "reported_DR_only_current_O_unknown",
                    "Unreported Other is not an observed zero")
    require(approved == ["AL-senate-86907"], "Unreviewed Senate partial-scenario extension")
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
            require(saved.get("review_version") == VERSION
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
