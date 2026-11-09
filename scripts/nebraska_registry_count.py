"""Use the source's registry-filtered count, not VEP; preserve PDF blank columns."""

import argparse
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from .washington_register_control import civic_source, csv_bytes, encoded


BASELINE_SHA="bb13c57bba29b96329af131ef490b5043cc376297a659027f84be5580a4598f9"
PDF_SHA="a9cad90c4816db72bb5cd87f9b69e28e94ef7ed82c0b9c6b9d75909173466a66"
NATIVE_SHA="80c1c838cb2cf9a6e4434eec010534468ba4e8bdd3590775bb4289bb59766228"
URL="https://sos.nebraska.gov/sites/default/files/doc/elections/vrstats/2026VR/Statewide-November-2026.pdf"
RIGHTS=(226.5,282.7,338.3,393.9,449.4,505.7,561.2,617.9)
LABELS=["Republican","Democratic","Libertarian","Legal Marijuana NOW","Nebraska Working People",
        "America First","Nonpartisan","Grand Total"]
CONTROL="ne-2026-native-registry-eligible-count-processed-20261101"
MEASURE="native_registration_system_eligible_to_vote_filtered_count_not_vep"
BASIS="native_registry_eligible_to_vote_Grand_Total_source_filter_not_estimated_eligible_population"


def parse_pages(pages, literal_headers=False):
    if len(pages)!=7:raise ValueError("Changed complete native PDF page coverage")
    rows=[]
    for number,page in enumerate(pages,1):
        text=" ".join(page["text"].split())
        if ("Count of Voters Eligible to Vote" not in text or "Vr Statistics Count Report" not in text):
            raise ValueError("Changed native registry-filtered report identity; not VEP")
        if "Processed: 11/01/2026 2:00 AM" not in text or "Printed: 11/02/2026 8:27 AM" not in text:
            raise ValueError("Changed native processed/printed clocks")
        if abs(page["width"]-792)>0.1 or abs(page["height"]-612)>0.1:
            raise ValueError("Changed native table geometry")
        # pdfplumber merges some overprinted header glyphs; retain those artifacts.
        headers={word[4] for word in page["words"] if 165<word[1]<205}
        required=set("Republican Democratic Libertarian Legal Marijuana NOW Working People Nonpartisan Grand Total".split())
        if literal_headers:
            required.update(("Nebraska","America","First"))
        if not required<=headers:
            raise ValueError("Changed native registration-affiliation column headers")
        expected=15 if number<7 else 4
        # Continuation pages start three points above the first-page body grid.
        origin=212.6 if number==1 else 209.6
        by_row={row:dict(labels=[],counts=[None]*8) for row in range(expected)}
        for word in page["words"]:
            x0,y0,x1,y1,literal=word
            if not 200<y0<565:continue
            row=round((y0-origin)/24)
            if row not in by_row or abs(y0-(origin+24*row))>2:
                raise ValueError("Unreviewed native body row position")
            if x0<171:
                if not re.fullmatch(r"[A-Za-z]+",literal):raise ValueError("Changed native county label")
                by_row[row]["labels"].append((x0,literal))
            elif re.fullmatch(r"\d[\d,]*",literal):
                position=min(range(8),key=lambda col:abs(x1-RIGHTS[col]))
                if abs(x1-RIGHTS[position])>4 or by_row[row]["counts"][position] is not None:
                    raise ValueError("Unreviewed or duplicate native numeric column")
                by_row[row]["counts"][position]=int(literal.replace(",",""))
            else:raise ValueError("Unreviewed native table cell")
        for row,values in by_row.items():
            label=" ".join(word for _,word in sorted(values["labels"]))
            if not label:raise ValueError("Missing native geography row")
            rows.append(dict(jurisdiction_literal=label,source_page=number,
                             native_row_position=row+1,counts=values["counts"]))
    return rows


