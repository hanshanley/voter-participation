"""Independently verify Alaska native scope sums with SQLite and exact fractions."""

import csv
from fractions import Fraction
import io
import json
from pathlib import Path
import sqlite3
import zipfile


def verify(inputs, output):
    count = 0

    def check(value):
        nonlocal count
        count += 1
        if not value:
            raise ValueError(f"Independent Alaska control check {count} failed")

    native = json.loads((inputs / "native-AK.json").read_bytes())
    result = json.loads((output / "complete-result.json").read_bytes())
    with zipfile.ZipFile(inputs / "accepted-identifiers.zip") as archive:
        previous = list(csv.DictReader(io.StringIO(archive.read("complete-native-units-with-reference-ids.csv").decode())))
    rows = [row for row in previous if row["provider"] == "civic" and row["state"] == "AK"]
    check(result["native_AK_rows"] == rows)
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE native(unit TEXT,role TEXT,name TEXT,party TEXT,votes INTEGER,PRIMARY KEY(unit,name,party))")
        for identity, unit in native["region_results"].items():
            for candidate in unit["candidates"]:
                connection.execute("INSERT INTO native VALUES(?,?,?,?,?)",
                    (identity, unit["type"], candidate["name"], candidate["party"], candidate["votes"]))
        for row in rows:
            found = connection.execute("SELECT role,votes FROM native WHERE unit=? AND name=? AND party=?",
                (row["native_unit_id"], row["candidate"], row["party"])).fetchone()
            check(found == (row["native_unit_type"], int(row["votes"])))
            check(row["native_updated"] == native["last_updated"] and row["native_round"] == str(native["round"]))
        check(connection.execute("SELECT COUNT(*) FROM native").fetchone()[0] == len(rows) == 288)
        names = {(c["name"], c["party"]): c["votes"] for c in native["candidates"]}
        roles = {"state": ("State",), "house_districts": ("House District",),
                 "house_districts_plus_explicit_overseas": ("House District", "Overseas"), "boroughs": ("Borough",),
                 "boroughs_plus_explicit_overseas": ("Borough", "Overseas"), "candidate_parent": ()}
        check(len(result["scope_candidate_checks"]) == 24)
        check({(r["scope"], r["candidate"], r["party"]) for r in result["scope_candidate_checks"]} ==
              {(scope, name, party) for scope in roles for name, party in names})
        for row in result["scope_candidate_checks"]:
            selected = roles[row["scope"]]
            expected = (names[row["candidate"], row["party"]], 0) if not selected else connection.execute(
                "SELECT SUM(votes),COUNT(*) FROM native WHERE name=? AND party=? AND role IN (" +
                ",".join("?" for _ in selected) + ")", (row["candidate"], row["party"], *selected)).fetchone()
            check((row["source_votes"], row["native_units"]) == expected)
            check(row["source_minus_state"] == expected[0] - names[row["candidate"], row["party"]])
            check(row["native_role_state_control_qualified"] ==
                  (row["scope"] == "boroughs_plus_explicit_overseas"))
            nested = connection.execute("SELECT votes FROM native WHERE role='State' AND name=? AND party=?",
                (row["candidate"], row["party"])).fetchone()[0]
            check(row["nested_state_votes"] == nested and row["source_minus_nested_state"] == expected[0] - nested)
            check(not row["county_allocation"] and not row["final_RCV_qualified"])
        check(len(result["scope_margins"]) == 6)
        for row in result["scope_margins"]:
            vector = [(party, sum(value for (_, p), value in names.items() if p == party))
                      for party in sorted({p for _, p in names})] if row["scope"] == "candidate_parent" else connection.execute(
                "SELECT party,SUM(votes) FROM native WHERE role IN (" +
                ",".join("?" for _ in roles[row["scope"]]) + ") GROUP BY party", roles[row["scope"]]).fetchall()
            votes = dict(vector)
            check(row["democratic_votes"] == votes["Democratic"] and row["republican_votes"] == votes["Republican"])
            check(row["candidate_selections"] == sum(votes.values()))
            margin = Fraction(100 * (votes["Democratic"] - votes["Republican"]), votes["Democratic"] + votes["Republican"])
            check((row["signed_DR_margin_numerator"], row["signed_DR_margin_denominator"]) == (margin.numerator, margin.denominator))
            check(row["registered_population"] is None and row["turnout"] is None and not row["final_RCV_qualified"])
    finally:
        connection.close()
    old = list(csv.DictReader(io.StringIO((inputs / "complete-prior-controls.csv").read_text())))
    check(len(old) == len(result["control_decisions"]) == 234)
    for first, last in zip(old, result["control_decisions"]):
        for key, value in first.items():
            check(last[key] == value)
        if first["state"] == "AK":
            check(last["alternative_native_votes"] == int(first["native_state_votes"]))
            check(last["selected_state_accounting_scope"] == "boroughs_plus_explicit_overseas")
            check(last["nested_state_parent_disagrees"])
        elif first["county_plus_explicit_unlocated_minus_state"] == "0":
            check(last["state_control_disposition"] == "preserved_previous_native_accounting")
        else:
            check(first["state"] == "ME" and first["candidate"] == "Write-in"
                  and first["county_plus_explicit_unlocated_minus_state"] == "-882")
            check(last["alternative_native_votes"] is None and last["state_control_disposition"] == "held_original_scope_gap")
        check(not last["county_fields_repaired"] and not last["turnout_qualified"])
    check((output / "complete-prior-crosschecks.csv").read_bytes() == (inputs / "complete-prior-crosschecks.csv").read_bytes())
    check(result["summary"]["qualified_state_accounting_controls"] == 233)
    check(result["summary"]["prior_different_counts_preserved"] == 215)
    for key in ("control_decisions", "native_AK_rows", "scope_candidate_checks", "scope_margins"):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=sorted(result[key][0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(result[key])
        check((output / ("complete-" + key.replace("_", "-") + ".csv")).read_bytes() == stream.getvalue().encode())
    check(json.loads((output / "summary.json").read_bytes()) == result["summary"])
    return dict(status="passed_independent_native_SQLite_Alaska_scope_checks", checks=count,
                native_rows=288, complete_controls=234, separate_state_accounting_qualified=233,
                prior_215_disagreements_preserved=True, county_repairs=0, turnout_or_RCV_promotion=False)
