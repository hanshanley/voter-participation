"""Screen changed House districts for land, without qualifying a vote comparison."""

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import zipfile


SERVICE = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer/10/query"
FIELDS = ("GEOID", "AREALAND", "AREAWATER", "HU100", "POP100", "LWBLKTYP", "VINTAGE")
BOUNDARY_HOLD = ["House boundary hold: changed_2020_block_membership"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(body):
    return hashlib.sha256(body).hexdigest()


def inputs(packet):
    suffixes = ("congress-comparisons.csv", "house-boundary-changed-blocks.csv.gz",
                "house-boundary-district-changes.csv.gz")
    with zipfile.ZipFile(packet) as archive:
        members = {suffix: [name for name in archive.namelist()
                            if name.startswith("queries/") and name.endswith("/" + suffix)]
                   for suffix in suffixes}
        require(all(len(hits) == 1 for hits in members.values()), "Missing or ambiguous source query")
        manifest = json.loads(archive.read("checksums.json"))
        result = {}
        for key, (member,) in members.items():
            body = archive.read(member)
            require(manifest.get(member) == {"bytes": len(body), "sha256": digest(body)},
                    "Changed source query: " + key)
            result[key] = body
        return result


def rows(body, zipped=False):
    return csv.DictReader(io.StringIO((gzip.decompress(body) if zipped else body).decode()))


def roster(queries):
    changes = {r["district"]: r for r in rows(queries["house-boundary-district-changes.csv.gz"], True)}
    by_id, affected = {}, defaultdict(set)
    for row in rows(queries["congress-comparisons.csv"]):
        if (row["chamber"], row["advertised"], json.loads(row["comparison_holds"])) != (
                "house", "True", BOUNDARY_HOLD):
            continue
        baseline = json.loads(row["baseline"])
        district, boundary = baseline["district"], baseline["boundary_eligibility"]
        fips, seat = boundary["state_fips"], boundary["district_code"]
        require(district not in by_id and boundary["district"] == district
                and boundary["state_code"] == row["state_code"] == district[:2]
                and fips.isascii() and len(fips) == 2 and fips.isdigit()
                and seat.isascii() and len(seat) == 2 and seat.isdigit()
                and district[3:] == ("AL" if seat == "00" else seat)
                and changes[district]["affected_split_blocks"] == "0", "Unexpected screen target")
        by_id[district] = fips, seat
    districts = {key: district for district, key in by_id.items()}
    require(len(districts) == len(by_id), "Duplicate reviewed geographic identity")
    for row in rows(queries["house-boundary-changed-blocks.csv.gz"], True):
        geoid, county = row["geoid_2020"], row["county_fips"]
        require(len(geoid) == 15 and geoid.isascii() and geoid.isdigit() and county == geoid[:5],
                "Malformed changed block")
        for field in ("cd119_code", "cd120_code"):
            if target := districts.get((county[:2], row[field])):
                require(geoid not in affected[target], "Duplicate changed block")
                affected[target].add(geoid)
    for district in by_id:
        change = changes[district]
        require(len(affected[district]) == int(change["blocks_gained"]) + int(change["blocks_lost"]) > 0,
                "Incomplete changed-block inventory")
    return {district: sorted(affected[district]) for district in sorted(by_id)}


def query_url(ids):
    return SERVICE + "?" + urlencode({
        "where": "GEOID IN (" + ",".join("'" + geoid + "'" for geoid in ids) + ")",
        "outFields": ",".join(FIELDS), "returnGeometry": "false", "f": "json",
    })


def attributes(body, ids):
    result = json.loads(body)
    require(not result.get("error") and not result.get("exceededTransferLimit"), "Census response incomplete")
    facts = {}
    for feature in result["features"]:
        a = feature["attributes"]
        g = a["GEOID"]
        require(set(a) == set(FIELDS) and g not in facts and a["VINTAGE"] == "70"
                and a["LWBLKTYP"] in ("L", "W", "B")
                and all(type(a[key]) is int and a[key] >= 0
                        for key in ("AREALAND", "AREAWATER", "HU100", "POP100")), "Invalid Census block attributes")
        facts[g] = a
    require(set(facts) == set(ids), "Census attribute inventory differs from request")
    return facts


def water(a):
    return (a["LWBLKTYP"] == "W" and a["AREALAND"] == a["HU100"] == a["POP100"] == 0
            and a["AREAWATER"] > 0)


def screen(affected, fetch):
    facts = {}
    for width in (3, 12):
        ids = set()
        for changes in affected.values():
            if any(not water(facts[g]) for g in changes if g in facts):
                continue
            count = min(width, len(changes))
            samples = (changes[i * (len(changes) - 1) // (count - 1 or 1)] for i in range(count))
            ids.update(g for g in samples if g not in facts)
        ids = sorted(ids)
        for offset in range(0, len(ids), 65):
            batch = ids[offset:offset + 65]
            facts.update(attributes(fetch(query_url(batch)), batch))
    result = []
    for district, changes in affected.items():
        checked = [g for g in changes if g in facts]
        nonwater = [g for g in checked if not water(facts[g])]
        result.append({"district": district, "changed_blocks": len(changes), "checked_blocks": len(checked),
                       "confirmed_nonwater_blocks": len(nonwater), "first_nonwater_witness": nonwater[0] if nonwater else "",
                       "screen": "not_water_only" if nonwater else "all_changes_water" if checked == changes
                       else "incomplete_water_evidence", "comparison_qualified_by_screen": False})
    return result, [facts[g] for g in sorted(facts)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Verified rolling ZIP (collect) or extracted audit inputs (replay)")
    parser.add_argument("output", type=Path)
    parser.add_argument("--collect", action="store_true", help="Fetch exact Census attributes and retain originals")
    args = parser.parse_args()
    root = args.output / "inputs" if args.collect else args.source
    queries = inputs(args.source) if args.collect else {
        p.name: p.read_bytes() for p in (root / "queries").iterdir()}
    affected = roster(queries)
    args.output.mkdir()
    requests = []
    if args.collect:
        (root / "queries").mkdir(parents=True)
        (root / "responses").mkdir()
        for name, body in queries.items():
            (root / "queries" / name).write_bytes(body)
    else:
        ledger = json.loads((root / "requests.json").read_bytes())

    def fetch(url):
        name = f"{len(requests):03d}.json"
        path = root / "responses" / name
        if args.collect:
            with urlopen(url, timeout=30) as response:
                body = response.read(1_000_001)
            require(len(body) <= 1_000_000, "Oversized Census response")
            path.write_bytes(body)
        else:
            body = path.read_bytes()
        receipt = {"name": name, "url": url, "sha256": digest(body)}
        if not args.collect:
            require(len(requests) < len(ledger) and receipt == ledger[len(requests)], "Census receipt differs")
        requests.append(receipt)
        return body

    decisions, blocks = screen(affected, fetch)
    if args.collect:
        (root / "requests.json").write_text(json.dumps(requests, indent=2) + "\n")
    else:
        require(requests == ledger, "Unused Census response in audit input")
    out = args.output / "outputs"
    out.mkdir()
    for name, entries in (("district-water-screen.csv", decisions), ("census-block-evidence.csv", blocks)):
        with (out / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(entries[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(entries)
    print(json.dumps({status: sum(r["screen"] == status for r in decisions)
                      for status in sorted({r["screen"] for r in decisions})}))


if __name__ == "__main__":
    main()