def registry_frame(first,second):
    rows,other=parse_pages(first,literal_headers=True),parse_pages(second)
    signature=lambda row:("".join(row["jurisdiction_literal"].split()),row["source_page"],row["native_row_position"],row["counts"])
    if [signature(row) for row in rows]!=[signature(row) for row in other]:
        raise ValueError("Independent native coordinate readers disagree")
    parents=[row for row in rows if row["jurisdiction_literal"]=="Grand Total"]
    counties=[row for row in rows if row["jurisdiction_literal"]!="Grand Total"]
    if len(parents)!=1:raise ValueError("Missing or duplicate native Grand Total; no county/party fallback")
    if len(counties)!=93 or len({row["jurisdiction_literal"] for row in counties})!=93:
        raise ValueError("Incomplete or duplicate native 93-county inventory")
    parent=parents[0]
    if type(parent["counts"][-1])is not int or parent["counts"][-1]<=0:
        raise ValueError("Missing explicit positive native statewide registry total")
    accounting,diagnostics=[],[]
    for row in rows:
        if type(row["counts"][-1])is not int:raise ValueError("Missing native county total; no party-sum repair")
        missing=[LABELS[index] for index,value in enumerate(row["counts"][:-1]) if value is None]
        known=sum(value for value in row["counts"][:-1] if value is not None)
        diagnostics.append(dict(scope=row["jurisdiction_literal"],check="observed_party_subtotal_minus_native_total",
            native_parent=row["counts"][-1],observed_child_subtotal=known,unknown_children=missing,
            complete_equation_qualified=not missing,difference=known-row["counts"][-1],
            blanks_not_recovered_by_complement=True))
        for position,(label,value) in enumerate(zip(LABELS,row["counts"]),1):
            accounting.append(dict(jurisdiction_literal=row["jurisdiction_literal"],source_page=row["source_page"],
                native_row_position=row["native_row_position"],native_column_position=position,
                native_column_label=label,native_count=value,native_cell_state="blank" if value is None else "observed_numeric",
                missing_is_zero=False,registry_filter_not_generic_vep=True,affiliation_not_party_voting=True))
    for index,label in enumerate(LABELS):
        observed=[row["counts"][index] for row in counties if row["counts"][index]is not None]
        missing=[row["jurisdiction_literal"] for row in counties if row["counts"][index]is None]
        diagnostics.append(dict(scope="all93counties",check=label+"_sum_minus_native_state_parent",
            native_parent=parent["counts"][index],observed_child_subtotal=sum(observed),unknown_children=missing,
            complete_equation_qualified=not missing and parent["counts"][index]is not None,
            difference=sum(observed)-parent["counts"][index] if parent["counts"][index]is not None else None,
            blanks_not_recovered_by_complement=True))
    return parent["counts"][-1],rows,accounting,diagnostics


