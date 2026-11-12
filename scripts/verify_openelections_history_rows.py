"""Compare every compiled cell to original CSVs without importing the compiler."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path


def verify(source):
    source=Path(source)
    jurisdictions=json.loads((source/"complete-jurisdiction-query.json").read_bytes())
    query_path=source/"derived/complete-source-row-query.csv.gz"
    rows=files=cells=checks=0
    aliases=dict(county=("county","county_name"),precinct=("precinct","precinct name","election_district"),
        office=("office","race"),district=("district",),candidate=("candidate",),
        party=("party",),votes=("votes","total_votes"))
    with gzip.open(query_path,"rt",encoding="utf-8",newline="") as stream:
        query=csv.DictReader(stream)
        for jurisdiction in jurisdictions:
            for product in jurisdiction["acquired_files"]:
                receipt=product["acquisition"]
                if not receipt["acquired"]:
                    continue
                body=(source/jurisdiction["state_code"]/"originals"/product["path"]).read_bytes()
                assert len(body)==receipt["bytes"] and hashlib.sha256(body).hexdigest()==receipt["sha256"]
                assert hashlib.sha1(b"blob "+str(len(body)).encode()+b"\0"+body).hexdigest()==product["native_git_blob"]
                try:text=body.decode("utf-8-sig")
                except UnicodeDecodeError:text=body.decode("iso-8859-1")
                native=csv.reader(io.StringIO(text,newline=""))
                header=next(native)
                for number,values in enumerate(native,2):
                    row=next(query)
                    assert json.loads(row["native_fields_json"])==dict(columns=header,values=values)
                    assert row["source_file"]==product["path"] and row["source_commit"]==jurisdiction["commit"]
                    assert row["year"]==str(product["year"]) and row["state_code"]==jurisdiction["state_code"]
                    assert row["source_row"]==str(number)
                    assert row["row_width_status"]==("exact" if len(header)==len(values) else "irregular_native_width_preserved")
                    for field,names in aliases.items():
                        positions=[i for i,name in enumerate(header) if name.strip().casefold() in names]
                        expected=values[positions[0]] if len(positions)==1 and positions[0]<len(values) else ""
                        assert row[field]==expected,field
                    assert "native_modes_not_added_to_totals" in row["qualification"]
                    assert "alternative_source_files_not_merged" in row["qualification"]
                    rows+=1;cells+=len(values);checks+=len(values)+16
                files+=1
        assert next(query,None) is None
    summary=json.loads((source/"derived/summary.json").read_bytes())
    assert rows==summary["source_rows"] and files==summary["source_files"]
    digest=hashlib.sha256()
    with query_path.open("rb") as stream:
        for body in iter(lambda:stream.read(1024*1024),b""):
            digest.update(body)
    return dict(status="pass",all_source_rows_and_every_native_cell_compared=True,
        all_canonical_aliases_independently_checked=True,source_rows=rows,source_files=files,
        native_cells_compared=cells,field_and_metadata_checks=checks,
        no_primary_compiler_imported=True,
        query=dict(bytes=query_path.stat().st_size,sha256=digest.hexdigest()),
        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        not_independent_official_total_geographic_or_turnout_qualification=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        raise ValueError("Do not overwrite a completed verification")
    proof=verify(args.source)
    args.output.write_text(json.dumps(proof,indent=2,sort_keys=True)+"\n")
    print(json.dumps(proof,sort_keys=True))
