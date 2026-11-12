"""Read declared historical state spreadsheets/returns without imputing their gaps."""

import argparse
from collections import Counter
import csv
from contextlib import ExitStack
import gzip
import io
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import zipfile

from scripts.historical_precinct_rows import count_status, encoded, pin


PA_FIELDS = [
    "election_year", "election_type", "county_code", "precinct_code",
    "candidate_office_rank", "candidate_district", "candidate_party_rank",
    "candidate_ballot_position", "candidate_office_code", "candidate_party_code",
    "candidate_number", "candidate_last_name", "candidate_first_name",
    "candidate_middle_name", "candidate_suffix", "vote_total", "yes_vote_total",
    "no_vote_total", "us_congressional_district", "state_senatorial_district",
    "state_house_district", "municipality_type_code", "municipality_name",
    "municipality_breakdown_code_1", "municipality_breakdown_name_1",
    "municipality_breakdown_code_2", "municipality_breakdown_name_2",
    "bi_county_code", "mcd_code", "fips_code", "vtd_code", "ballot_question",
    "record_type", "previous_precinct_code", "previous_us_congressional_district",
    "previous_state_senatorial_district", "previous_state_house_district"]
FIELDS = ["year", "state_code", "county_literal", "unit_literal", "unit_kind",
    "office_literal", "candidate_literal", "party_literal", "measure", "count_literal",
    "count_status", "source_sha256", "source_member", "source_table", "source_row",
    "source_column", "source_fields_json", "qualification"]
KS_HEADER = ["County", "Precinct", "Race", "Candidate", "Party", "Votes", "VTD"]


