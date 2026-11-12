"""Export native GIS attribute tables without approving or modifying their geometry."""

import argparse
import csv
import gzip
import io
import json
from pathlib import Path, PurePosixPath
import zipfile

from scripts.historical_precinct_rows import encoded,pin


def build(spec_path,source_root,output):
    import shapefile
    spec_path,source_root,output=Path(spec_path),Path(source_root),Path(output)
    if output.exists():
        raise ValueError("Use a new native GIS result version")
    spec=json.loads(spec_path.read_bytes())
    output.mkdir(parents=True)
    summaries=[]
    for source in spec["sources"]:
        if PurePosixPath(source["source_id"]).name!=source["source_id"] or source["source_id"] in (".",".."):
            raise ValueError("Unsafe source identifier")
        relative=PurePosixPath(source["original_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe native original path")
        original=source_root/str(relative)
        if pin(original)!=source["original_pin"]:
            raise ValueError("Native GIS original changed")
        with zipfile.ZipFile(original) as archive:
            body=archive.read(source["dbf_member"])
        reader=shapefile.Reader(dbf=io.BytesIO(body),encoding=source["encoding"])
        fields=reader.fields[1:]
        names=[field[0] for field in fields]
        header_bytes=int.from_bytes(body[8:10],"little")
        record_bytes=int.from_bytes(body[10:12],"little")
        if names!=source["expected_fields"]:
            raise ValueError("Native GIS attribute schema changed")
        if any(name not in names for name in source["election_fields"]):
            raise ValueError("Requested election fields absent")
        target=output/(source["source_id"]+".csv.gz")
        rows=0
        with target.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw,mode="wb",filename="",mtime=0,compresslevel=3) as gz:
                with io.TextIOWrapper(gz,encoding="utf-8",newline="") as stream:
                    writer=csv.DictWriter(stream,fieldnames=["year","state_code","source_id","source_row",
                        "source_scope","election_fields_json","native_attributes_json","native_raw_fields_json","qualification"],
                        lineterminator="\n")
                    writer.writeheader()
                    for row in reader.iterRecords():
                        values=list(row)
                        native=body[header_bytes+row.oid*record_bytes:header_bytes+(row.oid+1)*record_bytes]
                        raw_values=[]
                        position=1
                        for field in fields:
                            raw_values.append(native[position:position+field[2]].decode("latin1"))
                            position+=field[2]
                        if position!=record_bytes or len(native)!=record_bytes:
                            raise ValueError("Native DBF record width differs")
                        writer.writerow(dict(year=source["year"],state_code=source["state_code"],
                            source_id=source["source_id"],source_row=row.oid+1,source_scope=source["scope"],
                            election_fields_json=json.dumps({name:values[names.index(name)]
                                for name in source["election_fields"]},ensure_ascii=True,separators=(",",":")),
                            native_attributes_json=json.dumps(dict(fields=fields,values=values),
                                ensure_ascii=True,separators=(",",":")),
                            native_raw_fields_json=json.dumps(dict(columns=names,values=raw_values,
                                transport="latin1_lossless_dbf_octets"),ensure_ascii=True,separators=(",",":")),
                            qualification="publisher_compiled_source;source_specific_merging_or_allocation_not_raw_ballot_turnout;geometry_not_approved;demographics_are_resident_context"))
                        rows+=1
        reader.close()
        summaries.append(dict(source_id=source["source_id"],state_code=source["state_code"],
            year=source["year"],scope=source["scope"],native_attribute_rows=rows,
            election_fields=source["election_fields"],source_database_license=source["license"]))
    (output/"summary.json").write_bytes(encoded(dict(products=summaries,no_new_geometry_approval=True,
        allocated_variant_never_substituted_for_election_day_counts=True)))
    (output/"manifest.json").write_bytes(encoded(dict(spec=pin(spec_path),code=pin(Path(__file__)),
        files={p.name:pin(p) for p in output.iterdir() if p.is_file()})))
    return summaries


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec",type=Path,required=True)
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.spec,args.source_root,args.output),sort_keys=True))
