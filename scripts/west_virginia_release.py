"""Use the agency's preliminary ballot reference without claiming certified turnout."""

import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import zipfile

from .washington_register_control import civic_source, csv_bytes, encoded


BASELINE_SHA = "0df62bcce6d586ffff6e3fcc052a6b4634ddcb6e25ec63b9374ec33d599956ef"
SOURCE_SHA = "032919461a058dede04de6b6084a770e04f9efb19fc32e7f505e91d9325935ce"
NATIVE_SHA = "70966b61ce7c483b3039e8a6155ffb9ceefd334d2ebcaa774a84f143ce7ab2d0"
URL = "https://sos.wv.gov/article/wv-secretary-state-kris-warner-announces-canvassing-will-start-monday-november-9"
CONTROL = "wv-2026-native-preliminary-official-release-20261106"
MEASURE = "native_preliminary_ballots_cast_official_agency_release"
BASIS = "registered_voters_in_same_preliminary_release_cutoff_and_status_unspecified"


class FactualText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skipping = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skipping += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skipping:
            self.skipping -= 1

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def extract_facts(body):
    parser = FactualText()
    parser.feed(body.decode("utf-8"))
    text = " ".join(" ".join(parser.parts).split())
    if ("November 6, 2026" not in text or "2026 General Election" not in text
            or "canvassing will start on Monday, November 9" not in text):
        raise ValueError("Changed official release publication/election identity")
    pattern = (r"Preliminary turnout totals for West Virginia['\u2019]s November (\d+) General Election show that "
               r"([\d,]+) ballots were cast statewide, representing ([\d.]+)% of West Virgina['\u2019]s "
               r"([\d,]+) registered voters")
    matches = re.findall(pattern, text)
    if len(matches) != 1 or matches[0][0] != "3":
        raise ValueError("Missing or duplicate native preliminary cast-ballot/register statement")
    _, ballot, pct, register = matches[0]
    modes = re.findall(r"Of those ballots cast, ([\d,]+) were cast early, and ([\d,]+) absentee ballots have been received", text)
    if len(modes) != 1 or "During canvassing" not in text or "provisional ballots" not in text:
        raise ValueError("Missing native mode distinction or preliminary counting qualifier")
    historical = re.findall(r"([\d.]+)% in (2022|2018|2014|2010)", text)
    if len(historical) != 4 or len({year for _, year in historical}) != 4:
        raise ValueError("Incomplete separate source historical-percent context")
    facts = dict(year=2026, state_code="WV", election_date="2026-11-03",
                 publication_date="2026-11-06", source_url=URL, source_original_sha256=hashlib.sha256(body).hexdigest(),
                 native_ballots_cast=int(ballot.replace(",", "")), native_registered=int(register.replace(",", "")),
                 native_printed_pct=pct, native_early_cast=int(modes[0][0].replace(",", "")),
                 native_absentee_received=int(modes[0][1].replace(",", "")),
                 historical_pct={year: value for value, year in historical},
                 preliminary=True, statewide=True, canvass_pending_at_publication=True,
                 count_snapshot_time=None, registration_cutoff_date=None, source_timezone=None,
                 quoted_factual_fragments=[ballot + " ballots were cast statewide", register + " registered voters",
                                          "Preliminary turnout totals", pct + "%"],
                 full_article_prose_app_code_contact_details_and_session_headers_excluded=True)
    qualify_facts(facts)
    return facts


