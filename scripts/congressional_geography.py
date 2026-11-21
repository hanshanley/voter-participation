"""Reproduce comparison-specific House boundary decisions from complete Census BEFs."""

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import zipfile

from scripts.participation_intake.contract import encoded, pin


CONTRACT = "participation.congressional_boundary_review.v1"
VERSION = "20261117-01"
REVIEW_SHA256 = "9fc17fce1f678d5b1afc4f91a9206556fe4063a74350a4ba7231d4d0e3c8f4eb"
DIRECTORY = "data/results-intake/district-boundaries/" + VERSION
REVIEW_PATH = DIRECTORY + "/review.json.gz"
NAMES = ("cd119.zip", "cd120.zip", "CD119_BlockSplits.pdf", "CD120_BlockSplits.pdf")
DATA_PATHS = (REVIEW_PATH,) + tuple(DIRECTORY + "/" + name for name in NAMES)
FIPS = dict(item.split(":") for item in (
    "AL:01 AK:02 AZ:04 AR:05 CA:06 CO:08 CT:09 DE:10 FL:12 GA:13 HI:15 "
    "ID:16 IL:17 IN:18 IA:19 KS:20 KY:21 LA:22 ME:23 MD:24 MA:25 MI:26 "
    "MN:27 MS:28 MO:29 MT:30 NE:31 NV:32 NH:33 NJ:34 NM:35 NY:36 NC:37 "
    "ND:38 OH:39 OK:40 OR:41 PA:42 RI:44 SC:45 SD:46 TN:47 TX:48 UT:49 "
    "VT:50 VA:51 WA:53 WV:54 WI:55 WY:56"
).split())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_url(congress, name):
    year = {119: 2025, 120: 2027}[congress]
    return ("https://www2.census.gov/programs-surveys/decennial/rdo/mapping-files/"
            + str(year) + "/" + str(congress) + "-congressional-district-befs/" + name)


def block_rows(stream, congress):
    header = (["GEOID", "CDFP"] if congress == 119 else
              ["GEOID", "STATEFP", "COUNTYFP", "TRACTCE", "BLOCKCE", "CDFP"])
    reader = csv.reader(io.TextIOWrapper(stream, encoding="ascii", newline=""))
    require(next(reader, None) == header, "Census BEF schema differs")
    for row in reader:
        require(len(row) == len(header), "Incomplete Census BEF row")
        geoid, district = row[0], row[-1]
        require(re.fullmatch(r"[0-9]{15}", geoid) is not None
                and re.fullmatch(r"(?:[0-9]{2}|ZZ)", district) is not None,
                "Invalid literal Census block or district")
        if congress == 120:
            require("".join(row[1:5]) == geoid,
                    "Census geographic components differ from GEOID")
        yield int(geoid), district


def insert_blocks(database, table, stream, congress):
    database.execute(f"CREATE TABLE {table} (geoid INTEGER PRIMARY KEY, district TEXT NOT NULL)")
    try:
        database.executemany(f"INSERT INTO {table} VALUES (?,?)", block_rows(stream, congress))
    except sqlite3.IntegrityError as error:
        raise ValueError("Duplicate Census block identity") from error


def membership(stream, congress):
    """Order-independent exact membership; duplicate blocks fail, including identical copies."""
    result = {}
    with tempfile.TemporaryDirectory(prefix="congress-bef-") as scratch:
        database = sqlite3.connect(str(Path(scratch) / "blocks.sqlite3"))
        try:
            database.execute("PRAGMA journal_mode=OFF")
            database.execute("PRAGMA synchronous=OFF")
            database.execute("PRAGMA cache_size=-8192")
            insert_blocks(database, "blocks", stream, congress)
            database.commit()
            for block, district in database.execute("SELECT geoid,district FROM blocks ORDER BY geoid"):
                geoid = f"{block:015d}"
                value = result.setdefault(geoid[:2], {}).setdefault(
                    district, {"blocks": 0, "sha": hashlib.sha256()})
                value["sha"].update((geoid + "\n").encode())
                value["blocks"] += 1
        finally:
            database.close()
    require(bool(result), "Empty Census BEF")
    return {state: {district: {"blocks": value["blocks"], "sha256": value["sha"].hexdigest()}
                    for district, value in districts.items()} for state, districts in result.items()}


