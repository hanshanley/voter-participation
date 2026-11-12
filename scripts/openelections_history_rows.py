"""Preserve every statewide CSV row, including native modes and irregular fields."""

import argparse
from collections import Counter
import csv
import gzip
import io
import json
from pathlib import Path

from scripts.historical_precinct_rows import count_status, encoded, pin


ALIASES=dict(county=("county","county_name"),precinct=("precinct","precinct name","election_district"),
    office=("office","race"),district=("district",),candidate=("candidate",),
    party=("party",),votes=("votes","total_votes"))
FIELDS=["year","state_code","source_commit","source_file","source_row","county","precinct",
    "office","district","candidate","party","votes","vote_count_status","measure",
    "row_width_status","transport_encoding","native_fields_json","qualification"]


def decode_source(body):
    try:
        return body.decode("utf-8-sig"),"utf-8-sig"
    except UnicodeDecodeError:
        return body.decode("latin1"),"latin1_lossless_octet_transport_not_encoding_certification"


def canonical(header,values):
    result={}
    keys=[key.casefold().strip() for key in header]
    ambiguous=[]
    for name,aliases in ALIASES.items():
        indexes=[i for i,key in enumerate(keys) if key in aliases]
        result[name]=values[indexes[0]] if len(indexes)==1 and indexes[0]<len(values) else ""
        if len(indexes)>1:
            ambiguous.append(name)
    office=result["office"].casefold().strip()
    measure=("native_ballots_cast" if office in ("ballots cast","ballots cast - total","ballots_cast") else
             "native_registration_stock" if office in ("registered voters","registered voters - total") else
             "native_candidate_or_question_votes")
    qualifiers=["native_modes_not_added_to_totals","alternative_source_files_not_merged",
                "county_and_precinct_geography_unqualified","not_a_cross_year_boundary_or_person_join"]
    if ambiguous:
        qualifiers.append("ambiguous_fields_withheld:"+",".join(ambiguous))
    if not result["county"]:
        qualifiers.append("county_not_supplied_or_unambiguous;town_or_ward_not_substituted")
    return dict(result,vote_count_status=count_status(result["votes"]),measure=measure,
        row_width_status="exact" if len(header)==len(values) else "irregular_native_width_preserved",
        native_fields_json=json.dumps(dict(columns=header,values=values),ensure_ascii=True,separators=(",",":")),
        qualification=";".join(qualifiers))


def compile_rows(source,output):
    source,output=Path(source),Path(output)
    query=source/"complete-jurisdiction-query.json"
    settings=dict(source_query=pin(query),code=pin(Path(__file__)))
    if output.exists():
        manifest=json.loads((output/"manifest.json").read_bytes())
        if manifest["settings"]!=settings:
            raise ValueError("Changed source inventory or adapter needs a new result version")
        for name,expected in manifest["files"].items():
            if pin(output/name)!=expected:
                raise ValueError("Compiled historical statewide query changed")
        return dict(status="unchanged",source_requests=0,source_parses=0)
    jurisdictions=json.loads(query.read_bytes())
    output.mkdir(parents=True)
    inventories=[]
    counts=Counter()
    with (output/"complete-source-row-query.csv.gz").open("wb") as raw:
        with gzip.GzipFile(fileobj=raw,mode="wb",filename="",mtime=0,compresslevel=3) as compressed:
            with io.TextIOWrapper(compressed,encoding="utf-8",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=FIELDS,lineterminator="\n")
                writer.writeheader()
                for jurisdiction in jurisdictions:
                    state=jurisdiction["state_code"]
                    for product in jurisdiction["acquired_files"]:
                        receipt=product["acquisition"]
                        if not receipt["acquired"]:
                            continue
                        path=source/state/"originals"/product["path"]
                        if pin(path)!={key:receipt[key] for key in ("bytes","sha256")}:
                            raise ValueError("Pinned statewide original changed")
                        text,encoding=decode_source(path.read_bytes())
                        reader=csv.reader(io.StringIO(text,newline=""))
                        header=next(reader)
                        rows=0
                        for number,values in enumerate(reader,2):
                            record=canonical(header,values)
                            writer.writerow(dict(record,year=product["year"],state_code=state,
                                source_commit=jurisdiction["commit"],source_file=product["path"],
                                source_row=number,transport_encoding=encoding))
                            counts[(state,product["year"],record["measure"],record["vote_count_status"])]+=1
                            rows+=1
                        inventories.append(dict(state_code=state,year=product["year"],
                            source_file=product["path"],commit=jurisdiction["commit"],
                            native_fields=header,transport_encoding=encoding,source_rows=rows,
                            source=pin(path)))
    summary=dict(source_files=len(inventories),source_rows=sum(counts.values()),
        year_state_pairs={str(year):len({row["state_code"] for row in inventories if row["year"]==year})
            for year in (2018,2020)},
        counts=[dict(state_code=state,year=year,measure=measure,count_status=status,source_rows=n)
                for (state,year,measure,status),n in sorted(counts.items())],
        native_fields_modes_and_irregular_widths_retained=True,
        candidate_votes_never_substituted_for_ballots=True,
        missing_precincts_or_unreported_vote_modes_not_imputed=True,
        source_presence_is_not_full_precinct_coverage=True)
    (output/"complete-source-file-inventory.json").write_bytes(encoded(inventories))
    (output/"summary.json").write_bytes(encoded(summary))
    (output/"manifest.json").write_bytes(encoded(dict(settings=settings,
        files={p.name:pin(p) for p in output.iterdir() if p.is_file()})))
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(compile_rows(args.source,args.output),sort_keys=True))
