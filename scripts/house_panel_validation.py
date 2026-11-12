"""Private same-office House joints and conservatively selected public diagnostics."""

import argparse
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
import os
from pathlib import Path
import re
import zipfile


SOURCE_SHA = "e9921d391159cf8fcb68a0b69aa76c94a5bf73436f516606bf3fb310125ba5ac"
AP_SHA = "7d63dada53d1e6f5f3fac54417e189755d54ce312cf7945f16abe4f91c5bf62f"
STATES = "AK AL AR AZ CA CO CT DC DE FL GA HI IA ID IL IN KS KY LA MA MD ME MI MN MO MS MT NC ND NE NH NJ NM NV NY OH OK OR PA RI SC SD TN TX UT VA VT WA WI WV WY".split()
WEIGHTS = ("commonpostweight_24", "commonpostweight_22", "vvweight_post_22")
CHOICES = ("D", "R", "O", "CONTEST_NONVOTE", "REPORTED_NONVOTE", "UNKNOWN")
HISTORY = ("POSITIVE", "EXPLICIT_NONVOTE", "UNKNOWN")
MISSING = {"", "NA", "__NA__", "-1"}
ZERO = Decimal(0)


def history(value):
    if value in MISSING:
        return "UNKNOWN"
    if value not in set("1234567"):
        raise ValueError("Unqualified administrative-history code")
    return "EXPLICIT_NONVOTE" if value == "7" else "POSITIVE"


def house(row, year):
    value = row[f"CC{year}_412"]
    slots = set(map(str, range(1, 9 if year == 22 else 6)))
    allowed = slots | {"10", "11", "13", "98", "99"} | ({"12"} if year == 22 else set())
    if value in MISSING:
        return "UNKNOWN"
    if value not in allowed:
        raise ValueError("Do not borrow unsupported House codes from another wave")
    if value in slots:
        party = row[f"HouseCand{value}Party_post_{year}"]
        if party in MISSING:
            return "UNKNOWN"
        return {"Democratic": "D", "Republican": "R"}.get(party, "O")
    return {"10": "O", "11": "CONTEST_NONVOTE", "12": "REPORTED_NONVOTE"}.get(value, "UNKNOWN")


def weight(value):
    if value in MISSING:
        return None
    result = Decimal(value)
    if not result.is_finite() or result < 0:
        raise ValueError("Invalid native weight")
    return result if result else None


def cell():
    return dict(n=0, weight=ZERO, squared_weight=ZERO)


def add(target, value):
    target["n"] += 1
    target["weight"] += value
    target["squared_weight"] += value * value


def major_table():
    return {a + b: cell() for a in "DR" for b in "DR"}


def selected_table(table):
    if sum(c["n"] for c in table.values()) < 100 or any(c["n"] < 30 for c in table.values()):
        return dict(available=False, reason="whole_table_source_support_hold", cells=None, statistics=None)
    total = sum(c["weight"] for c in table.values())
    if not total:
        return dict(available=False, reason="empty_weight_frame", cells=None, statistics=None)
    statistics = {"gross_D_R_switch_pct_within_selected_both_major_choices":
                  100 * (table["DR"]["weight"] + table["RD"]["weight"]) / total}
    for previous in "DR":
        denominator = sum(table[previous + current]["weight"] for current in "DR")
        statistics[previous + "_to_opposite_pct_within_selected_previous_choice"] = (
            100 * table[previous + ("R" if previous == "D" else "D")]["weight"] / denominator
            if denominator else None)
    return dict(available=True, cells=table, statistics=statistics, reason=None)


