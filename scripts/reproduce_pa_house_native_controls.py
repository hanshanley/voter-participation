"""Reproduce the PA-only scope correction from complete accepted native exports."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import unittest
import zipfile


PARENT_SHA256 = "fa8f548d131cdd8938d25966ca65888812eca15f800693029a6712f0a4b82cdc"


def load_inputs(root):
    inputs = root / "inputs"
    for name, pin in json.loads((root / "frozen-inputs.json").read_bytes()).items():
        if Path(name).name != name:
            raise ValueError("Unsafe frozen member")
        body = (inputs / name).read_bytes()
        if dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) != pin:
            raise ValueError("Changed frozen input: "+name)
    parent = (inputs / "complete-accepted-endpoint-science.zip").read_bytes()
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA256:
        raise ValueError("The accepted complete 47-state predecessor changed")
    with zipfile.ZipFile(io.BytesIO(parent)) as archive:
        previous = json.loads(archive.read("results/complete-result.json"))
        held = json.loads(archive.read("inputs/held-2026-House-controls.json"))
        facts = json.loads(archive.read("inputs/native-house-facts.json"))
        recap = json.loads(archive.read("inputs/native-house-recap.json"))
        original = archive.read("inputs/complete-accepted-NORC-science.zip")
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        priors = json.loads(archive.read("inputs/fitted-synthetic-NORC-priors.json"))
    pa = next(row for row in held["return_controls"] if row["state_code"] == "PA")
    if pa != json.loads((inputs / "held-pa-control.json").read_bytes()):
        raise ValueError("The held native controls or county-validation exceptions changed")
    expected = sorted({row["district"] for row in facts["candidates"]})
    if expected != json.loads((inputs / "expected-house-districts.json").read_bytes()):
        raise ValueError("The independent official district inventory changed")
    return priors, previous, held, facts, recap


def verify_scope(native_csv, control, qualification, expected):
    checks = 0
    def check(value):
        nonlocal checks
        checks += 1
        if not value:
            raise ValueError("Independent native-control SQL check failed: "+str(checks))
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE native (state TEXT,district TEXT,name TEXT,party TEXT,votes INTEGER,url TEXT,clock TEXT)")
        rows = list(csv.DictReader(io.StringIO(gzip.decompress(native_csv).decode())))
        for row in rows:
            value = row["votes"]
            check(bool(value) and all("0" <= c <= "9" for c in value))
            db.execute("INSERT INTO native VALUES (?,?,?,?,?,?,?)", (
                row["state_code"], row["district"], row["name"], row["party"], int(value),
                row["source_url"], row["source_updated_at"]))
        check({r[0] for r in db.execute("SELECT DISTINCT district FROM native")} == set(expected))
        db.execute("CREATE TABLE held (district TEXT,name TEXT,party TEXT,votes INTEGER)")
        excluded = []
        for index, row in enumerate(control["full_candidate_control_rows"]):
            raw = row["reported_district_votes"]
            value = None if raw == "" else int(raw)
            db.execute("INSERT INTO held VALUES (?,?,?,?)", (
                row["district"], row["candidate"], row["literal_party"], value))
            if value is None:
                excluded.append(dict(control_index=index, **row))
        check(not list(db.execute("SELECT district,name,party,votes FROM native WHERE state='PA' "
            "EXCEPT SELECT district,name,party,votes FROM held WHERE votes IS NOT NULL")))
        check(not list(db.execute("SELECT district,name,party,votes FROM held WHERE votes IS NOT NULL "
            "EXCEPT SELECT district,name,party,votes FROM native WHERE state='PA'")))
        check(db.execute("SELECT count(*) FROM native WHERE state='PA'").fetchone()[0]
              == db.execute("SELECT count(votes) FROM held").fetchone()[0])
        totals = dict(D=0, R=0, O=0)
        for party, total in db.execute("SELECT CASE WHEN lower(trim(party)) IN ('democratic','democrat','dem') "
                "THEN 'D' WHEN lower(trim(party)) IN ('republican','rep') THEN 'R' ELSE 'O' END, "
                "sum(votes) FROM native WHERE state='PA' GROUP BY 1"):
            totals[party] = total
        for key in "DRO":
            check(totals[key] == control["current"][key]
                  == qualification["current_reported_candidate_counts"][key])
        check(excluded == qualification["county_validation_only_exceptions"])
        check([row["control_index"] for row in excluded] == control["missing_candidate_control_indices"])
        for row in qualification["native_district_sources"]:
            actual = db.execute("SELECT DISTINCT url,clock FROM native WHERE district=?",
                                (row["district"],)).fetchall()
            check(actual == [(row["url"], row["last_updated"])])
        check({row["district"] for row in qualification["native_district_sources"]}
              == {r[0] for r in db.execute("SELECT DISTINCT district FROM native WHERE state='PA'")})
        return dict(status="passed_independent_native_reported_controls_SQL_reconciliation",
            checks=checks, native_PA_candidate_rows=db.execute(
                "SELECT count(*) FROM native WHERE state='PA'").fetchone()[0],
            native_PA_districts=len(qualification["native_district_sources"]),
            county_validation_exceptions_retained=len(excluded), current_reported_counts=totals,
            county_counts_added_to_state=False, source_originals_reacquired=False,
            primary_qualifier_imported_by_SQL_verifier=False,
            independent_behavioral_or_administrative_validation=False)
    finally:
        db.close()


def analyze(root, result=None):
    from scripts import norc_house_endpoint_successor as successor
    from scripts import verify_norc_house_model as independent
    from scripts.reproduce_norc_house_endpoints import verify_reuse
    priors, previous, held, facts, recap = load_inputs(root)
    baseline = successor.comparisons(facts, recap, held, previous)
    old = {row["state_code"]: row for row in previous["rows"]}
    if any(row["reported_comparison"] != old[row["state_code"]]["reported_comparison"]
           for row in baseline["rows"]):
        raise ValueError("Default predecessor comparisons changed")
    native_csv = (root / "inputs/native-district-candidates.csv.gz").read_bytes()
    endpoints = successor.comparisons(facts, recap, held, previous,
        native_control_evidence=dict(csv=native_csv,
            audit=json.loads((root / "inputs/native-district-audit.json").read_bytes())))
    if result is None:
        result = successor.build(priors, previous, endpoints)
    if result["endpoint_update"]["changed_states"] != ["PA"]:
        raise ValueError("Only Pennsylvania may be recalculated")
    if result["endpoint_update"]["all_fifty_endpoint_decisions"] != endpoints["rows"]:
        raise ValueError("The complete source decisions changed")
    proof = independent.verify(result, priors)
    reuse = verify_reuse(result, previous, endpoints)
    if len(reuse["unchanged_states"]) != 49:
        raise ValueError("Every other state must retain all numerical fields and cases")
    pa = next(row for row in endpoints["rows"] if row["state_code"] == "PA")
    scope = verify_scope(native_csv, next(row for row in held["return_controls"]
        if row["state_code"] == "PA"), pa["native_current_control_scope"],
        {row["district"] for row in facts["candidates"]})
    return result, endpoints, proof, reuse, scope


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh output")
    root = args.package.resolve()
    sys.path.insert(0, str(root / "code"))
    from scripts.reproduce_norc_house_endpoints import offline
    from scripts import norc_house_model as model
    sys.addaudithook(offline)
    for probe in (lambda: socket.getaddrinfo("example.invalid", 443),
                  lambda: subprocess.run([sys.executable, "-c", "pass"], check=True)):
        try:
            probe()
        except PermissionError:
            pass
        else:
            raise ValueError("Offline guard failed")
    manifest = json.loads((root / "manifest.json").read_bytes())
    for name, pin in manifest["files"].items():
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Unsafe complete member")
        body = (root / name).read_bytes()
        if dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) != pin:
            raise ValueError("Changed complete member: "+name)
    tests = unittest.TextTestRunner().run(unittest.defaultTestLoader.discover(
        str(root / "code/tests"), pattern="test_house_native_controls.py"))
    if not tests.wasSuccessful():
        raise ValueError("Native-control behavior tests failed")
    result, endpoints, proof, reuse, scope = analyze(root)
    values = {"independent-verification.json": proof, "unchanged-state-reuse.json": reuse,
              "native-control-SQL-verification.json": scope, "complete-endpoint-decisions.json": endpoints}
    for name, value in values.items():
        if model.encoded(value) != (root / "checks" / name).read_bytes():
            raise ValueError("Source or independent proof changed: "+name)
    outputs = model.result_files(result)
    for name, body in outputs.items():
        if body != (root / "results" / name).read_bytes():
            raise ValueError("Complete query byte mismatch: "+name)
    args.output.mkdir(parents=True)
    for name, body in outputs.items():
        (args.output / name).write_bytes(body)
    receipt = dict(status="passed_complete_PA_only_offline_scope_successor",
        tests_passed=tests.testsRun, all_eight_complete_output_files_byte_identical=True,
        network_and_external_commands_blocked=True, source_models_refitted=False,
        states_recomputed=["PA"], unchanged_states_reused=49,
        independent=proof, native_SQL=scope, reuse=reuse)
    (args.output / "reproduction.json").write_bytes(model.encoded(receipt))
    print(json.dumps(receipt))
