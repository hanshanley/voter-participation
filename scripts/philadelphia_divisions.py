"""Publish Philadelphia's direct division counts on reviewed city reference polygons."""

import copy
import json
import re

from scripts.participation_intake.contract import encoded, observation_id, pin, validate_all
from scripts.results_pdf_county_parent import PHILADELPHIA_FEED, philadelphia_controls


FEED = "PA-philadelphia-division-reference"
SOURCE_ID = "PA-philadelphia-division-ballots"
SCOPE = "precinct/PA"
URL = ("https://services.arcgis.com/fLeGjb7u4uXqeF9q/ArcGIS/rest/services/"
       "Political_Divisions/FeatureServer/0/query?f=geojson&where=1%3D1"
       "&outFields=division_num,short_div_num&outSR=4326&orderByFields=objectid")
POLLING = {
    "url": "https://vote.phila.gov/media/2026_General_Polling_Places.xlsx",
    "bytes": 112753,
    "sha256": "23bf9d022494eee83866c3852d4de1aaab73a1583e9e32f69480407d072a39ae",
}
KEYS = {"bytes": 11923, "sha256": "e595a4d3844e53efbb5758052d0b38d40d55a2dfa9ebbe0768313cde7f4c9fdb"}
POLYGONS = {"bytes": 2419492, "sha256": "7fe40dd2d2bf11c0e4220a133921850e9b0b2ae81b3078634295f37f34d9021b"}
REVIEWED_AT = "2026-11-19T07:09:30Z"
LABEL = "City of Philadelphia division reference; not certified 2026 legal boundaries"
NOTE = ("Division totals are source counts, not full turnout rates. Mail ballots not assigned to "
        "a division remain in the separate county total and are not allocated.")
MODES = ("official", "uf_vap", "uf_vep")
LAYER_FILE = "counts/precinct-PA.json.gz"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def geometry_controls(data):
    features, source = data["features"], data["source"]
    require(data["polling_place_inventory"] == POLLING
            and source["url"] == URL and type(source["bytes"]) is int and source["bytes"] > 0
            and re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            and pin(encoded([row[0] for row in features])) == KEYS
            and pin(encoded(features)) == POLYGONS,
            "Philadelphia reference no longer matches the reviewed election inventory and polygons")
    return features


def parse_geometry(body):
    require(len(body) <= 5_000_000, "Philadelphia geometry exceeds intake bounds")
    value = json.loads(body)
    require(value["type"] == "FeatureCollection", "Missing Philadelphia division collection")
    rows, short_conflicts = [], []
    for feature in value["features"]:
        props = feature["properties"]
        key = props["division_num"]
        require(re.fullmatch(r"[0-9]{4}", key) and feature["geometry"]["type"] == "Polygon",
                "Changed Philadelphia division geometry")
        if props["short_div_num"] != key[2:]:
            short_conflicts.append([key, props["short_div_num"]])
        rows.append([key, feature["geometry"]])
    data = {"source": {"url": URL, **pin(body)}, "features": sorted(rows, key=lambda row: row[0]),
            "polling_place_inventory": POLLING, "short_field_conflicts": short_conflicts,
            "participation_observation_qualified": False}
    geometry_controls(data)
    return data


def collect(collector):
    return collector.capture(FEED, URL, parse_geometry, equivalent=lambda old, new: all(
        old[key] == new[key] for key in ("features", "short_field_conflicts")))


