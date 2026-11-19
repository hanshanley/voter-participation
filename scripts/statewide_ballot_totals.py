"""Reviewed direct statewide ballot parents, independent of congressional choices."""

import copy
import csv
import gzip
import io
import json
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from scripts import protected_official_wyoming, results_minnesota_turnout as mn
from scripts import results_alaska_turnout as alaska
from scripts import results_native_dc as dc
from scripts import results_native_north_carolina as nc
from scripts import results_native_oregon as oregon
from scripts import results_native_state_family as state_family
from scripts import results_state_statistics as state_statistics
from scripts import results_turnout_history as history
from scripts.results_state_statistics import AZ_URL
from scripts.participation_intake.contract import (
    VERSION, count, encoded, observation_id, pin, validate,
)


CONTRACT = "participation.reviewed_statewide_ballot_parent.v1"
VT_URL = ("https://outside.vermont.gov/dept/sos/Elections_Division/election_info_resources/"
          "elections_results_data/2026_general_election_voter_turnout.pdf")
VT_COUNTIES = ("ADDISON", "BENNINGTON", "CALEDONIA", "CHITTENDEN", "ESSEX", "FRANKLIN",
               "GRAND ISLE", "LAMOILLE", "ORANGE", "ORLEANS", "RUTLAND", "WASHINGTON",
               "WINDHAM", "WINDSOR")
VT_FIELDS = ("total_votes_cast_includes_absentee", "registered_voters", "absentee_votes_cast")
FL_REVIEW = "florida-consolidated-turnout-20261106-01"
FL_SOURCE = {
    "url": "https://floridaelectionwatch.gov/CountyReportingStatus",
    "bytes": 169716,
    "sha256": "f4a4ff86238aadf10336ba428aaef8a8c04374e0774642734968d7d14362ce72",
}
FL_COUNTIES = {"bytes": 38823, "sha256": "a170d6f84bc4c4abea37238dc52a7d92235978ac1ab6e0f11f8eaa19458b94bf"}
FL_TOTAL = ("TOTAL", "8,335,497", "13,704,495", "60.82%", "100%", "", "", "", "", "")
AR_FEED = "AR-registered-a7d02a1142f7e41c"
AR_CAPTURE = "2026-11-05T11:43:56.646427+00:00"
AR_SOURCE = {"url": state_family.AR_REVIEWED_URL, "bytes": 55645416,
             "sha256": "079518a65d5f66385ec1cb5cedcd93a02973d6ae24a0793427af8d08c9fe14bd"}
AR_REVIEW = "additional:AR-2026-native-counts"
AR_TOTAL = [893026, 1856404, 2761, 2768, 7]
AR_COUNTIES = {"bytes": 2385, "sha256": "e3ff11ddb2e0b2d94a817a72109708add0cbcb83214fb050ed4b9ae9ee7c6ebc"}
CT_FEED = "CT-native-local"
CT_ROOT = "https://ctemspublic.tgstg.net/ng-app/data/election/108/"
CT_SOURCE = {
    "url": CT_ROOT + "52337/voterTurnout_Electiondata.json", "bytes": 25884,
    "sha256": "4edd27b258832d7ab7013f404383f273fc292bbd9f91e131c4e5aa953ee42404",
}
CT_FIELDS = ("EV", "VV", "ABR", "ABC", "EBR", "EBC", "EDR", "EDC")
CT_TOTAL = ("2102250", "1150127", "53091", "52940", "381498", "381490", "15015", "14945")
CT_TOWNS = {"bytes": 11331, "sha256": "a108e82ffad5eeb905fbdf137e503e97d53a38da34af776f174aed738c29a260"}
CT_PARENT = {"ID": "108", "BC": "1,150,127", "PR": "775 of 776 (99.87%)", "RV": "2,102,250",
             "T": "169 of 169", "PT": "0 of 169", "TO": "54.71", "SVT": True}
OR_FEED = "OR-registered-395ba5d378c8d69d"
OR_DISPLAY_URL = "https://results.oregonvotes.gov/?ID=39"
OR_BASELINE_ID = "20e024e22223bce619b8d76b6d468c52"
NC_BASELINE_ID = "723967930e4366f2cf9c150b1fe976d0"
NC_FEED = "NC-registered-d6712073694b63cd"
NC_INPUT = "data/results-intake/nc-20261113-statewide-and-counties.json"
NC_PIN = {"bytes": 27005, "sha256": "9fc1b775d96cba4bf8da176be8351cf3b3b216969d69a3e88eb9a6c9c8c7a409"}
OR_COUNTIES = {"bytes": 531, "sha256": "81968386770cafeed21ad8fb51afd37fe455ad0c4beedb329247f63bd3057585"}
PROFILES = {
    "AK": {"state": "Alaska", "source_id": "ak-doe-statewide-voters-cast-20261103",
           "feed": alaska.FEED, "url": alaska.REPORT},
    "AR": {"state": "Arkansas", "source_id": "ar-sos-statewide-ballots-cast-20261103",
           "feed": AR_FEED, "url": AR_SOURCE["url"]},
    "AZ": {"state": "Arizona", "source_id": "az-sos-county-ballots-20261103",
           "feed": "AZ-official", "url": AZ_URL},
    "CT": {"state": "Connecticut", "source_id": "ct-sots-statewide-vv-20261103",
           "feed": CT_FEED, "url": CT_SOURCE["url"]},
    "FL": {"state": "Florida", "source_id": FL_REVIEW, "feed": None, "url": FL_SOURCE["url"]},
    "GA": {"state": "Georgia", "source_id": history.GA_FEED,
           "feed": history.GA_FEED, "url": history.GA_URL},
    "HI": {"state": "Hawaii", "source_id": "hi-oe-final-statewide-turnout-20261103",
           "feed": state_statistics.HI_FEED, "url": state_statistics.HI_URL},
    "KS": {"state": "Kansas", "source_id": history.KS_FEED,
           "feed": history.KS_FEED, "url": history.KS_URL},
    "MN": {"state": "Minnesota", "source_id": "mn-sos-reconciled-statewide-turnout-20261103",
           "feed": mn.IDENTITY, "url": mn.URL},
    "NJ": {"state": "New Jersey", "source_id": history.NJ_FEED,
           "feed": history.NJ_FEED, "url": history.NJ_URL},
    "OH": {"state": "Ohio", "source_id": history.OH_FEED,
           "feed": history.OH_FEED, "url": history.OH_BALLOTS},
    "OR": {"state": "Oregon", "source_id": "or-sos-reconciled-statewide-turnout-20261103",
           "feed": OR_FEED, "url": oregon.PAGE_URL},
    "MT": {"state": "Montana", "source_id": history.MT_FEED,
           "feed": history.MT_FEED, "url": history.MT_URL},
    "NC": {"state": "North Carolina", "source_id": "nc-ncsbe-reconciled-statewide-turnout-20261103",
           "feed": NC_FEED, "url": nc.URL},
    "SC": {"state": "South Carolina", "source_id": "sc-sec-statewide-turnout-20261103",
           "feed": "SC-official", "url": state_statistics.URL},
    "VA": {"state": "Virginia", "source_id": "va-elect-general-election-turnout",
           "feed": history.VA_FEED, "url": history.VA_URL},
    "VT": {"state": "Vermont", "source_id": "vt-sos-registered-turnout-20261103",
           "feed": "VT-registered-5a18635647c699ea", "url": VT_URL},
    "WA": {"state": "Washington", "source_id": "wa-sos-general-election-turnout",
           "feed": history.WA_FEED, "url": history.WA_URL},
    "WY": {
        "state": "Wyoming",
        "source_id": "wy-sos-direct-statewide-ballots-20261103",
        "feed": protected_official_wyoming.IDENTITY,
        "url": protected_official_wyoming.URL,
        "workbook": protected_official_wyoming.WORKBOOK,
        "sheet": "Statewide Total Ballots Cast",
        "cell": "B28",
        "county_rows": 23,
        "initial_shard": {
            "bytes": 102767,
            "sha256": "bc20d19bf2e516a45feb2f0af613708f6be295050305168ea05c2eeab5170c9c",
        },
    },
}
NOTES = [
    "Direct native statewide Total Ballots Cast cell, checked against every county parent; "
    "not a sum of candidate votes or an allocation to local areas.",
    "No matched registration, VAP, CVAP, VEP or demographic denominator is supplied here; "
    "no turnout rate or unique-voter count is qualified.",
    "The workbook filename says OFFICIAL. A native count-update clock, reporting-completion "
    "counter and separate certification evidence are not supplied.",
    "Existing mail activity, county and precinct observations remain separate and are not added.",
]
AZ_NOTES = [
    "Sum of all 15 native county ballotsCast declarations from one Arizona Secretary of State edition.",
    "Separate from the backend statewide field, which may report zero despite positive county counts.",
    "County certification statuses can differ. This is not a certified statewide count, a precinct allocation or a unique-voter count.",
    "County registration values are retained as context, not a qualified turnout denominator.",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compressed(value):
    body = bytearray(gzip.compress(encoded(value), compresslevel=6, mtime=0))
    body[9] = 3
    return bytes(body)


def identity(code):
    return observation_id(PROFILES[code]["source_id"], code + "-2026-11-03-general",
                          code + "-native-statewide-total",
                          {"AK": "native-voters-cast", "VT": "native-votes-cast-including-absentee",
                           "FL": "native-reported-participation",
                           "CT": "native-voters-voted",
                           "HI": "native-total-turnout",
                           "MT": "native-total-turnout",
                           "MN": "native-total-number-voted",
                           "SC": "native-total-voter-turnout",
                           "VA": "native-total-voting",
                           "WA": "native-ballots-counted"}.get(code, "native-total-ballots-cast"),
                          "source_defined" if code in {"AK", "CT", "FL", "HI", "SC", "VA", "VT", "MN", "MT"} else "all_methods")


def native_summary(code, entry):
    profile = PROFILES[code]
    require(isinstance(entry, dict) and entry.get("status") == "reported"
            and isinstance(entry.get("data"), dict),
            "Statewide ballot parent needs reported native evidence")
    data = entry["data"]
    facts = data.get("native_facts")
    require(code == "WY" and protected_official_wyoming.from_facts(facts) == data,
            "Statewide ballot parent differs from its complete native facts")
    original = entry.get("source")
    require(original == {"url": profile["url"], **facts["original"]},
            "Statewide ballot original pin or URL changed")
    controls = data["races"][0]["native_contest_controls"]
    return {
        "contract": CONTRACT,
        "source": copy.deepcopy(original),
        "query_pin": pin(encoded(facts)),
        "workbook": profile["workbook"], "sheet": profile["sheet"], "cell": profile["cell"],
        "ballots": controls["ballots"],
        "counties": [{key: row[key] for key in ("county", "physical_row", "ballots")}
                     for row in controls["counties"]],
    }


def observation(code, summary, retained=False):
    profile = PROFILES[code]
    if code == "AK":
        return alaska_observation(summary, retained)
    if code == "AR":
        return arkansas_observation(summary, retained)
    if code == "CT":
        return connecticut_observation(summary, retained)
    if code == "FL":
        return florida_observation(summary, retained)
    if code == "GA":
        return georgia_observation(summary, retained)
    if code == "HI":
        return hawaii_observation(summary, retained)
    if code == "KS":
        return kansas_observation(summary, retained)
    if code == "NJ":
        return new_jersey_observation(summary, retained)
    if code == "OH":
        return ohio_observation(summary, retained)
    if code == "OR":
        return oregon_observation(summary, retained)
    if code == "MT":
        return montana_observation(summary, retained)
    if code == "VT":
        return vermont_observation(summary, retained)
    if code == "MN":
        return minnesota_observation(summary, retained)
    if code == "NC":
        return north_carolina_observation(summary, retained)
    if code == "SC":
        return south_carolina_observation(summary, retained)
    if code in {"VA", "WA"}:
        return turnout_history_observation(code, summary, retained)
    arizona = code == "AZ"
    selector = ({"scope": "all_15_reported_county_declarations"} if arizona else
                {key: profile[key] for key in ("workbook", "sheet", "cell")})
    expected = {"contract", "source", "query_pin", "ballots", "counties",
                *(() if arizona else ("workbook", "sheet", "cell")),
                *(("source_edition", "backend_statewide_ballots") if arizona else ())}
    require(isinstance(summary, dict) and set(summary) == expected
            and summary["contract"] == CONTRACT, "Malformed reviewed statewide ballot summary")
    if not arizona:
        require(all(summary[key] == value for key, value in selector.items()),
                "Statewide ballot physical parent changed")
    source = summary["source"]
    for selected in (source, summary["query_pin"]):
        require(isinstance(selected, dict) and type(selected.get("bytes")) is int
                and selected["bytes"] > 0
                and isinstance(selected.get("sha256"), str)
                and len(selected["sha256"]) == 64
                and all(char in "0123456789abcdef" for char in selected["sha256"]),
                "Statewide ballot source or query pin is missing")
    require(set(source) == {"url", "bytes", "sha256"} and source["url"] == profile["url"],
            "Statewide ballot source identity changed")
    counties = summary["counties"]
    require(isinstance(counties, list) and len(counties) == (15 if arizona else profile["county_rows"]),
            "Statewide ballot county controls are incomplete")
    if arizona:
        from scripts.results_native_state_family import AZ_COUNTIES, _clock, _utc_clock
        identities = [(key, name, identity) for key, (name, _, identity) in sorted(AZ_COUNTIES.items())]
        edition = _clock(_utc_clock(summary["source_edition"]))
        require(all(set(row) == {"county_code", "county", "county_uuid", "ballots",
                                 "registration", "as_of", "official_status"}
                    and type(row["registration"]) is int and count(row["registration"]) == row["registration"]
                    and 0 <= row["ballots"] <= row["registration"]
                    and type(row["official_status"]) is bool
                    and _clock(_utc_clock(row["as_of"])) <= edition
                    for row in counties)
                and [(row["county_code"], row["county"], row["county_uuid"]) for row in counties] == identities
                and type(summary["backend_statewide_ballots"]) is int
                and summary["backend_statewide_ballots"] in {0, summary["ballots"]}
                and summary["ballots"] > 0, "Arizona county roll-up evidence changed")
    else:
        require(all(isinstance(row, dict) and set(row) == {"county", "physical_row", "ballots"}
                and isinstance(row["county"], str) and row["county"]
                and type(row["physical_row"]) is int for row in counties)
            and len({row["county"] for row in counties}) == len(counties)
            and [row["physical_row"] for row in counties] == list(range(5, 28)),
            "Statewide ballot county identity or physical rows changed")
    total = summary["ballots"]
    require(type(total) is int and count(total) == total
            and all(type(row["ballots"]) is int and count(row["ballots"]) == row["ballots"]
                    for row in counties)
            and sum(row["ballots"] for row in counties) == total,
            "Statewide ballot controls do not reconcile")
    status = "retained_after_failure" if retained else "reported"
    notes = AZ_NOTES if arizona else NOTES
    measure = "County ballotsCast declarations (sum)" if arizona else "Total Ballots Cast"
    view = {
        "state": profile["state"], "state_code": code, "year": 2026,
        "geography_level": "statewide", "mode": "official", "status": status,
        "ballots": total, "denominator": None, "denominator_basis": "electorate_not_supplied",
        "reported_pct": None, "validated_pct": None, "published_pct": None,
        "native_printed_pct": None, "source_date": None, "source_update_label": None,
        "source_update_timezone": None, "source_status_literal": None,
        "reported_units": None, "total_units": None,
        "source_url": source["url"], "source_sha256": source["sha256"],
        "complete_download_url": None, "automatic_source_refresh": True,
        "participation_measure_kind": "ballots_cast",
        "participation_measure_literal": measure,
        "participation_measure_label": "Statewide sum of reported county ballots" if arizona else "Native statewide ballots cast",
        "cast_ballot_count_qualified": True, "unique_voter_count_qualified": False,
        "maps_approved": False, "quality": list(notes),
        "source_reporting_label": " ".join(notes),
        "statewide_ballot_parent": copy.deepcopy(summary),
    }
    if arizona:
        view["source_publication_label"] = summary["source_edition"]
    row = {
        "contract": VERSION, "id": identity(code),
        "election": {"id": code + "-2026-11-03-general", "year": 2026,
                     "date": "2026-11-03", "type": "general", "qualification": "native"},
        "geography": {
            "id": code + "-native-statewide-total", "name": profile["state"],
            "state_code": code, "level": "state", "parent_id": None,
            "join": {"status": "nongeographic", "reference_id": None,
                     "feature_key": None, "evidence": None},
        },
        "measure": {"id": "native-total-ballots-cast", "literal": measure,
                    "kind": "ballots_cast", "mode": "all_methods", "unit": "ballots"},
        "count": {"value": total, "literal": total, "status": "reported"},
        "denominator": None,
        "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": None, "reported_units": None,
                             "total_units": None, "complete": None},
        "source": {"id": profile["source_id"], "url": source["url"],
                   "input_sha256": source["sha256"],
                   "selector": selector,
                   "classification": "public_aggregate", "fields": copy.deepcopy(view)},
        "quality": {"conflicts": [], "notes": list(notes)}, "view": view,
    }
    return validate(row)


