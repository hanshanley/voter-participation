"""Publish reviewed complete county ballot frames without replacing their source history."""

import copy
import gzip
import json
import re

from scripts.participation_count_additions import COUNTY_QUALIFIERS
from scripts.participation_intake.contract import VERSION, encoded, observation_id, pin, validate_all
from scripts.statewide_ballot_totals import compressed, identity as statewide_identity, require
from scripts import results_clarity_congress as clarity
from scripts import results_pdf_county_parent as county_pdf
from scripts import results_turnout_history as history


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
GA = {
    "code": "GA", "county_count": 159, "fips_prefix": "13",
    "reference_source": "in_person_early",
    "reference_sha256": "219c1cd18773865615eebeb9eeccc92e3095dcab0b1af4b4150226d4af105249",
}
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
SUMNER = ("TN", "Tennessee", "Sumner County", "47165", WILSON[4],
          county_pdf.SUMNER_FEED, county_pdf.SUMNER_INDEX, "TN:official-ballot-statistics:47165",
          "TN-2026-11-03-general", "native_registered_voters_same_sumner_county_summary")
BUXTON = ("ME", "Maine", "Buxton", "2309410",
          "cf02fa319f1e54c65a679dd25b79813988e10dd0a800c3511b68d3fc448259bc",
          history.BUXTON_FEED, history.BUXTON_URL, "ME:town-ballot-statistics:2309410",
          "ME-2026-11-03-general", "native_registered_voters_same_buxton_report")
PHILADELPHIA = ("PA", "Pennsylvania", "Philadelphia County", "42101",
                "76496baea4bf48228d8c9891aafdf76090f1267764ea38f4305889e36d9249e6",
                county_pdf.PHILADELPHIA_FEED, county_pdf.PHILADELPHIA_URL,
                "PA:official-ballot-statistics:42101", "PA-2026-11-03-general",
                "native_registered_voters_same_philadelphia_report")
SUMMIT = ("UT", "Utah", "Summit County", "49043",
          "d2271f1ead3ef5193c2300bd22672ece3bbfcad4e7db70b0fd7cb7b99ae376c6",
          county_pdf.SUMMIT_FEED, county_pdf.SUMMIT_INDEX, "UT:official-ballot-statistics:49043",
          "UT-2026-11-03-general", "native_pre_election_active_voters_same_summit_canvass")
SUMMIT_PREDECESSOR = "e25c5ea44c920c6b693895259496e6d0"
SUSSEX = ("NJ", "New Jersey", "Sussex County", "34037",
          "489eabbafe98495645d95ddb65581f5204b3bd7871b001d02d3aaa3ffa11733b",
          county_pdf.SUSSEX_FEED, county_pdf.SUSSEX_INDEX, "NJ:official-ballot-statistics:34037",
          "NJ-2026-11-03-general", "native_registered_voters_same_sussex_county_summary")
SUSSEX_PREDECESSOR = "1d35a9ce3b9d96be8c2a08d106d34637"
DOUGLAS = ("WI", "Wisconsin", "Douglas County", "55031",
           "4f53e9b43faa1cf6dd9e1f9b893993fe6f4aa42a78cfbb1afbeb39d3f6db5f74",
           county_pdf.DOUGLAS_FEED, county_pdf.DOUGLAS_INDEX, "WI:official-ballot-statistics:55031",
           "WI-2026-11-03-general", "native_registered_voters_same_douglas_county_summary")
OKTIBBEHA = ("MS", "Mississippi", "Oktibbeha County", "28105",
             "f92866ca5d6384cc3db5caaa52a66a442753296f8cf8de06ec62a355b32066ea",
             county_pdf.OKTIBBEHA_FEED, county_pdf.OKTIBBEHA_INDEX, "MS:official-ballot-statistics:28105",
             "MS-2026-11-03-general", "native_registered_voters_same_oktibbeha_county_summary")
WOODFORD = ("IL", "Illinois", "Woodford County", "17203",
            "ddc8ec595021ed04413207a23410d297a8c538d4c5ebbbe135f37c5d8bde5039",
            county_pdf.WOODFORD_FEED, county_pdf.WOODFORD_INDEX, "IL:official-ballot-statistics:17203",
            "IL-2026-11-03-general", "registration_not_qualified_from_woodford_summary")
