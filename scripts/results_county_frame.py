"""Publish reviewed complete county ballot frames without replacing their source history."""

import copy
import gzip
import json
import re

from scripts.participation_count_additions import COUNTY_QUALIFIERS
from scripts.participation_intake.contract import VERSION, encoded, observation_id, pin, validate_all
from scripts.statewide_ballot_totals import compressed, require
from scripts import results_clarity_congress as clarity
from scripts import results_pdf_county_parent as county_pdf


IA = {
    "code": "IA",
    "name": "Iowa",
    "county_count": 99,
    "fips_prefix": "19",
    "reference_sha256": "0589f3b0dafa88ff8936a0b2e1613cb57de5eda405313ac88667b47517a0032a",
    "reference_source": "in_person_early",
    "old_selections": ["6ba72e1e991fcf5fecbef0471e988fc1", "966f5584a55c79e0d736a48c9ec2c8af"],
}
MODES = ("available", "official", "uf_vap", "uf_vep")
NOTES = [
    "Official statewide results site, Ballots Cast statistics; not candidate votes.",
    "Registration and printed percentages are source context, not qualified turnout rates.",
    "The website publication timestamp is separate from the unknown count-update clock.",
    "Completely reported does not establish certification or a unique-voter count.",
]


def decode(body):
    return json.loads(gzip.decompress(body))


def county_reference(profile, native_index, shard):
    code = profile["code"]
    reference = native_index["county_bindings"][code][profile["reference_source"]]
    key_pattern = profile["fips_prefix"] + r"[0-9]{3}"
    scopes = reference["feature_scopes"]
    require(len(scopes) == len(reference["feature_keys"]) == reference["features"] == profile["county_count"]
            and set(scopes) == set(reference["feature_keys"])
            and reference["sha256"] == profile["reference_sha256"]
            and all(re.fullmatch(key_pattern, key) and scope == {
                "state_code": code, "name": scope["name"], "boundary_year": 2026}
                for key, scope in scopes.items()), "Reviewed county reference changed")
    names = {scope["name"]: key for key, scope in scopes.items()}
    require(len(names) == len(scopes), "Duplicate county reference name")
    baseline = {row["id"]: row for row in shard["records"]}
    sources = []
    provider = [baseline[key]["view"] for key in shard["views"][profile["reference_source"]]["counties"]]
    provider_by_id = {row["county_id"]: row for row in provider}
    require(len(provider_by_id) == len(provider) == len(scopes)
            and {row["feature_key"] for row in reference["rows"]} == set(scopes)
            and {row["county_id"] for row in reference["rows"]} == set(provider_by_id),
            "County reference does not bind the full existing map")
    for row in reference["rows"]:
        view = provider_by_id[row["county_id"]]
        require(view["county"] == scopes[row["feature_key"]]["name"]
                and view["county_fips"] == row["feature_key"], "County reference identity differs")
        sources.append(view["reference_geometry"])
    require(len(sources) == len(scopes) and all(item == sources[0] for item in sources)
            and sources[0]["sha256"] == reference["sha256"] and sources[0]["boundary_year"] == 2026,
            "Reviewed county geometry metadata differs")
    return names, reference, sources[0]


