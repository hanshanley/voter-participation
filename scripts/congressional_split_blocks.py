"""Verify exact split-block fragments separately from the immutable national BEF review."""

import argparse
import copy
import json
import math
from pathlib import Path

from scripts.participation_intake.contract import encoded, pin


CONTRACT = "participation.congressional_split_block_review.v1"
VERSION = "20261118-01"
DIRECTORY = "data/results-intake/district-splits/" + VERSION
REVIEW_PATH = DIRECTORY + "/review.json"
REVIEW_SHA256 = "ab7e5936486b9843c5676537be091cd7a545515f048d2c9c6efeb25d94060147"
NAMES = ("sources.json", "tl_2025_08_cd119.zip", "tl_2026_08_cd120.zip",
         "block.json", "layer.json")
DATA_PATHS = (REVIEW_PATH,) + tuple(DIRECTORY + "/" + name for name in NAMES)
METHOD = "identical_whole_block_membership_and_exact_unsimplified_split_fragments"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prove_fragments(block, previous, current, declared, inventory):
    from shapely.ops import unary_union

    require(block.geom_type in ("Polygon", "MultiPolygon") and block.is_valid
            and not block.is_empty and block.area > 0, "Invalid split-block polygon")
    require(set(previous) == set(current) == set(inventory),
            "Incomplete split-block district inventory")
    fragments = {}
    for phase, shapes in (("119", previous), ("120", current)):
        require(all(shape.geom_type in ("Polygon", "MultiPolygon")
                    and shape.is_valid and not shape.is_empty for shape in shapes.values()),
                "Invalid unsimplified district geometry")
        pieces = {key: shape.intersection(block) for key, shape in shapes.items()}
        members = {key for key, piece in pieces.items() if piece.area > 0}
        require(members == set(declared) and len(members) >= 2,
                "Split-block participating districts differ")
        # Test coverage before clipping: overlay rounding can leave artifacts when
        # separately clipped fragments are subsequently dissolved.
        require(unary_union([shapes[key] for key in sorted(members)]).covers(block),
                "District partition does not cover the complete split block")
        ordered = sorted(members)
        require(all(shapes[left].intersection(shapes[right]).intersection(block).area == 0
                    for index, left in enumerate(ordered) for right in ordered[index + 1:]),
                "Split-block district interiors overlap")
        require(all(pieces[key].is_valid and 0 < pieces[key].area < block.area
                    for key in members), "Split-block fragments are not a proper partition")
        fragments[phase] = pieces
    require(all(fragments["119"][key].equals(fragments["120"][key])
                for key in declared), "Changed split-block fragment")
    return {"complete_district_inventory": sorted(inventory),
            "participating_districts": sorted(declared),
            "unclipped_partition_covers_block": True,
            "overlapping_interiors": False, "proper_split": True,
            "exact_fragment_equality": {key: True for key in sorted(declared)},
            "tolerance_used": False, "geometry_repaired": False}