LAWRENCE = ("IL", "Illinois", "Lawrence County", "17101", WOODFORD[4],
            county_pdf.LAWRENCE_FEED, county_pdf.LAWRENCE_INDEX, "IL:official-ballot-statistics:17101",
            "IL-2026-11-03-general", "native_registered_voters_same_lawrence_county_summary")
ILLINOIS_COUNTY_PARENTS = (LAWRENCE, WOODFORD)
SPARSE_COUNTY_PARENTS = (PHILADELPHIA, OKTIBBEHA, *ILLINOIS_COUNTY_PARENTS)
RETAINED_CANVASSES_INPUT = "data/results-intake/retained-county-canvasses-20261119.json"
RETAINED_CANVASSES_SHA256 = "c37079cc1274b752a2c5ab4be3e26eb46d4febc091ac95f32ac5ccfdbe1aaaee"


def retained_county_canvass(entry, profile, body):
    if (body is None or profile not in (SUMMIT, SUSSEX, DOUGLAS)
            or entry.get("status") != "source_stopped" or entry.get("error_stage") != "acquisition"
            or entry.get("attempted_source_url") != profile[6]
            or entry.get("data") is not None or entry.get("source") is not None):
        return None
    require(pin(body)["sha256"] == RETAINED_CANVASSES_SHA256, "Retained county canvass evidence differs")
    evidence = json.loads(body)[profile[5]]
    require(evidence["index"]["url"] == profile[6], "Retained county archive identity differs")
    return evidence["data"]


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
    elif profile == WILSON:
        ballots, registered, fraction, label = county_pdf.wilson_controls(data)
        clock = None
        measure, register = "Ballots Cast - Total", "Registered Voters - Total"
        selector = {"scope": "countywide statistics", "physical_page": 1, "native_label": measure}
        notes = ["The four native voting-mode counts sum to the countywide ballot total.",
                 "The same report supplies registered voters, but no count-update clock."]
    elif profile == SUMNER:
        clock, ballots, registered, fraction = county_pdf.sumner_controls(data)
        label = "Complete reporting in native summary; certification not established"
        measure, register = "PUBLIC COUNT", "REGISTERED VOTERS"
        selector = {"scope": "countywide statistics", "physical_page": 1, "native_label": measure}
        notes = [
            "The same scanned report supplies the countywide count and registration, checked at two OCR resolutions.",
            "The three voting modes reconcile to PUBLIC COUNT. The report generation clock is not a count-update time.",
        ]
    elif profile == SUMMIT:
        clock, ballots, registered, fraction, _ = county_pdf.summit_controls(data)
        label = "Official county canvass"
        measure, register = "Total ballots counted", "Active voters on the Friday before the election"
        selector = {"scope": "countywide canvass statistics", "physical_pages": [1, 2, 3]}
        notes = [
            "The seven counted-ballot modes, cover, vote histories and official county summary reconcile.",
            "The denominator is the pre-election active registration stock, not all eligible residents.",
            "Report generation time has no declared timezone and is not a count-update clock.",
        ]
    elif profile == SUSSEX:
        clock, ballots, registered, fraction, _, _ = county_pdf.sussex_controls(data)
        label = "Official county summary; county clerk archive marks results certified"
        measure, register = "Ballots Cast - Total", "Registered Voters - Total"
        selector = {"scope": "countywide statistics", "physical_page": 1, "native_label": measure}
        notes = [
            "All six reported voting modes reconcile to the countywide total.",
            "Uses the same report's registrations, not an eligible-population estimate.",
            "Report generation time has no declared timezone and is not a count-update clock.",
        ]
    elif profile == DOUGLAS:
        clock, ballots, registered, fraction, units = county_pdf.douglas_controls(data)
        label = "CERTIFIED RESULTS"
        measure, register = "Ballots Cast - Total", "Registered Voters - Total"
        selector = {"scope": "countywide statistics", "physical_page": 1, "native_label": measure}
        notes = [
            f"The certified countywide summary shows {units} of {units} reporting.",
            "The same summary supplies ballots and registrations; no reporting-unit allocation.",
            "Report generation time has no declared timezone and is not a count-update clock.",
        ]
    elif profile == OKTIBBEHA:
        clock, ballots, registered, fraction = county_pdf.oktibbeha_controls(data)
        label = "OFFICIAL RESULTS"
        measure, register = "Ballots Cast - Total", "Registered Voters - Total"
        selector = {"scope": "countywide statistics", "physical_page": 1, "native_label": measure}
        notes = [
            "The five voting-mode counts, including affidavit ballots, reconcile to the countywide total.",
            "The fraction uses the same report's registrations, not the eligible population.",
            "The PDF's generation time is not a count-update clock and has no declared timezone.",
        ]
    elif profile == WOODFORD:
        clock, ballots, registered, units = county_pdf.woodford_controls(data)
        fraction, label = None, "OFFICIAL RESULTS"
        measure, register = "Ballots Cast - Total", "Registered Voters - Total"
        selector = {"scope": "countywide statistics before first contest", "native_label": measure}
        notes = [
            f"The county summary shows {units} of {units} precincts counted; ballot-style totals reconcile.",
            f"The report's registration field is {registered:,}; no matching denominator or rate is qualified.",
            "The generation time has no declared timezone and is not a count-update clock.",
        ]
    elif profile == LAWRENCE:
        clock, ballots, registered, fraction, label, units = county_pdf.lawrence_controls(data)
        measure, register = "BALLOTS CAST - TOTAL", "REGISTERED VOTERS - TOTAL"
        selector = {"scope": "countywide statistics", "physical_page": 1, "native_label": measure}
        notes = [
            f"The county summary shows {units} of {units} precincts counted; this is not certification.",
            "The fraction uses the same summary's registrations, not an eligible-population estimate.",
            "The generation time has no declared timezone and is not a count-update clock.",
        ]
    elif profile == BUXTON:
        ballots, registered, fraction = history.buxton_controls(data)
        clock = None
        label = "Town clerk state-and-town results; certification not established"
        measure, register = "Total Ballots Cast", "Registered Voters"
        selector = {"scope": "townwide state-and-town election statistics", "native_label": measure}
        notes = [
            "The town clerk's absentee and in-person counts reconcile to the townwide total.",
            "This is a same-report registered-voter fraction, not a York County rate.",
        ]
    else:
        require(profile == PHILADELPHIA, "Unknown local source profile")
        ballots, registered, fraction, status_literal, published, residual = county_pdf.philadelphia_controls(data)
        clock = data["date"]
        label = f"{status_literal} Philadelphia County Board of Elections results"
        measure, register = "Total Ballots Cast", "Registered Voters"
        selector = {"scope": "countywide turnout header", "native_label": measure}
        notes = [
            f"The countywide total includes {residual:,} mail ballots not assigned to a division in this report.",
            "The public query includes all native division rows; no residual is allocated and no division geography is inferred.",
            "The site update time is separate from certification and does not establish a count-update time.",
        ]
    town = profile == BUXTON
    level = "municipality" if town else "county"
    measure_id = "townwide-ballots-cast" if town else "countywide-ballots-cast"
    if profile in (SUSSEX, DOUGLAS):
        notes.append("Not a statewide total, unique-voter count or precinct allocation.")
    else:
        notes.append("Not a statewide total, certification claim, unique-voter count or precinct allocation.")
    rate = None if profile == WOODFORD else 100 * ballots / registered
    denominator = None if profile == WOODFORD else registered
    view = {
        "state_code": code, "state": state, "year": 2026, "county": county,
        "county_id": geo, "county_fips": None if town else fips, "geography_level": level,
        "mode": "official", "status": status, "source_mode": "all_methods",
        "ballots": ballots, "denominator": denominator, "registered": denominator,
        "denominator_basis": basis, "reported_pct": rate, "validated_pct": rate,
        "native_printed_pct": fraction, "source_status_literal": label,
        "source_date": clock[:10] if clock else None, "source_update_label": None, "source_update_timezone": None,
        "source_publication_label": clock.replace("T", " ") if clock else None, "source_publication_timezone": None,
        "source_url": report["url"], "source_sha256": report["sha256"],
        "source_count_qualified": True, "cast_ballot_count_qualified": True,
        "native_election_id_qualified": True, "unique_voter_count_qualified": False,
        "participation_measure_kind": "ballots_cast", "participation_measure_literal": measure,
        "participation_measure_label": "Townwide ballots cast" if town else "Countywide ballots cast",
        "complete_download_url": None, "automatic_source_refresh": True, "maps_approved": True,
        "reported_units": None, "total_units": None, "native_record": data,
        "reference_geometry": reference, "quality": notes,
    }
    if town:
        view["reference_municipality_key"] = fips
    elif profile in SPARSE_COUNTY_PARENTS:
        if profile == PHILADELPHIA:
            view.update(source_publication_label=published, source_publication_timezone="EST")
        view["supplemental_reference_geometry"] = view.pop("reference_geometry")
        view["maps_approved"] = False
    return {
        "contract": VERSION,
        "id": observation_id(feed, election, geo, measure_id, "all_methods"),
        "election": {"id": election, "year": 2026, "date": county_pdf.ELECTION,
                     "type": "general", "qualification": "native"},
        "geography": {"id": geo, "name": county, "state_code": code,
                      "level": level, "parent_id": None, "join": {
                          "status": "approved", "reference_id": reference["review_id"],
                          "feature_key": fips,
                          "evidence": "Exact named town in pinned 2024 Maine contextual reference"
                          if town else f"Exact countywide authority and named county in pinned {state} reference"}},
        "measure": {"id": measure_id, "literal": measure,
                    "kind": "ballots_cast", "mode": "all_methods", "unit": "ballots"},
        "count": {"value": ballots, "literal": ballots, "status": "reported"},
        "denominator": {"value": denominator, "literal": register,
                        "basis": basis, "qualified": denominator is not None},
        "source": {"id": feed, "url": report["url"], "input_sha256": report["sha256"],
                   "classification": "public_aggregate", "fields": copy.deepcopy(view),
                   "selector": selector},
        "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": label, "reported_units": None, "total_units": None, "complete": None},
        "quality": {"notes": notes, "conflicts": []},
        "view": view,
    }