def validate_existing(code, row):
    view = row.get("view", {})
    require(view.get("status") in ("reported", "retained_after_failure"),
            "Statewide ballot retained status changed")
    expected = observation(code, view.get("statewide_ballot_parent"),
                           view["status"] == "retained_after_failure")
    require(row == expected, "Existing statewide ballot observation changed")


def reviewed_addition(code, old, new, previous_pin):
    if code not in PROFILES or code == "WY" and previous_pin != PROFILES[code]["initial_shard"]:
        return False
    selected = identity(code)
    if selected in old or set(new) != set(old) | {selected}:
        return False
    try:
        validate_existing(code, new[selected])
    except (ValueError, KeyError, TypeError):
        return False
    return code != "WY" or all(old[key] == new[key] for key in old)


def arizona_summary(snapshot):
    entries = [item for item in snapshot.get("participation_observations", [])
               if item.get("channel") == "AZ-official" and item.get("status") == "reported"]
    if not entries:
        return None
    require(len(entries) == 1, "Ambiguous Arizona administrative source")
    entry, = entries
    data = entry["observation"]
    facts = data["native_state_statistics"]
    source = entry["source"]
    require(facts["profile"] == "az-native-county-declaration-rollup-v1"
            and facts["state_code"] == "AZ" and facts["election_date"] == "2026-11-03"
            and facts["source_url"] == source["url"] == AZ_URL
            and data["denominator"] is None and data["validated_pct"] is None,
            "Arizona statewide source measure or election changed")
    return {"contract": CONTRACT, "source": {key: source[key] for key in ("url", "bytes", "sha256")},
            "query_pin": pin(encoded(facts)), "ballots": data["ballots"],
            "counties": facts["county_controls"], "source_edition": facts["source_edition"],
            "backend_statewide_ballots": facts["backend_statewide_ballots"]}


def vermont_summary(snapshot):
    entry = snapshot.get("granular_sources", {}).get(PROFILES["VT"]["feed"], {})
    if entry.get("status") != "reported":
        return None
    data = entry["data"]
    queries = data["complete_native_query"]["groups"]["queries"]
    statewide, = queries["summary_total"]["rows"]
    counties = queries["summary_parents"]["rows"]
    return {"contract": CONTRACT, "source": entry["source"],
            "source_edition": data["source_clock"], "statewide": statewide, "counties": counties}


def versioned_report_date(literal):
    value = datetime.strptime(literal, "%m/%d/%Y")
    require(datetime(2026, 11, 3) <= value < datetime(2027, 2, 1),
            "Vermont report date is outside the reviewed election window")
    return value


