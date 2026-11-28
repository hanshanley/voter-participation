"""Whole-state House/turnout-constrained transition scenarios for all 50 states."""

import argparse
import csv
from decimal import Decimal
import gzip
import hashlib
import io
import itertools
import json
import math
from pathlib import Path
import sys
import zipfile


CONTRACT = "participation.statewide_house_transitions.v1"
CHOICES = ("D", "R", "O", "H", "N", "E")
TERMS = ("switching", "staying_home", "entry_return", "other_choice", "house_choice", "eligibility_change")
GROSS = ("switching", "no_ballot", "retained_category", "other_category", "house_choice", "eligibility_exit")
STATES = frozenset("AK AL AR AZ CA CO CT DE FL GA HI IA ID IL IN KS KY LA MA MD ME MI MN MO MS MT NC ND NE NH NJ NM NV NY OH OK OR PA RI SC SD TN TX UT VA VT WA WI WV WY".split())
FAMILIES = ("accepted_ridge_multinomial", "histogram_gradient_boosting", "extra_randomized_trees")
PROFILES = ("original", "attenuated", "full")
PARTY_PERSISTENCE = (.5, 1., 2.)
HOME_PERSISTENCE = (.5, 1., 2.)
FRAME_CHURN = (0., .02, .05)
BALLOT_SCALE = (.97, 1., 1.03)


def encoded(value):
    return (json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False) + "\n").encode()


def read_json(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)


def parse_turnout(raw, year):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    required = {"STATE", "STATE_ABV", "TOTAL_BALLOTS_COUNTED", "VEP"}
    if not required <= set(reader.fieldnames or []):
        raise ValueError("Missing statewide ballot/population fields")
    output = {}
    for row in reader:
        code = row["STATE_ABV"]
        if code not in STATES:
            continue
        if code in output:
            raise ValueError("Duplicate turnout state")
        def count(key):
            value = row[key].strip().replace(",", "")
            if not value.isdigit() or int(value) <= 0:
                raise ValueError("Unknown/nonpositive turnout benchmark: " + code + "/" + key)
            return int(value)
        ballots, eligible = count("TOTAL_BALLOTS_COUNTED"), count("VEP")
        if ballots > eligible:
            raise ValueError("Ballots exceed eligible-population benchmark")
        output[code] = dict(year=year, ballots=ballots, eligible=eligible,
            source_url=row.get("SOURCE", row.get("", "")), source_status=row.get("STATUS", "not supplied"),
            independently_certified=False, population_is_estimated=True)
    if set(output) != STATES:
        raise ValueError("All 50 turnout states are required")
    return output


def endpoint(house, benchmark, ballot_scale=1.):
    values = [house.get(key) for key in ("D", "R", "O")]
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("Unknown House counts cannot be filled with zero")
    unknown = house.get("U", 0)
    if type(unknown) is not int or unknown < 0:
        raise ValueError("Unknown unassigned-party candidate counts")
    values[2] += unknown
    exact_ballots = Decimal(benchmark["ballots"]) * Decimal(str(ballot_scale))
    ballots = float(exact_ballots)
    eligible = benchmark["eligible"]
    if Decimal(sum(values)) > exact_ballots or exact_ballots > eligible:
        raise ValueError("Incompatible hypothetical ballot benchmark")
    if values[0] + values[1] <= 0:
        raise ValueError("Known D/R denominator is not positive")
    return dict(house=values, ballots=ballots, eligible=eligible,
                no_reported_house_choice=float(exact_ballots-sum(values)), no_ballot=float(eligible-exact_ballots))


def margins(before, after, churn=.02):
    if churn < 0:
        raise ValueError("Negative eligibility-frame churn")
    frame = max(before["eligible"], after["eligible"]) + churn * min(before["eligible"], after["eligible"])
    def values(point):
        return [*point["house"], point["no_reported_house_choice"], point["no_ballot"], frame-point["eligible"]]
    rows, columns = values(before), values(after)
    if min(*rows, *columns) < -1e-7 or any(abs(sum(v)-frame) > 1e-6 for v in (rows, columns)):
        raise ValueError("Eligibility/ballot/House accounting does not reconcile")
    return frame, [value/frame for value in rows], [value/frame for value in columns]


