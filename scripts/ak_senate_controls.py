"""Qualify a separate native Alaska Senate accounting scope, never county allocation."""

import argparse
from collections import Counter, defaultdict
import csv
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import zipfile


PINS = {
    "native-AK.json": "3289bf5f9b24d2b1d4f666ad4b8d2375aa377effca990118fa4fa24ba979d4c5",
    "accepted-identifiers.zip": "1c3938ea0d933d7e9fd628d07b0d3244c76fa795a18ac1bb21692a11a771d7ef",
    "complete-prior-controls.csv": "a7e8bd4a811aa27721ba289bee3589feb125de2bb834764fa6a014665232c93e",
    "complete-prior-crosschecks.csv": "672a3bc38c540a8ba01409dc81a8fb72c912673f87b3ea5cf886859fe422b9ef",
    "policy.json": "71da48f23119229ca97a11ca0447a1e62c9e2ddbd2811a2323a2a49739ffadc9",
}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def read_csv(body):
    return list(csv.DictReader(io.StringIO(body.decode())))


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=sorted(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def load(root):
    manifest = json.loads((root / "manifest.json").read_bytes())
    for name, expected in manifest.items():
        if Path(name).name != name or pin((root / name).read_bytes()) != expected:
            raise ValueError("Changed or unsafe frozen input")
    for name, expected in PINS.items():
        if pin((root / name).read_bytes())["sha256"] != expected:
            raise ValueError("Changed accepted source, predecessor or policy")
    with zipfile.ZipFile(root / "accepted-identifiers.zip") as archive:
        for name, expected in json.loads(archive.read("checksums.json")).items():
            if pin(archive.read(name)) != expected:
                raise ValueError("Changed complete accepted predecessor")
        rows = read_csv(archive.read("complete-native-units-with-reference-ids.csv"))
    return (json.loads((root / "native-AK.json").read_bytes()),
            read_csv((root / "complete-prior-controls.csv").read_bytes()), rows,
            (root / "complete-prior-crosschecks.csv").read_bytes(),
            json.loads((root / "policy.json").read_bytes()))


def build(native, controls, rows, prior, policy):
    if pin(encoded(policy))["sha256"] != PINS["policy.json"]:
        raise ValueError("Changed native scope policy")
    if (native["election_type"], native["election_scope"], native["province"], native["round"]) != (
            "US Senate", "General", "AK", 1) or native["test_data"]:
        raise ValueError("Wrong election or source round")
    selected = [dict(row) for row in rows if row["provider"] == "civic" and row["state"] == "AK"]
    roster = {}
    for candidate in native["candidates"]:
        key = candidate["name"], candidate["party"]
        if key in roster or type(candidate["votes"]) is not int or candidate["votes"] < 0:
            raise ValueError("Invalid native statewide candidate")
        roster[key] = candidate["votes"]
    if len(roster) != 4:
        raise ValueError("Changed native candidate roster")
    units = defaultdict(dict)
    types = {}
    for row in selected:
        identity, candidate = row["native_unit_id"], (row["candidate"], row["party"])
        if (candidate not in roster or candidate in units[identity] or not row["votes"].isdigit()
                or row["native_round"] != str(native["round"])
                or row["native_updated"] != native["last_updated"] or row["contest"] != "SG"):
            raise ValueError("Invalid, duplicated or changed native candidate-unit evidence")
        if identity in types and types[identity] != row["native_unit_type"]:
            raise ValueError("Conflicting native unit roles")
        types[identity] = row["native_unit_type"]
        units[identity][candidate] = int(row["votes"])
    if any(set(values) != set(roster) for values in units.values()):
        raise ValueError("Incomplete native candidate-unit roster")
    districts = {key for key, role in types.items() if role == "House District"}
    overseas = {key for key, role in types.items() if role == "Overseas"}
    state = {key for key, role in types.items() if role == "State"}
    boroughs = {key for key, role in types.items() if role == "Borough"}
    expected = set(policy["expected_district_ids"])
    qualified_roster = (districts == expected and overseas == {policy["overseas_id"]}
                        and state == {policy["state_id"]} and len(boroughs) == policy["expected_borough_count"])
    if state != {policy["state_id"]}:
        raise ValueError("Missing or duplicated native state region")
    nested = units[policy["state_id"]]
    scopes = {
        "candidate_parent": set(), "state": state, "house_districts": districts,
        "house_districts_plus_explicit_overseas": districts | overseas,
        "boroughs": boroughs, "boroughs_plus_explicit_overseas": boroughs | overseas,
    }
    checks, margins, qualified = [], [], {}
    for scope, identities in scopes.items():
        vector = dict(roster) if scope == "candidate_parent" else {
            key: sum(units[identity][key] for identity in identities) for key in roster}
        matches = vector == roster
        allowed = scope == "boroughs_plus_explicit_overseas" and qualified_roster and matches
        for (name, party), value in vector.items():
            checks.append(dict(scope=scope, candidate=name, party=party, native_units=len(identities),
                source_votes=value, native_state_votes=roster[name, party],
                source_minus_state=value - roster[name, party],
                nested_state_votes=nested[name, party], source_minus_nested_state=value - nested[name, party],
                native_role_state_control_qualified=allowed, county_allocation=False,
                native_round=native["round"], snapshot_clock=native["last_updated"],
                independent_outcome_validation=False, final_RCV_qualified=False))
            if allowed:
                qualified[name, party] = value
        totals = Counter()
        for (_, party), value in vector.items():
            totals[party] += value
        dem, rep = totals["Democratic"], totals["Republican"]
        margin = Fraction(100 * (dem - rep), dem + rep) if dem + rep else None
        margins.append(dict(scope=scope, native_units=len(identities), democratic_votes=dem,
            republican_votes=rep, other_native_party_votes=sum(vector.values()) - dem - rep,
            candidate_selections=sum(vector.values()), signed_DR_margin_numerator=margin.numerator if margin else 0,
            signed_DR_margin_denominator=margin.denominator if margin else 1,
            signed_DR_margin_pp=float(margin) if margin is not None else None,
            disposition="top_level_candidate_parent_reference" if scope == "candidate_parent" else
                "different_native_nested_state_preserved" if scope == "state" else
                "native_role_state_control_qualified" if allowed else "diagnostic_component_or_mismatched_scope",
            turnout=None, registered_population=native["registered_voters"],
            reported_percent_reporting=native["percent_reporting"], final_RCV_qualified=False))
    decisions = []
    for original in controls:
        row = dict(original)
        key = row["candidate"], row["party"]
        alternative = qualified.get(key) if row["state"] == "AK" else None
        accepted = row["county_plus_explicit_unlocated_minus_state"] == "0"
        if row["state"] == "AK" and int(row["native_state_votes"]) != roster[key]:
            raise ValueError("Changed prior statewide control")
        row.update(alternative_native_votes=alternative, county_fields_repaired=False,
            nested_state_parent_disagrees=(nested[key] != roster[key]) if row["state"] == "AK" else None,
            selected_state_accounting_scope="boroughs_plus_explicit_overseas" if alternative is not None
                else "previous_accepted_county_plus_explicit_unlocated" if accepted else None,
            state_control_disposition="qualified_native_noncounty_state_accounting" if alternative is not None
                else "preserved_previous_native_accounting" if accepted else "held_original_scope_gap",
            final_RCV_qualified=False, turnout_qualified=False)
        decisions.append(row)
    baseline = read_csv(prior)
    summary = dict(native_AK_rows=len(selected), native_unit_roles=dict(sorted(Counter(types.values()).items())),
        complete_candidate_control_decisions=len(decisions),
        dispositions=dict(sorted(Counter(row["state_control_disposition"] for row in decisions).items())),
        qualified_state_accounting_controls=sum(row["selected_state_accounting_scope"] is not None for row in decisions),
        original_county_fields_unchanged=True, native_round=native["round"],
        snapshot_clock=native["last_updated"], partial_percent_reporting=native["percent_reporting"],
        registered_voters=native["registered_voters"], prior_crosschecks=len(baseline),
        nested_state_parent_disagreements=sum(nested[key] != roster[key] for key in roster),
        prior_different_counts_preserved=sum(row["status"] == "different_reported_count" for row in baseline),
        source_acquisitions_or_old_reductions_repeated=False, new_fits=0, frontend_activation=False)
    return dict(contract="participation.ak_senate_native_scope.v1", policy=policy, summary=summary,
        control_decisions=decisions, native_AK_rows=selected, scope_candidate_checks=checks, scope_margins=margins)


def files(result, prior):
    return {"complete-result.json": encoded(result), "summary.json": encoded(result["summary"]),
        "complete-prior-crosschecks.csv": prior,
        **{"complete-" + key.replace("_", "-") + ".csv": csv_bytes(result[key])
           for key in ("control_decisions", "native_AK_rows", "scope_candidate_checks", "scope_margins")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh output")
    inputs = load(args.inputs)
    result = build(*inputs)
    args.output.mkdir(parents=True)
    for name, body in files(result, inputs[3]).items():
        (args.output / name).write_bytes(body)
    print(json.dumps(result["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