def vermont_observation(summary, retained):
    require(summary["contract"] == CONTRACT, "Vermont statewide report contract changed")
    source, statewide, counties = (summary[key] for key in ("source", "statewide", "counties"))
    require(set(source) == {"url", "bytes", "sha256"} and source["url"] == VT_URL
            and type(source["bytes"]) is int and source["bytes"] > 0,
            "Vermont statewide report source changed")
    require(tuple(row["native_unit"] for row in counties) == VT_COUNTIES
            and statewide["native_unit"] == statewide["parent"] == "State Total",
            "Vermont statewide county identity changed")
    for row in [*counties, statewide]:
        ballots, registered, absentee = (row[key] for key in VT_FIELDS)
        require(all(type(row[key]) is int and count(row[key]) == row[key] for key in VT_FIELDS)
                and 0 <= absentee <= ballots <= registered,
                "Vermont native participation totals are inconsistent")
    require(all(sum(row[key] for row in counties) == statewide[key] for key in VT_FIELDS),
            "Vermont county and statewide totals disagree")
    ballots, registered, _ = (statewide[key] for key in VT_FIELDS)
    printed = statewide["native_turnout_percent"]
    require(registered > 0 and printed.endswith("%")
            and abs(100 * Decimal(ballots) / registered - Decimal(printed[:-1])) <= Decimal("0.005"),
            "Vermont statewide printed turnout fraction disagrees")
    versioned_report_date(summary["source_edition"])
    status = "retained_after_failure" if retained else "reported"
    notes = ["Vermont's native State Total reconciles to all 14 county controls.",
             "The source-defined rate divides Total Votes Cast (includes absentee) by the same report's Registered Voters.",
             "This is not a population or demographic rate. The report date does not establish a count-update time."]
    basis = "native_registered_voters_same_vermont_report"
    measure = "Total Votes Cast (includes absentee)"
    rate = 100 * ballots / registered
    view = {"state": "Vermont", "state_code": "VT", "year": 2026,
            "geography_level": "statewide", "mode": "official", "status": status,
            "ballots": ballots, "denominator": registered, "denominator_basis": basis,
            "reported_pct": rate, "validated_pct": rate, "native_printed_pct": printed,
            "source_date": None, "source_update_label": None, "source_update_timezone": None,
            "source_publication_label": summary["source_edition"],
            "reported_units": None, "total_units": None,
            "source_url": source["url"], "source_sha256": source["sha256"],
            "complete_download_url": None, "automatic_source_refresh": True, "maps_approved": False,
            "participation_measure_kind": "participation_reported", "participation_measure_literal": measure,
            "participation_measure_label": measure, "cast_ballot_count_qualified": False,
            "unique_voter_count_qualified": False, "quality": notes,
            "source_reporting_label": " ".join(notes), "statewide_ballot_parent": copy.deepcopy(summary)}
    return validate({
        "contract": VERSION, "id": identity("VT"),
        "election": {"id": "VT-2026-11-03-general", "year": 2026, "date": "2026-11-03",
                     "type": "general", "qualification": "native"},
        "geography": {"id": "VT-native-statewide-total", "name": "Vermont", "state_code": "VT",
                      "level": "state", "parent_id": None, "join": {"status": "nongeographic",
                          "reference_id": None, "feature_key": None, "evidence": None}},
        "measure": {"id": "native-votes-cast-including-absentee", "literal": measure,
                    "kind": "participation_reported", "mode": "source_defined", "unit": "source_reported_count"},
        "count": {"value": ballots, "literal": ballots, "status": "reported"},
        "denominator": {"value": registered, "literal": "Registered Voters", "basis": basis, "qualified": True},
        "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": None, "reported_units": None, "total_units": None, "complete": None},
        "source": {"id": PROFILES["VT"]["source_id"], "url": source["url"], "input_sha256": source["sha256"],
                   "selector": statewide["source_ref"], "classification": "public_aggregate",
                   "fields": copy.deepcopy(view)},
        "quality": {"conflicts": [], "notes": notes}, "view": view,
    })


def minnesota_summary(snapshot):
    sources = snapshot.get("granular_sources", {})
    report, local = sources.get(mn.IDENTITY, {}), sources.get("MN-native-local", {})
    if report.get("status") != "reported" or local.get("status") != "reported":
        return None
    data = report["data"]
    facts = mn.reconcile(data, local["data"]["complete_native_query"])
    require(data["reconciliation"] == facts and data["statistical_txt"] == local["source"],
            "Minnesota statewide report does not match the retained statistical TXT")
    return {"contract": CONTRACT, "source": report["source"], "statistical_txt": local["source"],
            "source_edition": data["date"], "source_status": data["status"],
            "fields": data["fields"], "counties": data["counties"],
            "county_count": facts["counties"], "precincts": facts["precincts"],
            "total_number_voted": facts["total_number_voted"]}


def minnesota_observation(summary, retained):
    from scripts.results_granular import MN_URL

    profile = PROFILES["MN"]
    for field, url in (("source", profile["url"]), ("statistical_txt", MN_URL)):
        receipt = summary[field]
        require(set(receipt) == {"url", "bytes", "sha256"} and receipt["url"] == url
                and type(receipt["bytes"]) is int and receipt["bytes"] > 0
                and len(receipt["sha256"]) == 64
                and all(char in "0123456789abcdef" for char in receipt["sha256"]),
                "Minnesota statewide original receipt changed")
    fields, counties = summary["fields"], summary["counties"]
    total, precincts = summary["total_number_voted"], summary["precincts"]
    literal = summary["source_status"]
    require(summary["contract"] == CONTRACT and len(counties) == summary["county_count"] == 87
            and len({row["county_id"] for row in counties}) == 87
            and sum(row["total_number_voted"] for row in counties) == total
            and sum(row["precincts"] for row in counties) == precincts
            and mn.integer(fields["Estimated Voters"]) == total
            and summary["source_edition"] == datetime.strptime(
                fields["Last Updated"], "%m/%d/%y %I:%M %p").isoformat()
            and literal in {"Unofficial Results", "Official Results"},
            "Minnesota statewide ballot evidence differs")
    status = "retained_after_failure" if retained else "reported"
    notes = [
        "Statewide source Total Number Voted from complete reporting precinct statistics; "
        "matches the state's printed Estimated Voters in every county.",
        "Published Estimated Turnout uses a separate UF electorate estimate. "
        "No administrative turnout rate or unique-voter count is qualified.",
        "Source status is shown as printed. The reporting page does not itself establish certification.",
    ]
    measure = "Total Number Voted"
    view = {"state": profile["state"], "state_code": "MN", "year": 2026,
        "geography_level": "statewide", "mode": "official", "status": status,
        "ballots": total, "denominator": None, "denominator_basis": "electorate_not_supplied",
        "reported_pct": None, "validated_pct": None, "published_pct": None,
        "native_printed_pct": None, "source_date": summary["source_edition"][:10],
        "source_update_label": fields["Last Updated"], "source_update_timezone": None,
        "source_status_literal": literal, "reported_units": precincts, "total_units": precincts,
        "source_url": profile["url"], "source_sha256": summary["source"]["sha256"],
        "complete_download_url": None, "automatic_source_refresh": True,
        "participation_measure_kind": "participation_reported", "participation_measure_literal": measure,
        "participation_measure_label": "Total number voted (precinct statistics)",
        "cast_ballot_count_qualified": False, "unique_voter_count_qualified": False,
        "native_election_id_qualified": True, "maps_approved": False,
        "quality": notes, "source_reporting_label": " ".join(notes),
        "statewide_ballot_parent": copy.deepcopy(summary)}
    return validate({
        "contract": VERSION, "id": identity("MN"),
        "election": {"id": "MN-2026-11-03-general", "year": 2026, "date": "2026-11-03",
                     "type": "general", "qualification": "native"},
        "geography": {"id": "MN-native-statewide-total", "name": profile["state"],
                      "state_code": "MN", "level": "state", "parent_id": None,
                      "join": {"status": "nongeographic", "reference_id": None,
                               "feature_key": None, "evidence": None}},
        "measure": {"id": "native-total-number-voted", "literal": measure,
                    "kind": "participation_reported", "mode": "source_defined", "unit": "source_reporting_count"},
        "count": {"value": total, "literal": total, "status": "reported"},
        "denominator": None, "source_clock": {"literal": fields["Last Updated"], "timezone": None},
        "reporting_status": {"literal": literal, "reported_units": precincts,
                             "total_units": precincts, "complete": True},
        "source": {"id": profile["source_id"], "url": profile["url"],
                   "input_sha256": summary["source"]["sha256"], "classification": "public_aggregate",
                   "selector": {"ersElectionId": 201, "html_statistic": "Estimated Voters",
                                "txt_statistic": measure}, "fields": copy.deepcopy(view)},
        "quality": {"conflicts": [], "notes": notes}, "view": view})


def turnout_history_summary(snapshot, code):
    entry = snapshot.get("granular_sources", {}).get(PROFILES[code]["feed"], {})
    if entry.get("status") != "reported":
        return None
    data = entry["data"]
    if data["current_election_status"] == "not_yet_published":
        return None
    row = data["complete_native_query"][0]
    require(data["current_election_status"] == "row_published" and row["year"] == 2026,
            f"{code} general-election table has no 2026 parent")
    summary = {"contract": CONTRACT, "source": entry["source"], "native_row": row}
    if code == "VA":
        require(data["published_after_certification"] is True and data["native_measure"] == "Total Voting",
                "Virginia source publication policy changed")
        summary["published_after_certification"] = True
    return summary


def turnout_history_observation(code, summary, retained):
    source, native = summary["source"], summary["native_row"]
    profile, virginia = PROFILES[code], code == "VA"
    measure = "Total Voting" if virginia else "Ballots Counted"
    count_field = "total_voting" if virginia else "ballots_counted"
    registered, ballots, printed = (native[k] for k in ("registered_voters", count_field, "published_turnout"))
    status = "Published after certification" if virginia else None
    if virginia:
        require(summary["published_after_certification"] is True and native["native_year"] == "2026",
                "Virginia source publication scope changed")
    require(summary["contract"] == CONTRACT and set(source) == {"url", "sha256", "bytes"}
            and source["url"] == profile["url"] and type(source["bytes"]) is int and source["bytes"] > 0
            and isinstance(printed, str) and re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,2})?%", printed)
            and native["year"] == 2026 and type(registered) is type(ballots) is int
            and count(registered) == registered and count(ballots) == ballots and 0 < ballots <= registered,
            f"{code} statewide statistical parent changed")
    places = len(printed.partition(".")[2].removesuffix("%"))
    exact = Decimal(ballots) * 100 / registered
    compatible = exact.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP) == Decimal(printed[:-1])
    require(native["rate_qualified"] is compatible, f"{code} published rate audit differs")
    notes = [f"{profile['state']} statewide general-election table; {measure} and registrations are from one printed row.",
             "The Department publishes this series after certification; no native count-update clock is supplied."
             if virginia else "Calendar-year row has no native count-update clock or explicit certification statement.",
             "No county/precinct allocation, CVAP, VEP or unique-voter claim."]
    if virginia:
        notes.append("The source register includes active, inactive and overseas voters.")
    if not compatible:
        notes.append("Printed fraction disagrees with the source counts; no turnout rate is qualified.")
    rate = float(exact) if compatible else None
    basis = "native_registered_voters_same_statewide_general_election_table"
    kind = "participation_reported" if virginia else "ballots_cast"
    view = {"state": profile["state"], "state_code": code, "year": 2026, "mode": "official",
            "geography_level": "statewide", "status": "retained_after_failure" if retained else "reported",
            "ballots": ballots, "denominator": registered, "denominator_basis": basis,
            "reported_pct": rate, "validated_pct": rate, "published_pct": None,
            "native_printed_pct": printed, "source_date": None, "source_update_label": None,
            "source_update_timezone": None, "source_status_literal": status,
            "reported_units": None, "total_units": None, "source_url": source["url"],
            "source_sha256": source["sha256"], "complete_download_url": None, "automatic_source_refresh": True,
            "participation_measure_kind": kind, "participation_measure_literal": measure,
            "participation_measure_label": "Statewide Total Voting" if virginia else "Statewide ballots counted",
            "cast_ballot_count_qualified": not virginia,
            "unique_voter_count_qualified": False, "native_election_id_qualified": True,
            "maps_approved": False, "quality": notes, "source_reporting_label": " ".join(notes),
            "statewide_ballot_parent": copy.deepcopy(summary)}
    return validate({
        "contract": VERSION, "id": identity(code),
        "election": {"id": code + "-2026-11-03-general", "year": 2026, "date": "2026-11-03",
                     "type": "general", "qualification": "native"},
        "geography": {"id": code + "-native-statewide-total", "name": profile["state"], "state_code": code,
                      "level": "state", "parent_id": None, "join": {"status": "nongeographic",
                          "reference_id": None, "feature_key": None, "evidence": None}},
        "measure": {"id": "native-total-voting" if virginia else "native-ballots-counted", "literal": measure,
                    "kind": kind, "mode": "source_defined" if virginia else "all_methods",
                    "unit": "source_reporting_count" if virginia else "ballots"},
        "count": {"value": ballots, "literal": ballots, "status": "reported"},
        "denominator": {"value": registered, "literal": "Registered Voters", "basis": basis,
                        "qualified": compatible},
        "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": status, "reported_units": None, "total_units": None, "complete": None},
        "source": {"id": profile["source_id"], "url": source["url"], "input_sha256": source["sha256"],
                   "classification": "public_aggregate", "selector": {"Year": 2026},
                   "fields": copy.deepcopy(view)},
        "quality": {"conflicts": [] if compatible else [{"code": "printed_turnout_disagrees"}], "notes": notes},
        "view": view})


