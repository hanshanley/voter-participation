"""Acquire one pinned publisher partition per office, not duplicate state copies."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import threading
from urllib.parse import quote
import zipfile

from scripts.participation_intake.contract import IntakeError
from scripts.participation_intake.engine import Store


def selected_files(tree, year):
    if tree.get("truncated"):
        raise ValueError("A truncated publisher inventory is not a complete source")
    prefix = str(year)+"-precinct-"
    files = []
    for row in tree["tree"]:
        if row["type"] != "blob":
            continue
        path = PurePosixPath(row["path"])
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe native source path")
        role = None
        if row["path"] in ("LICENSE", "README.md"):
            role = "publisher_documentation"
        elif len(path.parts) == 2 and path.parts[0].startswith(prefix):
            office = path.parts[0][len(prefix):]
            if office in {"house", "president", "senate", "state", "local"}:
                if path.name == path.parts[0]+".zip":
                    role = "nonduplicated_office_partition"
                elif path.suffix == ".md":
                    role = "office_coding_and_coverage"
        if role:
            files.append(dict(row, role=role))
    partitions = [row for row in files if row["role"] == "nonduplicated_office_partition"]
    if len(partitions) != 5:
        raise ValueError("Expected five explicit office partitions, not an inferred national bundle")
    return sorted(files, key=lambda row: row["path"])


def blob_digest(path):
    size = path.stat().st_size
    value = hashlib.sha1(b"blob "+str(size).encode()+b"\0")
    full = hashlib.sha256()
    with path.open("rb") as stream:
        for body in iter(lambda: stream.read(1024*1024), b""):
            value.update(body)
            full.update(body)
    return dict(bytes=size, git_blob=value.hexdigest(), sha256=full.hexdigest())


def acquire(root, year):
    root = Path(root)
    repository = json.loads((root/"repository.json").read_bytes())
    commit = json.loads((root/"commit.json").read_bytes())
    tree = json.loads((root/"tree.json").read_bytes())
    if repository["full_name"] != "MEDSL/official-precinct-returns" or year != 2016:
        raise ValueError("This registered partition layout is the original MEDSL2016 product")
    if repository.get("license", {}).get("spdx_id") != "MIT":
        raise ValueError("Publisher license requires review")
    if not re.fullmatch(r"[a-f0-9]{40}", commit["sha"]):
        raise ValueError("An immutable publisher commit is required")
    files = selected_files(tree, year)
    source = root/"source"
    source.mkdir(exist_ok=True)
    context = threading.local()

    def retrieve(description):
        relative = description["path"]
        path = source/relative
        receipt_path = Path(str(path)+".receipt.json")
        url = "https://raw.githubusercontent.com/"+repository["full_name"]+"/"+commit["sha"]+"/"+quote(relative, safe="/")
        prior = None
        if receipt_path.exists():
            prior = json.loads(receipt_path.read_bytes())
            if prior["url"] != url:
                raise ValueError("Original receipt is bound to another publisher snapshot")
            if prior.get("source_stopped"):
                return dict(prior, reused=True, new_source_requests=0)
        path.parent.mkdir(parents=True, exist_ok=True)
        reused = path.exists()
        origin = "held_original"
        requested = 0
        if not reused:
            if prior and prior.get("acquired"):
                raise ValueError("A previously acquired original disappeared")
            if not hasattr(context, "store"):
                context.store = Store(root/"cache")
            existing = context.store.db.execute("SELECT sha,stopped FROM inputs WHERE url=?", (url,)).fetchone()
            try:
                if existing and existing[1]:
                    raise IntakeError("source_stopped", "Existing shared-store access hold")
                if existing and existing[0]:
                    body = (context.store.root/"objects"/existing[0]).read_bytes()
                    if hashlib.sha256(body).hexdigest() != existing[0]:
                        raise ValueError("Shared-store original changed")
                    origin = "cached_original"
                else:
                    requested = 1
                    body, acquired = context.store.acquire(dict(url=url))
                    origin = acquired["origin"]
            except IntakeError as error:
                stopped = context.store.db.execute("SELECT stopped FROM inputs WHERE url=?", (url,)).fetchone()
                receipt = dict(url=url, source_stopped=bool(stopped and stopped[0]),
                    error=error.as_dict(), acquired=False, native_path=relative,
                    new_source_requests=requested, observed_at=datetime.now(timezone.utc).isoformat(),
                    no_alternative_route_attempted=True)
                receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True)+"\n")
                return receipt
            temporary = Path(str(path)+".part")
            temporary.write_bytes(body)
            actual = blob_digest(temporary)
            if actual["bytes"] != description["size"] or actual["git_blob"] != description["sha"]:
                raise ValueError("Acquired bytes differ from the publisher blob: "+relative)
            temporary.replace(path)
        actual = blob_digest(path)
        if actual["bytes"] != description["size"] or actual["git_blob"] != description["sha"]:
            raise ValueError("Native publisher blob differs: "+relative)
        members = []
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                if archive.testzip() is not None:
                    raise ValueError("Native ZIP failed CRC")
                for member in archive.infolist():
                    native = PurePosixPath(member.filename)
                    if native.is_absolute() or ".." in native.parts:
                        raise ValueError("Unsafe native ZIP member")
                    members.append(dict(name=member.filename, bytes=member.file_size, crc=member.CRC,
                                        directory=member.is_dir()))
        receipt = dict(url=url, status=200, acquired=True, native_path=relative, role=description["role"],
            original_publisher_commit=commit["sha"], reused=reused, new_source_requests=requested,
            origin=origin, observed_at=datetime.now(timezone.utc).isoformat(),
            **actual, zip_members=members, numerical_counts_not_yet_qualified=True)
        if prior and prior.get("acquired"):
            if any(prior[key] != receipt[key] for key in ("bytes", "git_blob", "sha256", "zip_members")):
                raise ValueError("Held original differs from its original acquisition receipt")
            receipt = dict(prior, reused=True, new_source_requests=0)
        else:
            receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True)+"\n")
        return receipt

    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(retrieve, files))
    summary = dict(year=year, source_repository=repository["full_name"], source_commit=commit["sha"],
        license="MIT", source_files=len(receipts), acquired_files=sum(row["acquired"] for row in receipts),
        source_requests=sum(row["new_source_requests"] for row in receipts),
        office_partitions=sum(row["acquired"] and row.get("role")=="nonduplicated_office_partition" for row in receipts),
        original_bytes=sum(row.get("bytes",0) for row in receipts),
        alternative_state_and_RDA_copies_not_double_counted=True,
        complete_collection_not_complete_precinct_or_turnout_coverage=True, source_receipts=receipts)
    manifest = root/"acquisition.json"
    if not manifest.exists():
        manifest.write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    result = acquire(args.root,args.year)
    print(json.dumps({key:value for key,value in result.items() if key!="source_receipts"},sort_keys=True))
