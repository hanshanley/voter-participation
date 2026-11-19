"""Reconcile versioned Clarity federal returns and separate ballot statistics."""

import copy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import gzip
import io
import json
from pathlib import Path
import re
import zipfile

from scripts.participation_intake.contract import IntakeError, encoded, pin
from scripts.results_official_congress import CONTRACT, require


IDENTITY = "IA-official-statewide-results"
ROOT = "https://electionresults.iowa.gov/IA/127077"
URL = ROOT + "/current_ver.txt"
PAGE = ROOT + "/web.345435/"
FACT_CONTRACT = "participation.clarity_versioned_federal_facts.v1"
RETAINED_CAPTURE = Path("data/results-intake/iowa-retained-capture.json.gz")
RETAINED_PIN = {"bytes": 1498552,
                "sha256": "a5c9bbbb8b6bf7082c36a0f85c6d6be81327a3ad8a60088d551539e93a4f6479"}
ELECTION_FIELDS = (
    "internalname", "electionid", "electiondate", "isstateelection",
    "parentelectionid", "istestmode", "showtestdatawatermark",
    "chkisfinalupload", "chkiscanvasupload", "ballotscast", "registeredvoters",
    "chkoverrideballotscastonreport", "chkoverrideregisterdvotersonreport",
    "rankedchoicevoting",
)
PRODUCTS = {
    "config": "config.json", "settings": "en/electionsettings.json",
    "status": "status.json", "sum": "sum.json", "summary": "en/summary.json",
    "details": "details.json",
}
OFFICES = {
    "United States Senator": ("senate", "2", "IA-Senate"),
    **{f"United States Representative District {i}": ("house", str(i), f"IA-{i:02d}")
       for i in range(1, 5)},
}
PARTIES = {"DEM": "D", "REP": "R", "LIB": "O"}


def decode(body):
    return gzip.decompress(body) if body.startswith(b"\x1f\x8b") else body


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate Clarity JSON property")
        result[key] = value
    return result


def document(body):
    return json.loads(decode(body), object_pairs_hook=unique)


def integer(value):
    require(type(value) is int and 0 <= value <= 2**53 - 1,
            "Missing, negative or unsafe Clarity count")
    return value


def publication_clock(value):
    require(isinstance(value, str) and value.endswith(" CST"),
            "Unreviewed Clarity publication timezone")
    local = datetime.strptime(value, "%m/%d/%Y %I:%M:%S %p CST")
    from datetime import timedelta
    return local.replace(tzinfo=timezone(-timedelta(hours=6))).astimezone(timezone.utc)


def report_url(version):
    # These empty path components are literal output of the declared download widget.
    return f"https://electionresults.iowa.gov//IA//127077/{version}/reports/detailtxt.zip"


def selected_facts(bodies, version):
    settings = document(bodies["settings"])
    election = settings["settings"]["electiondetails"]
    return {
        "contract": FACT_CONTRACT, "version": version,
        "config": document(bodies["config"]),
        "election": {key: copy.deepcopy(election[key]) for key in ELECTION_FIELDS},
        "entityname": settings["entityname"],
        "parententityname": settings["parententityname"],
        "publication_label": settings["websiteupdatedat"],
        "state_precincts": {key: settings[key] for key in (
            "stateprecinctsreporting", "stateprecinctsparticipating",
            "stateprecinctspartiallyreporting")},
        **{key: document(bodies[key]) for key in ("status", "sum", "summary", "details")},
        "text_report": text_original(bodies["text"]),
    }


def text_original(body):
    with zipfile.ZipFile(io.BytesIO(body)) as packet:
        require(packet.namelist() == ["detail.txt"]
                and packet.getinfo("detail.txt").file_size < 20_000_000,
                "Unreviewed Clarity complete-text archive")
        return packet.read("detail.txt").decode("utf-8-sig")