def project_county_parent(counts, native, snapshot, profile, *, retained_canvasses=None):
    code, _, county, fips, reference_sha, feed, url, geo, election, _ = profile
    town = profile == BUXTON
    predecessor = {SUMMIT: SUMMIT_PREDECESSOR, SUSSEX: SUSSEX_PREDECESSOR}.get(profile)
    year = 2024 if town or predecessor else 2026
    reference_key = "reference_municipality_key" if town else "county_fips"
    entry = snapshot.get("granular_sources", {}).get(feed, {})
    data = entry.get("data")
    require(data is not None or entry.get("status") != "reported",
            f"{county} reported source is missing its facts")
    index = json.loads(counts["index.json"])
    declaration = index["states"].get(code)
    if declaration is None and data is None:
        return counts, native, []
    require(declaration is not None, f"{county} canonical shard missing")
    path = declaration["file"]
    require(pin(counts[path]) == {k: declaration[k] for k in ("bytes", "sha256")}, f"{code} shard pin differs")
    shard = decode(counts[path])
    require(shard["state_code"] == code and shard["year"] == 2026, f"{code} shard scope differs")
    rows = {record["id"]: record for record in shard["records"]}
    key = observation_id(feed, election, geo,
                         "townwide-ballots-cast" if town else "countywide-ballots-cast", "all_methods")
    prior = rows.get(key)
    retained = False
    if data is None and prior is None:
        data = retained_county_canvass(entry, profile, retained_canvasses)
        if data is None:
            return counts, native, []
        # A reviewed older selector or an empty slot is required for a retained bootstrap.
        for mode in ("official", "uf_vap", "uf_vep"):
            selected = shard["views"][mode]["counties"]
            if predecessor:
                if predecessor not in selected:
                    return counts, native, []
            elif any(rows[item]["view"].get(reference_key) == fips
                     or rows[item]["geography"]["join"]["feature_key"] == fips for item in selected):
                return counts, native, []
        retained = True
    if data is not None and not retained:
        require(entry["status"] in {"reported", "retained_after_failure"}
                and entry["source"]["url"] == url
                and isinstance(entry.get("first_observed_at"), str), f"{county} collection receipt differs")
        if profile in (WILSON, BUXTON, PHILADELPHIA):
            require(entry["source"] == data["report"], "Wilson receipt differs from report evidence")
    native_index = json.loads(native["index.json"])
    mappings = native_index["county_bindings"][code]
    reference_mode = ("available" if predecessor else "mail_returned"
                      if profile in SPARSE_COUNTY_PARENTS else "in_person_early")
    early = mappings[reference_mode]
    geometry = {key: copy.deepcopy(early[key]) for key in ("feature_keys", "feature_scopes", "features", "sha256")}
    matches = [item for item in early["rows"] if item["feature_key"] == fips]
    require(len(matches) == 1 and early["sha256"] == reference_sha
            and fips in early["feature_keys"]
            and early["feature_scopes"][fips] == {"state_code": code, "name": county, "boundary_year": year},
            f"{county} reference identity changed")
    refs = [rows[key]["view"]["reference_geometry"] for key in shard["views"][reference_mode]["counties"]
            if rows[key]["view"]["county_id"] == matches[0]["county_id"]
            and (key == predecessor and rows[key]["geography"]["join"]["feature_key"] == fips
                 if predecessor else rows[key]["view"].get(reference_key) == fips)]
    require(len(refs) == 1 and refs[0]["sha256"] == reference_sha
            and refs[0]["boundary_year"] == year, f"{county} reference provenance differs")
    if town:
        require(refs[0]["geography_scope"] == "provider_partial_locality_activity",
                "Maine contextual reference scope changed")
        refs[0] = {**refs[0], "geography_scope": "native_partial_town_turnout"}
    elif profile in SPARSE_COUNTY_PARENTS:
        refs[0] = {**refs[0], "geography_scope": "native_partial_county_context",
                   "partial_county_fips": [fips]}
        geometry["embedded_reference_required"] = False
    if data is None:
        old = prior["view"]
        require(old["status"] in {"reported", "retained_after_failure"} and prior ==
                county_parent_observation(profile, old["native_record"], refs[0], old["status"]),
                f"{county} last-good count differs from its reviewed evidence")
        candidate = county_parent_observation(profile, old["native_record"], refs[0], "retained_after_failure")
    else:
        candidate = county_parent_observation(
            profile, data, refs[0], "retained_after_failure" if retained else entry["status"])
    if prior and data is not None:
        old = prior["view"]["native_record"]
        regression = profile in (CUYAHOGA, SUMNER, PHILADELPHIA, SUMMIT, SUSSEX, DOUGLAS) and data["date"] < old["date"]
        if profile == CUYAHOGA:
            regression |= (old["report_status"] == county_pdf.STATUSES[1]
                           and data["report_status"] != county_pdf.STATUSES[1])
        elif profile == WILSON:
            regression |= (prior["view"]["source_status_literal"] == "OFFICIAL RESULTS"
                           and candidate["view"]["source_status_literal"] != "OFFICIAL RESULTS")
        elif profile == PHILADELPHIA:
            regression |= (old["complete_native_query"]["status"] == "Official"
                           and data["complete_native_query"]["status"] != "Official")
        elif profile in (OKTIBBEHA, *ILLINOIS_COUNTY_PARENTS):
            regression |= county_pdf.county_summary_regressed(old, data)
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
        if predecessor and not prior:
            require(predecessor in frame["counties"] and len(known) == 1
                    and rows[predecessor]["view"]["county_id"] == known[0]["county_id"] == matches[0]["county_id"]
                    and rows[predecessor]["view"]["county"] == ("Sussex" if profile == SUSSEX else county)
                    and rows[predecessor]["geography"]["join"]["feature_key"] == fips,
                    f"{county} predecessor does not match the reviewed county selector")
            frame["counties"][frame["counties"].index(predecessor)] = key
            binding["rows"][binding["rows"].index(known[0])] = copy.deepcopy(bound)
            known = [bound]
        else:
            require(known == ([bound] if prior else []), f"{county} feature binding differs")
        require(not any(
            rows[selected]["view"].get(reference_key) == fips and selected != key
            for selected in frame["counties"]), f"{county} frame would shadow another source")
        if not prior and not predecessor:
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