def review_panel(rows):
    scopes = {state: {"raw_rows": 0, "raw_full_joint": {}, "frames": {
        key: {"used": cell(), "full_joint": {}, "both_major_choices": major_table(),
              "both_major_choices_and_positive_history": major_table(),
              "missing_or_zero_weight_rows": 0} for key in WEIGHTS}}
        for state in (*STATES, "UNLOCATED", "ALL_SOURCE")}
    count = 0
    record_state_comparison = dict(same=0, different=0, unknown=0)
    chosen_missing_party = {"22": 0, "24": 0}
    for row in rows:
        count += 1
        state = row["TS_state_24"]
        if state not in MISSING and state not in STATES:
            raise ValueError("Unexpected matched-state coding")
        state = state if state in STATES else "UNLOCATED"
        previous_state = row["TS_state_22"]
        if previous_state not in MISSING and previous_state not in STATES:
            raise ValueError("Unexpected earlier matched-state coding")
        comparison = ("unknown" if previous_state not in STATES or state == "UNLOCATED"
                      else "same" if previous_state == state else "different")
        record_state_comparison[comparison] += 1
        for year in (22, 24):
            slot = row[f"CC{year}_412"]
            if slot in map(str, range(1, 9 if year == 22 else 6)):
                chosen_missing_party[str(year)] += row[f"HouseCand{slot}Party_post_{year}"] in MISSING
        a, b = house(row, 22), house(row, 24)
        h0, h1 = history(row["TS_g2022"]), history(row["TS_g2024"])
        key = "|".join((h0, a, h1, b))
        for scope in (state, "ALL_SOURCE"):
            result = scopes[scope]
            result["raw_rows"] += 1
            result["raw_full_joint"][key] = result["raw_full_joint"].get(key, 0) + 1
            for name in WEIGHTS:
                frame = result["frames"][name]
                value = weight(row[name])
                if value is None:
                    frame["missing_or_zero_weight_rows"] += 1
                    continue
                add(frame["used"], value)
                add(frame["full_joint"].setdefault(key, cell()), value)
                if a in "DR" and b in "DR":
                    add(frame["both_major_choices"][a + b], value)
                    if h0 == h1 == "POSITIVE":
                        add(frame["both_major_choices_and_positive_history"][a + b], value)
    for result in scopes.values():
        assert sum(result["raw_full_joint"].values()) == result["raw_rows"]
        for frame in result["frames"].values():
            assert frame["used"]["n"] + frame["missing_or_zero_weight_rows"] == result["raw_rows"]
            assert sum(v["weight"] for v in frame["full_joint"].values()) == frame["used"]["weight"]
    return dict(source_rows=count, scopes=scopes, matched_record_state_comparison=record_state_comparison,
                chosen_missing_candidate_party=chosen_missing_party)


def ap_code(value):
    match = re.match(r"^\s*(?:\()?(-?\d+)", value)
    return int(match[1]) if match else None


