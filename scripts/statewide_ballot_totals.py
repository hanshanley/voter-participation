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
PROFILES = {
    "AK": {"state": "Alaska", "source_id": "ak-doe-statewide-voters-cast-20261103",
           "feed": alaska.FEED, "url": alaska.REPORT},
    "AZ": {"state": "Arizona", "source_id": "az-sos-county-ballots-20261103",
           "feed": "AZ-official", "url": AZ_URL},
    "MN": {"state": "Minnesota", "source_id": "mn-sos-reconciled-statewide-turnout-20261103",
           "feed": mn.IDENTITY, "url": mn.URL},
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
                           "MN": "native-total-number-voted",
                           "VA": "native-total-voting",
                           "WA": "native-ballots-counted"}.get(code, "native-total-ballots-cast"),
                          "source_defined" if code in {"AK", "VA", "VT", "MN"} else "all_methods")


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
    if code == "VT":
        return vermont_observation(summary, retained)
    if code == "MN":
        return minnesota_observation(summary, retained)
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


def project(files, snapshot):
    result = dict(files)
    index = json.loads(files["index.json"])
    current = json.loads(gzip.decompress(files["current.json.gz"]))
    original_current = copy.deepcopy(current)
    require(index.get("contract") == "participation.count_index.v1" and index.get("year") == 2026
            and current.get("contract") == "participation.current_snapshot.v1",
            "Wrong statewide ballot count input contract")
    changes = []
    feeds = snapshot.get("congress", {}).get("official_candidate_evidence", {})
    statewide_sources = {"AK": alaska_summary, "AZ": arizona_summary, "MN": minnesota_summary,
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
        summary = (turnout_history_summary(snapshot, code) if code in {"VA", "WA"} else
                   statewide_sources[code](snapshot) if code in statewide_sources else
                   native_summary(code, entry) if isinstance(entry, dict) and entry.get("status") == "reported" else None)
        if summary is None:
            if previous is None:
                continue
            row = observation(code, previous["view"]["statewide_ballot_parent"], retained=True)
        else:
            row = observation(code, summary)
            if previous is not None:
                before = previous["view"]["statewide_ballot_parent"]
                after = row["view"]["statewide_ballot_parent"]
                require(before["source"]["sha256"] != after["source"]["sha256"]
                        or code == "AK" and before["statewide_feed"] != after["statewide_feed"]
                        or code == "MN" and before["statistical_txt"] != after["statistical_txt"] or before == after,
                        "Unchanged statewide ballot original has different native facts")
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
        require(len(mirrors) <= 1 and (not mirrors or previous is not None
                and mirrors[0] == previous["view"]), "Statewide ballot display preimage changed")
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
            if "statewide_ballot_parent" in row]
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