def text_tables(text):
    lines = text.splitlines()
    header = next((i for i, line in enumerate(lines) if line.split() ==
                   ["County", "Registered", "Voters", "Ballots", "Cast", "Voter", "Turnout"]), None)
    require(header is not None, "Missing independent ballot-statistics header")
    statistics = {}
    for line in lines[header + 1:]:
        if not line.strip():
            continue
        cells = re.split(r"\s{2,}", line.strip())
        require(len(cells) == 4 and cells[1].isdigit() and cells[2].isdigit()
                and re.fullmatch(r"[0-9]+\.[0-9]{2}%", cells[3]),
                "Changed independent ballot-statistics row")
        require(cells[0] not in statistics, "Duplicate independent ballot-statistics unit")
        statistics[cells[0]] = cells[1:]
        if cells[0] == "Total:":
            break
    contests = {}
    for i, line in enumerate(lines):
        match = re.fullmatch(r"(.+?) \( 1\)", line.strip())
        if match is None or match[1] not in OFFICES:
            continue
        name = match[1]
        require(name not in contests, "Duplicate independent federal contest")
        names = re.split(r"\s{2,}", lines[i + 1].strip())
        roles = re.split(r"\s{2,}", lines[i + 2].strip())
        require(roles == ["County", "Registered Voters"]
                + ["Election Day", "Absentee", "Total"] * len(names) + ["Total"],
                "Changed independent federal method columns")
        rows = {}
        for line in lines[i + 3:]:
            if not line.strip():
                continue
            cells = re.split(r"\s{2,}", line.strip())
            require(len(cells) == 3 + 3 * len(names)
                    and all(cell.isdigit() for cell in cells[1:]),
                    "Changed independent federal count row")
            county, counts = cells[0], list(map(int, cells[1:]))
            require(county not in rows, "Duplicate independent federal county")
            vectors = [counts[1 + 3*j:4 + 3*j] for j in range(len(names))]
            require(all(ed + absentee == total for ed, absentee, total in vectors)
                    and sum(row[2] for row in vectors) == counts[-1],
                    "Independent federal method or candidate totals differ")
            rows[county] = {"registered": counts[0], "vectors": vectors, "total": counts[-1]}
            if county == "Totals:":
                break
        require("Totals:" in rows, "Missing independent federal parent")
        contests[name] = {"names": names, "rows": rows}
    require(set(contests) == set(OFFICES), "Incomplete independent federal office inventory")
    return statistics, contests


