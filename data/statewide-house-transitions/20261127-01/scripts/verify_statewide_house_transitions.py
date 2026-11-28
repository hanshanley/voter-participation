"""Independently verify every statewide transition matrix and scenario output."""

import argparse
import csv
from decimal import Decimal
import gzip
import json
import math
from pathlib import Path


CATEGORIES = "DROHNE"
TERMS = ("switching", "staying_home", "entry_return", "other_choice", "house_choice", "eligibility_change")
GROSS = ("switching", "no_ballot", "retained_category", "other_category", "house_choice", "eligibility_exit")


def load(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)


def verify(inputs, product):
    data = load(product / "viewer-data.json")
    assert data["contract"] == "participation.statewide_house_transitions.v1"
    assert data["quick_development_preview"] is False
    assert data["confidence_intervals"] is None and data["model_units_are_people"] is False
    assert data["measured_staying_home"] is None and data["identified_individual_histories"] is False
    congress = load(inputs / "congressional.json.gz")
    states = {row["state_code"]: row for row in congress["house_states"]}
    shown = {row["state_code"]: row for row in data["rows"]}
    assert len(shown) == len(data["rows"]) == len(states) == 50 and shown.keys() == states.keys()
    benchmarks = {}
    for year in (2024, 2026):
        with (inputs / f"UF-{year}.csv").open(encoding="utf-8-sig", newline="") as stream:
            benchmarks[year] = {row["STATE_ABV"]: row for row in csv.DictReader(stream)}
    priors = {profile: {family: {row["state_code"]: row for row in model["rows"]}
                       for family, model in load(inputs / f"source-{profile}.json.gz")["models"].items()}
              for profile in data["profiles"]}

    def counts(code, year, scale, frame):
        row = benchmarks[year][code]
        ballots = Decimal(row["TOTAL_BALLOTS_COUNTED"].replace(",", "")) * Decimal(str(scale))
        eligible = Decimal(row["VEP"].replace(",", ""))
        house = states[code]["previous" if year == 2024 else "current"]
        parties = [house["D"], house["R"], house["O"] + house.get("U", 0)]
        if ballots < sum(parties) or ballots > eligible:
            return None
        return [*parties, float(ballots - sum(parties)), float(eligible - ballots), frame - float(eligible)]

    def values(matrix, rows, columns):
        old, new = rows[0]+rows[1], columns[0]+columns[1]
        delta = 100*(columns[0]/new-rows[0]/old)
        parts = dict.fromkeys(TERMS, 0.)
        for i, a in enumerate(CATEGORIES):
            for j, b in enumerate(CATEGORIES):
                if "E" in (a, b): key="eligibility_change"
                elif (a, b) in (("D","R"),("R","D")): key="switching"
                elif a in "DRO" and b == "N": key="staying_home"
                elif a == "N" and b in "DRO": key="entry_return"
                elif "H" in (a, b): key="house_choice"
                else: key="other_choice"
                numerator = int(b=="D") - int(a=="D")
                denominator = int(b in "DR") - int(a in "DR")
                parts[key] += 50*matrix[i][j]*((1/old+1/new)*numerator
                    -(rows[0]+columns[0])*denominator/(old*new))
        total = sum(rows[:3])
        gross = dict(switching=matrix[0][1]+matrix[1][0], no_ballot=sum(matrix[i][4] for i in range(3)),
            retained_category=sum(matrix[i][i] for i in range(3)),
            other_category=matrix[0][2]+matrix[1][2]+matrix[2][0]+matrix[2][1],
            house_choice=sum(matrix[i][3] for i in range(3)), eligibility_exit=sum(matrix[i][5] for i in range(3)))
        return {key:100*value/total for key,value in gross.items()}, parts, delta

    def check_matrix(matrix, rows, columns):
        assert all(math.isfinite(v) and v >= 0 for row in matrix for v in row)
        assert all(abs(sum(matrix[i])-rows[i]) < .001 for i in range(6))
        assert all(abs(sum(matrix[i][j] for i in range(6))-columns[j]) < .001 for j in range(6))

    for code, row in shown.items():
        assert row["available"] is True
        point = row["point"]; frame = point["frame"]
        a = counts(code, 2024, 1., frame); b = counts(code, 2026, 1., frame)
        check_matrix(point["joint"], a, b)
        gross, parts, delta = values(point["joint"], a, b)
        assert all(abs(gross[key]-point["gross_pct"][key]) < 1e-7 for key in GROSS)
        assert all(abs(parts[key]-point["contributions_pp"][key]) < 1e-7 for key in TERMS)
        assert abs(sum(parts.values())-delta) < 1e-7 and abs(sum(gross.values())-100) < 1e-7
        assert row["context_holds"] == states[code]["comparison_holds"]
    ranges = {code:{key:[math.inf,-math.inf] for key in (*("gross_"+k for k in GROSS),*("contribution_"+k for k in TERMS))} for code in states}
    seen = set(); feasible = rejected = 0
    with gzip.open(product / "complete-sensitivity.csv.gz", "rt", newline="") as stream:
        for row in csv.DictReader(stream):
            code = row["state_code"]
            parameters = tuple(float(row[key]) for key in ("party_persistence","home_persistence","frame_churn","ballots24_scale","ballots26_scale"))
            identity = (code,row["profile"],row["family"],*parameters)
            assert identity not in seen; seen.add(identity)
            party, home, churn, scale24, scale26 = parameters
            e0 = int(benchmarks[2024][code]["VEP"].replace(",", "")); e1 = int(benchmarks[2026][code]["VEP"].replace(",", ""))
            frame = max(e0,e1)+churn*min(e0,e1)
            a, b = counts(code,2024,scale24,frame), counts(code,2026,scale26,frame)
            if a is None or b is None:
                assert row["status"] == "incompatible_hypothetical_ballot_benchmark" and not row["frame"]
                rejected += 1; continue
            assert row["status"] == "modeled_conditional_scenario"
            assert abs(float(row["frame"])-frame) < 1e-7
            matrix = [[float(row[f"flow_{x}_{y}"]) for y in CATEGORIES] for x in CATEGORIES]
            check_matrix(matrix,a,b)
            gross, parts, delta = values(matrix,a,b)
            computed = {**{"gross_"+k:v for k,v in gross.items()},**{"contribution_"+k:v for k,v in parts.items()}}
            assert abs(sum(parts.values())-delta) < 1e-7 and abs(sum(gross.values())-100) < 1e-7
            source = priors[row["profile"]][row["family"]][code]["joint"]
            sr = list(map(sum,source)); sc = [sum(source[i][j] for i in range(5)) for j in range(5)]
            kernel = [[1. for _ in range(6)] for _ in range(6)]; mapping={0:0,1:1,2:2,4:3}
            for i,old_i in mapping.items():
                for j,old_j in mapping.items():
                    denom=sr[old_i]*sc[old_j]
                    kernel[i][j]=(1-1e-8)*source[old_i][old_j]/denom+1e-8 if denom else 1.
            kernel[0][0]*=party;kernel[1][1]*=party;kernel[4][4]*=home
            i0=next(i for i,v in enumerate(a) if v);j0=next(j for j,v in enumerate(b) if v)
            anchor=math.log(matrix[i0][j0]/kernel[i0][j0])
            for i in range(6):
                for j in range(6):
                    if a[i] and b[j]:
                        residual=math.log(matrix[i][j]/kernel[i][j])-math.log(matrix[i][j0]/kernel[i][j0])-math.log(matrix[i0][j]/kernel[i0][j])+anchor
                        assert abs(residual)<1e-8
            for key, value in computed.items():
                assert abs(float(row[key])-value)<1e-7
                ranges[code][key][0]=min(ranges[code][key][0],value);ranges[code][key][1]=max(ranges[code][key][1],value)
            feasible += 1
    expected=50*len(data['profiles'])*len(data['families'])*len(data['party_persistence'])*len(data['home_persistence'])*len(data['frame_churn'])*len(data['ballot_benchmark_scales'])**2
    assert len(seen)==expected==109350
    for code, row in shown.items():
        for key,pair in ranges[code].items():
            assert abs(row['sensitivity'][key]['minimum']-pair[0])<1e-7
            assert abs(row['sensitivity'][key]['maximum']-pair[1])<1e-7
    return dict(status='passed',states=50,point_matrices=50,queried_scenarios=len(seen),
        independently_verified_scenario_matrices=feasible,rejected_incompatible_benchmark_scenarios=rejected,
        six_category_margins_and_all_accounting_checked=True,source_projection_odds_checked=True,
        old_comparison_holds_do_not_suppress_state_estimates=True,individual_histories_claimed=False)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,required=True);parser.add_argument('--product',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(verify(args.inputs,args.product)))
