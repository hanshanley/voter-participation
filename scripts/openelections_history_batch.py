"""Collect declared statewide historical CSVs from independent OpenElections repositories."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import threading
from urllib.parse import quote

from scripts.precinct_source_batch import fetch_index, ledger_holds, STATE_CODES
from scripts.participation_intake.contract import encoded, pin
from scripts.participation_intake.engine import Store


DATES={2018:"20181106",2020:"20201103"}


def statewide_files(tree,state):
    if tree.get("truncated"):
        raise ValueError("A truncated inventory cannot qualify statewide source selection")
    answer=[]
    for row in tree["tree"]:
        if row["type"]!="blob":
            continue
        path=PurePosixPath(row["path"])
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe native repository path")
        for year,date in DATES.items():
            if re.fullmatch(date+"__"+state.lower()+r"__general__precinct(?:__[^/]+)?\.csv",path.name,re.I):
                answer.append(dict(row,year=year,state_code=state))
    return sorted(answer,key=lambda row:row["path"])


def supplemental_files(tree,state,prior):
    if tree.get("truncated"):
        raise ValueError("A truncated inventory cannot qualify supplemental selection")
    present={p["year"] for p in prior["acquired_files"] if p["acquisition"]["acquired"]}
    answer=[]
    for row in tree["tree"]:
        if row["type"]!="blob":
            continue
        path=PurePosixPath(row["path"])
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe native repository path")
        for year,date in DATES.items():
            if year in present:
                continue
            prefix=date+"__"+state.lower()+"__general"
            kind=None
            if re.fullmatch(prefix+r"__[a-z0-9]+(?:_[a-z0-9]+)*__precinct\.csv",path.name,re.I):
                kind="county_partition_geography_unqualified"
            elif path.name.casefold()==prefix+"__ward.csv":
                kind="native_ward_not_assumed_precinct"
            elif path.name.casefold()==prefix+"__town.csv":
                kind="native_town_not_assumed_precinct"
            elif path.name.casefold()==prefix+".csv":
                kind="native_unsuffixed_general_schema_requires_review"
            if kind:
                answer.append(dict(row,year=year,state_code=state,source_product_scope=kind))
    return sorted(answer,key=lambda row:row["path"])


def github_json(endpoint):
    result=subprocess.run(["gh","api",endpoint],capture_output=True,text=True)
    if result.returncode:
        raise ValueError("GitHub metadata route stopped without retry: "+result.stderr.strip())
    return json.loads(result.stdout)


def collect(repositories,output,ledger="",metadata_root=None):
    output=Path(output)
    metadata_root=Path(metadata_root) if metadata_root is not None else None
    output.mkdir(parents=True,exist_ok=True)
    local=threading.local()
    stopped=ledger_holds(ledger)
    states=set(STATE_CODES.values())
    selected=[row for row in repositories if row["full_name"].rsplit("-",1)[-1].upper() in states
        and not row.get("private")]
    if len(selected)!=51:
        raise ValueError("Expected the 50 states and DC, excluding the separate US repository")
    completed=output/"complete-jurisdiction-query.json"
    if completed.exists():
        rows=json.loads(completed.read_bytes())
        scope="supplemental_partitions" if metadata_root is not None else "statewide"
        if any(row.get("selection_scope","statewide")!=scope for row in rows):
            raise ValueError("A different source selection requires a new output directory")
        if {row["state_code"] for row in rows}!=states or len(rows)!=51:
            raise ValueError("Held complete jurisdiction inventory changed")
        derived_manifest=output/"derived/manifest.json"
        if derived_manifest.exists():
            expected=json.loads(derived_manifest.read_bytes())["settings"]["source_query"]
            if pin(completed.read_bytes())!=expected:
                raise ValueError("Held source query differs from the accepted numerical reduction")
        count=0
        for row in rows:
            for product in row["acquired_files"]:
                receipt=product["acquisition"]
                if receipt["acquired"]:
                    body=(output/row["state_code"]/"originals"/product["path"]).read_bytes()
                    if pin(body)!={key:receipt[key] for key in ("bytes","sha256")}:
                        raise ValueError("Held statewide original changed")
                    if hashlib.sha1(b"blob "+str(len(body)).encode()+b"\0"+body).hexdigest()!=product["native_git_blob"]:
                        raise ValueError("Held statewide Git blob changed")
                    count+=1
        return dict(status="unchanged",jurisdictions=51,statewide_csv_files_acquired=count,
            source_requests=0,source_parses=0)

    def jurisdiction(repository):
        state=repository["full_name"].rsplit("-",1)[-1].upper()
        directory=output/state
        directory.mkdir(exist_ok=True)
        hold_path=directory/"metadata-hold.json"
        if hold_path.exists():
            return json.loads(hold_path.read_bytes())
        metadata=(metadata_root/state) if metadata_root is not None else directory
        branch_path,tree_path=metadata/"branch.json",metadata/"tree.json"
        try:
            if metadata_root is not None and not (branch_path.exists() and tree_path.exists()):
                raise ValueError("Supplemental collection requires already-held pinned branch/tree metadata")
            if branch_path.exists():
                branch=json.loads(branch_path.read_bytes())
            else:
                branch=github_json("repos/"+repository["full_name"]+"/branches/"+repository["default_branch"])
                branch=dict(name=branch["name"],commit=dict(sha=branch["commit"]["sha"]))
                branch_path.write_bytes(encoded(branch))
            sha=branch["commit"]["sha"]
            if not re.fullmatch(r"[a-f0-9]{40}",sha):
                raise ValueError("An immutable source commit is required")
            if tree_path.exists():
                tree=json.loads(tree_path.read_bytes())
            else:
                tree=github_json("repos/"+repository["full_name"]+"/git/trees/"+sha+"?recursive=1")
                tree_path.write_bytes(encoded(tree))
            if metadata_root is None:
                files=statewide_files(tree,state)
            else:
                prior=json.loads((metadata/"source-query.json").read_bytes())
                if prior["commit"]!=sha or prior["state_code"]!=state:
                    raise ValueError("Supplemental source metadata differs from its pinned acquisition")
                files=supplemental_files(tree,state,prior)
        except ValueError as error:
            held=dict(state_code=state,status="metadata_hold",reason=str(error),acquired_files=[])
            hold_path.write_bytes(encoded(held))
            return held
        if not hasattr(local,"store"):
            local.store=Store(output/"cache")
        acquired=[]
        for row in files:
            url="https://raw.githubusercontent.com/"+repository["full_name"]+"/"+sha+"/"+quote(row["path"],safe="/")
            receipt=fetch_index(local.store,url,stopped)
            if receipt["acquired"]:
                body=(output/"cache/objects"/receipt["sha256"]).read_bytes()
                blob=hashlib.sha1(b"blob "+str(len(body)).encode()+b"\0"+body).hexdigest()
                if blob!=row["sha"] or len(body)!=row["size"]:
                    raise ValueError("OpenElections original differs from its pinned Git blob")
                if body.startswith(b"version https://git-lfs.github.com/spec/"):
                    receipt=dict(receipt,acquired=False,status="LFS_pointer_not_election_rows")
                else:
                    path=directory/"originals"/row["path"]
                    path.parent.mkdir(parents=True,exist_ok=True)
                    if path.exists() and path.read_bytes()!=body:
                        raise ValueError("A held statewide source changed")
                    if not path.exists():
                        path.write_bytes(body)
            acquired.append(dict(path=row["path"],year=row["year"],native_git_blob=row["sha"],acquisition=receipt,
                **({"source_product_scope":row["source_product_scope"]} if metadata_root is not None else {})))
        record=dict(state_code=state,repository=repository["full_name"],commit=sha,
            repository_license=repository.get("license"),status="statewide_file_inventory_not_geographic_completion",
            acquired_files=acquired,no_county_file_requests=metadata_root is None,
            selection_scope="supplemental_partitions" if metadata_root is not None else "statewide",
            independent_collector_not_a_MEDSL_download_mirror=True)
        (directory/"source-query.json").write_bytes(encoded(record))
        return record

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(jurisdiction,selected))
    rows.sort(key=lambda row:row["state_code"])
    (output/"complete-jurisdiction-query.json").write_bytes(encoded(rows))
    summary=dict(jurisdictions=len(rows),
        statewide_csv_files_acquired=sum(p["acquisition"]["acquired"] for row in rows for p in row["acquired_files"]),
        source_requests=sum(p["acquisition"]["source_requests"] for row in rows for p in row["acquired_files"]),
        bytes=sum(p["acquisition"].get("bytes",0) for row in rows for p in row["acquired_files"] if p["acquisition"]["acquired"]),
        year_state_pairs={str(year):sum(any(p["year"]==year and p["acquisition"]["acquired"]
            for p in row["acquired_files"]) for row in rows) for year in DATES},
        not_independent_turnout_or_full_precinct_coverage=True)
    (output/"summary.json").write_bytes(encoded(summary))
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repositories",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--ledger",type=Path,default=Path(__file__).resolve().parents[1]/"SOURCES.md")
    parser.add_argument("--supplemental-from",type=Path,
        help="Reuse held pinned metadata; collect only native partitions missing a statewide CSV")
    args=parser.parse_args()
    repositories=[json.loads(line) for line in args.repositories.read_text().splitlines()]
    repositories=[row for row in repositories if re.fullmatch(r"openelections/openelections-data-[a-z]{2}",row["full_name"])]
    print(json.dumps(collect(repositories,args.output,args.ledger.read_text(),args.supplemental_from),sort_keys=True))