def block_changes(past, current, database):
    insert_blocks(database, "past", past, 119)
    insert_blocks(database, "current", current, 120)
    return database.execute("""
        SELECT p.geoid, p.district, c.district FROM past p
        LEFT JOIN current c USING (geoid) WHERE p.district IS NOT c.district
        UNION ALL
        SELECT c.geoid, NULL, c.district FROM current c
        LEFT JOIN past p USING (geoid) WHERE p.geoid IS NULL
        ORDER BY 1
    """)


CHANGE_FILES = ("house-boundary-changed-blocks.csv", "house-boundary-county-exchanges.csv",
                "house-boundary-district-changes.csv")


def change_tables(review, differences):
    """Geographic inventory only, not a population or vote crosswalk."""
    blocks, county_counts, incoming, outgoing = [], Counter(), Counter(), Counter()
    districts = {(row["state_fips"], row["district_code"]): key
                 for key, row in review["decisions"].items()}
    for block, past, current in differences:
        geoid = f"{block:015d}"
        state_fips, county = geoid[:2], geoid[:5]
        before, after = districts.get((state_fips, past)), districts.get((state_fips, current))
        if before is None and after is None:
            continue
        if before is not None:
            outgoing[before] += 1
        if after is not None:
            incoming[after] += 1
        blocks.append((geoid, county, past, current))
        county_counts[(county, past or "", current or "")] += 1
    district_rows = []
    for key, decision in sorted(review["decisions"].items()):
        before, after = (decision[field]["blocks"] for field in ("previous_membership", "current_membership"))
        gained, lost = incoming[key], outgoing[key]
        require(before + gained - lost == after and lost <= before and gained <= after
                and (gained == lost == 0) == decision["whole_block_membership_equal"],
                "Changed-block inventory does not reconcile for " + key)
        district_rows.append((key, before, after, gained, lost, before - lost,
                              len(decision["affected_split_blocks"])))
    return {
        CHANGE_FILES[0]: (("geoid_2020", "county_fips", "cd119_code", "cd120_code"), blocks),
        CHANGE_FILES[1]: (("county_fips", "cd119_code", "cd120_code", "blocks"),
                          [(*key, count) for key, count in sorted(county_counts.items())]),
        CHANGE_FILES[2]: (("district", "cd119_blocks", "cd120_blocks", "blocks_gained", "blocks_lost",
                           "blocks_unchanged", "affected_split_blocks"), district_rows),
    }


def export_changes(originals, review):
    for congress in (119, 120):
        name = f"cd{congress}.zip"
        require({**pin(originals[name]), "url": source_url(congress, name)} == review["evidence"][name],
                "Changed original Census evidence")
    with (tempfile.TemporaryDirectory(prefix="congress-bef-diff-") as scratch,
          zipfile.ZipFile(io.BytesIO(originals["cd119.zip"])) as a,
          zipfile.ZipFile(io.BytesIO(originals["cd120.zip"])) as b,
          a.open("NationalCD119.txt") as past, b.open("NationalCD120.txt") as current):
        database = sqlite3.connect(str(Path(scratch) / "blocks.sqlite3"))
        try:
            database.execute("PRAGMA journal_mode=OFF")
            database.execute("PRAGMA synchronous=OFF")
            tables = change_tables(review, block_changes(past, current, database))
        finally:
            database.close()
    outputs = {}
    for name, (header, rows) in tables.items():
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
        outputs[name] = buffer.getvalue().encode("ascii")
    return outputs


def load_changes(root, review):
    source_dir = Path(root) / DIRECTORY
    return export_changes({name: (source_dir / name).read_bytes() for name in ("cd119.zip", "cd120.zip")},
                          review)