def alaska_summary(snapshot):
    entry = snapshot.get("granular_sources", {}).get(alaska.FEED, {})
    if entry.get("status") != "reported":
        return None
    data = entry["data"]
    query = data["complete_native_query"]
    result = alaska.reconcile(query["pdf"], query["statewide_feed"])
    require(data["date"] == result["date"] and data["reconciliation"] == result,
            "Alaska participation controls differ from the complete native query")
    return {"contract": CONTRACT, "source": data["report"], "statewide_feed": entry["source"],
            "source_edition": data["date"], "complete_native_query": query}


def alaska_observation(summary, retained):
    profile, query = PROFILES["AK"], summary["complete_native_query"]
    facts = alaska.reconcile(query["pdf"], query["statewide_feed"])
    for key, url in (("source", alaska.REPORT), ("statewide_feed", alaska.URL)):
        receipt = summary[key]
        require(set(receipt) == {"url", "bytes", "sha256"} and receipt["url"] == url
                and type(receipt["bytes"]) is int and receipt["bytes"] > 0
                and re.fullmatch(r"[a-f0-9]{64}", receipt["sha256"]),
                "Alaska statewide report receipt differs")
    require(summary["contract"] == CONTRACT and summary["source_edition"] == facts["date"],
            "Alaska statewide report edition differs")
    ballots, registered = facts["voters"], facts["registered"]
    rate = 100 * ballots / registered
    label, basis = "Voters Cast", "native_registered_voters_same_alaska_summary"
    notes = [
        "Statewide Voters Cast and registration from one election summary, corroborated by federal b/v controls, not candidate votes.",
        "Precinct inventories may differ between the summary PDF and statewide feed. Neither completeness nor a unique-voter count is inferred.",
        "Report generation and feed update clocks are retained separately; their timezone and a count clock are not independently declared.",
    ]
    view = {"state": "Alaska", "state_code": "AK", "year": 2026, "mode": "official",
            "geography_level": "statewide", "status": "retained_after_failure" if retained else "reported",
            "ballots": ballots, "denominator": registered, "denominator_basis": basis,
            "reported_pct": rate, "validated_pct": rate, "published_pct": None,
            "native_printed_pct": facts["printed_fraction"], "source_date": facts["date"][:10],
            "source_update_label": None, "source_update_timezone": None,
            "source_publication_label": query["pdf"]["page_clocks_and_ordinals"][0][0],
            "source_status_literal": facts["source_status"], "reported_units": facts["reported_precincts"],
            "total_units": None, "source_url": profile["url"], "source_sha256": summary["source"]["sha256"],
            "complete_download_url": None, "automatic_source_refresh": True, "maps_approved": False,
            "participation_measure_kind": "voters_reported", "participation_measure_literal": label,
            "participation_measure_label": "Statewide Voters Cast (source-reported)",
            "native_election_id_qualified": True, "cast_ballot_count_qualified": False,
            "unique_voter_count_qualified": False, "quality": notes,
            "source_reporting_label": " ".join(notes), "statewide_ballot_parent": copy.deepcopy(summary)}
    return validate({
        "contract": VERSION, "id": identity("AK"),
        "election": {"id": "AK-2026-11-03-general", "year": 2026, "date": "2026-11-03",
                     "type": "general", "qualification": "native"},
        "geography": {"id": "AK-native-statewide-total", "name": "Alaska", "state_code": "AK",
                      "level": "state", "parent_id": None, "join": {"status": "nongeographic",
                          "reference_id": None, "feature_key": None, "evidence": None}},
        "measure": {"id": "native-voters-cast", "literal": label, "kind": "voters_reported",
                    "mode": "source_defined", "unit": "source_reporting_count"},
        "count": {"value": ballots, "literal": ballots, "status": "reported"},
        "denominator": {"value": registered, "literal": "Registered Voters", "basis": basis, "qualified": True},
        "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": facts["source_status"], "reported_units": facts["reported_precincts"],
                             "total_units": None, "complete": None},
        "source": {"id": profile["source_id"], "url": profile["url"],
                   "input_sha256": summary["source"]["sha256"], "classification": "public_aggregate",
                   "selector": {"physical_page": 1, "statistic": label}, "fields": copy.deepcopy(view)},
        "quality": {"conflicts": [], "notes": notes}, "view": view})


def arkansas_summary(snapshot, shard, previous):
    entry = snapshot.get("granular_sources", {}).get(AR_FEED, {})
    facts = (entry.get("data") or {}).get("statewide_ballot_parent")
    if entry.get("status") == "reported" and facts is not None:
        return {"contract": CONTRACT, "source": entry["source"], "archived_capture": None, **facts}
    if previous is not None:
        return None
    records = [row for row in shard["records"] if row["view"].get("review_id") == AR_REVIEW
               and row["geography"]["level"] in {"county", "county_equivalent"}]
    if not records:
        return None
    counties = {row["view"]["county_id"].removeprefix("additional:AR:"): row["view"]["native_record"]
                for row in records}
    require(len(counties) == len(records), "Duplicate retained Arkansas county controls")
    facts = state_family.arkansas_parent(dict(zip(state_family.AR_PARENT_FIELDS, AR_TOTAL)), counties)
    require(pin(encoded(facts["counties"])) == AR_COUNTIES, "Retained Arkansas county controls changed")
    return {"contract": CONTRACT, "source": AR_SOURCE, "archived_capture": AR_CAPTURE,
            "election_id": state_family.AR_ELECTION_ID, "status": "UNOFFICIAL",
            "count_source_clock": None, **facts}


def arkansas_observation(summary, retained):
    source, statewide, counties = (summary[key] for key in ("source", "statewide", "counties"))
    archive = summary["archived_capture"]
    require(summary["contract"] == CONTRACT and summary["election_id"] == state_family.AR_ELECTION_ID
            and summary["status"] in {"OFFICIAL", "UNOFFICIAL"} and summary["count_source_clock"] is None
            and set(source) == {"url", "bytes", "sha256"} and source["url"] == AR_SOURCE["url"]
            and type(source["bytes"]) is int and source["bytes"] > 0
            and re.fullmatch(r"[a-f0-9]{64}", source["sha256"]),
            "Arkansas statewide report identity or receipt changed")
    if archive is not None:
        require(retained and archive == AR_CAPTURE and source == AR_SOURCE and statewide == AR_TOTAL
                and summary["status"] == "UNOFFICIAL" and pin(encoded(counties)) == AR_COUNTIES,
                "Retained Arkansas statewide edition changed")
    fields = state_family.AR_PARENT_FIELDS
    require(all(len(row) == len(fields) + 1 for row in counties) and len(statewide) == len(fields),
            "Arkansas statewide query fields changed")
    native = {row[0]: {"LocationID": row[0], **dict(zip(fields, row[1:]))} for row in counties}
    require(state_family.arkansas_parent(dict(zip(fields, statewide)), native)
            == {"statewide": statewide, "counties": counties}, "Arkansas statewide query changed")
    ballots, registered, reported, total, partial = statewide
    measure = "Total Ballots Cast"
    status = "retained_after_failure" if retained else "reported"
    notes = ["Arkansas's direct statewide total agrees with all 75 counties in the same full-election export.",
             "The registration stock and reporting-unit counters are contextual. No rate, certification, "
             "unique-voter estimate or new local map join is qualified.",
             "The capture time is not a native count-update clock."]
    if archive:
        notes.insert(0, "Retained from the November 5, 2026 capture; not a current or final total.")
    view = {"state": "Arkansas", "state_code": "AR", "year": 2026, "mode": "official",
            "geography_level": "statewide", "status": status, "ballots": ballots,
            "registered": registered, "denominator": None, "denominator_basis": "electorate_not_supplied",
            "reported_pct": None, "validated_pct": None, "native_printed_pct": None,
            "source_update_label": None, "source_update_timezone": None,
            "source_date": None, "source_capture_date": archive, "source_status_literal": summary["status"],
            "reported_units": reported, "total_units": total, "partially_reported_units": partial,
            "source_url": source["url"], "source_sha256": source["sha256"], "complete_download_url": None,
            "automatic_source_refresh": True, "maps_approved": False,
            "participation_measure_kind": "ballots_cast", "participation_measure_literal": measure,
            "participation_measure_label": "Native statewide ballots cast", "cast_ballot_count_qualified": True,
            "unique_voter_count_qualified": False, "quality": notes,
            "source_reporting_label": " ".join(notes), "statewide_ballot_parent": copy.deepcopy(summary)}
    return validate({
        "contract": VERSION, "id": identity("AR"),
        "election": {"id": "AR-2026-11-03-general", "year": 2026, "date": "2026-11-03",
                     "type": "general", "qualification": "native"},
        "geography": {"id": "AR-native-statewide-total", "name": "Arkansas", "state_code": "AR",
                      "level": "state", "parent_id": None, "join": {"status": "nongeographic",
                          "reference_id": None, "feature_key": None, "evidence": None}},
        "measure": {"id": "native-total-ballots-cast", "literal": measure,
                    "kind": "ballots_cast", "mode": "all_methods", "unit": "ballots"},
        "count": {"value": ballots, "literal": ballots, "status": "reported"},
        "denominator": None, "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": summary["status"], "reported_units": reported,
                             "total_units": total, "complete": False if reported < total else None},
        "source": {"id": PROFILES["AR"]["source_id"], "url": source["url"], "input_sha256": source["sha256"],
                   "classification": "public_aggregate", "selector": {"path": "TurnoutData.TotalBallotsCast"},
                   "fields": copy.deepcopy(view)},
        "quality": {"conflicts": [], "notes": notes}, "view": view,
    })


