"""Export declared native CSV/TSV archive members with explicit schema recipes."""

import argparse
import csv
import gzip
import io
import json
from pathlib import Path, PurePosixPath
import zipfile

from scripts.historical_precinct_rows import count_status, encoded, pin

FIELDS=["year","state_code","source_url","source_member","source_row","county","unit",
    "office","candidate","party","votes","vote_count_status","measure",
    "native_fields_json","qualification"]


def build(spec_path,source_root,output):
    spec_path,source_root,output=Path(spec_path),Path(source_root),Path(output)
    if output.exists():
        raise ValueError("Use a new native tabular result version")
    spec=json.loads(spec_path.read_bytes())
    output.mkdir(parents=True)
    rows=0
    with (output/"complete-native-row-query.csv.gz").open("wb") as raw:
        with gzip.GzipFile(fileobj=raw,mode="wb",filename="",mtime=0,compresslevel=3) as gz:
            with io.TextIOWrapper(gz,encoding="utf-8",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=FIELDS,lineterminator="\n")
                writer.writeheader()
                for source in spec["sources"]:
                    path=PurePosixPath(source["original_path"])
                    if path.is_absolute() or ".." in path.parts:
                        raise ValueError("Unsafe native original path")
                    original=source_root/str(path)
                    if pin(original)!=source["original_pin"]:
                        raise ValueError("Native original changed")
                    if source.get("container","zip")=="zip":
                        with zipfile.ZipFile(original) as archive:
                            body=archive.read(source["member"])
                    elif source["container"]=="plain":
                        body=original.read_bytes()
                    else:
                        raise ValueError("Unsupported native table container")
                    reader=csv.reader(io.StringIO(body.decode(source["encoding"]),newline=""),
                        delimiter=source["delimiter"])
                    header=next(reader)
                    if header!=source["expected_header"]:
                        raise ValueError("Native table schema changed")
                    columns=source["canonical_columns"]
                    if any(header.count(name)!=1 for name in columns.values()):
                        raise ValueError("Canonical fields require unambiguous native columns")
                    for number,values in enumerate(reader,2):
                        if len(values)!=len(header):
                            raise ValueError("Native table row width differs")
                        for name,expected in source.get("required_values",{}).items():
                            if header.count(name)!=1 or values[header.index(name)]!=expected:
                                raise ValueError("Native election identity differs")
                        selected={name:values[header.index(column)] for name,column in columns.items()}
                        writer.writerow(dict(selected,year=source["year"],state_code=source["state_code"],
                            source_url=source["source_url"],source_member=source.get("member",source["original_path"]),source_row=number,
                            vote_count_status=count_status(selected["votes"]),measure=source["measure"],
                            native_fields_json=json.dumps(dict(columns=header,values=values),
                                ensure_ascii=True,separators=(",",":")),
                            qualification="native_modes_not_summed;literal_unit_flag_not_geometry;no_turnout_denominator_or_cross_year_join"))
                        rows+=1
    summary=dict(source_rows=rows,source_products=len(spec["sources"]),
        all_native_cells_and_mode_columns_retained=True,no_geometry_or_turnout_qualification=True)
    (output/"summary.json").write_bytes(encoded(summary))
    (output/"manifest.json").write_bytes(encoded(dict(spec=pin(spec_path),code=pin(Path(__file__)),
        files={p.name:pin(p) for p in output.iterdir() if p.is_file()})))
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec",type=Path,required=True)
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.spec,args.source_root,args.output),sort_keys=True))
