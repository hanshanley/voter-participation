"""Verify every district's native DBF identity and raw SHP ring fingerprint independently."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile


def check(condition, message):
    if not condition:
        raise ValueError(message)


def digest(body):
    return hashlib.sha256(body).hexdigest()


def dbf_records(body):
    count, header, width = struct.unpack_from("<IHH", body, 4)
    fields = []
    for offset in range(32, header - 1, 32):
        if body[offset] == 13:
            break
        name = body[offset:offset+11].split(b"\0")[0].decode("ascii")
        kind, length, decimals = chr(body[offset+11]), body[offset+16], body[offset+17]
        fields.append((name, kind, length, decimals))
    check(sum(field[2] for field in fields) + 1 == width, "DBF physical row width differs")
    rows = []
    for index in range(count):
        row = body[header+index*width:header+(index+1)*width]
        check(len(row) == width and row[0] == 32, "Missing or deleted native DBF record")
        record, offset = {}, 1
        for name, kind, length, decimals in fields:
            text = row[offset:offset+length].decode("utf-8").strip()
            check(kind in ("C", "N", "F"), "Unreviewed native DBF field type")
            record[name] = (float(text) if decimals else int(text)) if kind in ("N", "F") and text else text
            offset += length
        rows.append(record)
    return rows


def shp_records(body):
    check(struct.unpack_from(">I", body, 0)[0] == 9994
          and struct.unpack_from(">I", body, 24)[0]*2 == len(body)
          and struct.unpack_from("<II", body, 28) == (1000, 5), "Native SHP header differs")
    offset, records = 100, []
    while offset < len(body):
        index, words = struct.unpack_from(">II", body, offset)
        check(index == len(records)+1, "Native SHP record ordinal differs")
        value = body[offset+8:offset+8+words*2]
        check(struct.unpack_from("<I", value, 0)[0] == 5, "Native SHP record is not polygon")
        parts, points = struct.unpack_from("<II", value, 36)
        check(len(value) == 44+parts*4+points*16, "Native polygon physical extent differs")
        starts = list(struct.unpack_from("<"+"I"*parts, value, 44)) + [points]
        xy = [list(struct.unpack_from("<dd", value, 44+parts*4+i*16)) for i in range(points)]
        rings = [xy[start:end] for start, end in zip(starts, starts[1:])]
        check(starts[0] == 0 and all(start < end for start, end in zip(starts, starts[1:]))
              and all(ring[0] == ring[-1] for ring in rings), "Native polygon rings differ")
        records.append(rings)
        offset += 8+words*2
    check(offset == len(body), "Trailing native SHP data")
    return records


def verify(inputs, output):
    queries = json.loads(gzip.decompress((output / "district-geography.json.gz").read_bytes()))
    paths = json.loads(gzip.decompress((output / "district-paths.json.gz").read_bytes()))
    by_geoid = {row["geoid"]: row for row in queries}
    check(len(by_geoid) == len(queries) == 438, "Complete native district query inventory differs")
    checked, vertices = 0, 0
    for phase, folder, acquisition_name in (
        ("previous", "baseline-originals", "baseline-district-acquisition.json"),
        ("current", "originals", "district-acquisition.json"),
    ):
        acquisition = json.loads((inputs / acquisition_name).read_bytes())
        check(len(acquisition["outcomes"]) == 50, "Incomplete original acquisition")
        for outcome in acquisition["outcomes"].values():
            body = (inputs / folder / outcome["file"]).read_bytes()
            check(len(body) == outcome["receipt"]["bytes"] and digest(body) == outcome["receipt"]["sha256"],
                  "Native archive differs from acquisition receipt")
            stem = outcome["file"][:-4]
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                attributes = dbf_records(archive.read(stem+".dbf"))
                geometries = shp_records(archive.read(stem+".shp"))
            check(len(attributes) == len(geometries), "Native shape/attribute count differs")
            for native, rings in zip(attributes, geometries):
                row = by_geoid[native["GEOID"]][phase]
                ring_body = (json.dumps(rings, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()
                check(row["native_attributes"] == native and row["native_rings_sha256"] == digest(ring_body)
                      and row["native_vertices"] == sum(map(len, rings))
                      and row["native_ring_count"] == len(rings), "Native complete attributes or ring query differs")
                check(by_geoid[native["GEOID"]]["electoral_comparison_qualified"] is False,
                      "Geometry output wrongly qualifies an electoral comparison")
                checked += 1
                vertices += sum(map(len, rings))
    for path in paths["paths"]:
        native = by_geoid[path["geoid"]]["current"]
        check(path["district"] == native["district"] and path["native_rings_sha256"] == native["native_rings_sha256"]
              and path["d"].count("M") == native["native_ring_count"]
              and path["d"].count("Z") == native["native_ring_count"],
              "Projected display path loses native identity or ring inventory")
    with (output / "district-geography.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    check(len(rows) == 438 and all(row["electoral_comparison_qualified"] == "False" for row in rows),
          "CSV query inventory or qualification differs")
    manifest = json.loads((output / "manifest.json").read_bytes())
    for name, expected in manifest["files"].items():
        body = (output / name).read_bytes()
        check(expected == {"bytes": len(body), "sha256": digest(body)}, "Compiled output pin differs")
    return {"passed": True, "native_records": checked, "native_vertices": vertices,
            "original_archives": 100, "voting_districts": 435, "unassigned_areas": 3,
            "independent_stdlib_shp_dbf_reader": True, "new_electoral_qualifications": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(verify(args.inputs, args.output)), flush=True)


if __name__ == "__main__":
    main()