def connecticut_summary(snapshot, shard, previous):
    entry = snapshot.get("granular_sources", {}).get(CT_FEED, {})
    if entry.get("status") == "reported":
        data = entry["data"]
        rows = data["complete_native_query"]
        require(set(rows) == {str(i) for i in range(1, 171)} and rows["170"]["NM"] == "Total",
                "Connecticut statewide town inventory changed")
        version = data["source_version"]
        return {"contract": CONTRACT, "version": version, "archived": False,
                "source": {"url": data["source_url"], **data["numerical_input_pins"]["voterTurnout_Electiondata"]},
                "parent": data["election_parent"], "total": [rows["170"][key] for key in CT_FIELDS],
                "towns": [[str(i), rows[str(i)]["NM"], *[rows[str(i)][key] for key in CT_FIELDS]]
                          for i in range(1, 170)]}
    if previous is not None:
        return None
    towns = [[row["view"]["source_town_id"], row["geography"]["name"],
              *[row["view"]["native_record"][key] for key in CT_FIELDS]]
             for row in shard["records"] if row["view"].get("source_town_id")]
    if not towns:
        return None
    towns.sort(key=lambda town: int(town[0]))
    return {"contract": CONTRACT, "version": 52337, "archived": True, "source": CT_SOURCE,
            "parent": CT_PARENT, "total": list(CT_TOTAL), "towns": towns}


def connecticut_observation(summary, retained):
    source, towns, totals, parent, version = (summary[k] for k in ("source", "towns", "total", "parent", "version"))
    require(summary["contract"] == CONTRACT and type(version) is int and version >= 52337
            and set(source) == {"url", "bytes", "sha256"} and type(source["bytes"]) is int and source["bytes"] > 0
            and re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            and source["url"] == f"{CT_ROOT}{version}/voterTurnout_Electiondata.json"
            and [row[0] for row in towns] == [str(i) for i in range(1, 170)]
            and len({row[1] for row in towns}) == 169
            and all(len(row) == len(CT_FIELDS) + 2 for row in towns) and len(totals) == len(CT_FIELDS),
            "Connecticut statewide evidence or edition changed")
    if summary["archived"]:
        require(retained and source == CT_SOURCE and parent == CT_PARENT and totals == list(CT_TOTAL)
                and pin(encoded(towns)) == CT_TOWNS, "Retained Connecticut town evidence changed")
    values = [[count(value) for value in row[2:]] for row in towns]
    totals = [count(value) for value in totals]
    require(None not in totals and all(None not in row for row in values)
            and [sum(column) for column in zip(*values)] == totals
            and parent["ID"] == "108" and [count(parent[key]) for key in ("RV", "BC")] == totals[:2],
            "Connecticut town controls and direct statewide parent disagree")
    registered, total = totals[:2]
    measure = "Voters voted (native VV)"
    profile = PROFILES["CT"]
    notes = ["Direct statewide VV checked against the separate election parent and all 169 town rows.",
             "The eligible-voter field and printed fraction are source context, not a qualified turnout rate.",
             "No clock, certification, unique-voter count or map join is inferred."]
    if summary["archived"]:
        notes.insert(0, "Retained November 5, 2026 capture. The parent reported 775 of 776 reporting units.")
    view = {"state": "Connecticut", "state_code": "CT", "year": 2026, "mode": "official",
            "geography_level": "statewide", "status": "retained_after_failure" if retained else "reported",
            "ballots": total, "registered": registered, "denominator": None,
            "denominator_basis": "electorate_not_supplied", "reported_pct": None, "validated_pct": None,
            "native_printed_pct": parent["TO"], "source_update_label": None,
            "source_update_timezone": None, "source_date": None, "source_version": version,
            "source_status_literal": "Source-reported turnout", "reported_units": None, "total_units": None,
            "source_url": source["url"], "source_sha256": source["sha256"], "complete_download_url": None,
            "automatic_source_refresh": True, "maps_approved": False,
            "participation_measure_kind": "participation_reported", "participation_measure_literal": measure,
            "participation_measure_label": measure, "cast_ballot_count_qualified": False,
            "unique_voter_count_qualified": False, "quality": notes,
            "source_reporting_label": " ".join(notes), "statewide_ballot_parent": copy.deepcopy(summary)}
    return validate({
        "contract": VERSION, "id": identity("CT"),
        "election": {"id": "CT-2026-11-03-general", "year": 2026, "date": "2026-11-03",
                     "type": "general", "qualification": "native"},
        "geography": {"id": "CT-native-statewide-total", "name": "Connecticut", "state_code": "CT",
                      "level": "state", "parent_id": None, "join": {"status": "nongeographic",
                          "reference_id": None, "feature_key": None, "evidence": None}},
        "measure": {"id": "native-voters-voted", "literal": measure,
                    "kind": "participation_reported", "mode": "source_defined", "unit": "source_reported_count"},
        "count": {"value": total, "literal": total, "status": "reported"},
        "denominator": None, "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": None, "reported_units": None, "total_units": None, "complete": None},
        "source": {"id": profile["source_id"], "url": source["url"], "input_sha256": source["sha256"],
                   "classification": "public_aggregate", "selector": {"native_row": "170", "field": "VV"},
                   "fields": copy.deepcopy(view)},
        "quality": {"conflicts": [], "notes": notes}, "view": view,
    })


def hawaii_summary(snapshot):
    entry = snapshot.get("granular_sources", {}).get(state_statistics.HI_FEED, {})
    if entry.get("status") != "reported":
        return None
    data = entry["data"]
    reports = data["complete_native_query"]
    require(data["reconciliation"] == state_statistics.hawaii_controls(reports)
            and reports["histatewide"]["source"] == entry["source"],
            "Hawaii statewide facts differ from their complete report query")
    return {"contract": CONTRACT, "source": entry["source"], "reports": reports}


def hawaii_observation(summary, retained):
    require(summary["contract"] == CONTRACT, "Malformed Hawaii statewide report")
    facts = state_statistics.hawaii_controls(summary["reports"])
    parent, source = facts["statewide"], summary["source"]
    require(source == summary["reports"]["histatewide"]["source"], "Hawaii statewide source receipt differs")
    difference = facts["administration_minus_statewide"]["In-Person TURNOUT"]
    notes = ["Direct statewide TOTAL TURNOUT, not candidate votes or a sum of local reports.",
             "The statewide mail and in-person counts reconcile internally. The four separately printed "
             f"administration reports have an in-person difference of {difference:+d} versus statewide.",
             "The native FINAL label does not independently establish certification. The print time is not "
             "a count-update clock. No turnout rate, unique-voter estimate or new map join is qualified."]
    measure, profile = "TOTAL TURNOUT", PROFILES["HI"]
    clock = parent["source_clock"]
    view = {"state": "Hawaii", "state_code": "HI", "year": 2026, "mode": "official",
            "geography_level": "statewide", "status": "retained_after_failure" if retained else "reported",
            "ballots": parent["count"], "registered": parent["registered"], "denominator": None,
            "denominator_basis": "electorate_not_supplied", "reported_pct": None, "validated_pct": None,
            "native_printed_pct": parent["native_fraction_literal"], "source_update_label": None,
            "source_update_timezone": None, "source_date": None, "source_publication_label": clock,
            "source_status_literal": "FINAL", "reported_units": None, "total_units": None,
            "source_url": source["url"], "source_sha256": source["sha256"], "complete_download_url": None,
            "automatic_source_refresh": True, "maps_approved": False,
            "participation_measure_kind": "participation_reported", "participation_measure_literal": measure,
            "participation_measure_label": "Native statewide total turnout", "cast_ballot_count_qualified": False,
            "unique_voter_count_qualified": False, "quality": notes,
            "source_reporting_label": " ".join(notes), "statewide_ballot_parent": copy.deepcopy(summary)}
    return validate({
        "contract": VERSION, "id": identity("HI"),
        "election": {"id": "HI-2026-11-03-general", "year": 2026, "date": "2026-11-03",
                     "type": "general", "qualification": "native"},
        "geography": {"id": "HI-native-statewide-total", "name": "Hawaii", "state_code": "HI",
                      "level": "state", "parent_id": None, "join": {"status": "nongeographic",
                          "reference_id": None, "feature_key": None, "evidence": None}},
        "measure": {"id": "native-total-turnout", "literal": measure,
                    "kind": "participation_reported", "mode": "source_defined", "unit": "source_reported_count"},
        "count": {"value": parent["count"], "literal": parent["count"], "status": "reported"},
        "denominator": None, "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": "FINAL", "reported_units": None, "total_units": None, "complete": None},
        "source": {"id": profile["source_id"], "url": source["url"], "input_sha256": source["sha256"],
                   "classification": "public_aggregate", "selector": {"native_label": measure, "page": parent["page"]},
                   "fields": copy.deepcopy(view)},
        "quality": {"conflicts": [], "notes": notes}, "view": view,
    })


def archive_report_summary(snapshot, code):
    profile = PROFILES[code]
    entry = snapshot.get("granular_sources", {}).get(profile["feed"], {})
    if entry.get("status") != "reported" or not entry["data"].get("report"):
        return None
    require(entry["source"]["url"] == profile["url"] or
            code == "OH" and entry["source"]["url"] == history.OH_ELECTION,
            "Turnout report is not archive-bound")
    return {"contract": CONTRACT, "source": entry["data"]["report"],
            "index": entry["source"], "query": entry["data"]["complete_native_query"]}