def project_sumner(counts, native, snapshot):
    return project_county_parent(counts, native, snapshot, SUMNER)


def project_buxton(counts, native, snapshot):
    return project_county_parent(counts, native, snapshot, BUXTON)


def project_philadelphia(counts, native, snapshot):
    return project_county_parent(counts, native, snapshot, PHILADELPHIA)


def project_summit(counts, native, snapshot, *, retained_canvasses=None):
    return project_county_parent(counts, native, snapshot, SUMMIT, retained_canvasses=retained_canvasses)


def project_sussex(counts, native, snapshot, *, retained_canvasses=None):
    return project_county_parent(counts, native, snapshot, SUSSEX, retained_canvasses=retained_canvasses)


def project_douglas(counts, native, snapshot, *, retained_canvasses=None):
    return project_county_parent(counts, native, snapshot, DOUGLAS, retained_canvasses=retained_canvasses)


def project_oktibbeha(counts, native, snapshot):
    return project_county_parent(counts, native, snapshot, OKTIBBEHA)


def project_illinois(counts, native, snapshot):
    changes = []
    for profile in ILLINOIS_COUNTY_PARENTS:
        counts, native, delta = project_county_parent(counts, native, snapshot, profile)
        changes.extend(delta)
    return counts, native, changes


def project_georgia(counts, native):
    index = json.loads(counts["index.json"])
    declaration = index["states"].get("GA")
    if declaration is None:
        return counts, native, []
    path = declaration["file"]
    require(pin(counts[path]) == {k: declaration[k] for k in ("bytes", "sha256")},
            "Georgia county shard pin differs")
    shard = decode(counts[path])
    rows = {r["id"]: r for r in shard["records"]}
    state = rows.get(statewide_identity("GA"))
    if state is None:
        return counts, native, []
    native_index = json.loads(native["index.json"])
    bindings = native_index["county_bindings"]["GA"]
    names, context, reference = county_reference(GA, native_index, shard)
    query = state["view"]["statewide_ballot_parent"]["query"]
    history.georgia_controls(query)
    require({row["name"] for row in query["counties"]} == set(names),
            "Georgia source and map county identities differ")
    common = {key: value for key, value in state["view"].items() if key != "statewide_ballot_parent"}
    projected = {}
    for row in query["counties"]:
        name, ballots, registered = row["name"], row["ballots"], row["registered"]
        fips = names[name]
        geo = "GA:official-ballot-statistics:" + fips
        key = observation_id(history.GA_FEED, state["election"]["id"], geo, "countywide-ballots-cast", "all_methods")
        status = "Official per county feed" if row["official"] else "Unofficial per county feed"
        notes = ["BallotsCast and registered voters come from this county's row in the same statewide release.",
                 "Precinct reporting fraction is source context, not independent evidence of certification."]
        if common["status"] == "retained_after_failure":
            notes.append(f"Retained county counts from the Georgia feed edition published {query['published']}; "
                         "the current source did not supply a replacement.")
        rate = 100 * ballots / registered
        clock = {"literal": row["updated"], "timezone": "UTC"}
        view = {**common, "geography_level": "county", "county_id": geo, "county": name,
                "county_fips": fips, "maps_approved": True, "reference_geometry": reference,
                "ballots": ballots, "registered": registered, "denominator": registered,
                "reported_pct": rate, "validated_pct": rate,
                "source_mode": "all_methods", "source_status_literal": status,
                "source_update_label": clock["literal"], "source_update_timezone": clock["timezone"],
                "source_reporting_label": " ".join(notes), "native_record": row, "quality": notes,
                "participation_measure_label": "Countywide ballots cast",
                "participation_measure_literal": "BallotsCast"}
        projected[key] = {**{k: state[k] for k in ("contract", "election")}, "id": key,
            "geography": {"id": geo, "name": name, "state_code": "GA", "level": "county",
                          "parent_id": state["geography"]["id"], "join": {
                              "status": "approved", "reference_id": reference["review_id"],
                              "feature_key": fips, "evidence": "Exact named county on the pinned Georgia reference"}},
            "measure": {**state["measure"], "id": "countywide-ballots-cast", "literal": "BallotsCast"},
            "count": {"value": ballots, "literal": ballots, "status": "reported"},
            "denominator": {**state["denominator"], "value": registered},
            "source": {**state["source"], "fields": view, "selector": {"native_id": row["id"]}},
            "source_clock": clock,
            "reporting_status": {"literal": status, "reported_units": None, "total_units": None, "complete": None},
            "quality": {"notes": notes, "conflicts": []}, "view": view}
    validate_all(projected.values())
    old = {key: row for key, row in rows.items()
           if row["source"]["id"] == history.GA_FEED and row["geography"]["level"] == "county"}
    require(not old or list(old) == list(projected), "Georgia county source inventory changed")

    def binding(records):
        return {**{k: context[k] for k in ("sha256", "features", "feature_keys", "feature_scopes")},
                "rows": [{"feature_key": row["view"]["county_fips"], "county_id": row["view"]["county_id"],
                          "qualifier": {k: row["view"].get(k) for k in COUNTY_QUALIFIERS}}
                         for row in records.values()]}

    legacy = shard["views"]["available"]["counties"]
    require(len(legacy) == 159 and {rows[key]["view"]["county"] for key in legacy} == set(names)
            and all(rows[key]["measure"]["literal"] == "ballotsCast" for key in legacy),
            "Georgia legacy county observation scope changed")
    for mode in ("official", "uf_vap", "uf_vep"):
        frame = shard["views"][mode]
        require(frame["qualified"] and frame["counties"] == (list(old) if old else legacy)
                and bindings.get(mode) == (binding(old) if old else None),
                "Georgia county selector or map preimage differs")
        frame["counties"] = list(projected)
        bindings[mode] = binding(projected)
        declaration["views"][mode]["counties"] = len(projected)
        declaration["views"][mode]["dispositions"]["counties"] = {
            **coverage(projected.values()), "geography_levels": ["county"]}
    if old == projected:
        return counts, native, []
    rows.update(projected)
    shard["records"] = list(rows.values())
    counts = dict(counts, **{path: compressed(shard)})
    declaration.update(pin(counts[path]), records=len(rows))
    index["coverage"]["GA"].update(records=len(rows), **coverage(rows.values()),
                                   zeros=sum(row["count"]["value"] == 0 for row in rows.values()))
    counts["index.json"] = encoded(index)
    native = dict(native, **{"index.json": encoded(native_index)})
    changes = [{"state_code": "GA", "id": key, "previous": old[key]["count"]["value"] if key in old else None,
                "current": row["count"]["value"], "source_status": row["view"]["status"]}
               for key, row in projected.items() if old.get(key) != row]
    return counts, native, changes


