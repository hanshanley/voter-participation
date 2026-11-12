"""Join source-presence evidence without claiming complete precinct turnout or boundaries."""

import argparse
from collections import defaultdict
import csv
import io
import json
from pathlib import Path

from scripts.historical_precinct_rows import encoded, pin
from scripts.precinct_source_batch import STATE_CODES

YEARS=(2016,2018,2020,2022,2024)


def decisions(inputs):
    states=set(STATE_CODES.values())
    grouped=defaultdict(list)
    identities=set()
    for source in inputs["sources"]:
        key=(source["state_code"],source["year"],source["source_id"])
        if key in identities or key[0] not in states or key[1] not in YEARS:
            raise ValueError("Duplicate or unsupported source/state/year evidence")
        identities.add(key)
        if not source["provenance"] or not source["scope"]:
            raise ValueError("Source evidence needs provenance and literal scope")
        grouped[key[:2]].append(source)
    rows=[]
    for year in YEARS:
        for state in sorted(states):
            sources=sorted(grouped[(state,year)],key=lambda s:s["source_id"])
            parsed=[s for s in sources if s.get("compiled_query_available")]
            ballot=[s for s in sources if s.get("native_ballot_field_rows",0)>0]
            scopes=sorted({s["scope"] for s in sources})
            rows.append(dict(year=year,state_code=state,source_products_present=bool(sources),
                compiled_query_available=bool(parsed),
                source_ids=";".join(s["source_id"] for s in sources),
                source_scopes=";".join(scopes),
                parsed_native_rows_or_cells=sum(s.get("parsed_rows_or_cells",0) for s in parsed),
                native_ballot_field_rows=sum(s.get("native_ballot_field_rows",0) for s in ballot),
                ballot_rows_are_not_participant_totals=True,
                existing_presidential_geometry_source=any(s.get("existing_geometry_source") for s in sources),
                newly_approved_geometry_joins=False,complete_precinct_coverage_qualified=False,
                group_turnout_qualified=False,individual_transitions_identified=False,
                disposition=("source_present_scope_and_completeness_still_require_qualification"
                    if sources else "not_in_this_selected_collection_not_global_source_absence"),
                sources_json=json.dumps(sources,sort_keys=True,separators=(",",":"))))
    return rows


def build(inputs_path,output):
    inputs_path,output=Path(inputs_path),Path(output)
    if output.exists():
        raise ValueError("Use a new historical coverage version")
    rows=decisions(json.loads(inputs_path.read_bytes()))
    output.mkdir(parents=True)
    stream=io.StringIO(newline="")
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    (output/"all-255-state-year-decisions.csv").write_text(stream.getvalue(),encoding="utf-8")
    summary=dict(state_year_decisions=len(rows),years={str(year):dict(
        jurisdictions_with_selected_sources=sum(r["source_products_present"] for r in rows if r["year"]==year),
        jurisdictions_with_compiled_queries=sum(r["compiled_query_available"] for r in rows if r["year"]==year),
        no_selected_source=[r["state_code"] for r in rows if r["year"]==year and not r["source_products_present"]])
        for year in YEARS},source_presence_is_not_geographic_or_turnout_completeness=True,
        existing_sources_retained_not_reacquired=True)
    (output/"summary.json").write_bytes(encoded(summary))
    (output/"manifest.json").write_bytes(encoded(dict(inputs=pin(inputs_path),code=pin(Path(__file__)),
        files={p.name:pin(p) for p in output.iterdir() if p.is_file()})))
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.inputs,args.output),sort_keys=True))