def archive_membership(body, congress):
    national = f"NationalCD{congress}.txt"
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and national in names
                and all("/" not in name and name.lower().endswith(".txt") for name in names),
                "Unexpected Census BEF archive inventory")
        require(all(info.file_size <= 400_000_000 for info in archive.infolist()),
                "Oversized Census BEF member")
        with archive.open(national) as stream:
            result = membership(stream, congress)
        regions = []
        for name in names:
            if name == national:
                continue
            with archive.open(name) as stream:
                regional = membership(stream, congress)
            require(len(regional) == 1
                    and all(rows == result.get(state) for state, rows in regional.items()),
                    "Regional Census BEF differs from national member")
            regions.append({"member": name, "state_fips": next(iter(regional))})
    return result, regions


def split_blocks(body, congress):
    from pypdf import PdfReader

    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(body)).pages)
    require(f"{congress}th Congress" in text
            and "2020 Census block" in text and "This list provides all" in text,
            "Congress or complete split-block declaration differs")
    pattern = (r"\b([0-9]{2})\s+[A-Za-z ]+\s+([0-9]{3})\s+([0-9]{6})\s+"
               r"([0-9]{4})\s+([0-9]{15})\s+([0-9]{2}(?:,[0-9]{2})+)\s+([0-9]{2})\b")
    result = []
    for state, county, tract, block, geoid, districts, assigned in re.findall(pattern, text):
        require(state + county + tract + block == geoid
                and assigned in districts.split(","), "Split-block geographic identity differs")
        result.append({"state_fips": state, "geoid": geoid,
                       "districts": districts.split(","), "tabulated_with": assigned})
    require(len(result) > 0 and len({row["geoid"] for row in result}) == len(result)
            and sorted(row["geoid"] for row in result) == sorted(re.findall(r"\b[0-9]{15}\b", text)),
            "Incomplete or duplicate split-block table")
    return result


def decisions(inventories, splits):
    previous, current = inventories["119"], inventories["120"]
    require(previous.keys() == current.keys()
            and set(previous) == set(FIPS.values()) | {"11", "72"},
            "Complete Census jurisdiction inventory differs")
    result = {}
    for state, code in FIPS.items():
        require(previous[code].keys() == current[code].keys(),
                "Congressional seat inventory differs")
        districts = [district for district in previous[code] if district not in ("ZZ", "98")]
        require(bool(districts) and ("00" not in districts or len(districts) == 1),
                "At-large district identity differs")
        for district in districts:
            before, after = previous[code][district], current[code][district]
            for value in (before, after):
                require(type(value.get("blocks")) is int and value["blocks"] > 0
                        and re.fullmatch(r"[a-f0-9]{64}", value.get("sha256", "")) is not None,
                        "Invalid reviewed block-membership fingerprint")
            affected = [row for rows in splits.values() for row in rows
                        if row["state_fips"] == code and district in row["districts"]]
            holds = []
            if before != after:
                holds.append("changed_2020_block_membership")
            if affected:
                holds.append("split_block_geometry_unresolved")
            key = state + "-" + ("AL" if district == "00" else district)
            result[key] = {
                "district": key, "state_code": state, "state_fips": code,
                "district_code": district, "previous_year": 2024, "current_year": 2026,
                "previous_congress": 119, "current_congress": 120,
                "previous_membership": before, "current_membership": after,
                "affected_split_blocks": sorted({row["geoid"] for row in affected}),
                "whole_block_membership_equal": before == after,
                "boundary_compatible": not holds, "holds": holds, "review_version": VERSION,
                "method": "identical_2020_census_block_union_without_affected_split_blocks",
                "legal_boundary_certification": False,
                "historical_votes_allocated": False, "behavioral_model_qualified": False,
            }
    require(len(result) == 435, "Incomplete voting House district boundary inventory")
    return dict(sorted(result.items()))


def compile_review(originals):
    inventories, regions, splits, evidence = {}, {}, {}, {}
    for congress in (119, 120):
        name, split = f"cd{congress}.zip", f"CD{congress}_BlockSplits.pdf"
        inventories[str(congress)], regions[str(congress)] = archive_membership(
            originals[name], congress)
        splits[str(congress)] = split_blocks(originals[split], congress)
        for filename in (name, split):
            evidence[filename] = {**pin(originals[filename]), "url": source_url(congress, filename)}
    return {"contract": CONTRACT, "version": VERSION, "evidence": evidence,
            "national_memberships": inventories, "regional_copies_verified": regions,
            "split_blocks": splits, "decisions": decisions(inventories, splits)}