def observation(profile, row, reference, data, original, status, key=None):
    code = profile["code"]
    date = data["election_date"]
    election_id = f"{code}-{date}-general"
    parent = f"{code}:official-ballot-statistics:state"
    geo_id = f"{code}:official-ballot-statistics:{key}" if key else parent
    title = row["county"] + " County" if key else profile["name"]
    native_status = row["native_status"]
    label = {0: "Source reporting status 0", 4: "Completely reported"}.get(native_status)
    if key is None:
        label = "All counties completely reported"
    reported, total = row["reported_units"], row["total_units"]
    complete = (key is None or native_status in (0, 4)) and total > 0 and reported == total
    url = original["url"]
    view = {
        "state_code": code, "year": 2026, "county": title, "county_id": geo_id,
        "geography_level": "county" if key else "statewide", "county_fips": key,
        "geography": title, "state": profile["name"], "mode": "official", "status": status,
        "ballots": row["ballots"], "denominator": None,
        "denominator_basis": "native_registration_qualification_withheld",
        "registered": row["registered_stock"], "native_printed_pct": row["printed_fraction"],
        "reported_pct": None, "validated_pct": None, "source_date": None,
        "source_mode": "all_methods", "maps_approved": bool(key),
        "source_update_label": None, "source_update_timezone": None,
        "source_status_literal": label, "reported_units": reported, "total_units": total,
        "source_url": url, "source_sha256": original["sha256"], "complete_download_url": None,
        "automatic_source_refresh": True, "source_count_qualified": True,
        "participation_measure_kind": "ballots_cast", "participation_measure_literal": "Ballots Cast",
        "participation_measure_label": "Ballots cast", "cast_ballot_count_qualified": True,
        "unique_voter_count_qualified": False, "native_election_id_qualified": True,
        "source_reporting_label": " ".join(NOTES), "quality": NOTES,
        "review_id": f"{code.lower()}-official-county-ballots-20261118",
        "source_publication_label": data["source_publication_label"],
        "source_publication_timezone": data["source_publication_timezone"],
        "source_version": data["source_version"], "native_record": dict(row),
    }
    if key:
        view["reference_geometry"] = copy.deepcopy(reference)
    return {
        "contract": VERSION,
        "id": observation_id(clarity.IDENTITY, election_id, geo_id, "official-ballots-cast", "all_methods"),
        "election": {"id": election_id, "year": 2026, "date": date, "type": "general",
                     "qualification": "native"},
        "geography": {"id": geo_id, "name": title, "state_code": code, "parent_id": parent if key else None,
                      "level": "county" if key else "state",
                      "join": {"status": "approved" if key else "nongeographic",
                               "reference_id": reference["review_id"] if key else None,
                               "feature_key": key, "evidence": "Exact name in pinned 2026 county reference" if key else None}},
        "measure": {"id": "official-ballots-cast", "kind": "ballots_cast", "literal": "Ballots Cast",
                    "mode": "all_methods", "unit": "ballots"},
        "count": {"value": row["ballots"], "literal": row["ballots"], "status": "reported"},
        "source": {"id": clarity.IDENTITY, "url": url, "input_sha256": original["sha256"],
                   "classification": "public_aggregate", "selector": {"native_id": row["native_id"]},
                   "fields": copy.deepcopy(view)},
        "source_clock": {"literal": None, "timezone": None}, "denominator": None,
        "reporting_status": {"literal": label, "reported_units": reported, "total_units": total,
                             "complete": complete},
        "quality": {"conflicts": [], "notes": NOTES},
        "view": view,
    }


def coverage(rows):
    return {
        "reported": sum(row["count"]["status"] == "reported" for row in rows),
        "unknown": sum(row["count"]["status"] == "unknown" for row in rows),
        "withheld": sum(row["count"]["status"] == "withheld" for row in rows),
        "qualified_fractions": sum(bool(row["denominator"] and row["denominator"]["qualified"]) for row in rows),
    }


