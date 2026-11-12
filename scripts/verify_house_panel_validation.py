"""Independently verify private House joints using SQL classification and exact fractions."""

import argparse
from collections import Counter, defaultdict
import csv
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("panel", "ap2024", "results", "policy", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_bytes())
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(args.panel) == policy["source_sha256"]["CES_panel_2020_2022_2024_v2"]
    assert digest(args.ap2024) == policy["source_sha256"]["AP2024"]
    private = json.loads((args.results / "private-full-panel-joints.json").read_bytes())
    ap = json.loads((args.results / "private-AP-joint.json").read_bytes())
    public = json.loads((args.results / "public-candidate.json").read_bytes())
    weights = policy["CES"]["weight_frames"]
    fields = ["TS_state_24", "TS_g2022", "TS_g2024", "CC22_412", "CC24_412"] + weights + [
        f"HouseCand{i}Party_post_{year}" for year, maximum in ((22, 8), (24, 5))
        for i in range(1, maximum + 1)]
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE native (" + ",".join(f"{f} TEXT" for f in fields) + ")")
    with args.panel.open(encoding="utf-8-sig", newline="") as stream:
        db.executemany("INSERT INTO native VALUES(" + ",".join("?" for f in fields) + ")",
                       ([row[f] for f in fields] for row in csv.DictReader(stream)))

    def sql_choice(year, maximum):
        candidate = "CASE CC%d_412 " % year + " ".join(
            f"WHEN '{i}' THEN HouseCand{i}Party_post_{year}" for i in range(1, maximum + 1)) + " END"
        slots = ",".join(f"'{i}'" for i in range(1, maximum + 1))
        election_nonvote = f"WHEN CC{year}_412='12' THEN 'REPORTED_NONVOTE' " if year == 22 else ""
        return (f"CASE WHEN CC{year}_412 IN ({slots}) THEN CASE "
                f"WHEN {candidate}='Democratic' THEN 'D' WHEN {candidate}='Republican' THEN 'R' "
                f"WHEN {candidate} IN ('','NA','__NA__','-1') THEN 'UNKNOWN' ELSE 'O' END "
                f"WHEN CC{year}_412='10' THEN 'O' WHEN CC{year}_412='11' THEN 'CONTEST_NONVOTE' "
                + election_nonvote + "ELSE 'UNKNOWN' END")

    def sql_history(year):
        return (f"CASE WHEN TS_g{year} IN ('1','2','3','4','5','6') THEN 'POSITIVE' "
                f"WHEN TS_g{year}='7' THEN 'EXPLICIT_NONVOTE' ELSE 'UNKNOWN' END")

    query = "SELECT " + ",".join(["TS_state_24", sql_history(2022), sql_choice(22, 8),
                                  sql_history(2024), sql_choice(24, 5)] + weights) + " FROM native"
    raw = defaultdict(Counter)
    sums = defaultdict(lambda: [0, Fraction(0), Fraction(0)])
    positive22 = Counter()
    for state, h0, a, h1, b, *values in db.execute(query):
        state = state if state in private["scopes"] and state != "ALL_SOURCE" else "UNLOCATED"
        key = "|".join((h0, a, h1, b))
        positive22[h0] += 1
        for scope in (state, "ALL_SOURCE"):
            raw[scope][key] += 1
            for name, value in zip(weights, values):
                if value in ("", "NA", "__NA__", "-1") or Fraction(value) == 0:
                    continue
                number = Fraction(value)
                assert number > 0
                item = sums[scope, name, key]
                item[0] += 1
                item[1] += number
                item[2] += number * number
    checks = 0

    def equal(a, b):
        nonlocal checks
        assert a == b, "Independent arithmetic mismatch"
        checks += 1

    def verify_cell(stored, expected):
        equal(stored["n"], expected[0])
        equal(Fraction(stored["weight"]), expected[1])
        equal(Fraction(stored["squared_weight"]), expected[2])

    equal(sum(positive22.values()), 6175)
    equal(dict(positive22), {"POSITIVE": 4818, "EXPLICIT_NONVOTE": 604, "UNKNOWN": 753})
    for scope, result in private["scopes"].items():
        equal(dict(raw[scope]), result["raw_full_joint"])
        equal(sum(raw[scope].values()), result["raw_rows"])
        for name, frame in result["frames"].items():
            native = {key: value for (s, w, key), value in sums.items() if s == scope and w == name}
            equal(set(native), set(frame["full_joint"]))
            for key, stored in frame["full_joint"].items():
                verify_cell(stored, native[key])
            used = [sum(v[i] for v in native.values()) for i in range(3)]
            verify_cell(frame["used"], used)
            equal(frame["missing_or_zero_weight_rows"], result["raw_rows"] - used[0])
            for selected in ("both_major_choices", "both_major_choices_and_positive_history"):
                expected = {key: [0, Fraction(0), Fraction(0)] for key in ("DD", "DR", "RD", "RR")}
                for key, values in native.items():
                    h0, a, h1, b = key.split("|")
                    if a in ("D", "R") and b in ("D", "R") and (
                            selected == "both_major_choices" or h0 == h1 == "POSITIVE"):
                        expected[a + b] = [left + right for left, right in zip(expected[a + b], values)]
                for key, stored in frame[selected].items():
                    verify_cell(stored, expected[key])
    db.close()
    expected_ap = {key: [0, Fraction(0), Fraction(0)] for key in ("DD", "DR", "RD", "RR")}
    source_positive = 0

    def number(value):
        try:
            return int(value.strip().split()[0].strip("()"))
        except (ValueError, IndexError):
            return None

    with zipfile.ZipFile(args.ap2024) as archive, io.TextIOWrapper(
            archive.open("AP_VOTECAST_2024_GENERAL.csv"), encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["POLLCLOSE_STATE_WEIGHT"] in ("", "NA", "-1", "__NA__"):
                continue
            value = Fraction(row["POLLCLOSE_STATE_WEIGHT"])
            if not value:
                continue
            assert value > 0
            source_positive += 1
            if number(row["QPVVOTE22"]) in (1, 2, 3) or number(row["LIKELYVOTER"]) != 1:
                continue
            before = {1: "R", 2: "D"}.get(number(row["QVOTE2022"]))
            after = {1: "D", 2: "R"}.get(number(row["HOUSEVOTE"]))
            if before and after:
                item = expected_ap[before + after]
                item[0] += 1
                item[1] += value
                item[2] += value * value
    equal(source_positive, ap["positive_weight_source_rows"])
    for key, stored in ap["table"].items():
        verify_cell(stored, expected_ap[key])
    equal(len(public["decisions"]), 319)
    equal(sum(v["available"] for v in public["decisions"]), 2)
    for decision in public["decisions"]:
        if not decision["available"]:
            equal(decision["cells"], None)
            equal(decision["statistics"], None)
        else:
            expected = (private["scopes"]["ALL_SOURCE"]["frames"]["commonpostweight_24"][
                "both_major_choices_and_positive_history"]
                if decision["source"] == "CES_retained_panel" else ap["table"])
            equal(decision["cells"], expected)
            equal(all(v["n"] >= 30 for v in expected.values()), True)
    report = dict(status="pass", method="independent_SQL_classification_and_exact_fraction_native_arithmetic",
        checks=checks, source_rows=6175, query_decisions=319, available_source_tables=2,
        historical_positive_nonvote_unknown_control_preserved=True,
        raw_cases_identifiers_private_fine_cells_exported=False,
        policy_sha256=digest(args.policy), reviewer_sha256=policy["reviewer_sha256"],
        verifier_sha256=digest(Path(__file__)),
        private_result_sha256={p.name: digest(p) for p in sorted(args.results.glob("*.json"))})
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "method", "checks", "source_rows", "query_decisions")}))


if __name__ == "__main__":
    main()
