"""Compile literal historical candidate returns without inferring turnout or maps."""

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


EXTRA = ["source_partition", "source_row", "vote_count_status",
         "general_non_special", "analysis_qualification"]
OFFICES = ("house", "president", "senate")


def pin(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for body in iter(lambda:stream.read(1024*1024),b""):
            value.update(body)
    return dict(bytes=Path(path).stat().st_size, sha256=value.hexdigest())


def encoded(value):
    return (json.dumps(value,sort_keys=True,indent=2)+"\n").encode()


def count_status(literal):
    if literal == "*":
        return "suppressed"
    if literal in ("", "NA"):
        return "unknown"
    if re.fullmatch(r"-?\d+",literal):
        return "negative_correction" if int(literal)<0 else "reported"
    return "noninteger_native_literal"


def rows_from_partition(path):
    with zipfile.ZipFile(path) as archive:
        member = path.stem+".csv"
        if archive.namelist().count(member) != 1:
            raise ValueError("One exact native CSV is required, not AppleDouble metadata")
        with archive.open(member) as source:
            reader = csv.DictReader(io.TextIOWrapper(source,encoding="latin1",newline=""))
            fields = reader.fieldnames
            required = {"year","stage","special","state_postal","county_fips","jurisdiction",
                        "precinct","candidate","office","district","party","mode","votes"}
            if not fields or len(set(fields)) != len(fields) or not required.issubset(fields):
                raise ValueError("Unexpected native historical-return schema")
            for number,row in enumerate(reader,2):
                if None in row or any(value is None for value in row.values()) or row["year"]!="2016":
                    raise ValueError("Native row width/year changed")
                yield fields,number,row


def compile_rows(source_root, output):
    source_root, output = Path(source_root), Path(output)
    acquisition = json.loads((source_root/"acquisition.json").read_bytes())
    if acquisition["source_commit"] != "5965d5e572dfb9affaf8b295e6ddee94773a6cf8":
        raise ValueError("Review a new source revision before changing the historical contract")
    receipts = {row["native_path"]:row for row in acquisition["source_receipts"]}
    selected = {}
    for office in OFFICES:
        name = f"2016-precinct-{office}/2016-precinct-{office}.zip"
        path = source_root/"source"/name
        if pin(path) != {key:receipts[name][key] for key in ("bytes","sha256")}:
            raise ValueError("Native input differs from its acquisition receipt")
        selected[office] = path
    settings = dict(inputs={office:pin(path) for office,path in selected.items()},
        code=pin(Path(__file__)), source_commit=acquisition["source_commit"])
    recipe = hashlib.sha256(encoded(settings)).hexdigest()
    if output.exists():
        manifest = json.loads((output/"manifest.json").read_bytes())
        if manifest["recipe"] != recipe:
            raise ValueError("Changed inputs or code require a new output directory")
        for name,expected in manifest["files"].items():
            if pin(output/name) != expected:
                raise ValueError("A compiled complete query changed")
        return dict(status="unchanged", source_requests=0, source_parses=0, directory=str(output))
    output.mkdir(parents=True)
    counts = defaultdict(Counter)
    units = defaultdict(set)
    issues = Counter()
    total = 0
    header = None
    target = output/"complete-source-row-query.csv.gz"
    with target.open("wb") as raw, gzip.GzipFile(fileobj=raw,mode="wb",filename="",mtime=0,compresslevel=3) as compressed:
        with io.TextIOWrapper(compressed,encoding="utf-8",newline="") as stream:
            for office,path in selected.items():
                for fields,number,row in rows_from_partition(path):
                    if header is None:
                        header = fields
                        writer = csv.DictWriter(stream,fieldnames=header+EXTRA,lineterminator="\n")
                        writer.writeheader()
                    if fields != header:
                        raise ValueError("Native office partitions use different ordered schemas")
                    general = row["stage"]=="gen" and row["special"]=="FALSE"
                    status = count_status(row["votes"])
                    qualification = ["literal_candidate_return_not_ballots",
                                     "native_modes_not_summed",
                                     "reporting_unit_scope_and_geometry_unqualified",
                                     "lossless_latin1_text_transport_not_publisher_encoding_certification"]
                    if row["state_postal"] in ("AL","SC"):
                        qualification.append("straight_ticket_accounting_requires_separate_review")
                    if row["county_fips"] in ("","NA"):
                        qualification.append("native_county_identifier_not_supplied")
                    if not general:
                        qualification.append("outside_ordinary_general_selection")
                    writer.writerow(dict(row,source_partition=office,source_row=number,
                        vote_count_status=status,general_non_special=str(general).lower(),
                        analysis_qualification=";".join(qualification)))
                    key = (row["state_postal"],office)
                    counts[key]["source_candidate_rows"] += 1
                    counts[key]["general_non_special_rows"] += general
                    counts[key][status+"_rows"] += 1
                    counts[key]["native_total_mode_rows"] += row["mode"].casefold()=="total"
                    counts[key]["native_county_identifier_missing_rows"] += row["county_fips"] in ("","NA")
                    if general:
                        units[key].add((row["county_fips"],row["jurisdiction"],row["precinct"],row["district"]))
                    issues[(row["state_postal"],office,status,row["stage"],row["special"],row["mode"])] += 1
                    total += 1
    columns = ["state_code","source_partition","source_candidate_rows","general_non_special_rows",
        "reported_rows","suppressed_rows","unknown_rows","negative_correction_rows",
        "noninteger_native_literal_rows","native_total_mode_rows",
        "native_county_identifier_missing_rows","distinct_native_general_scope_keys"]
    with (output/"jurisdiction-office-inventory.csv").open("w",newline="") as stream:
        writer = csv.DictWriter(stream,fieldnames=columns,lineterminator="\n")
        writer.writeheader()
        for (state,office),values in sorted(counts.items()):
            writer.writerow(dict({column:values[column] for column in columns[2:-1]},
                state_code=state,source_partition=office,distinct_native_general_scope_keys=len(units[(state,office)])))
    with (output/"complete-mode-and-count-dispositions.csv").open("w",newline="") as stream:
        writer = csv.writer(stream,lineterminator="\n")
        writer.writerow(["state_code","source_partition","vote_count_status","stage","special","mode","source_rows"])
        writer.writerows([*key,value] for key,value in sorted(issues.items()))
    summary = dict(year=2016, source_commit=acquisition["source_commit"],source_candidate_rows=total,
        jurisdictions=sorted({state for state,office in counts}), office_partitions=list(OFFICES),
        counts_by_partition={office:sum(value["source_candidate_rows"] for (state,part),value in counts.items()
                                           if part==office) for office in OFFICES},
        original_local_and_state_office_partitions_also_acquired=True,
        local_and_state_partitions_not_reduced_by_this_federal_query=True,
        source_fields_preserved=header, arbitrary_mode_sums_or_count_allocations=0,
        ballots_cast_or_group_turnout_derived=False, precinct_geometry_or_cross_year_joins_qualified=False,
        national_precinct_completeness_claimed=False, recipe=recipe)
    summary["text_transport"] = "ISO-8859-1 lossless source-octet mapping; publisher character encoding not certified"
    (output/"summary.json").write_bytes(encoded(summary))
    (output/"manifest.json").write_bytes(encoded(dict(recipe=recipe, settings=settings,
        files={str(path.relative_to(output)):pin(path) for path in sorted(output.iterdir()) if path.is_file()})))
    return dict(summary,directory=str(output))


def package(source_root, results, destination):
    source_root, results, destination = Path(source_root), Path(results), Path(destination)
    if destination.exists():
        raise ValueError("A complete historical source package is immutable")
    acquisition = json.loads((source_root/"acquisition.json").read_bytes())
    members = {}
    for receipt in acquisition["source_receipts"]:
        if not receipt["acquired"]:
            raise ValueError("Cannot package an incomplete acquisition as complete")
        path = source_root/"source"/receipt["native_path"]
        if pin(path) != {key:receipt[key] for key in ("bytes","sha256")}:
            raise ValueError("An original changed before packaging")
        members["source/"+receipt["native_path"]] = path
    members["acquisition.json"] = source_root/"acquisition.json"
    for path in results.iterdir():
        if path.is_file():
            members["queries/"+path.name] = path
    repository = Path(__file__).resolve().parents[1]
    for relative in ["scripts/historical_precinct_rows.py","scripts/acquire_medsl_partitions.py",
                     "tests/test_historical_precinct_rows.py","tests/test_acquire_medsl_partitions.py"]:
        members["code/"+relative] = repository/relative
    for path in sorted((repository/"scripts/participation_intake").glob("*.py")):
        members["code/scripts/participation_intake/"+path.name] = path
    manifest = {name:pin(path) for name,path in sorted(members.items())}
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,"w") as archive:
        for name,path in sorted(members.items()):
            info = zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED if path.suffix in (".zip",".gz") else zipfile.ZIP_DEFLATED
            archive.writestr(info,path.read_bytes())
        archive.writestr("checksums.json",encoded(manifest))
        archive.writestr("REPRODUCE.txt",
            "All five nonduplicated MEDSL2016 office partitions and their MIT license are included.\n"
            "Federal queries preserve every native field; they are not summed turnout or map approvals.\n"
            "With Python3 and no network, run from code:\n"
            "python -m scripts.historical_precinct_rows --source ../ --output ../reproduced\n"
            "No private inputs or additional downloads are needed. Compare all files in queries/\n"
            "with reproduced/. A valid rerun verifies complete output hashes without parsing again.\n")
    return dict(**pin(destination),members=len(members)+2,complete_originals_and_queries=True)


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--package",type=Path)
    args = parser.parse_args()
    result = compile_rows(args.source,args.output)
    if args.package:
        result["complete_download"] = package(args.source,args.output,args.package)
    print(json.dumps(result,sort_keys=True))