def compile_review(root):
    from shapely.geometry import Polygon

    from scripts import congressional_geography as geography
    from scripts.house_district_map import read_archive

    root = Path(root)
    original = geography.load_review(root, include_split_geometry=False)
    require(original is not None, "Missing complete national boundary review")
    base = root / DIRECTORY
    sources = json.loads((base / "sources.json").read_bytes())
    require(sources.get("contract") == CONTRACT and sources.get("version") == VERSION
            and sources.get("previous_year") == 2024 and sources.get("current_year") == 2026
            and sources.get("previous_congress") == 119 and sources.get("current_congress") == 120,
            "Wrong split-block election or congressional cycle")
    require(set(sources.get("evidence", {})) == set(NAMES) - {"sources.json"},
            "Incomplete split-block source evidence")
    evidence = {"sources.json": pin((base / "sources.json").read_bytes())}
    for name in NAMES[1:]:
        body = (base / name).read_bytes()
        expected = sources["evidence"][name]
        require(pin(body) == {key: expected[key] for key in ("bytes", "sha256")}
                and expected.get("status") == 200 and bool(expected.get("recorded_at"))
                and expected.get("timestamp_basis") in (
                    "retained_collector_checked_at", "acquisition_batch_completed_at"),
                "Changed split-block source body or receipt")
        evidence[name] = expected
    state, fips = sources["state_code"], sources["state_fips"]
    require(geography.FIPS.get(state) == fips, "Wrong split-block state identity")
    shapes = {}
    for year, congress in ((2025, 119), (2026, 120)):
        name = f"tl_{year}_{fips}_cd{congress}.zip"
        require(name in evidence and evidence[name]["url"] == (
            f"https://www2.census.gov/geo/tiger/TIGER{year}/CD/" + name),
            "Wrong original district geometry source")
        _, shapes[str(congress)] = read_archive((base / name).read_bytes(), state, year, congress)
    layer = json.loads((base / "layer.json").read_bytes())
    response = json.loads((base / "block.json").read_bytes())
    service = ("https://tigerweb.geo.census.gov/arcgis/rest/services/Census2020/"
               "tigerWMS_Census2020/MapServer/10")
    geoid = sources["block_geoid"]
    require(isinstance(geoid, str) and len(geoid) == 15 and geoid.isascii()
            and geoid.isdigit() and geoid.startswith(fips), "Wrong literal split-block GEOID")
    require(evidence["layer.json"]["url"] == service + "?f=pjson"
            and evidence["block.json"]["url"] == service + (
                "/query?f=json&where=GEOID%3D%27" + geoid
                + "%27&outFields=GEOID%2CSTATE%2CCOUNTY%2CTRACT%2CBLOCK"
                "&returnGeometry=true&outSR=4269"),
            "Wrong full-resolution 2020 Census block query")
    require(layer.get("geometryType") == "esriGeometryPolygon"
            and "Query" in layer.get("capabilities", "").split(",")
            and response.get("geometryType") == "esriGeometryPolygon"
            and response.get("spatialReference", {}).get("wkid") == 4269
            and response.get("exceededTransferLimit") is not True
            and "error" not in response and len(response.get("features", [])) == 1
            and "transform" not in response, "Incomplete or quantized split-block geometry")
    feature = response["features"][0]
    require(feature["attributes"] == {
        "GEOID": geoid, "STATE": fips, "COUNTY": geoid[2:5],
        "TRACT": geoid[5:11], "BLOCK": geoid[11:]}, "Wrong split-block attributes")
    rings = feature["geometry"]["rings"]
    require(len(rings) == 1 and len(rings[0]) >= 4 and rings[0][0] == rings[0][-1]
            and all(len(point) == 2 and all(type(value) in (int, float)
                                           and math.isfinite(value) for value in point)
                    and -180 <= point[0] <= 180 and -90 <= point[1] <= 90
                    for point in rings[0]), "Unsupported or invalid split-block rings")
    declarations = {}
    for congress in ("119", "120"):
        matches = [row for row in original["split_blocks"][congress] if row["geoid"] == geoid]
        require(len(matches) == 1, "Missing complete Census split-block declaration")
        declarations[congress] = matches[0]
    require(declarations["119"] == declarations["120"],
            "Split-block declaration changed across congresses")
    declared = {state + "-" + district for district in declarations["119"]["districts"]}
    inventory = {key for key in original["decisions"] if key.startswith(state + "-")}
    checks = prove_fragments(Polygon(rings[0]), shapes["119"], shapes["120"], declared, inventory)
    districts = {}
    for key in sorted(declared):
        row = original["decisions"][key]
        require(row["whole_block_membership_equal"]
                and row["affected_split_blocks"] == [geoid]
                and row["holds"] == ["split_block_geometry_unresolved"],
                "Changed membership or unresolved additional split block")
        districts[key] = {"original_decision": pin(encoded(row)), "split_blocks": [geoid]}
    return {"contract": CONTRACT, "version": VERSION,
            "previous_year": 2024, "current_year": 2026,
            "previous_congress": 119, "current_congress": 120,
            "baseline_review_sha256": geography.REVIEW_SHA256, "evidence": evidence,
            "block_geoid": geoid, "declarations": declarations, "geometry_checks": checks,
            "districts": districts, "method": METHOD,
            "historical_votes_allocated": False, "legal_boundary_certification": False,
            "behavioral_model_qualified": False}


def validate_review(review):
    require(isinstance(review, dict) and review.get("contract") == CONTRACT
            and review.get("version") == VERSION
            and pin(encoded(review))["sha256"] == REVIEW_SHA256,
            "Changed reviewed split-block policy")
    return review


def load_review(root):
    base = Path(root) / DIRECTORY
    review = validate_review(json.loads((Path(root) / REVIEW_PATH).read_bytes()))
    require(set(review["evidence"]) == set(NAMES), "Incomplete split-block evidence")
    for name, expected in review["evidence"].items():
        require(pin((base / name).read_bytes()) == {
            key: expected[key] for key in ("bytes", "sha256")}, "Changed original split-block evidence")
    return review


def apply_review(original, extension):
    from scripts import congressional_geography as geography

    validate_review(extension)
    require(original.get("version") == geography.VERSION
            and pin(encoded(original))["sha256"] == extension["baseline_review_sha256"],
            "Split-block review does not match the complete national boundary policy")
    result = copy.deepcopy(original)
    for key, decision in extension["districts"].items():
        before = result["decisions"][key]
        require(pin(encoded(before)) == decision["original_decision"],
                "Split-block district membership or original decision changed")
        before.update(boundary_compatible=True, holds=[], method=METHOD,
                      split_geometry_review_version=VERSION,
                      split_geometry_review_sha256=REVIEW_SHA256)
    result["split_geometry_review"] = extension
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    require(not args.output.exists(), "Use a new split-block review output")
    body = encoded(compile_review(args.repository))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(body)
    print(json.dumps(pin(body)))


if __name__ == "__main__":
    main()