def normalized(facts):
    require(facts.get("contract") == FACT_CONTRACT
            and isinstance(facts.get("version"), str)
            and re.fullmatch(r"[1-9][0-9]{0,8}", facts["version"]),
            "Unreviewed Clarity source facts or version")
    election = facts["election"]
    require(all(election.get(key) == value for key, value in {
        "internalname": "2026 General Election", "electionid": "127077",
        "electiondate": "11/3/2026", "isstateelection": "1", "parentelectionid": "0",
        "istestmode": False, "showtestdatawatermark": "0", "rankedchoicevoting": "0",
        "chkoverrideballotscastonreport": False,
        "chkoverrideregisterdvotersonreport": False,
    }.items()) and facts["entityname"] == "IA" and facts["parententityname"] is None
            and facts["config"] == {
                "languages": "en|English", "lang": "en", "isPublished": True,
                "versionTemplate": 345435},
            "Changed Clarity election, test, override or publication scope")
    require(all(type(election[key]) is bool for key in ("chkisfinalupload", "chkiscanvasupload")),
            "Changed Clarity finality declaration")
    publication_clock(facts["publication_label"])
    status = facts["status"]
    counties = status["P"]
    require(len(counties) == len(set(counties)) == 99
            and all(isinstance(name, str) and name.strip() == name and name for name in counties),
            "Incomplete or duplicate Clarity county inventory")
    for key in ("R", "B", "PX", "PY", "S"):
        require(isinstance(status[key], list) and len(status[key]) == len(counties),
                "Clarity county status-vector lengths differ")
        for value in status[key]:
            integer(value)
    require(all(reported <= total for reported, total in zip(status["PX"], status["PY"]))
            and all(value in (0, 1, 2, 3, 4) for value in status["S"]),
            "Unreviewed Clarity county status or reporting counter")
    statistics, reports = text_tables(facts["text_report"])
    require(set(statistics) == set(counties) | {"Total:"},
            "Independent ballot-statistics county inventory differs")
    observations = []
    for i, name in enumerate(counties):
        registered, ballots, fraction = statistics[name]
        require(int(registered) == status["R"][i] and int(ballots) == status["B"][i],
                "JSON/text administrative statistics disagree")
        if int(registered):
            expected = (Decimal(int(ballots)) * 100 / Decimal(int(registered))).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP)
            require(Decimal(fraction[:-1]) == expected,
                    "Independent printed registration fraction does not reconcile")
        observations.append({
            "native_id": name, "county": name, "ballots": status["B"][i],
            "registered_stock": status["R"][i], "printed_fraction": fraction,
            "reported_units": status["PX"][i], "total_units": status["PY"][i],
            "native_status": status["S"][i],
        })
    state_ballots, state_registered = sum(status["B"]), sum(status["R"])
    require(list(map(int, statistics["Total:"][:2])) == [state_registered, state_ballots]
            and sum(status["PX"]) == integer(facts["state_precincts"]["stateprecinctsreporting"])
            and sum(status["PY"]) == integer(facts["state_precincts"]["stateprecinctsparticipating"]),
            "Independent administrative state controls differ")
    collections = []
    for value in (facts["summary"], facts["sum"]["Contests"], facts["details"]["Contests"]):
        require(isinstance(value, list) and value
                and len({row["K"] for row in value}) == len(value),
                "Missing or duplicate native Clarity contest identities")
        collections.append({row["K"]: row for row in value})
    summary, current, details = collections
    require(summary.keys() == current.keys() == details.keys(),
            "Clarity complete contest inventories differ")
    races = []
    county_memberships = []
    for key, descriptor in summary.items():
        if descriptor.get("CAT") != "Federal":
            continue
        name = descriptor["C"]
        require(name in OFFICES, "Unreviewed federal office or election stage")
        row, children = current[key], details[key]
        chamber, seat, district = OFFICES[name]
        for field in ("C", "CH", "P", "V", "T", "VF", "IsRCV"):
            require(descriptor[field] == row[field], "Clarity descriptor/current candidate frame differs")
        require(row["VF"] == 1 and row["IsRCV"] is False
                and not row["IsCumulative"] and row["IsContestNoChoice"] == 0,
                "Unreviewed Clarity vote-for, ranked or cumulative election")
        require(len(row["CH"]) == len(set(row["CH"])) == len(row["V"]) == len(row["P"])
                == len(row["CHAggId"]) == len(set(row["CHAggId"]))
                and row["CH"].count("Write-in") == 1,
                "Incomplete or duplicate Clarity candidate/write-in inventory")
        candidates = []
        for candidate_id, candidate, party, votes in zip(
                row["CHAggId"], row["CH"], row["P"], row["V"]):
            require(type(candidate_id) is int and candidate_id > 0
                    and isinstance(candidate, str) and candidate.strip() == candidate
                    and party in (*PARTIES, ""), "Unreviewed Clarity candidate identity or party")
            generic = candidate == "Write-in"
            require(not generic or party == "", "Generic write-in has a changed party role")
            candidates.append({
                "candidate_id": str(candidate_id), "name": candidate,
                "literal_party": party, "party_name": party,
                "party_group": PARTIES.get(party, "U"),
                "role": "generic_write_in" if generic else "named_candidate",
                "votes": integer(votes),
            })
        require(all(sum(c["party_group"] == party for c in candidates) == 1 for party in "DR")
                and row["T"] == [sum(c["votes"] for c in candidates)],
                "Clarity major-party coverage or printed total differs")
        names = children["P"]
        require(len(names) == len(set(names)) and set(names) <= set(counties)
                and all(len(children[k]) == len(names)
                        for k in ("PX", "PY", "Eid", "Cid", "V", "T"))
                and integer(row["TP"]) == len(names)
                and integer(row["PR"]) == sum(x == y for x, y in zip(children["PX"], children["PY"])),
                "Changed Clarity contest county/reporting inventory")
        table = reports[name]
        require(table["names"] == row["CH"] and set(table["rows"]) == set(names) | {"Totals:"},
                "Independent federal candidate or county names differ")
        for i, county in enumerate(names):
            vector = children["V"][i]
            require(len(vector) == len(candidates)
                    and all(integer(v) == v for v in vector)
                    and isinstance(children["Eid"][i], str) and children["Eid"][i].isdigit()
                    and isinstance(children["Cid"][i], str) and children["Cid"][i].isdigit()
                    and integer(children["PX"][i]) <= integer(children["PY"][i])
                    and sum(vector) == integer(children["T"][i])
                    and [v[2] for v in table["rows"][county]["vectors"]] == vector
                    and table["rows"][county]["registered"] == status["R"][counties.index(county)]
                    and children["T"][i] <= status["B"][counties.index(county)],
                    "Federal county JSON/text/ballot accounting differs")
        require(all(sum(v[i] for v in children["V"]) == candidate["votes"]
                    for i, candidate in enumerate(candidates))
                and [v[2] for v in table["rows"]["Totals:"]["vectors"]] == row["V"]
                and table["rows"]["Totals:"]["total"] == row["T"][0],
                "Federal county vectors do not reconcile to the state candidate control")
        if chamber == "senate":
            require(set(names) == set(counties) and row["BC"] == state_ballots
                    and row["TV"] == state_registered, "Senate statewide statistical scope differs")
        else:
            county_memberships.extend(names)
        races.append({
            "state_code": "IA", "chamber": chamber, "district": district, "seat": seat,
            "native_contest_id": key, "native_office_label": name,
            "election_date": "2026-11-03", "stage": "general", "election_kind": "regular",
            "source_update_label": None, "source_update_timezone": None,
            "source_publication_label": facts["publication_label"],
            "reported_units": row["PR"], "total_units": row["TP"], "partial_units": None,
            "reporting_unit_kind": "county", "complete_reporting": row["PR"] == row["TP"],
            "contest_total": row["T"][0], "candidates": candidates,
        })
    require(len(races) == len(OFFICES) and {r["native_office_label"] for r in races} == set(OFFICES)
            and sorted(county_memberships) == sorted(counties),
            "Incomplete federal inventory or overlapping House county memberships")
    return {
        "contract": CONTRACT, "election_date": "2026-11-03",
        "source_updated_at": None, "source_publication_label": facts["publication_label"],
        "source_publication_timezone": "CST", "source_version": facts["version"],
        "native_facts": copy.deepcopy(facts), "races": sorted(races, key=lambda r: r["district"]),
        "administrative_statistics": {
            "counties": observations, "state_ballots": state_ballots,
            "state_registered_stock": state_registered,
            "native_state_scalar_ballots": election["ballotscast"],
            "native_state_scalar_registered": election["registeredvoters"],
            "state_totals_method": "complete_county_status_vector_sum_corresponding_to_native_UI_and_text_parent",
            "registration_is_not_an_analytical_denominator": True,
        },
        "provider_other_equivalence_qualified": False, "conditional_model_eligible": False,
        "participation_observation_qualified": False,
        "candidate_votes_are_not_ballots_or_turnout": True,
        "holds": ["Separate reviewed candidate/model bridge required; blank native parties retained.",
                  "Website publication label is not a native count-update clock.",
                  "Registration stock is not automatically a qualified turnout denominator."],
    }