def project(counts, native, snapshot):
    entry = snapshot.get("congress", {}).get("official_candidate_evidence", {}).get(clarity.IDENTITY)
    data = entry.get("data") if entry and entry["status"] == "reported" else None
    require(not entry or entry["status"] != "reported" or isinstance(data, dict),
            "Reported Iowa source is missing its facts")
    profile, code = IA, IA["code"]
    index = json.loads(counts["index.json"])
    if data is None and code not in index["states"]:
        return counts, native, []
    declaration = index["states"][code]
    path = declaration["file"]
    require(pin(counts[path]) == {k: declaration[k] for k in ("bytes", "sha256")}, "County count shard pin differs")
    shard = decode(counts[path])
    require(shard["contract"] == "participation.count_snapshot.v1"
            and shard["state_code"] == code and shard["year"] == 2026, "County count shard scope differs")
    previous = {row["id"]: row for row in shard["records"] if row["source"]["id"] == clarity.IDENTITY}
    status = "reported"
    if (not previous and entry and entry["status"] == "retained_after_failure"
            and entry.get("reviewed_retained_capture") is True):
        require(clarity.retained_capture_matches(entry), "Reviewed Iowa retained capture pin differs")
        data, status = entry["data"], "retained_after_failure"
    if data is None and not previous:
        return counts, native, []
    native_index = json.loads(native["index.json"])
    active = decode(counts["current.json.gz"])
    reports = active["snapshot"]["reporting"]
    old_state = [row["view"] for row in previous.values() if row["geography"]["level"] == "state"]
    mirrors = [row for row in reports if row["state_code"] == code]
    require(len(old_state) <= 1 and mirrors == old_state, "Iowa statewide reporting preimage differs")
    names, geometry, reference = county_reference(profile, native_index, shard)
    if data is not None:
        require(clarity.normalized(data["native_facts"]) == {
            key: value for key, value in data.items() if key != "numerical_input_manifest"},
            "Iowa county counts differ from the complete native facts")
        stats = data["administrative_statistics"]
        rows = stats["counties"]
        require(len(rows) == profile["county_count"]
                and {row["county"] + " County" for row in rows} == set(names),
                "Iowa native county names differ from the full reference")
        original = data["numerical_input_manifest"]["text"]
        require(original["url"] == clarity.report_url(data["source_version"])
                and re.fullmatch(r"[a-f0-9]{64}", original["sha256"])
                and type(original["bytes"]) is int and original["bytes"] > 0,
                "Iowa independent statistical report receipt differs")
        is_complete = all(row["native_status"] in (0, 4) and
                          0 < row["total_units"] == row["reported_units"] for row in rows)
        if is_complete:
            selected = [observation(profile, row, reference, data, original, status,
                                    names[row["county"] + " County"]) for row in rows]
            state = {"county": None, "native_id": "Total:", "ballots": stats["state_ballots"],
                     "registered_stock": stats["state_registered_stock"], "printed_fraction": None,
                     "reported_units": len(rows), "total_units": len(rows),
                     "native_status": None}
            selected.append(observation(profile, state, reference, data, original, status))
        else:
            data = None
    if data is None:
        if not previous:
            return counts, native, []
        selected = copy.deepcopy(list(previous.values()))
        for row in selected:
            row["source"]["fields"]["status"] = row["view"]["status"] = "retained_after_failure"
    validate_all(selected)
    new = {row["id"]: row for row in selected}
    county = {key: row for key, row in new.items() if row["geography"]["level"] == "county"}
    require(len(new) == profile["county_count"] + 1 and len(county) == profile["county_count"]
            and (not previous or set(new) == set(previous)), "Iowa official observation inventory changed")
    county_ids = list(county)
    rows_by_id = {row["id"]: row for row in shard["records"]}
    require(len(rows_by_id) == len(shard["records"]), "Duplicate county observation IDs")
    state_row = next(row for key, row in new.items() if key not in county)
    if old_state:
        reports[reports.index(mirrors[0])] = copy.deepcopy(state_row["view"])
    else:
        reports.append(copy.deepcopy(state_row["view"]))
    old_ids = county_ids if previous else profile["old_selections"]
    binding = {key: copy.deepcopy(geometry[key]) for key in ("feature_keys", "feature_scopes", "features", "sha256")}
    binding["rows"] = [{
        "county_id": row["view"]["county_id"], "feature_key": row["geography"]["join"]["feature_key"],
        "qualifier": {key: row["view"].get(key) for key in COUNTY_QUALIFIERS},
    } for row in county.values()]
    for mode in MODES:
        frame = shard["views"][mode]
        require(frame["qualified"] and frame["counties"] == old_ids
                and native_index["county_bindings"][code].get(mode) == (binding if previous else None),
                "Iowa county selection or map preimage differs")
        frame["counties"] = county_ids
        declaration["views"][mode]["counties"] = len(county)
        declaration["views"][mode]["dispositions"]["counties"] = {
            **coverage(county.values()), "geography_levels": ["county"]}
        native_index["county_bindings"][code][mode] = copy.deepcopy(binding)
    if previous == new:
        return counts, native, []
    require(not (set(new) - set(previous)) & set(rows_by_id), "County source would overwrite another observation")
    rows_by_id.update(new)
    shard["records"] = list(rows_by_id.values())
    counts = dict(counts)
    counts[path] = compressed(shard)
    index["coverage"][code].update(records=len(rows_by_id), **coverage(shard["records"]),
                                   zeros=sum(row["count"]["value"] == 0 for row in shard["records"]))
    declaration.update(pin(counts[path]), records=len(rows_by_id))
    counts["current.json.gz"] = compressed(active)
    if "current_snapshot" in index:
        require(index["current_snapshot"]["file"] == "current.json.gz",
                "Iowa statewide display file differs from its declaration")
        index["current_snapshot"].update(pin(counts["current.json.gz"]))
    counts["index.json"] = encoded(index)
    native = dict(native, **{"index.json": encoded(native_index)})
    changes = [{"state_code": code, "id": key, "previous": previous[key]["count"]["value"] if key in previous else None,
                "current": row["count"]["value"], "source_status": row["view"]["status"]}
               for key, row in new.items() if previous.get(key) != row]
    return counts, native, changes


CUYAHOGA_FIPS = "39035"
CUYAHOGA_GEO = "OH:countywide-ballot-report:39035"
CUYAHOGA_ELECTION = "OH-2026-11-03-general"
CUYAHOGA_BASIS = "native_registered_voters_same_official_county_report"
CUYAHOGA_REFERENCE = "a9cb5f455b746d94a0ccf9c18c36d804ef0e728d9f63e119da69b40ce5e764e8"