def kansas_observation(summary, retained):
    source, index = summary["source"], summary["index"]
    require(summary["contract"] == CONTRACT and index["url"] == history.KS_URL
            and re.fullmatch(r"https://(?:www\.)?sos\.ks\.gov/elections/26elec/"
                             r"2026-General-Election-Turnout-Information\.xlsx", source["url"])
            and all(type(receipt["bytes"]) is int and receipt["bytes"] > 0
                    and re.fullmatch(r"[a-f0-9]{64}", receipt["sha256"]) for receipt in (source, index)),
            "Kansas turnout workbook or archive receipt changed")
    ballots, registered = history.kansas_controls(summary["query"])
    measure, register = "TOTAL BALLOTS CAST", "REGISTERED VOTERS"
    basis = "native_registered_voters_same_kansas_workbook"
    rate = 100 * ballots / registered
    label = "General-election turnout workbook"
    notes = ["The printed statewide ballot and registration totals agree with all 105 county rows.",
             "This is a same-workbook registered-voter fraction, not VAP, VEP or a demographic rate.",
             "No native count-update clock, separate certification evidence or new local map join is inferred."]
    return archive_observation("KS", summary, retained, ballots, registered, measure, register,
                               basis, label, notes, None, None, "statewide total")


def new_jersey_observation(summary, retained):
    source, index = summary["source"], summary["index"]
    require(summary["contract"] == CONTRACT and index["url"] == history.NJ_URL
            and re.fullmatch(history.new_jersey_report_url(2026), source["url"])
            and all(type(receipt["bytes"]) is int and receipt["bytes"] > 0
                    and re.fullmatch(r"[a-f0-9]{64}", receipt["sha256"]) for receipt in (source, index)),
            "New Jersey turnout report or archive receipt changed")
    query = summary["query"]
    ballots, registered = history.new_jersey_controls(query, "2026-11-03")
    notes = ["The printed statewide totals agree with all 21 county rows from the same PDF.",
             "This is ballots cast divided by the report's registered voters, not VAP, VEP or a demographic rate.",
             "The NJDOE footer dates the report edition, not count updates or separate certification.",
             "Rejected ballots and district counts remain in the native query, not additions to turnout."]
    return archive_observation(
        "NJ", summary, retained, ballots, registered, "Total Number of Ballots Cast",
        "Total Number of Registered Voters", "native_registered_voters_same_nj_report",
        "General-election turnout report", notes, str(query["total"]["printed_percent"]) + "%",
        query["published_date"], "TOTAL")


def ohio_observation(summary, retained):
    source, receipt = summary["source"], summary["index"]
    query = summary["query"]
    derived = query.get("basis") == "dated_xml_county_sum"
    require(summary["contract"] == CONTRACT and receipt == source
            and (source == query["election"]["source"] if derived else source["url"] == history.OH_BALLOTS)
            and type(source["bytes"]) is int and source["bytes"] > 0
            and re.fullmatch(r"[a-f0-9]{64}", source["sha256"]),
            "Ohio turnout report or collection receipt changed")
    ballots, registered = history.ohio_controls(query)
    notes = ["Ohio's two printed statewide totals agree with all 88 county rows and the dated unofficial XML.",
             "This is ballots counted divided by the same report's registered voters, not VAP, VEP or a demographic rate.",
             "Outstanding overseas and provisional ballots are separate. Complete precinct reporting is not certification."]
    if derived:
        notes[0] = "Statewide total sums VotersParticipated across all 88 counties in the dated unofficial XML."
        notes[2] = "Outstanding ballot counts are not given by this XML. Complete precinct reporting is not certification."
    return archive_observation(
        "OH", summary, retained, ballots, registered, "Ballots Counted", "Registered Voters",
        "native_registered_voters_same_ohio_report", "Unofficial election-night canvass", notes,
        None if derived else query["total"][8] + "%", None, query["total"][1])


def oregon_summary(snapshot):
    entry = snapshot.get("granular_sources", {}).get(OR_FEED, {})
    if entry.get("status") != "reported":
        return None
    require(entry["adapter"] == oregon.ADAPTER and entry["source"]["url"] == oregon.API_URL,
            "Oregon statewide turnout requires its reviewed county feed")
    query, = entry["data"]["complete_native_query"]
    return {"contract": CONTRACT, "query": query, "county_source": entry["source"],
            "source": {"url": oregon.PAGE_URL, **query["independent_official_header"]["source_pin"]}}


def oregon_clock(value):
    return datetime.strptime(value, "%m/%d/%Y | %I:%M %p PT")


def north_carolina_summary(snapshot, retained_original):
    entry = snapshot.get("granular_sources", {}).get(NC_FEED, {})
    if entry.get("status") == "reported":
        query, = entry["data"]["complete_native_query"]
        require(entry["adapter"] == nc.ADAPTER and entry["source"] == {"url": nc.URL, **query["source_pin"]},
                "North Carolina statewide county query receipt changed")
        return {"contract": CONTRACT, "source": entry["source"], "original": query["source_body"]}
    if retained_original is None:
        return None
    require(pin(retained_original) == NC_PIN, "North Carolina retained original hash changed")
    return {"contract": CONTRACT, "source": {"url": nc.URL, **NC_PIN},
            "original": retained_original.decode("utf-8")}


def north_carolina_observation(summary, retained):
    original = summary["original"].encode("utf-8")
    require(summary["contract"] == CONTRACT and summary["source"] == {"url": nc.URL, **pin(original)},
            "North Carolina statewide original differs from its receipt")
    _, records, checks = nc._parse(original)
    row = nc._source_vector(records["0"])
    require(all(delta == 0 for delta in checks.values()) and
            0 <= row["ballots"] <= row["registered"] and row["registered"] > 0
            and row["total_units"] == row["reported_units"] > 0,
            "North Carolina statewide totals do not reconcile across all 100 counties")
    notes = ["Ballots cast, active and inactive registration, and precinct counts reconcile across all 100 counties.",
             "The source does not declare a time zone. Full precinct reporting is not independent certification."]
    return archive_observation(
        "NC", summary, retained, row["ballots"], row["registered"], "Ballots Cast",
        "Active and inactive registered voters", "active_and_inactive_registered_voters",
        row["status"], notes, row["published_pct"], None, "STATEWIDE",
        source_clock=row["source_clock_literal"], reporting=(row["reported_units"], row["total_units"]))


def georgia_observation(summary, retained):
    source, query = summary["source"], summary["query"]
    require(summary["contract"] == CONTRACT and summary["index"] == source and source["url"] == history.GA_URL
            and type(source["bytes"]) is int and source["bytes"] > 0
            and re.fullmatch(r"[a-f0-9]{64}", source["sha256"]), "Georgia turnout receipt changed")
    ballots, registered = history.georgia_controls(query)
    official = sum(row["official"] for row in query["counties"])
    reporting = sum(row["precincts_reporting"] == 1 for row in query["counties"])
    notes = [
        "Statewide count sums county BallotsCast across all 159 counties, not candidate votes.",
        ("The statewide feed's zero is a placeholder for this count, not zero turnout."
         if not query["state_ballots"] else "The published statewide ballot count agrees with the county sum."),
        f"Same-feed registered voters reconcile across all counties. "
        f"{official} county entries are marked official; {reporting} report all precincts.",
        f"Feed edition published {query['published']}; this is not a common county count-update clock.",
    ]
    return archive_observation(
        "GA", summary, retained, ballots, registered, "County ballots cast, summed statewide",
        "Source-reported total voters", "native_registered_voters_same_georgia_bulk_report",
        "Official per feed" if query["official"] else "Unofficial per statewide feed",
        notes, None, query["published"][:10], "159 county turnout rows")


def oregon_observation(summary, retained):
    source, county_source, query = (summary[k] for k in ("source", "county_source", "query"))
    header, rows = query["independent_official_header"], query["county_records"]
    require(summary["contract"] == CONTRACT and source == {"url": oregon.PAGE_URL, **header["source_pin"]}
            and county_source == {"url": oregon.API_URL, **query["source_pin"]}
            and all(type(s["bytes"]) is int and s["bytes"] > 0 and
                    re.fullmatch(r"[a-f0-9]{64}", s["sha256"]) for s in (source, county_source))
            and header["election_date"] == "11/3/2026" and header["election_type"] == "General"
            and header["status"] in ("Unofficial", "Official") and header["statewide_clock_zone_literal"] == "PT"
            and datetime(2026, 11, 3) <= oregon_clock(header["source_update_label"]) < datetime(2027, 2, 1)
            and len(rows) == 36 and pin(encoded(header["counties"])) == OR_COUNTIES
            and {r["CountyID"]: r["CountyName"] for r in rows} == header["counties"],
            "Oregon statewide turnout receipt or inventory changed")
    ballots, registered = header["ballots_counted"], header["active_registered_voters"]
    require(all(r["PrecinctName"] == "Countywide"
                and type(r["calcVoterTurnout"]) is int and type(r["Voters"]) is int
                and 0 <= r["calcVoterTurnout"] <= r["Voters"] for r in rows)
            and type(ballots) is int and type(registered) is int and 0 <= ballots <= registered
            and registered > 0 and sum(r["calcVoterTurnout"] for r in rows) == ballots
            and sum(r["Voters"] for r in rows) == registered,
            "Oregon statewide turnout and active registration do not reconcile")
    notes = ["Statewide Ballots Counted and Active Registered Voters agree with all 36 county rows.",
             "This is a same-report active-registration fraction, not VAP, VEP or a demographic rate.",
             "County rate and geography decisions are unchanged. Report status is as declared by the source."]
    return archive_observation("OR", summary, retained, ballots, registered, "Ballots Counted",
                               "Active Registered Voters", "active_registered_voters", header["status"],
                               notes, None, None, "Statewide Voter Turnout",
                               source_clock=header["source_update_label"], source_timezone="PT")


def montana_observation(summary, retained):
    source = summary["source"]
    require(summary["contract"] == CONTRACT and summary["index"] == source and source["url"] == history.MT_URL
            and type(source["bytes"]) is int and source["bytes"] > 0
            and re.fullmatch(r"[a-f0-9]{64}", source["sha256"]), "Montana turnout receipt changed")
    query = summary["query"]
    ballots, registered, clock = history.montana_controls(query)
    fully, partial, missing = query["precincts"]
    notes = ["Native Total Turnout and Registered Voters from the same statewide results header.",
             f"{fully:,} precincts fully reported, {partial:,} partial, {missing:,} not reported.",
             "The source does not establish certification, a unique-person count or a county allocation."]
    return archive_observation(
        "MT", summary, retained, ballots, registered, "Total Turnout", "Registered Voters",
        "native_registered_voters_same_montana_header", "Unofficial statewide results", notes,
        query["printed_rate"], clock.date().isoformat(), "Statewide Voter Turnout",
        source_clock=query["clock"], source_timezone="MT", reporting=(fully, fully + partial + missing))