def project_ohio(counts, native):
    index = json.loads(counts["index.json"])
    declaration = index["states"].get("OH")
    if declaration is None:
        return counts, native, []
    path = declaration["file"]
    shard = decode(counts[path])
    rows = {r["id"]: r for r in shard["records"]}
    state = rows.get(statewide_identity("OH"))
    if state is None:
        return counts, native, []
    native_index = json.loads(native["index.json"])
    mappings = native_index["county_bindings"]["OH"]
    names, context, reference = county_reference({
        "code": "OH", "county_count": 88, "fips_prefix": "39",
        "reference_source": "in_person_early", "reference_sha256": CUYAHOGA_REFERENCE,
    }, native_index, shard)
    summary = state["view"]["statewide_ballot_parent"]
    query = summary["query"]
    history.ohio_controls(query)
    require({row[1] + " County" for row in query["counties"]} == set(names)
            and names["Cuyahoga County"] == CUYAHOGA_FIPS, "Ohio county identity differs")
    cuyahoga_id = observation_id(CUYAHOGA[5], CUYAHOGA_ELECTION, CUYAHOGA_GEO,
                                 "countywide-ballots-cast", "all_methods")
    if cuyahoga_id not in rows:
        return counts, native, []
    stable = {key: copy.deepcopy(state[key]) for key in ("contract", "election", "measure", "source_clock")}
    source = {key: value for key, value in state["source"].items() if key != "fields"}
    common = {key: value for key, value in state["view"].items() if key != "statewide_ballot_parent"}
    projected = {}
    for native_id, county, ballots, registered, reported, units, absentee, provisional, printed in query["counties"]:
        fips = names[county + " County"]
        if fips == CUYAHOGA_FIPS:
            continue
        name, geo = county + " County", "OH:enr-county:" + fips
        key = observation_id(source["id"], state["election"]["id"], geo,
                             state["measure"]["id"], "all_methods")
        notes = [
            "County ballots counted and registration reconcile to the dated statewide unofficial frame.",
            ("The XML does not report outstanding ballots." if query.get("basis") == "dated_xml_county_sum"
             else "Outstanding UOCAVA and provisional ballots are separate."),
            "Election-day precinct reporting is not certification.",
        ]
        if common["status"] == "retained_after_failure":
            notes.append(f"Retained from the XML edition generated {query['election']['generated_at']} after a "
                         "source failure. The edition timestamp is not a ballot-count update time.")
        rate = 100 * ballots / registered
        native_row = {"county_object_id": native_id, "outstanding_uocava": absentee,
                      "outstanding_provisional": provisional, "xml_edition": query["election"]["source"]}
        view = {**common, "geography_level": "county", "county_id": geo, "county": name,
                "county_fips": fips, "maps_approved": True, "reference_geometry": reference,
                "ballots": ballots, "denominator": registered, "reported_pct": rate,
                "validated_pct": rate, "native_printed_pct": printed + "%" if printed else None,
                "source_mode": "all_methods",
                "reported_units": reported, "total_units": units, "native_record": native_row,
                "participation_measure_label": "County ballots counted", "quality": notes}
        projected[key] = {**stable, "id": key, "geography": {
            "id": geo, "name": name, "state_code": "OH", "level": "county",
            "parent_id": state["geography"]["id"], "join": {
                "status": "approved", "reference_id": reference["review_id"], "feature_key": fips,
                "evidence": "Exact Ohio county identity on the pinned 2026 county context",
            }},
            "source": {**source, "selector": {"native_id": native_id}, "fields": copy.deepcopy(view)},
            "source_clock": state["source_clock"], "count": {"value": ballots, "literal": ballots, "status": "reported"},
            "denominator": {**state["denominator"], "value": registered},
            "reporting_status": {"literal": view["source_status_literal"], "reported_units": reported,
                                 "total_units": units, "complete": None},
            "quality": {"notes": notes, "conflicts": []}, "view": view}
    validate_all(projected.values())
    old = {key: rows[key] for key in projected if key in rows}
    require(not old or set(old) == set(projected), "Ohio county source inventory was partially projected")
    for mode in ("official", "uf_vap", "uf_vep"):
        frame, binding = shard["views"][mode], mappings[mode]
        old_ids = [cuyahoga_id, *old]
        require(frame["qualified"] and frame["counties"] == old_ids
                and len(binding["rows"]) == len(old_ids)
                and {item["feature_key"] for item in binding["rows"]} ==
                    {CUYAHOGA_FIPS, *(row["view"]["county_fips"] for row in old.values())}
                and all(binding[field] == context[field] for field in ("sha256", "features", "feature_keys", "feature_scopes")),
                "Ohio county selection or map preimage changed")
        frame["counties"] = [cuyahoga_id, *projected]
        binding["rows"] = [item for item in binding["rows"] if item["feature_key"] == CUYAHOGA_FIPS] + [
            {"feature_key": row["view"]["county_fips"], "county_id": row["view"]["county_id"],
             "qualifier": {field: row["view"].get(field) for field in COUNTY_QUALIFIERS}}
            for row in projected.values()]
        declaration["views"][mode]["counties"] = len(frame["counties"])
        declaration["views"][mode]["dispositions"]["counties"] = {
            **coverage([rows[cuyahoga_id], *projected.values()]), "geography_levels": ["county"]}
    if old == projected:
        return counts, native, []
    rows.update(projected)
    shard["records"] = list(rows.values())
    counts = dict(counts, **{path: compressed(shard)})
    declaration.update(pin(counts[path]), records=len(rows))
    index["coverage"]["OH"].update(records=len(rows), **coverage(rows.values()),
                                   zeros=sum(row["count"]["value"] == 0 for row in rows.values()))
    counts["index.json"] = encoded(index)
    native = dict(native, **{"index.json": encoded(native_index)})
    changes = [{"state_code": "OH", "id": key, "previous": old[key]["count"]["value"] if key in old else None,
                "current": row["count"]["value"], "source_status": row["view"]["status"]}
               for key, row in projected.items() if old.get(key) != row]
    return counts, native, changes