def qualify_facts(facts):
    if (facts["year"] != 2026 or facts["state_code"] != "WV" or facts["election_date"] != "2026-11-03"
            or facts["publication_date"] != "2026-11-06" or facts["preliminary"] is not True
            or facts["statewide"] is not True or facts["canvass_pending_at_publication"] is not True):
        raise ValueError("Changed native preliminary statewide scope")
    if any(facts[field] is not None for field in ("count_snapshot_time", "registration_cutoff_date", "source_timezone")):
        raise ValueError("Publication date is not a native count or registration cutoff")
    ballot, register = facts.get("native_ballots_cast"), facts.get("native_registered")
    if type(ballot) is not int or type(register) is not int or min(ballot, register) <= 0:
        raise ValueError("Missing explicit native cast-ballot or registration parent; no mode/eligible fallback")
    with localcontext() as context:
        context.prec = 80
        exact_pct = Decimal(ballot) / register * 100
        if exact_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != Decimal(facts["native_printed_pct"]):
            raise ValueError("Native percentage disagreement; do not repair source counts")
    if sum(len(quote.split()) for quote in facts["quoted_factual_fragments"]) > 25:
        raise ValueError("Public factual quotation budget exceeded")
    return ballot, register


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "complete-permitted-native-facts.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete version17 baseline or frozen permitted factual inputs")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        sums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(sums) | {"checksums.json"}:
            raise ValueError("Changed complete factual input inventory")
        for name, metadata in sums.items():
            body = archive.read(name)
            if len(body) != metadata["bytes"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient factual input")
        facts = json.loads(archive.read("native-facts.json"))
    if facts["source_original_sha256"] != SOURCE_SHA:
        raise ValueError("Changed frozen official source provenance")
    ballots, registered = qualify_facts(facts)
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 34, 23):
        raise ValueError("Changed complete version17 coverage")
    target = next(row for row in states if row["state_code"] == "WV")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate an existing West Virginia frame")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "WV" and row["dimension"] == "overall")
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or voter + nonvoter != weight or min(voter, nonvoter) < 0 or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state denominator")
        modeled, nonmodeled = registered * (voter / weight), registered * (nonvoter / weight)
        contrast = Decimal(ballots) - modeled
        if abs(modeled + nonmodeled - registered) > Decimal("1e-60"):
            raise ValueError("Conditional source-register partition failed")
    time = "Agency release publication November6,2026; count snapshot/registration cutoff/timezone unknown; preliminary before canvass"
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=ballots,
                  control_registered_denominator=registered, control_denominator_basis=BASIS,
                  control_native_time=time, control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="WV", year=2026, geographic_level="state", geography="West Virginia",
                   source_family=URL, measure=MEASURE, native_measure="Agency preliminary statewide ballots cast, not early/received-ballot sums",
                   numerator=ballots, denominator=registered, denominator_basis=BASIS,
                   denominator_label="Registered voters in same agency statement; active/inactive status and register cutoff unspecified",
                   source_time_label=time, source_url=URL, native_status="Preliminary; canvass pending at publication, counts may change",
                   source_kind="reviewed_primary_agency_preliminary_participation_statement",
                   scope_notes="Publication date is not the count cutoff. Mode/unique-voter/completion details unqualified. Early cast and absentee received are nonadditive. Historical percentages remain unmatched context.",
                   selected_state_reference=True, disposition="selected_source_defined_reference_not_independent_validation")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="WV", control_id=CONTROL, control_measure=MEASURE,
                    control_native_status=control["native_status"], native_registered_denominator=registered,
                    native_denominator_basis=BASIS, source_time_label=time, source_url=URL, civic_source_n=source["n"],
                    civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
                    civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
                    reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
                    assumption="same-release native registered denominator is exchangeable with source-weighted statewide survey propensity; source counting and population cutoffs unqualified",
                    scenario_units="same_release_registered_units_not_administratively_observed_people")
    scenarios.append(scenario)
    comparison = dict(state_code="WV", year=2026, source_publication_date=facts["publication_date"],
                      native_snapshot_time=None, native_registration_cutoff=None, native_ballots_cast=ballots,
                      native_registered=registered, native_printed_pct=facts["native_printed_pct"], preliminary=True,
                      native_early_cast=facts["native_early_cast"], native_absentee_received=facts["native_absentee_received"],
                      mode_counts_not_added_or_relabelled=True,
                      conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
                      native_minus_conditional_participant_units=str(contrast),
                      population_and_counting_cutoffs_independently_matched=False,
                      generic_cast_ballot_measure_approved=False, observed_staying_home=None,
                      rate_approved=False, map_approved=False, county_or_demographic_allocation=False)
    qualification = dict(
        election_date="2026-11-03", publication_date="2026-11-06", publication_not_count_snapshot_time=True,
        native_count_snapshot_time=None, native_registration_cutoff_date=None, source_timezone=None,
        native_ballots_cast=ballots, native_registered_parent=registered, native_printed_pct=facts["native_printed_pct"],
        active_inactive_status_qualified=False, same_release_source_parents_not_inferred_from_early_or_returned_counts=True,
        preliminary=True, canvass_pending_at_publication=True, counting_complete=False, certification_approved=False,
        all_fifty_five_counties_reporting_not_inferred=True, mode_totals_not_added=True,
        absentee_received_not_relabelled_cast=True, historical_percent_denominators_and_comparability_unqualified=True,
        source_population_transport_validated=False, survey_model_not_fitted_to_native_ballots=True,
        native_minus_model_not_validation_or_observed_staying_home=True,
        generic_cast_ballot_measure_approved=False, source_rate_is_preliminary_not_final_turnout=True,
        derived_state_frame_rate_approved=False, maps_approved=False, county_or_demographic_survey_allocation=False,
        observed_staying_home=None, demographic_population=None, design_confidence_interval=None,
        source_original_sha256=SOURCE_SHA, complete_permitted_factual_inputs_included=True,
        full_page_app_code_full_article_prose_contact_details_and_session_headers_not_redistributed=True,
        quoted_factual_words=sum(len(quote.split()) for quote in facts["quoted_factual_fragments"]))
    native_rows = [dict(year=2026, measure=key, native_value=facts[key], role=role) for key, role in (
        ("native_ballots_cast", "preliminary_statewide_agency_cast_reference"),
        ("native_registered", "same_statement_registration_parent_cutoff_unspecified"),
        ("native_printed_pct", "native_preliminary_percent_not_final_turnout"),
        ("native_early_cast", "source_early_cast_not_added_to_state_total"),
        ("native_absentee_received", "source_received_not_relabelled_cast"))]
    native_rows.extend(dict(year=year, measure="native_historical_pct", native_value=value,
                            role="source_context_only_denominator_comparability_unqualified")
                       for year, value in facts["historical_pct"].items())
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-native-participation-facts.csv": csv_bytes(native_rows),
        "complete-source-participation-comparison.csv": csv_bytes([comparison]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=35, conditional_scenarios=24,
            conditional_registration_frame_added=1, native_source_defined_ballot_reference_added=1,
            generic_cast_ballot_controls_added=0, native_fact_rows=len(native_rows),
            all_fifty_unaffected_states_twenty_three_prior_frames_and_thirty_four_controls_preserved=True,
            no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "complete-permitted-native-facts.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("west_virginia_release.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_west_virginia_release.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "WV agency preliminary2026General source463912ballotsCAST/1210385registered/native38.33%.\n"
        "Publication11/6/2026 is NOTcount/registercutoff/timezone; preliminary beforecanvass, no completion/certification.\n"
        "Nativeearly162349/absenteereceived7001 are nonadditive; received is NOT cast. No55countyreporting inference.\n"
        "Historical2010/14/18/22 percentages are unmatched context, NOT comparable populations or native counts.\n"
        "Same-release registered/Civic conditional units assume unvalidated transport. Native-minus-model is NOT validation/stayinghome.\n"
        "Source-defined reference only; generic cast/rate/map/localallocation/population approval withheld like prior native scopes.\n"
        "Complete permitted numerical factual inputs, <=25words short factual quotes and original-byte provenance included.\n"
        "Full original page is privately held, NOT redistributed: appcode/fullprose/contactdetails/sessionheaders excluded.\n"
        "python3 -m unittest discover -s tests -p test_west_virginia_release.py\n"
        "python3 -m scripts.west_virginia_release --inputs inputs --output reproduced\n"
        "Optional factual-source extraction from supplied local original: python3 -m scripts.west_virginia_release --extract-html ORIGINAL --extract-output NEW.json\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) for name, body in sorted(files.items())})
    output.mkdir(parents=True)
    for name, body in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, body in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, body)
    print(files["summary.json"].decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--extract-html", type=Path)
    parser.add_argument("--extract-output", type=Path)
    args = parser.parse_args()
    if args.extract_html:
        if not args.extract_output or args.extract_output.exists():
            raise ValueError("Fresh explicit factual extraction output required")
        raw = args.extract_html.read_bytes()
        if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
            raise ValueError("Changed frozen original")
        args.extract_output.write_bytes(encoded(extract_facts(raw)))
    elif args.inputs and args.output:
        export(args.inputs, args.output)
    else:
        parser.error("Provide --inputs/--output or --extract-html/--extract-output")