def archive_observation(code, summary, retained, ballots, registered, measure, register,
                        basis, label, notes, printed_rate, edition, selector, *,
                        source_clock=None, source_timezone=None, reporting=(None, None)):
    profile, source = PROFILES[code], summary["source"]
    rate = 100 * ballots / registered
    direct_ballots = code != "MT"
    kind, mode = ("ballots_cast", "all_methods") if direct_ballots else ("participation_reported", "source_defined")
    reported, total = reporting
    view = {"state": profile["state"], "state_code": code, "year": 2026, "mode": "official",
            "geography_level": "statewide", "status": "retained_after_failure" if retained else "reported",
            "ballots": ballots, "denominator": registered, "denominator_basis": basis,
            "reported_pct": rate, "validated_pct": rate, "native_printed_pct": printed_rate,
            "source_update_label": source_clock, "source_update_timezone": source_timezone, "source_date": edition,
            "source_status_literal": label, "reported_units": reported, "total_units": total,
            "source_url": source["url"], "source_sha256": source["sha256"], "complete_download_url": None,
            "automatic_source_refresh": True, "maps_approved": False,
            "participation_measure_kind": kind, "participation_measure_literal": measure,
            "participation_measure_label": "Native statewide ballots cast" if direct_ballots else "Native statewide reported turnout",
            "cast_ballot_count_qualified": direct_ballots,
            "unique_voter_count_qualified": False, "quality": notes,
            "source_reporting_label": " ".join(notes), "statewide_ballot_parent": copy.deepcopy(summary)}
    return validate({
        "contract": VERSION, "id": identity(code),
        "election": {"id": code + "-2026-11-03-general", "year": 2026, "date": "2026-11-03",
                     "type": "general", "qualification": "native"},
        "geography": {"id": code + "-native-statewide-total", "name": profile["state"], "state_code": code,
                      "level": "state", "parent_id": None, "join": {"status": "nongeographic",
                          "reference_id": None, "feature_key": None, "evidence": None}},
        "measure": {"id": "native-total-ballots-cast" if direct_ballots else "native-total-turnout", "literal": measure,
                    "kind": kind, "mode": mode, "unit": "ballots" if direct_ballots else "source_reported_count"},
        "count": {"value": ballots, "literal": ballots, "status": "reported"},
        "denominator": {"value": registered, "literal": register, "basis": basis, "qualified": True},
        "source_clock": {"literal": source_clock, "timezone": source_timezone},
        "reporting_status": {"literal": label, "reported_units": reported, "total_units": total,
                             "complete": reported == total if total is not None else None},
        "source": {"id": profile["source_id"], "url": source["url"], "input_sha256": source["sha256"],
                   "classification": "public_aggregate", "selector": {"native_row": selector},
                   "fields": copy.deepcopy(view)},
        "quality": {"conflicts": [], "notes": notes}, "view": view,
    })


def south_carolina_summary(snapshot):
    entries = [item for item in snapshot.get("participation_observations", [])
               if item.get("channel") == "SC-official" and item.get("status") == "reported"]
    if not entries:
        return None
    require(len(entries) == 1, "Ambiguous South Carolina statewide source")
    entry, = entries
    return {"contract": CONTRACT, "source": entry["source"], "query": entry["observation"]}


def south_carolina_observation(summary, retained):
    source, data = summary["source"], summary["query"]
    profile = PROFILES["SC"]
    require(summary["contract"] == CONTRACT and set(source) == {"url", "bytes", "sha256"}
            and type(source["bytes"]) is int and source["bytes"] > 0,
            "Malformed South Carolina statewide receipt")
    measure = "Total Voter Turnout"
    view = state_statistics.refresh({
        "state": profile["state"], "state_code": "SC", "source_url": profile["url"],
        "year": 2026, "county_id": "native:SC:statewide", "geography_level": "statewide",
        "mode": "official", "status": "retained_after_failure" if retained else "reported",
        "participation_measure_kind": "source_defined_participation_count",
        "participation_measure_literal": measure, "participation_measure_label": measure,
        "cast_ballot_count_qualified": False, "unique_voter_count_qualified": False,
        "maps_approved": False, "denominator_basis": state_statistics.BASIS,
        "denominator": None, "complete_download_url": None,
    }, data, source)
    view.pop("accepted_source_provenance")
    view["statewide_ballot_parent"] = copy.deepcopy(summary)
    return validate({
        "contract": VERSION, "id": identity("SC"),
        "election": {"id": "SC-2026-11-03-general", "year": 2026, "date": "2026-11-03",
                     "type": "general", "qualification": "native"},
        "geography": {"id": "SC-native-statewide-total", "name": profile["state"], "state_code": "SC",
                      "level": "state", "parent_id": None, "join": {"status": "nongeographic",
                          "reference_id": None, "feature_key": None, "evidence": None}},
        "measure": {"id": "native-total-voter-turnout", "literal": measure,
                    "kind": "participation_reported", "mode": "source_defined", "unit": "source_reported_count"},
        "count": {"value": data["ballots"],
                  "literal": data["native_state_statistics"]["fields"]["total"]["literal"], "status": "reported"},
        "denominator": None, "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": state_statistics.TITLE, "reported_units": None,
                             "total_units": None, "complete": None},
        "source": {"id": profile["source_id"], "url": source["url"], "input_sha256": source["sha256"],
                   "classification": "public_aggregate", "selector": {"native_label": measure},
                   "fields": copy.deepcopy(view)},
        "quality": {"conflicts": [], "notes": data["quality"]}, "view": view,
    })


def florida_summary(shard):
    rows = sorted(
        (row["view"]["native_record"] for row in shard["records"]
         if row["view"].get("review_id") == FL_REVIEW and row["geography"]["level"] == "county"),
        key=lambda row: row["native_county_code"])
    if pin(encoded(rows)) != FL_COUNTIES:
        return None
    return {"contract": CONTRACT, "source": FL_SOURCE, "printed_statewide_total": list(FL_TOTAL),
            "county_query_pin": FL_COUNTIES, "county_queries": rows,
            "capture_date": "2026-11-06"}


def florida_observation(summary, retained):
    rows = summary["county_queries"]
    require(retained and summary["contract"] == CONTRACT and summary["source"] == FL_SOURCE
            and summary["capture_date"] == "2026-11-06"
            and summary["printed_statewide_total"] == list(FL_TOTAL)
            and summary["county_query_pin"] == pin(encoded(rows)) == FL_COUNTIES
            and len(rows) == len({row["native_county_code"] for row in rows}) == 67,
            "Florida retained report or county inventory differs")
    total, registered = (int(value.replace(",", "")) for value in FL_TOTAL[1:3])
    require(sum(int(row["reported_participants"]) for row in rows) == total
            and sum(int(row["eligible_active_registered_voters"]) for row in rows) == registered,
            "Florida statewide and county totals disagree")
    status = "Unofficial Election Night Results"
    notes = ["Dated November 6 capture; retained as source-reported participation, not a fresh or final count.",
             "The printed statewide count agrees with all 67 counties from that report.",
             "Provisional and overseas reporting was incomplete; the printed registration fraction is not a qualified rate.",
             "No native count-update clock, independent certification, unique-voter count or new local map join."]
    view = {"state": "Florida", "state_code": "FL", "year": 2026, "mode": "official",
            "geography_level": "statewide", "status": "retained_after_failure",
            "ballots": total, "registered": registered, "denominator": None,
            "denominator_basis": "electorate_not_supplied", "reported_pct": None,
            "validated_pct": None, "published_pct": None, "native_printed_pct": FL_TOTAL[3],
            "source_date": None, "source_update_label": None, "source_update_timezone": None,
            "source_capture_date": summary["capture_date"], "source_status_literal": status,
            "reported_units": None, "total_units": None, "source_url": FL_SOURCE["url"],
            "source_sha256": FL_SOURCE["sha256"], "complete_download_url": None,
            "automatic_source_refresh": True, "participation_measure_kind": "participation_reported",
            "participation_measure_literal": "Voter Turnout",
            "participation_measure_label": "Dated statewide reported participation",
            "native_election_id_qualified": True, "cast_ballot_count_qualified": False,
            "unique_voter_count_qualified": False, "maps_approved": False,
            "quality": notes, "source_reporting_label": " ".join(notes),
            "statewide_ballot_parent": copy.deepcopy(summary)}
    return validate({
        "contract": VERSION, "id": identity("FL"),
        "election": {"id": "FL-2026-11-03-general", "year": 2026, "date": "2026-11-03",
                     "type": "general", "qualification": "native"},
        "geography": {"id": "FL-native-statewide-total", "name": "Florida", "state_code": "FL",
                      "level": "state", "parent_id": None, "join": {"status": "nongeographic",
                          "reference_id": None, "feature_key": None, "evidence": None}},
        "measure": {"id": "native-reported-participation", "literal": "Voter Turnout",
                    "kind": "participation_reported", "mode": "source_defined", "unit": "source_reporting_count"},
        "count": {"value": total, "literal": total, "status": "reported"},
        "denominator": None, "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": status, "reported_units": None, "total_units": None, "complete": None},
        "source": {"id": FL_REVIEW, "url": FL_SOURCE["url"], "input_sha256": FL_SOURCE["sha256"],
                   "classification": "public_aggregate", "selector": {"native_row": "TOTAL"},
                   "fields": copy.deepcopy(view)},
        "quality": {"conflicts": [], "notes": notes}, "view": view})