def review_ap(path):
    table, positive = major_table(), 0
    with zipfile.ZipFile(path) as archive, io.TextIOWrapper(
            archive.open("AP_VOTECAST_2024_GENERAL.csv"), encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        fields = ("POLLCLOSE_STATE_WEIGHT", "LIKELYVOTER", "HOUSEVOTE", "QPVVOTE22", "QVOTE2022")
        indices = [header.index(field) for field in fields]
        for raw in reader:
            row = dict(zip(fields, (raw[i] for i in indices)))
            value = weight(row["POLLCLOSE_STATE_WEIGHT"])
            if value is None:
                continue
            positive += 1
            before = None if ap_code(row["QPVVOTE22"]) in (1, 2, 3) else {
                1: "R", 2: "D"}.get(ap_code(row["QVOTE2022"]))
            after = {1: "D", 2: "R"}.get(ap_code(row["HOUSEVOTE"])) if ap_code(row["LIKELYVOTER"]) == 1 else None
            if before and after:
                add(table[before + after], value)
    return dict(positive_weight_source_rows=positive, table=table)


def public_selection(panel, ap):
    decisions = []
    selected = {}
    for scope, result in panel["scopes"].items():
        for name, frame in result["frames"].items():
            for selection in ("both_major_choices", "both_major_choices_and_positive_history"):
                eligible = (scope, name, selection) == (
                    "ALL_SOURCE", "commonpostweight_24", "both_major_choices_and_positive_history")
                value = selected_table(frame[selection]) if eligible else dict(
                    available=False, reason="outside_prespecified_public_scope", cells=None, statistics=None)
                decision = dict(source="CES_retained_panel", scope=scope, weight_frame=name,
                                selection=selection, **value)
                decisions.append(decision)
                if value["available"]:
                    selected["CES_retained_panel"] = decision
    decision = dict(source="AP2024_source", scope="POOLED_SOURCE_NOT_NATIONAL_POPULATION",
                    weight_frame="POLLCLOSE_STATE_WEIGHT",
                    selection="modeled_current_voter_both_recalled22_and_current24_major_choices",
                    **selected_table(ap["table"]))
    decisions.append(decision)
    if decision["available"]:
        selected["AP2024_source"] = decision
    differences = None
    if len(selected) == 2:
        differences = {key: selected["AP2024_source"]["statistics"][key] -
                       selected["CES_retained_panel"]["statistics"][key]
                       for key in selected["CES_retained_panel"]["statistics"]}
    return dict(contract="participation.house_panel_concordance.v1", decisions=decisions,
        available_source_tables=len(selected), unmatched_source_differences_pp=differences,
        current_2026_model_changed=False, independent_individual_truth=False,
        population_validation=False, source_code_transport_assumption_required=True,
        design_confidence_intervals=None, precinct_allocation=False)


def encoded(value):
    def convert(item):
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, dict):
            return {key: convert(v) for key, v in item.items()}
        if isinstance(item, list):
            return [convert(v) for v in item]
        return item
    return (json.dumps(convert(value), indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("panel", "ap2024", "bridge", "history-qualification", "policy", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or (Path(__file__).resolve().parents[1] in args.output.resolve().parents):
        raise ValueError("Use a fresh private output outside the repository")
    pin = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    policy = json.loads(args.policy.read_bytes())
    bridge = json.loads(args.bridge.read_bytes())
    qualification = json.loads(args.history_qualification.read_bytes())
    if (pin(args.panel) != SOURCE_SHA or pin(args.ap2024) != AP_SHA or
            policy["reviewer_sha256"] != pin(Path(__file__)) or
            policy["tests_sha256"] != pin(Path(__file__).resolve().parents[1] / "tests/test_house_panel_validation.py") or
            policy["bridge_sha256"] != pin(args.bridge) or
            policy["history_qualification_sha256"] != pin(args.history_qualification)):
        raise ValueError("Frozen source/code/design binding differs")
    if (bridge["status"] != "cross_wave_common_item_bridge_conditional_not_panel_native_labels" or
            bridge["panel_numeric_labels_directly_qualified"] is not False or
            bridge["panel_code_transport_assumption_required"] is not True or
            qualification["status"] != "three_wave_participation_codes_qualified_from_explicit_numbered_guide" or
            qualification["source_sha256"] != SOURCE_SHA):
        raise ValueError("Missing or promoted native coding qualification")
    with localcontext() as context:
        context.prec = 70
        with args.panel.open(encoding="utf-8-sig", newline="") as stream:
            panel = review_panel(csv.DictReader(stream))
        if panel["source_rows"] != 6175:
            raise ValueError("Changed native retained-panel case count")
        ap = review_ap(args.ap2024)
        public = public_selection(panel, ap)
    args.output.mkdir(mode=0o700, parents=True)
    for name, value in (("private-full-panel-joints.json", panel), ("private-AP-joint.json", ap),
                        ("public-candidate.json", public)):
        path = args.output / name
        path.write_bytes(encoded(value))
        os.chmod(path, 0o600)
    print(json.dumps(dict(status="new_same_office_joint_diagnostic_calculated", cases=panel["source_rows"],
                         full_public_decisions=len(public["decisions"]),
                         available_source_tables=public["available_source_tables"],
                         not_population_validation=True)))


if __name__ == "__main__":
    main()