CUYAHOGA = ("OH", "Ohio", county_pdf.COUNTY, CUYAHOGA_FIPS, CUYAHOGA_REFERENCE,
            county_pdf.IDENTITY, county_pdf.INDEX_URL, CUYAHOGA_GEO, CUYAHOGA_ELECTION, CUYAHOGA_BASIS)
WILSON = ("TN", "Tennessee", county_pdf.WILSON_COUNTY, "47189",
          "458587d28a6301475c907be4e2a0385e05b5acaad2cf622baafcae0578e8b67d",
          county_pdf.WILSON_FEED, county_pdf.WILSON_URL, "TN:official-ballot-statistics:47189",
          "TN-2026-11-03-general", "native_registered_voters_same_wilson_county_summary")


def county_parent_observation(profile, data, reference, status):
    code, state, county, fips, _, feed, _, geo, election, basis = profile
    report = data["report"]
    if profile == CUYAHOGA:
        clock, ballots, registered, fraction = county_pdf.validate_data(data)
        label = data["report_status"]
        measure, register = "Total Ballots Cast", "Registered Voters"
        selector = {"physical_pages": list(range(1, len(data["complete_native_query"]) + 1)),
                    "scope": county_pdf.SCOPE}
        notes = [
            "Countywide ballots and registrations from the same PDF parent, checked across every page.",
            "The report generation clock is not an independently identified count-update time.",
        ]
    else:
        ballots, registered, fraction, label = county_pdf.wilson_controls(data)
        clock = None
        measure, register = "Ballots Cast - Total", "Registered Voters - Total"
        selector = {"scope": "countywide statistics", "physical_page": 1, "native_label": measure}
        notes = ["The four native voting-mode counts sum to the countywide ballot total.",
                 "The same report supplies registered voters, but no count-update clock."]
    notes.append("Not a statewide total, certification claim, unique-voter count or precinct allocation.")
    rate = 100 * ballots / registered
    view = {
        "state_code": code, "state": state, "year": 2026, "county": county,
        "county_id": geo, "county_fips": fips, "geography_level": "county",
        "mode": "official", "status": status, "source_mode": "all_methods",
        "ballots": ballots, "denominator": registered, "registered": registered,
        "denominator_basis": basis, "reported_pct": rate, "validated_pct": rate,
        "native_printed_pct": fraction, "source_status_literal": label,
        "source_date": clock[:10] if clock else None, "source_update_label": None, "source_update_timezone": None,
        "source_publication_label": clock.replace("T", " ") if clock else None, "source_publication_timezone": None,
        "source_url": report["url"], "source_sha256": report["sha256"],
        "source_count_qualified": True, "cast_ballot_count_qualified": True,
        "native_election_id_qualified": True, "unique_voter_count_qualified": False,
        "participation_measure_kind": "ballots_cast", "participation_measure_literal": measure,
        "participation_measure_label": "Countywide ballots cast",
        "complete_download_url": None, "automatic_source_refresh": True, "maps_approved": True,
        "reported_units": None, "total_units": None, "native_record": data,
        "reference_geometry": reference, "quality": notes,
    }
    return {
        "contract": VERSION,
        "id": observation_id(feed, election, geo,
                             "countywide-ballots-cast", "all_methods"),
        "election": {"id": election, "year": 2026, "date": county_pdf.ELECTION,
                     "type": "general", "qualification": "native"},
        "geography": {"id": geo, "name": county, "state_code": code,
                      "level": "county", "parent_id": None, "join": {
                          "status": "approved", "reference_id": reference["review_id"],
                          "feature_key": fips,
                          "evidence": f"Exact countywide authority and named county in pinned {state} reference"}},
        "measure": {"id": "countywide-ballots-cast", "literal": measure,
                    "kind": "ballots_cast", "mode": "all_methods", "unit": "ballots"},
        "count": {"value": ballots, "literal": ballots, "status": "reported"},
        "denominator": {"value": registered, "literal": register,
                        "basis": basis, "qualified": True},
        "source": {"id": feed, "url": report["url"], "input_sha256": report["sha256"],
                   "classification": "public_aggregate", "fields": copy.deepcopy(view),
                   "selector": selector},
        "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": label, "reported_units": None, "total_units": None, "complete": None},
        "quality": {"notes": notes, "conflicts": []},
        "view": view,
    }


