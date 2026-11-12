"""Package explicit complete factual source/query sets with deterministic metadata."""

import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
import zipfile

from scripts.historical_precinct_rows import encoded,pin


def build(destination,members,instructions):
    destination=Path(destination)
    if destination.exists():
        raise ValueError("A published/scientific package must not be overwritten")
    for prefix in ("originals/","queries/","code/"):
        if not any(name.startswith(prefix) for name in members):
            raise ValueError("Complete originals, queries and code are required, not metadata alone")
    for name,path in members.items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            raise ValueError("Unsafe archive member")
        if name in ("checksums.json","REPRODUCE.txt") or Path(path).is_symlink() or not Path(path).is_file():
            raise ValueError("Invalid/duplicate source member")
    manifest={name:pin(Path(path)) for name,path in sorted(members.items())}
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,"w") as archive:
        for name,path in sorted(members.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.external_attr=0o100644<<16
            info.compress_type=zipfile.ZIP_STORED if str(path).endswith((".gz",".zip")) else zipfile.ZIP_DEFLATED
            info._compresslevel=3
            with Path(path).open("rb") as source,archive.open(info,"w",force_zip64=True) as target:
                shutil.copyfileobj(source,target,1024*1024)
        for name,body in (("checksums.json",encoded(manifest)),("REPRODUCE.txt",instructions.encode())):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.external_attr=0o100644<<16
            archive.writestr(info,body)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("Complete archive failed CRC")
    return dict(**pin(destination),members=len(members)+2,
        all_originals_queries_and_code_included=True,metadata_only=False)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    spec=json.loads(args.spec.read_bytes())
    print(json.dumps(build(args.output,spec["members"],spec["instructions"]),sort_keys=True))