def association_kernel(joint, party_persistence=1., home_persistence=1.):
    if len(joint) != 5 or any(len(row) != 5 for row in joint):
        raise ValueError("Expected the complete existing DRONU source prior")
    if any(not math.isfinite(value) or value < 0 for row in joint for value in row):
        raise ValueError("Invalid source prior")
    if abs(sum(map(sum, joint))-1) > 1e-8:
        raise ValueError("Source prior is not normalized")
    rows = [sum(row) for row in joint]
    columns = [sum(joint[i][j] for i in range(5)) for j in range(5)]
    result = [[1. for _ in CHOICES] for _ in CHOICES]
    # H and E have neutral associations; source unknown responses are not nonvoting.
    mapping = {0: 0, 1: 1, 2: 2, 4: 3}
    for new_i, old_i in mapping.items():
        for new_j, old_j in mapping.items():
            independent = rows[old_i] * columns[old_j]
            result[new_i][new_j] = (1-1e-8)*joint[old_i][old_j]/independent + 1e-8 if independent else 1.
    result[0][0] *= party_persistence
    result[1][1] *= party_persistence
    result[4][4] *= home_persistence
    return result


def project(kernel, rows, columns):
    q = [[rows[i]*columns[j]*kernel[i][j] for j in range(6)] for i in range(6)]
    for iteration in range(10000):
        for i in range(6):
            total = sum(q[i])
            multiplier = rows[i]/total if rows[i] else 0.
            q[i] = [value*multiplier for value in q[i]]
        for j in range(6):
            total = sum(q[i][j] for i in range(6))
            multiplier = columns[j]/total if columns[j] else 0.
            for i in range(6):
                q[i][j] *= multiplier
        if max(abs(sum(q[i])-rows[i]) for i in range(6)) < 1e-12:
            return q, iteration + 1
    raise ValueError("Whole-state transition projection did not converge")


def term(before, after):
    if "E" in (before, after):
        return "eligibility_change"
    if {before, after} == {"D", "R"}:
        return "switching"
    if before in ("D", "R", "O") and after == "N":
        return "staying_home"
    if before == "N" and after in ("D", "R", "O"):
        return "entry_return"
    if "H" in (before, after):
        return "house_choice"
    return "other_choice"


def statistics(q, rows, columns):
    v0, v1 = sum(rows[:2]), sum(columns[:2])
    if min(v0, v1) <= 0:
        raise ValueError("No positive known D/R denominator")
    a = 50 * (1/v0+1/v1)
    b = -50 * (rows[0]+columns[0])/(v0*v1)
    parts = dict.fromkeys(TERMS, 0.)
    for i, before in enumerate(CHOICES):
        for j, after in enumerate(CHOICES):
            change_d = int(after == "D") - int(before == "D")
            change_total = int(after in ("D", "R")) - int(before in ("D", "R"))
            parts[term(before, after)] += q[i][j] * (a*change_d+b*change_total)
    recorded = sum(rows[:3])
    gross = dict(switching=q[0][1]+q[1][0], no_ballot=sum(q[i][4] for i in range(3)),
        retained_category=sum(q[i][i] for i in range(3)),
        other_category=sum(q[i][2] for i in (0, 1))+sum(q[2][j] for j in (0, 1)),
        house_choice=sum(q[i][3] for i in range(3)), eligibility_exit=sum(q[i][5] for i in range(3)))
    gross = {key: 100*value/recorded for key, value in gross.items()}
    change = 100*(columns[0]/v1-rows[0]/v0)
    if abs(sum(parts.values())-change) > 1e-7 or abs(sum(gross.values())-100) > 1e-7:
        raise ValueError("Whole-state transition accounting does not reconcile")
    return dict(gross_pct=gross, contributions_pp=parts, recorded_change_pp=change,
                previous_D_share=100*rows[0]/v0, current_D_share=100*columns[0]/v1)