def division_row(parent, source_row):
    unit, registered, ballots, polls, mail, provisional = source_row
    name = "Division " + unit
    geography = "PA:philadelphia:division:" + unit
    measure = {**parent["measure"], "id": "division-ballots-cast"}
    identity = observation_id(SOURCE_ID, parent["election"]["id"], geography, measure["id"], "all_methods")
    view = {key: parent["view"][key] for key in ("state_code", "year", "county_id", "county", "county_fips",
            "mode", "source_mode", "status", "source_status_literal", "source_url", "source_sha256",
            "source_update_label", "source_update_timezone", "automatic_source_refresh",
            "cast_ballot_count_qualified", "unique_voter_count_qualified", "participation_measure_kind",
            "participation_measure_literal")}
    view.update(unit=name, unit_key=unit, unit_kind="precinct", geography_level="precinct",
                ballots=ballots, denominator=None, reported_pct=None, registered=None, maps_approved=False,
                denominator_basis="division_rate_not_qualified",
                participation_measure_label="Division ballots cast", source_reporting_label=NOTE,
                rate_withheld_reason="Unassigned county mail ballots are not included in division totals.",
                native_record={"division_registered_voters": registered, "polling_place": polls,
                               "mail": mail, "provisional": provisional}, quality=[NOTE])
    return {
        "contract": parent["contract"], "id": identity, "election": parent["election"], "measure": measure,
        "geography": {"id": geography, "name": name, "state_code": "PA", "level": "precinct",
                      "parent_id": parent["geography"]["id"],
                      "join": {"status": "unreviewed", "feature_key": None, "reference_id": None,
                               "evidence": "Exact division reference kept in a separate reviewed layer."}},
        "source": {**parent["source"], "id": SOURCE_ID, "selector": {"ward_division": unit},
                   "fields": copy.deepcopy(view)},
        "count": {"status": "reported", "value": ballots, "literal": ballots}, "view": view,
        "source_clock": parent["source_clock"], "denominator": None,
        "reporting_status": {"literal": view["source_status_literal"], "reported_units": None,
                             "total_units": None, "complete": None},
        "quality": {"notes": [NOTE], "conflicts": []},
    }


def retain_layer(native, shard, declaration):
    from scripts.results_county_frame import decode
    from scripts.statewide_ballot_totals import compressed

    if LAYER_FILE not in native:
        return native
    layer = decode(native[LAYER_FILE])
    observations = {row["id"]: row for row in shard["records"] if row["source"]["id"] == SOURCE_ID}
    require(len(observations) == len(layer["rows"])
            and all(observations.get(row["observation"]["id"]) == row["observation"]
                    for row in layer["rows"]), "Philadelphia last-good divisions differ")
    layer["source_counts"].update({key: declaration[key] for key in ("bytes", "sha256")})
    body = compressed(layer)
    index = json.loads(native["index.json"])
    index["layers"][SCOPE].update(pin(body))
    index["config"]["state_metadata"]["PA"]["notes"] = (
        "Retained last-good Philadelphia division map. A compatible new count and boundary frame was unavailable.")
    return dict(native, **{LAYER_FILE: body, "index.json": encoded(index)})