def validate_review(review):
    if "split_geometry_review" in review:
        import copy
        from scripts.congressional_split_blocks import apply_review
        original = copy.deepcopy(review)
        extension = original.pop("split_geometry_review")
        original["decisions"] = decisions(original["national_memberships"], original["split_blocks"])
        validate_review(original)
        require(review == apply_review(original, extension),
                "Boundary decisions differ from reviewed split geometry")
        return review
    require(review.get("contract") == CONTRACT and review.get("version") == VERSION,
            "Unreviewed House boundary successor")
    require(set(review.get("evidence", {})) == set(NAMES)
            and set(review.get("split_blocks", {})) == {"119", "120"},
            "Incomplete boundary evidence")
    for congress in (119, 120):
        inventory = review["national_memberships"][str(congress)]
        for split in review["split_blocks"][str(congress)]:
            require(split["geoid"].startswith(split["state_fips"])
                    and len(split["geoid"]) == 15 and split["geoid"].isascii()
                    and split["geoid"].isdigit() and len(split["districts"]) >= 2
                    and len(set(split["districts"])) == len(split["districts"])
                    and split["tabulated_with"] in split["districts"]
                    and all(district in inventory[split["state_fips"]]
                            for district in split["districts"]), "Invalid reviewed split-block identity")
        for name in (f"cd{congress}.zip", f"CD{congress}_BlockSplits.pdf"):
            require(review["evidence"][name]["url"] == source_url(congress, name),
                    "Boundary source URL differs")
    require(review["decisions"] == decisions(review["national_memberships"], review["split_blocks"]),
            "Boundary decisions differ from their complete membership and split evidence")
    return review


def load_review(root, *, include_split_geometry=True):
    path = Path(root) / REVIEW_PATH
    if not path.exists():
        return None
    review = json.loads(gzip.decompress(path.read_bytes()))
    require(pin(encoded(review))["sha256"] == REVIEW_SHA256, "Changed reviewed House boundary policy")
    validate_review(review)
    for name in NAMES:
        expected = review["evidence"][name]
        require(pin((path.parent / name).read_bytes()) == {
            key: expected[key] for key in ("bytes", "sha256")}, "Changed original Census evidence")
    if include_split_geometry:
        from scripts import congressional_split_blocks as split
        return split.apply_review(review, split.load_review(root))
    return review


def comparison_decision(review, district, race):
    row = review["decisions"].get(district)
    require(row is not None and row["state_code"] == race["state_code"]
            and race["chamber"] == "house" and race["voting_house_seat"] is True
            and int(race["seat"]) == (1 if row["district_code"] == "00" else int(row["district_code"]))
            and race["election_date"] == "2026-11-03",
            "House boundary evidence does not match the current race")
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--changes-only", action="store_true",
                        help="Reconcile and export changes against the existing pinned review in --originals")
    args = parser.parse_args(argv)
    require(not args.output.exists(), "Use a new boundary review output directory")
    if args.changes_only:
        review = json.loads(gzip.decompress((args.originals / "review.json.gz").read_bytes()))
        require(pin(encoded(review))["sha256"] == REVIEW_SHA256, "Changed reviewed House boundary policy")
        validate_review(review)
        originals = {name: (args.originals / name).read_bytes() for name in ("cd119.zip", "cd120.zip")}
        changes = export_changes(originals, review)
        args.output.mkdir(parents=True)
        for name, body in changes.items():
            (args.output / name).write_bytes(body)
        print(json.dumps({name: body.count(b"\n") - 1 for name, body in changes.items()}))
        return
    originals = {name: (args.originals / name).read_bytes() for name in NAMES}
    review = validate_review(compile_review(originals))
    args.output.mkdir(parents=True)
    for name in NAMES:
        shutil.copyfile(args.originals / name, args.output / name)
    body = gzip.compress(encoded(review), mtime=0)
    (args.output / "review.json.gz").write_bytes(body[:9] + bytes([3]) + body[10:])
    print(json.dumps({"districts": len(review["decisions"]),
                      "boundary_compatible": sum(row["boundary_compatible"]
                                                 for row in review["decisions"].values())}))


if __name__ == "__main__":
    main()