def fit(joint, before, after, party=1., home=1., churn=.02):
    frame, rows, columns = margins(before, after, churn)
    q, iterations = project(association_kernel(joint, party, home), rows, columns)
    result = statistics(q, rows, columns)
    result.update(frame=frame, rows=[value*frame for value in rows], columns=[value*frame for value in columns],
                  joint=[[value*frame for value in row] for row in q], iterations=iterations)
    return result


def build(inputs, output, quick=False):
    if output.exists():
        raise ValueError("Use a fresh scientific product directory")
    runtime = read_json(inputs / "runtime.json")
    congress = read_json(inputs / "congressional.json.gz")
    sources = {profile: read_json(inputs / f"source-{profile}.json.gz") for profile in PROFILES}
    benchmarks = {year: parse_turnout((inputs/f"UF-{year}.csv").read_bytes(), year) for year in (2024, 2026)}
    states = {row["state_code"]: row for row in congress["house_states"]}
    if set(states) != STATES or len(congress["house_states"]) != 50:
        raise ValueError("Every state, not only comparable states, is required")
    priors = {}
    for profile, source in sources.items():
        if source["metadata"]["return_conditioned"] is not False or source["metadata"]["source_models_refitted"] is not False:
            raise ValueError("Do not use return-conditioned priors as independent source associations")
        for family in FAMILIES:
            priors[profile, family] = {row["state_code"]: row for row in source["models"][family]["rows"]}
            if set(priors[profile, family]) != STATES:
                raise ValueError("All 50 source priors required")
    output.mkdir(parents=True)
    case_path = output / "complete-sensitivity.csv.gz"
    records, point_rows = [], []
    scenario_keys = ("state_code", "profile", "family", "party_persistence", "home_persistence", "frame_churn", "ballots24_scale", "ballots26_scale", "status")
    metric_keys = tuple("gross_"+key for key in GROSS)+tuple("contribution_"+key for key in TERMS)
    joint_keys = tuple("flow_"+before+"_"+after for before in CHOICES for after in CHOICES)
    with case_path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped, io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
        writer = csv.DictWriter(text, fieldnames=[*scenario_keys, *metric_keys, "frame", *joint_keys], lineterminator="\n"); writer.writeheader()
        for code in sorted(STATES):
            state = states[code]
            before = endpoint(state["previous"], benchmarks[2024][code])
            after = endpoint(state["current"], benchmarks[2026][code])
            point = fit(priors["original", FAMILIES[0]][code]["joint"], before, after)
            ranges = {key: [math.inf, -math.inf] for key in metric_keys}
            queried = feasible = 0
            grid = [("original", FAMILIES[0], 1., 1., .02, 1., 1.)] if quick else itertools.product(PROFILES,FAMILIES,PARTY_PERSISTENCE,HOME_PERSISTENCE,FRAME_CHURN,BALLOT_SCALE,BALLOT_SCALE)
            for profile, family, party, home, churn, scale24, scale26 in grid:
                queried += 1
                row = dict(zip(scenario_keys[:-1], (code,profile,family,party,home,churn,scale24,scale26)))
                try:
                    a0 = endpoint(state["previous"], benchmarks[2024][code], scale24)
                    a1 = endpoint(state["current"], benchmarks[2026][code], scale26)
                except ValueError:
                    writer.writerow({**row, "status":"incompatible_hypothetical_ballot_benchmark"}); continue
                result = fit(priors[profile,family][code]["joint"], a0, a1, party, home, churn)
                values = {**{"gross_"+k:v for k,v in result["gross_pct"].items()}, **{"contribution_"+k:v for k,v in result["contributions_pp"].items()}}
                for key, value in values.items():
                    ranges[key][0] = min(ranges[key][0], value); ranges[key][1] = max(ranges[key][1], value)
                flows = {"flow_"+a+"_"+b:result["joint"][i][j] for i,a in enumerate(CHOICES) for j,b in enumerate(CHOICES)}
                writer.writerow({**row, "status":"modeled_conditional_scenario", **values, "frame":result["frame"], **flows}); feasible += 1
            sensitivity = {key:dict(minimum=pair[0], maximum=pair[1]) for key,pair in ranges.items()}
            record = dict(state_code=code, available=True, point=point, sensitivity=sensitivity,
                previous={**benchmarks[2024][code], "house":before["house"]}, current={**benchmarks[2026][code], "house":after["house"]},
                context_holds=state["comparison_holds"], queries=queried, feasible_scenarios=feasible,
                population_or_individual_histories_validated=False)
            records.append(record)
            point_rows.append(dict(state_code=code, **point["gross_pct"],
                **{"contribution_"+k:v for k,v in point["contributions_pp"].items()}, recorded_D_share_change_pp=point["recorded_change_pp"],
                context_holds=" | ".join(state["comparison_holds"])))
            print(json.dumps(dict(state=code, switching=point["gross_pct"]["switching"], no_ballot=point["gross_pct"]["no_ballot"], feasible=feasible, queried=queried)), flush=True)
    source_files = ("runtime.json", "congressional.json.gz", "UF-2024.csv", "UF-2026.csv", *(f"source-{p}.json.gz" for p in PROFILES))
    input_pins = {name:dict(bytes=(inputs/name).stat().st_size, sha256=hashlib.sha256((inputs/name).read_bytes()).hexdigest()) for name in source_files}
    numerical_runtime=dict(implementation=sys.implementation.name,python_major_minor=list(sys.version_info[:2]))
    version = hashlib.sha256(encoded(dict(protocol=CONTRACT, input_pins=input_pins, party=PARTY_PERSISTENCE, home=HOME_PERSISTENCE, churn=FRAME_CHURN, ballots=BALLOT_SCALE,numerical_runtime=numerical_runtime,quick=quick))).hexdigest()
    metadata = dict(contract=CONTRACT, version=version, input_pins=input_pins, method="whole_state_house_and_turnout_constrained_6_category_projection",
        runtime_version=runtime["version"], runtime_checked_at=runtime["checked_at"], states=50, categories=list(CHOICES),
        numerical_runtime=numerical_runtime, default_profile="original", default_family=FAMILIES[0], point_party_persistence=1., point_home_persistence=1.,
        point_frame_churn=.02, population_or_individual_histories_validated=False, confidence_intervals=None,
        candidate_votes_are_not_ballots=True, source_unknown_responses_are_not_nonvoting=True,
        source_nonparticipation_is_only_a_transported_association_not_completed_abstention=True,
        measured_staying_home=None, identified_individual_histories=False, model_units_are_people=False,
        candidate_availability_effects_are_not_persuasion=True, state_frames_are_not_additive_unique_people=True,
        prior_source_models_refitted=False, constraints_used_not_predictive_validation=True,
        gross_percentage_denominator="all_2024_reported_D_R_Other_or_unassigned_House_votes",
        contribution_units="Democratic_share_of_reported_D_plus_R_percentage_points",
        no_ballot_definition="modeled_prior_reported_House_votes_transitioning_to_no_ballot_within_the_assumed_eligible_frame",
        no_house_choice_definition="ballots_minus_reported_House_candidate_choices_including_unreported_unopposed_choices_and_exhaustion",
        profiles=list(PROFILES), families=list(FAMILIES), party_persistence=list(PARTY_PERSISTENCE), home_persistence=list(HOME_PERSISTENCE),
        frame_churn=list(FRAME_CHURN), ballot_benchmark_scales=list(BALLOT_SCALE), ranges_are_confidence_intervals=False,
        local_allocation=False, quick_development_preview=quick)
    viewer = dict(**metadata, rows=records)
    (output/"viewer-data.json").write_bytes(encoded(viewer))
    stream = io.StringIO(newline=""); writer=csv.DictWriter(stream,fieldnames=list(point_rows[0]),lineterminator="\n");writer.writeheader();writer.writerows(point_rows)
    (output/"complete-state-comparisons.csv").write_text(stream.getvalue())
    (output/"summary.json").write_bytes(encoded(dict(**metadata, total_scenarios=sum(r["queries"] for r in records), feasible_scenarios=sum(r["feasible_scenarios"] for r in records))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args(); build(args.inputs, args.output, args.quick)