def build(inputs):
    baseline=(inputs/"baseline-complete-analysis.zip").read_bytes()
    native=(inputs/"complete-nebraska-native-inputs.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest()!=BASELINE_SHA or hashlib.sha256(native).hexdigest()!=NATIVE_SHA:
        raise ValueError("Changed complete version19 baseline or pinned sufficient native input")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        sums=json.loads(archive.read("checksums.json"))
        if set(archive.namelist())!=set(sums)|{"checksums.json"}:raise ValueError("Changed complete native input inventory")
        for name,metadata in sums.items():
            body=archive.read(name)
            if len(body)!=metadata["bytes"] or hashlib.sha256(body).hexdigest()!=metadata["sha256"]:raise ValueError("Changed sufficient native input")
        if hashlib.sha256(archive.read("registration.pdf")).hexdigest()!=PDF_SHA:raise ValueError("Changed pinned original PDF")
        views=json.loads(archive.read("coordinate-views.json"))
    total,rows,accounting,diagnostics=registry_frame(views["pymupdf"],views["pdfplumber"])
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read=lambda name:list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states,controls,scenarios=(read(name) for name in ("complete-state-control-query.csv","complete-native-control-dispositions.csv","complete-conditional-registered-scenarios.csv"))
    if (len(states),len(controls),len(scenarios))!=(51,36,25):raise ValueError("Changed complete version19 coverage")
    target=next(row for row in states if row["state_code"]=="NE")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"]!="False":raise ValueError("Do not duplicate Nebraska frame")
    source=next(row for row in civic_source(baseline)["participation"] if row["scope"]=="NE" and row["dimension"]=="overall")
    with localcontext() as context:
        context.prec=80
        weight,voter,nonvoter=(Decimal(source[key]) for key in ("weight","modeled_voter_weight","modeled_nonvoter_weight"))
        if weight<=0 or voter+nonvoter!=weight or min(voter,nonvoter)<0 or str(source["n"])!=target["civic_source_n"]:raise ValueError("Changed full public Civic denominator")
        modeled,nonmodeled=total*(voter/weight),total*(nonvoter/weight)
        if abs(modeled+nonmodeled-total)>Decimal("1e-60"):raise ValueError("Conditional source-registry partition failed")
    time="Native Processed11/01/2026 2:00AM; Printed11/02/2026 8:27AM; timezone/cutoff unknown, neither is a live update"
    target.update(control_id=CONTROL,control_measure=MEASURE,control_native_numerator=None,
        control_registered_denominator=total,control_denominator_basis=BASIS,control_native_time=time,
        control_source_url=URL,conditional_registered_frame_scenario_available="True")
    control=dict(controls[0])
    control.update(id=CONTROL,state_code="NE",year=2026,geographic_level="state",geography="Nebraska source-filtered registration statistics",
        source_family=URL,measure=MEASURE,native_measure="Count of Voters Eligible to Vote in registration-system statistics, not generic VEP",
        numerator=None,denominator=total,denominator_basis=BASIS,
        denominator_label="Explicit native filtered registry Grand Total; eligibility/filter definition and active/inactive status not independently qualified",
        source_time_label=time,source_url=URL,native_status="Administrative registry statistics report, not election counting/certification",
        source_kind="reviewed_public_registration_system_filtered_count",
        scope_notes="All93counties/eight count columns retained. Blank cells not zero/complement recoveries. Native party affiliations not votes; no legal eligibility or general eligible-population certification.",
        selected_state_reference=False,disposition="source_filtered_registry_frame_no_independent_population_or_native_ballot_reference")
    controls.append(control)
    scenario=dict(scenarios[0])
    scenario.update(year=2026,state_code="NE",control_id=CONTROL,control_measure=MEASURE,
        control_native_status=control["native_status"],native_registered_denominator=total,native_denominator_basis=BASIS,
        source_time_label=time,source_url=URL,civic_source_n=source["n"],civic_weight=source["weight"],
        civic_modeled_voter_weight=source["modeled_voter_weight"],civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
        conditional_modeled_voter_count=str(modeled),conditional_modeled_nonvoter_count=str(nonmodeled),
        reported_cast_ballot_measure_control=None,reported_cast_minus_conditional_modeled_voter_count=None,
        assumption="source-filtered administrative registry count is exchangeable with statewide source-weighted survey propensity; not VEP/legal eligibility or population validation",
        scenario_units="native_registry_filtered_eligible_count_units_not_generic_vep_or_observed_people")
    scenarios.append(scenario)
    complete=[row for row in diagnostics if row["complete_equation_qualified"]]
    qualification=dict(native_report_title="Count of Voters Eligible to Vote",native_registry_filtered_parent=total,
        source_is_administrative_registration_statistics_not_estimated_eligible_population=True,
        generic_voting_eligible_population_estimate=None,independent_legal_eligibility_certification=False,
        active_inactive_status_qualified=False,registry_eligibility_filter_definition_independently_qualified=False,
        native_processed_clock="11/01/2026 2:00 AM",native_printed_clock="11/02/2026 8:27 AM",
        native_timezone=None,independently_qualified_registration_cutoff=None,processed_printed_not_live_update_or_cutoff=True,
        explicit_native_parent_not_party_or_county_derived=True,all93county_and752count_slots_preserved=True,
        independent_coordinate_readers_agree=True,blank_count_cells=sum(row["native_count"]is None for row in accounting),
        primary_literal_headers_and_secondary_unmerged_header_fragments_checked=True,
        secondary_merged_header_glyph_artifacts_retained_not_fuzzy_relabelled=True,
        source_party_affiliation_not_vote_choice=True,blanks_not_zero_or_complements=True,
        native_accounting_checks=diagnostics,complete_equation_discrepancies=[row for row in complete if row["difference"]],
        source_population_transport_validated=False,generic_cast_ballot_measure_approved=False,
        selected_native_statewide_ballots=None,native_minus_model=None,observed_staying_home=None,
        design_confidence_interval=None,demographic_population=None,county_or_group_survey_allocation=False,
        derived_state_rate_approved=False,maps_approved=False,counting_completion_approved=False,certification_approved=False,
        legacy_registered_denominator_column_explicitly_qualified_as_filtered_registry_units=True,
        montana_denied_registration_index_route_stopped=True,nevada_iframe_discovery_not_promoted_to_native_data=True)
    frame=dict(state_code="NE",year=2026,native_registry_filtered_parent=total,
        native_processed_clock="11/01/2026 2:00 AM",native_printed_clock="11/02/2026 8:27 AM",native_timezone=None,
        native_registration_cutoff=None,source_filtered_registry_count_not_generic_vep=True,
        independent_population_or_legal_eligibility_validation=False,
        conditional_modeled_participant_units=str(modeled),conditional_modeled_nonparticipant_units=str(nonmodeled),
        selected_native_statewide_ballots=None,native_minus_model=None,observed_staying_home=None,rate_approved=False,map_approved=False)
    return {"complete-state-control-query.csv":csv_bytes(states),
        "complete-native-control-dispositions.csv":csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv":csv_bytes(scenarios),
        "complete-native-registry-accounting.csv":csv_bytes(accounting),
        "complete-nebraska-filtered-registry-frame.csv":csv_bytes([frame]),
        "source-qualification.json":encoded(qualification),
        "summary.json":encoded(dict(state_and_dc_rows=51,source_control_records=37,conditional_scenarios=26,
            source_filtered_registry_frame_added=1,native_statewide_ballot_controls_added=0,native_county_rows=93,
            native_count_slots=752,native_missing_count_cells=qualification["blank_count_cells"],
            native_registry_filtered_parent=total,complete_equation_discrepancies=len(qualification["complete_equation_discrepancies"]),
            all_fifty_unaffected_states_twenty_five_prior_frames_and_thirty_six_controls_preserved=True,no_new_website_view=True))}


def export(inputs,output):
    if output.exists():raise ValueError("Do not overwrite a completed analysis")
    files=build(inputs)
    for name in ("baseline-complete-analysis.zip","complete-nebraska-native-inputs.zip"):files["inputs/"+name]=(inputs/name).read_bytes()
    for name in ("nebraska_registry_count.py","extract_nebraska_registry.py","washington_register_control.py"):
        files["scripts/"+name]=Path(__file__).with_name(name).read_bytes()
    name="tests/test_nebraska_registry_count.py";files[name]=Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"]=(
        "Nebraska: source-filtered registry counts, not observed participation\n\n"
        "The native 'Count of Voters Eligible to Vote' Grand Total is 1,265,022.\n"
        "This registration-system report is NOT an estimated voting-eligible\n"
        "population (VEP) or independent legal-eligibility certification.\n"
        "Processed: November 1, 2026, 2:00 AM. Printed: November 2, 2026, 8:27 AM.\n"
        "Timezone and registration cutoff are unknown; neither clock is a live update.\n\n"
        "All 93 counties, eight count columns and 752 slots are retained. Coordinate\n"
        "mapping preserves 126 blank slots, without zero filling, shifting columns\n"
        "left or recovering blanks by complement. Party affiliations are registry\n"
        "accounting, NOT party votes. Status and eligibility-filter criteria remain\n"
        "unqualified. Raw header glyph artifacts remain in the original views.\n\n"
        "Conditional modeled units assume unvalidated statewide Civic transport.\n"
        "They are not administratively observed people or observed staying home.\n"
        "No native ballots, residual, rate, map, local/group allocation or fabricated\n"
        "design intervals. The legacy denominator column is qualified by its basis\n"
        "and scenario-units fields; it does not rename this source as generic VEP.\n\n"
        "Includes the original PDF, two independent coordinate views, third native\n"
        "text view, headers/clocks, receipts, entire version-19 baseline, maintained\n"
        "reader/shared helpers, tests, every query and checksums.\n\n"
        "python3 -m unittest discover -s tests -p test_nebraska_registry_count.py\n"
        "python3 -m scripts.nebraska_registry_count --inputs inputs --output reproduced\n"
        "\nOptional native refresh requires PyMuPDF, pdfplumber and pypdf:\n"
        "python3 -m scripts.extract_nebraska_registry --pdf ORIGINAL --output NEW\n\n"
        "Montana's denied registration-index route stays stopped. Its full denied\n"
        "body is locally held, not redistributed. Nevada's iframe-only discovery\n"
        "is unqualified: no HTTP 403 status or native numerical input is claimed.\n").encode()
    files["checksums.json"]=encoded({name:dict(bytes=len(body),sha256=hashlib.sha256(body).hexdigest()) for name,body in sorted(files.items())})
    output.mkdir(parents=True)
    for name,body in files.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    with zipfile.ZipFile(output/"complete-analysis.zip","w") as archive:
        for name,body in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type,info.external_attr=zipfile.ZIP_DEFLATED,0o644<<16
            archive.writestr(info,body)
    print(files["summary.json"].decode())


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--inputs",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();export(args.inputs,args.output)