def literal(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def alabama_rows(body, year):
    import xlrd
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        for member in sorted(archive.namelist()):
            if not member.lower().endswith(".xls") or member.startswith("__MACOSX/"):
                continue
            match = re.fullmatch(str(year)+r"-General-(.+)\.xls", member, re.I)
            if not match:
                raise ValueError("Unreviewed Alabama county workbook identity")
            workbook = xlrd.open_workbook(file_contents=archive.read(member),on_demand=True)
            try:
                for sheet in workbook.sheets():
                    if sheet.row_values(0)[:3] != ["Contest Title","Party","Candidate"]:
                        raise ValueError("Unreviewed Alabama table schema: "+member)
                    for row in range(1,sheet.nrows):
                        native = sheet.row_values(row)
                        office,party,candidate = native[:3]
                        for column in range(3,sheet.ncols):
                            unit = literal(sheet.cell_value(0,column))
                            value = sheet.cell(row,column)
                            measure = ("ballots_cast" if str(office).strip()=="BALLOTS CAST - TOTAL" else
                                "registration_stock" if str(office).strip()=="REGISTERED VOTERS - TOTAL" else
                                "native_contest_or_administrative_value")
                            kind = ("pooled_administrative_unit" if re.search(
                                r"ABSENTEE|PROVISIONAL|CURBSIDE|EARLY",unit,re.I) else
                                "parent_total" if unit.strip().upper() in ("TOTAL","GRAND TOTAL") else
                                "native_precinct_label_unjoined")
                            raw = literal(value.value)
                            status = count_status(raw)
                            if value.ctype not in (xlrd.XL_CELL_NUMBER,xlrd.XL_CELL_EMPTY,xlrd.XL_CELL_BLANK):
                                status = "native_noncount_cell"
                            yield dict(county_literal=match[1],unit_literal=unit,unit_kind=kind,
                                office_literal=office,candidate_literal=candidate,party_literal=party,
                                measure=measure,count_literal=raw,count_status=status,
                                source_member=member,source_table=sheet.name,source_row=row+1,
                                source_column=column+1,source_fields_json=json.dumps(dict(
                                    contest=office,party=party,candidate=candidate,unit=unit,
                                    cell_type=value.ctype,value=value.value),ensure_ascii=True),
                                qualification="native_cells_not_summed;registration_zeros_not_qualified_denominators;no_geometry_or_rates")
            finally:
                workbook.release_resources()


def pennsylvania_rows(body, year, documentation):
    text = documentation.decode("ascii")
    expected = re.search(r"Record Count:\s*([\d,]+)",text)
    if not expected or not re.search(r"Requested Year\s+"+str(year),text):
        raise ValueError("Native Pennsylvania year/count documentation is absent")
    total = 0
    for number,values in enumerate(csv.reader(io.StringIO(body.decode("ascii"),newline="")),1):
        if len(values)!=len(PA_FIELDS) or values[0]!=str(year) or values[1]!="G":
            raise ValueError("Pennsylvania native field width or election differs")
        source = dict(zip(PA_FIELDS,values))
        total += 1
        yield dict(county_literal=source["county_code"],unit_literal=source["precinct_code"],
            unit_kind="native_precinct_code_unjoined",office_literal=source["candidate_office_code"],
            candidate_literal=" ".join(source[key] for key in
                ("candidate_first_name","candidate_middle_name","candidate_last_name","candidate_suffix") if source[key]),
            party_literal=source["candidate_party_code"],measure="candidate_or_question_votes",
            count_literal=source["vote_total"],count_status=count_status(source["vote_total"]),
            source_member="",source_table="native_37_field_returns",source_row=number,source_column=16,
            source_fields_json=json.dumps(source,ensure_ascii=True),
            qualification="native_county_code_not_FIPS;yes_no_totals_and_other_native_fields_retained;no_ballot_or_geometry_inference")
    if total!=int(expected[1].replace(",","")):
        raise ValueError("Pennsylvania row count differs from its native companion")


def kansas_rows(body, grids):
    import openpyxl
    workbook = openpyxl.load_workbook(io.BytesIO(body),read_only=True,data_only=False)
    try:
        for sheet in workbook.worksheets:
            header = None
            for number,cells in enumerate(sheet.iter_rows(),1):
                values = [cell.value for cell in cells]
                grids.write(json.dumps(dict(sheet=sheet.title,row=number,values=values,
                    types=[cell.data_type for cell in cells]),default=str,ensure_ascii=True)+"\n")
                if number==1:
                    header=values
                    continue
                if header!=KS_HEADER:
                    continue
                if not any(value is not None for value in values):
                    continue
                source=dict(zip(KS_HEADER,values))
                raw=literal(source["Votes"])
                yield dict(county_literal=literal(source["County"]),unit_literal=literal(source["Precinct"]),
                    unit_kind="native_precinct_label_unjoined",office_literal=literal(source["Race"]),
                    candidate_literal=literal(source["Candidate"]),party_literal=literal(source["Party"]),
                    measure="candidate_or_question_votes",count_literal=raw,count_status=count_status(raw),
                    source_member="",source_table=sheet.title,source_row=number,source_column=6,
                    source_fields_json=json.dumps(source,default=str,ensure_ascii=True),
                    qualification="long_table_only;other_county_worksheet_grids_retained_but_not_merged;no_ballot_or_geometry_inference")
    finally:
        workbook.close()


def compile_products(products_root, output):
    products_root,output=Path(products_root),Path(output)
    manifest=json.loads((products_root/"manifest.json").read_bytes())
    query=products_root/"complete-product-query.json"
    if pin(query)!=manifest["files"]["complete-product-query.json"]:
        raise ValueError("The acquired product query changed")
    products=json.loads(query.read_bytes())
    inputs={}
    for product in products:
        receipt=product["acquisition"]
        if not receipt["acquired"]:
            continue
        path=products_root/"originals"/receipt["sha256"]
        if pin(path)!={key:receipt[key] for key in ("bytes","sha256")}:
            raise ValueError("Acquired native product changed")
        inputs[product["url"]]=path.read_bytes()
    if output.exists():
        existing=json.loads((output/"manifest.json").read_bytes())
        if existing["code"]!=pin(Path(__file__)):
            raise ValueError("Changed source adapters require a new version")
        for name,expected in existing["files"].items():
            if pin(output/name)!=expected:
                raise ValueError("Compiled historical source query changed")
        if set(existing["inputs"])!=set(inputs):
            raise ValueError("Compiled historical input selection differs")
        for product in products:
            if product["url"] in inputs and existing["inputs"][product["url"]]!=pin(
                    products_root/"originals"/product["acquisition"]["sha256"]):
                raise ValueError("Historical source input changed")
        return dict(status="unchanged",source_requests=0,source_parses=0)
    output.mkdir(parents=True)
    counts=Counter()
    dispositions=[]
    with ExitStack() as stack:
        raw=stack.enter_context((output/"complete-source-cell-query.csv.gz").open("wb"))
        gz=stack.enter_context(gzip.GzipFile(fileobj=raw,mode="wb",filename="",mtime=0,compresslevel=3))
        stream=stack.enter_context(io.TextIOWrapper(gz,encoding="utf-8",newline=""))
        writer=csv.DictWriter(stream,fieldnames=FIELDS,lineterminator="\n")
        writer.writeheader()
        for product in products:
            state,year=product["state_code"],product["year"]
            if product["url"] not in inputs:
                dispositions.append(dict(state_code=state,year=year,url=product["url"],status="source_not_acquired"))
                continue
            body=inputs[product["url"]]
            name=unquote(Path(urlsplit(product["url"]).path).name)
            status="original_retained_no_numerical_reduction"
            source_rows=0
            if state=="AL" and name.lower().endswith(".zip"):
                rows=alabama_rows(body,year)
                status="native_wide_cells_exported_ballots_and_stocks_distinct"
            elif state=="PA" and name.startswith("ElectionReturns_") and name.endswith("_PrecinctReturns.txt"):
                companions=[p for p in products if p["state_code"]==state and p["year"]==year
                    and Path(urlsplit(p["url"]).path).name==f"ElectionReturns_{year}_General_ReadMeFile.txt"]
                if len(companions)!=1:
                    raise ValueError("Unique acquired native Pennsylvania companion is required")
                rows=pennsylvania_rows(body,year,inputs[companions[0]["url"]])
                status="all_native_37_field_returns_exported"
            elif state=="KS" and name.endswith(".xlsx"):
                grid_raw=stack.enter_context((output/("grid-"+product["acquisition"]["sha256"]+".jsonl.gz")).open("wb"))
                grid_gz=stack.enter_context(gzip.GzipFile(fileobj=grid_raw,mode="wb",filename="",mtime=0,compresslevel=3))
                grid=stack.enter_context(io.TextIOWrapper(grid_gz,encoding="utf-8",newline=""))
                rows=kansas_rows(body,grid)
                status="native_long_table_exported_other_county_sheets_retained_not_merged"
            else:
                rows=()
                if "VoterRegistration" in name:
                    status="separate_registration_stock_schema_not_inferred_from_returns"
            for row in rows:
                writer.writerow(dict(row,year=year,state_code=state,source_sha256=product["acquisition"]["sha256"]))
                counts[(state,year,row["measure"],row["count_status"])]+=1
                source_rows+=1
            dispositions.append(dict(state_code=state,year=year,url=product["url"],
                sha256=product["acquisition"]["sha256"],status=status,exported_cells_or_rows=source_rows))
    summary=dict(source_products=len(products),exported_source_cells_or_rows=sum(counts.values()),
        counts=[dict(state_code=state,year=year,measure=measure,count_status=status,rows=n)
                for (state,year,measure,status),n in sorted(counts.items())],
        candidate_votes_never_substituted_for_ballots=True,registration_stocks_not_turnout=True,
        kansas_supplemental_county_sheets_not_falsely_merged=True,
        geography_joins_or_cross_year_identity_approved=False)
    (output/"complete-product-dispositions.json").write_bytes(encoded(dispositions))
    (output/"summary.json").write_bytes(encoded(summary))
    (output/"manifest.json").write_bytes(encoded(dict(
        inputs={url:pin(products_root/"originals"/p["acquisition"]["sha256"])
                for p in products for url in [p["url"]] if p["acquisition"]["acquired"]},
        code=pin(Path(__file__)),
        files={p.name:pin(p) for p in output.iterdir() if p.is_file()})))
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--products",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(compile_products(args.products,args.output),sort_keys=True))