def project(files, snapshot, nc_retained_original=None):
    result = dict(files)
    index = json.loads(files["index.json"])
    current = json.loads(gzip.decompress(files["current.json.gz"]))
    original_current = copy.deepcopy(current)
    require(index.get("contract") == "participation.count_index.v1" and index.get("year") == 2026
            and current.get("contract") == "participation.current_snapshot.v1",
            "Wrong statewide ballot count input contract")
    changes = []
    feeds = snapshot.get("congress", {}).get("official_candidate_evidence", {})
    statewide_sources = {"AK": alaska_summary, "AZ": arizona_summary, "HI": hawaii_summary,
                         "MN": minnesota_summary,
                         "VT": vermont_summary}
    for code, profile in PROFILES.items():
        if code not in index["states"]:
            continue
        declaration = index["states"][code]
        path = declaration["file"]
        require(pin(result[path]) == {key: declaration[key] for key in ("bytes", "sha256")},
                "Statewide ballot canonical shard pin changed")
        shard = json.loads(gzip.decompress(result[path]))
        require(shard.get("state_code") == code and shard.get("year") == 2026
                and shard.get("contract") == "participation.count_snapshot.v1",
                "Wrong statewide ballot state inventory")
        rows = {row["id"]: row for row in shard["records"]}
        require(len(rows) == len(shard["records"]), "Duplicate statewide ballot observation")
        selected = identity(code)
        previous = rows.get(selected)
        if previous is not None:
            validate_existing(code, previous)
        entry = feeds.get(profile["feed"])
        summary = (arkansas_summary(snapshot, shard, previous) if code == "AR" else
                   connecticut_summary(snapshot, shard, previous) if code == "CT" else
                   florida_summary(shard) if code == "FL" else
                   south_carolina_summary(snapshot) if code == "SC" else
                   oregon_summary(snapshot) if code == "OR" else
                   north_carolina_summary(snapshot, nc_retained_original if previous is None else None) if code == "NC" else
                   turnout_history_summary(snapshot, code) if code in {"VA", "WA"} else
                   archive_report_summary(snapshot, code) if code in {"GA", "KS", "MT", "NJ", "OH"} else
                   statewide_sources[code](snapshot) if code in statewide_sources else
                   native_summary(code, entry) if isinstance(entry, dict) and entry.get("status") == "reported" else None)
        if summary is None:
            if previous is None:
                continue
            row = observation(code, previous["view"]["statewide_ballot_parent"], retained=True)
        else:
            row = observation(code, summary, retained=code == "FL"
                              or code == "NC" and snapshot.get("granular_sources", {}).get(NC_FEED, {}).get("status") != "reported"
                              or code == "CT" and summary["archived"]
                              or code == "AR" and summary["archived_capture"] is not None)
            if previous is not None:
                before = previous["view"]["statewide_ballot_parent"]
                after = row["view"]["statewide_ballot_parent"]
                require(before["source"]["sha256"] != after["source"]["sha256"]
                        or code == "AR" and {**before, "archived_capture": None} == after
                        or code == "AK" and before["statewide_feed"] != after["statewide_feed"]
                        or code == "HI" and before["reports"]["histatewide"] == after["reports"]["histatewide"]
                        or code in {"KS", "NJ"} and before["query"] == after["query"]
                        or code == "OH" and {key: value for key, value in before["query"].items() if key != "election"}
                        == {key: value for key, value in after["query"].items() if key != "election"}
                        or code == "OR" and before["query"]["independent_official_header"]
                        == after["query"]["independent_official_header"]
                        or code == "CT" and before["towns"] == after["towns"] and before["total"] == after["total"]
                        or code == "MN" and before["statistical_txt"] != after["statistical_txt"] or before == after,
                        "Unchanged statewide ballot original has different native facts")
                if code == "CT" and after["version"] < before["version"]:
                    row = observation(code, before, retained=True)
                if code == "NJ" and after["query"]["published_date"] < before["query"]["published_date"]:
                    row = observation(code, before, retained=True)
                if code == "OH" and after["query"]["election"]["generated_at"] < before["query"]["election"]["generated_at"]:
                    row = observation(code, before, retained=True)
                if code == "GA":
                    old_query, new_query = before["query"], after["query"]
                    previous_counties = {r["id"]: r for r in old_query["counties"]}
                    if (history.georgia_edition(new_query["published"]) < history.georgia_edition(old_query["published"])
                            or old_query["official"] and not new_query["official"]
                            or any(history.georgia_edition(r["updated"]) <
                                   history.georgia_edition(previous_counties[r["id"]]["updated"])
                                   or previous_counties[r["id"]]["official"] and not r["official"]
                                   for r in new_query["counties"])):
                        row = observation(code, before, retained=True)
                if code == "OR":
                    old_header, new_header = (value["query"]["independent_official_header"] for value in (before, after))
                    if (oregon_clock(new_header["source_update_label"]) < oregon_clock(old_header["source_update_label"])
                            or old_header["status"] == "Official" and new_header["status"] != "Official"):
                        row = observation(code, before, retained=True)
                if code == "NC" and (
                        nc._clock(row["source_clock"]["literal"]) < nc._clock(previous["source_clock"]["literal"])
                        or previous["reporting_status"]["literal"] == "OFFICIAL"
                        and row["reporting_status"]["literal"] != "OFFICIAL"):
                    row = observation(code, before, retained=True)
                if code == "MT" and history.montana_controls(after["query"])[2] < history.montana_controls(before["query"])[2]:
                    row = observation(code, before, retained=True)
                if code == "AR" and before["status"] == "OFFICIAL" and after["status"] != "OFFICIAL":
                    row = observation(code, before, retained=True)
                if code == "MN" and (after["source_edition"] < before["source_edition"]
                        or before["source_status"] == "Official Results"
                        and after["source_status"] != "Official Results"):
                    row = observation(code, before, retained=True)
                if code in {"AZ", "VT"}:
                    from scripts.results_native_state_family import _clock
                    edition_clock = _clock if code == "AZ" else versioned_report_date
                    if edition_clock(after["source_edition"]) < edition_clock(before["source_edition"]):
                        row = observation(code, before, retained=True)
                if code == "AK" and (after["source_edition"] < before["source_edition"]
                        or before["complete_native_query"]["statewide_feed"]["certified"]
                        and not after["complete_native_query"]["statewide_feed"]["certified"]):
                    row = observation(code, before, retained=True)
        reporting = current["snapshot"]["reporting"]
        mirrors = [item for item in reporting if item["state_code"] == code]
        initial_sc = (code == "SC" and previous is None and len(mirrors) == 1
                      and mirrors[0].get("review_id") == "participation-native-declarations-20261113-02"
                      and mirrors[0].get("source_url") == profile["url"]
                      and mirrors[0].get("county_id") == "native:SC:statewide"
                      and mirrors[0].get("native_statistics") == row["view"]["native_statistics"]
                      and mirrors[0].get("ballots") == row["count"]["value"]
                      and mirrors[0].get("denominator") is None)
        initial_or = False
        if code == "OR" and previous is None and len(mirrors) == 1:
            mirror = mirrors[0]
            require(mirror.get("source_url") == OR_DISPLAY_URL and mirror.get("county_id") is None
                    and mirror.get("denominator_basis") == "active_registered_voters",
                    "Oregon statewide display scope changed")
            mirror_clock = oregon_clock(mirror["source_update_label"])
            new_clock = oregon_clock(row["source_clock"]["literal"])
            if new_clock < mirror_clock:
                continue
            initial_or = new_clock > mirror_clock or (
                mirror["ballots"] == row["count"]["value"]
                and mirror["denominator"] == row["denominator"]["value"])
        initial_nc = False
        if code == "NC" and previous is None and len(mirrors) == 1:
            mirror = mirrors[0]
            require(mirror["source_url"] == nc.URL and mirror.get("county_id") is None
                    and mirror["denominator_basis"] == "active_and_inactive_registered_voters",
                    "North Carolina statewide display scope changed")
            mirror_clock = nc._clock(mirror["source_update_label"])
            new_clock = nc._clock(row["source_clock"]["literal"])
            if new_clock < mirror_clock:
                continue
            initial_nc = new_clock > mirror_clock or (
                mirror["ballots"] == row["count"]["value"] and mirror["denominator"] == row["denominator"]["value"])
        require(len(mirrors) <= 1 and (not mirrors or previous is not None
                and mirrors[0] == previous["view"] or initial_sc or initial_or or initial_nc),
                "Statewide ballot display preimage changed")
        if previous is None:
            require(code != "WY" or pin(result[path]) == profile["initial_shard"],
                    "Unreviewed initial statewide ballot inventory")
            shard["records"].append(row)
        else:
            shard["records"] = [row if item["id"] == selected else item for item in shard["records"]]
        if mirrors:
            reporting[reporting.index(mirrors[0])] = copy.deepcopy(row["view"])
        else:
            reporting.append(copy.deepcopy(row["view"]))
        if row != previous:
            result[path] = compressed(shard)
            declaration.update(pin(result[path]), records=len(shard["records"]))
            if code in index.get("coverage", {}):
                records = shard["records"]
                index["coverage"][code].update(
                    records=len(records),
                    reported=sum(item["count"]["status"] == "reported" for item in records),
                    unknown=sum(item["count"]["status"] == "unknown" for item in records),
                    withheld=sum(item["count"]["status"] == "withheld" for item in records),
                    zeros=sum(item["count"]["value"] == 0 for item in records),
                    qualified_fractions=sum(bool(item["denominator"] and item["denominator"]["qualified"])
                                            for item in records))
            changes.append({"state_code": code, "id": selected,
                            "previous": previous["count"]["value"] if previous else None,
                            "current": row["count"]["value"], "source_status": row["view"]["status"]})
    if "DC" in index["states"]:
        declaration = index["states"]["DC"]
        dc_body = result[declaration["file"]]
        require(pin(dc_body) == {key: declaration[key] for key in ("bytes", "sha256")},
                "D.C. canonical shard pin changed")
        source_entry = snapshot.get("granular_sources", {}).get(dc.FEED, {})
        selected = [view for record in json.loads(gzip.decompress(dc_body))["records"]
                    if (view := dc.citywide_view(record, retained=source_entry.get("status") != "reported"))
                    is not None]
        if selected:
            require(len(selected) == 1, "Ambiguous D.C. citywide canonical record")
            view, = selected
            reporting = current["snapshot"]["reporting"]
            mirrors = [row for row in reporting if row["state_code"] == "DC"]
            require(len(mirrors) <= 1 and (not mirrors or mirrors[0].get("equivalent_county_observation_id")
                    == view["equivalent_county_observation_id"]), "D.C. citywide display preimage changed")
            if mirrors:
                reporting[reporting.index(mirrors[0])] = view
            else:
                reporting.append(view)
    if current != original_current:
        result["current.json.gz"] = compressed(current)
        if "current_snapshot" in index:
            require(index["current_snapshot"]["file"] == "current.json.gz",
                    "Statewide ballot display file differs from its declaration")
            index["current_snapshot"].update(pin(result["current.json.gz"]))
    if changes or current != original_current:
        result["index.json"] = encoded(index)
    return result, changes


def exports(files):
    current = json.loads(gzip.decompress(files["current.json.gz"]))
    rows = [row for row in current["snapshot"]["reporting"]
            if "statewide_ballot_parent" in row or "equivalent_county_observation_id" in row]
    fields = ("state_code", "year", "ballots", "status", "denominator", "validated_pct",
              "source_update_label", "source_update_timezone", "source_url", "source_sha256")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({key: row[key] for key in fields} for row in rows)
    return {
        "participation/native-statewide-ballot-totals.csv": output.getvalue().encode(),
        "participation/native-statewide-ballot-totals.json.gz": compressed({
            "contract": CONTRACT, "rows": rows, "limitations": list(NOTES),
        }),
    }