def compatible(data, previous, observed):
    require(publication_clock(data["source_publication_label"]) <= observed,
            "Clarity publication clock is in the future")
    if previous is None:
        return
    require(normalized(previous["native_facts"]) ==
            {key: value for key, value in previous.items() if key != "numerical_input_manifest"}
            and int(data["source_version"]) >= int(previous["source_version"])
            and publication_clock(data["source_publication_label"]) >=
                publication_clock(previous["source_publication_label"]),
            "Clarity prior source changed or version/publication regressed")
    require(data["source_version"] != previous["source_version"]
            or data["native_facts"] == previous["native_facts"],
            "Clarity immutable version content changed")
    old = {r["district"]: r for r in previous["races"]}
    for race in data["races"]:
        before = old[race["district"]]
        require(race["native_contest_id"] == before["native_contest_id"]
                and [{k: v for k, v in c.items() if k != "votes"} for c in race["candidates"]]
                == [{k: v for k, v in c.items() if k != "votes"} for c in before["candidates"]],
                "Clarity candidate identity or write-in inventory changed")
        old_detail = next(r for r in previous["native_facts"]["details"]["Contests"]
                          if r["K"] == before["native_contest_id"])
        new_detail = next(r for r in data["native_facts"]["details"]["Contests"]
                          if r["K"] == race["native_contest_id"])
        require(all(old_detail[key] == new_detail[key] for key in ("P", "Eid", "Cid")),
                "Clarity native child contest or district county frame changed")
    require([r["county"] for r in data["administrative_statistics"]["counties"]]
            == [r["county"] for r in previous["administrative_statistics"]["counties"]],
            "Clarity county frame changed")
    before_status = previous["native_facts"]["status"]["S"]
    require(all(old != 0 or new == 0 for old, new in zip(before_status, data["native_facts"]["status"]["S"])),
            "Clarity certified county status regressed")