def project(counts, native, snapshot):
    from scripts.results_county_frame import coverage, decode
    from scripts.statewide_ballot_totals import compressed

    entry = snapshot.get("granular_sources", {}).get(FEED, {})
    data = entry.get("data")
    if data is None and LAYER_FILE not in native:
        return counts, native
    index = json.loads(counts["index.json"])
    declaration = index["states"]["PA"]
    path = declaration["file"]
    shard = decode(counts[path])
    if data is None:
        return counts, retain_layer(native, shard, declaration)
    features = geometry_controls(data)
    require(entry["source"] == data["source"] and entry["status"] in {"reported", "retained_after_failure"},
            "Philadelphia geometry receipt differs")
    parents = [row for row in shard["records"] if row["source"]["id"] == PHILADELPHIA_FEED]
    if not parents:
        return counts, retain_layer(native, shard, declaration)
    parent, = parents
    facts = parent["view"]["native_record"]
    _, _, _, _, _, residual = philadelphia_controls(facts)
    source_rows = {row[0].replace("-", ""): row for row in facts["complete_native_query"]["divisions"]}
    if set(source_rows) != {key for key, _ in features}:
        return counts, retain_layer(native, shard, declaration)
    observations = [division_row(parent, source_rows[key]) for key, _ in features]
    validate_all(observations)
    ids = [row["id"] for row in observations]
    old = [row["id"] for row in shard["records"] if row["source"]["id"] == SOURCE_ID]
    require(not old or old == ids, "Philadelphia existing division inventory differs")
    shard["records"] = [row for row in shard["records"] if row["source"]["id"] != SOURCE_ID] + observations
    for mode in MODES:
        frame = shard["views"][mode]
        require(frame["qualified"] and frame["precincts"] == old,
                "Philadelphia division table would replace another frame")
        frame["precincts"] = ids
        declaration["views"][mode]["precincts"] = len(ids)
        declaration["views"][mode]["dispositions"]["precincts"] = {
            **coverage(observations), "geography_levels": ["precinct"]}
    counts = dict(counts, **{path: compressed(shard)})
    declaration.update(pin(counts[path]), records=len(shard["records"]))
    index["coverage"]["PA"].update(records=len(shard["records"]), **coverage(shard["records"]),
                                   zeros=sum(row["count"]["value"] == 0 for row in shard["records"]))
    counts["index.json"] = encoded(index)
    geometry = compressed({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"key": record["geography"]["name"]}, "geometry": polygon}
        for record, (_, polygon) in zip(observations, features)]})
    geometry_pin = pin(geometry)
    geom_file = "geometry/" + geometry_pin["sha256"] + ".json.gz"
    meta = {"source_id": SOURCE_ID, "counts_only": True, "reference_context_only": True,
            "area_column_label": "County", "expected_features": len(ids), "boundary_label": LABEL,
            "reference_title": "Ballots cast by Philadelphia division",
            "reference_coverage_label": "Philadelphia only: 1,703 matched division references, counts only.",
            "notes": f"{len(ids):,} divisions. {residual:,} mail ballots remain unassigned to divisions."}
    layer = compressed({
        "contract": "participation.reference_bindings.v1", "id": SCOPE, "state_code": "PA",
        "geometry": {"file": geom_file, **geometry_pin},
        "source_counts": {"file": path, **pin(counts[path]), "source_id": SOURCE_ID, "source_rows": len(ids)},
        "review": {"reviewed": True, "review_id": FEED, "scope": "public_authoritative_reference_context",
                   "matching": "exact_literal_only", "legal_election_boundaries_certified": False,
                   "rates_approved": False, "source_observations_preserved": True,
                   "reference_label": LABEL, "geometry_retrieved_at_utc": REVIEWED_AT,
                   "omitted_units_note": NOTE, "source_geometry": data["source"],
                   "short_field_conflicts": data["short_field_conflicts"],
                   "polling_place_inventory": POLLING},
        "rows": [{"key": row["geography"]["name"], "geometry_type": polygon["type"], "observation": row,
                  "properties": {**row["view"], "key": row["geography"]["name"],
                                 "source_count_observation_id": row["id"], "reference_context_only": True,
                                 "maps_approved": True, "legal_election_boundaries_certified": False,
                                 "boundary_label": LABEL}}
                 for row, (_, polygon) in zip(observations, features)],
        "held_rows": [],
    })
    nindex = json.loads(native["index.json"])
    require(SCOPE not in nindex["layers"] or nindex["layers"][SCOPE]["file"] == LAYER_FILE,
            "Philadelphia division layer would overwrite another source")
    nindex["layers"][SCOPE] = {"file": LAYER_FILE, **pin(layer), "features": len(ids),
                               "geometry_sha256": geometry_pin["sha256"], "eligible_modes": list(MODES),
                               "coverage": {"fractions": 0, "source_rows": len(ids),
                                            "reported": len(ids), "unknown": 0, "withheld": 0}}
    nindex["config"]["states"]["PA"] = geom_file
    nindex["config"]["state_metadata"]["PA"] = meta
    return counts, dict(native, **{LAYER_FILE: layer, geom_file: geometry, "index.json": encoded(nindex)})