def project_county_parent(counts, native, snapshot, profile):
    code, _, county, fips, reference_sha, feed, url, geo, _, _ = profile
    entry = snapshot.get("granular_sources", {}).get(feed, {})
    if not entry.get("data"):
        return counts, native, []
    require(entry["status"] in {"reported", "retained_after_failure"}
            and entry["source"]["url"] == url
            and isinstance(entry.get("first_observed_at"), str), f"{county} collection receipt differs")
    if profile == WILSON:
        require(entry["source"] == entry["data"]["report"], "Wilson receipt differs from report evidence")
    index = json.loads(counts["index.json"])
    declaration = index["states"][code]
    path = declaration["file"]
    require(pin(counts[path]) == {k: declaration[k] for k in ("bytes", "sha256")}, f"{code} shard pin differs")
    shard = decode(counts[path])
    require(shard["state_code"] == code and shard["year"] == 2026, f"{code} shard scope differs")
    rows = {record["id"]: record for record in shard["records"]}
    native_index = json.loads(native["index.json"])
    mappings = native_index["county_bindings"][code]
    early = mappings["in_person_early"]
    geometry = {key: copy.deepcopy(early[key]) for key in ("feature_keys", "feature_scopes", "features", "sha256")}
    matches = [item for item in early["rows"] if item["feature_key"] == fips]
    require(len(matches) == 1 and early["sha256"] == reference_sha
            and fips in early["feature_keys"]
            and early["feature_scopes"][fips] == {"state_code": code, "name": county, "boundary_year": 2026},
            f"{county} reference identity changed")
    refs = [rows[key]["view"]["reference_geometry"] for key in shard["views"]["in_person_early"]["counties"]
            if rows[key]["view"]["county_id"] == matches[0]["county_id"]
            and rows[key]["view"]["county_fips"] == fips]
    require(len(refs) == 1 and refs[0]["sha256"] == reference_sha
            and refs[0]["boundary_year"] == 2026, f"{county} reference provenance differs")
    candidate = county_parent_observation(profile, entry["data"], refs[0], entry["status"])
    key = candidate["id"]
    prior = rows.get(key)
    if prior:
        old = prior["view"]["native_record"]
        regression = (entry["data"]["date"] < old["date"] or old["report_status"] == county_pdf.STATUSES[1]
                      and entry["data"]["report_status"] != county_pdf.STATUSES[1]) if profile == CUYAHOGA else (
                          prior["view"]["source_status_literal"] == "OFFICIAL RESULTS"
                          and candidate["view"]["source_status_literal"] != "OFFICIAL RESULTS")
        if regression or entry["status"] == "retained_after_failure":
            candidate = copy.deepcopy(prior)
            candidate["source"]["fields"]["status"] = candidate["view"]["status"] = "retained_after_failure"
    if prior == candidate:
        return counts, native, []
    validate_all([candidate])
    bound = {"county_id": geo, "feature_key": fips,
             "qualifier": {field: candidate["view"].get(field) for field in COUNTY_QUALIFIERS}}
    rows[key] = candidate
    # Keep the complete early-activity overview separate from this partial full-election frame.
    for mode in ("official", "uf_vap", "uf_vep"):
        frame = shard["views"][mode]
        binding = mappings.setdefault(mode, {**copy.deepcopy(geometry), "rows": []})
        require(frame["qualified"] and all(binding[field] == value for field, value in geometry.items())
                and (key in frame["counties"]) == bool(prior), f"{county} selected mode preimage differs")
        known = [row for row in binding["rows"] if row["feature_key"] == fips]
        require(known == ([bound] if prior else []) and not any(
            rows[selected]["view"].get("county_fips") == fips and selected != key
            for selected in frame["counties"]), f"{county} frame would shadow another source")
        if not prior:
            frame["counties"].append(key)
            binding["rows"].append(copy.deepcopy(bound))
        selected = [rows[item] for item in frame["counties"]]
        declaration["views"][mode]["counties"] = len(selected)
        declaration["views"][mode]["dispositions"]["counties"] = {
            **coverage(selected), "geography_levels": sorted({r["geography"]["level"] for r in selected})}
    shard["records"] = list(rows.values())
    counts = dict(counts, **{path: compressed(shard)})
    declaration.update(pin(counts[path]), records=len(rows))
    index["coverage"][code].update(records=len(rows), **coverage(rows.values()),
                                   zeros=sum(row["count"]["value"] == 0 for row in rows.values()))
    counts["index.json"] = encoded(index)
    native = dict(native, **{"index.json": encoded(native_index)})
    return counts, native, [{"state_code": code, "id": key,
                            "previous": prior["count"]["value"] if prior else None,
                            "current": candidate["count"]["value"],
                            "source_status": candidate["view"]["status"]}]


def project_cuyahoga(counts, native, snapshot):
    return project_county_parent(counts, native, snapshot, CUYAHOGA)


def project_wilson(counts, native, snapshot):
    return project_county_parent(counts, native, snapshot, WILSON)