def retained_capture_matches(entry):
    return all(key in entry for key in ("source", "first_observed_at", "data")) and pin(encoded(
        {key: entry[key] for key in ("source", "first_observed_at", "data")})) == RETAINED_PIN


def collect(collector):
    def parse_version(body):
        version = decode(body).decode("ascii").strip()
        require(re.fullmatch(r"[1-9][0-9]{0,8}", version), "Invalid Clarity current-version pointer")
        bodies, receipts = {}, {}
        for key, path in PRODUCTS.items():
            bodies[key], receipts[key] = collector.acquire(f"{ROOT}/{version}/json/{path}")
        bodies["text"], receipts["text"] = collector.acquire(report_url(version))
        data = normalized(selected_facts(bodies, version))
        compatible(data, (collector.prior.get(IDENTITY) or {}).get("data"), collector.observation_time())
        data["numerical_input_manifest"] = {
            key: {"url": report_url(version) if key == "text" else
                  f"{ROOT}/{version}/json/{PRODUCTS[key]}", **pin(value)}
            for key, value in bodies.items()
        }
        return data
    entry = collector.capture(IDENTITY, URL, parse_version)
    if entry["status"] == "reported":
        entry.pop("reviewed_retained_capture", None)
    if (entry.get("data") is None and entry["error_stage"] == "acquisition"
            and (entry["error"] == "source_unavailable" or entry["error_detail"] ==
                 "Source did not return a complete successful original")):
        path = Path(__file__).resolve().parents[1] / RETAINED_CAPTURE
        if path.is_file():
            saved = document(path.read_bytes())
            require(set(saved) == {"source", "first_observed_at", "data"}
                    and retained_capture_matches(saved), "Reviewed Iowa retained capture pin differs")
            observed = datetime.fromisoformat(saved["first_observed_at"])
            require(observed <= collector.observation_time(), "Iowa retained capture is in the future")
            compatible(saved["data"], None, observed)
            for original in saved["data"]["numerical_input_manifest"].values():
                try:
                    collector.guard(original["url"])
                except IntakeError as error:
                    if error.code == "source_stopped":
                        return entry
                    raise
            entry.update(saved, status="retained_after_failure", reviewed_retained_capture=True)
    return entry
