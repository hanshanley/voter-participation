"""Reconcile Connecticut House ballot lines against the versioned town and fusion controls."""
import json
import re
from collections import Counter

from scripts.participation_intake.contract import pin

IDENTITY = "CT-official-house-candidates"
ROOT = "https://ctemspublic.tgstg.net/ng-app/data/election/108/"
URL = ROOT + "Version.json"
FILES = ("Lookupdata", "stateVotes_Electiondata", "candidateGrouping_Electiondata",
         "election_Electiondata", "townVotes_Electiondata", "townStatus_Electiondata")
DATE = "2026-11-03"
PARTIES = {"D": "D", "R": "R", "IND": "O", "G": "O", "WF": "O", "WI": "O"}


def require(condition, detail):
    if not condition:
        raise ValueError(f"Connecticut official House: {detail}")


def number(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9]+", value), "invalid printed vote count")
    return int(value)


def votes(rows):
    values = {}
    for row in rows:
        require(len(row) == 1, "ambiguous candidate line")
        key, value = next(iter(row.items()))
        require(key not in values and isinstance(value, dict) and "V" in value, "repeated or missing candidate line")
        values[key] = number(value["V"])
    return values


def version(body):
    value = json.loads(body)["Version"]
    require(type(value) is int and value >= 52337, "unexpected version")
    return value


def normalize(number_version, inputs):
    from scripts.results_official_congress import CONTRACT

    lookup, statewide, coendorsed, parent, towns, stats = (inputs[name] for name in FILES)
    election = lookup["election"]
    require((election["ID"], election["DT"], election["ET"], election["EC"], parent["ID"])
            == ("108", "11/03/2026", "G", "SE", "108"), "wrong election or stage")
    require(set(towns) == set(stats) == set(lookup["townIds"]) and len(towns) == 169,
            "incomplete town reporting frame")
    precincts = re.fullmatch(r"([0-9]+) of ([0-9]+) \([0-9.]+%\)", parent["PR"])
    require(precincts and 0 < int(precincts[1]) <= int(precincts[2]), "inconsistent statewide reporting counts")
    statuses = {value["TS"].strip(" (*)") for value in stats.values()}
    require(statuses <= {"Unofficial Results", "Official Results"} and statuses, "unknown town publication status")
    official = statuses == {"Official Results"}
    parent_complete = (precincts[1] == precincts[2] and parent["T"] == "169 of 169" and parent["PT"] == "0 of 169")
    races = []
    for entry in lookup["officeList"]:
        office, = entry.values()
        if office["OT"] != "C":
            continue
        seat, key = office["D"], office["ID"]
        require(re.fullmatch(r"[1-5]", seat) and office["NM"] == f"Representative in Congress {seat}"
                and office["DT"] == f"Connecticut 0{seat}", "unexpected federal office or district")
        counts = votes(statewide[key])
        literal = {}
        for line, count in counts.items():
            candidate = lookup["candidateIds"][line]
            party = lookup["partyIds"][candidate["P"]]
            name, code = candidate["NM"], party["CD"]
            require(name and code in PARTIES, "unknown candidate name or party")
            literal[line] = dict(candidate_id=line, name=name, literal_party=party["NM"], party_code=code,
                                 votes=count, votes_literal=str(count))
        town_lines = {}
        for town, payload in towns.items():
            if key not in payload:
                continue
            town_counts = votes(payload[key])
            require(set(town_counts) == set(counts), "town omits or adds a statewide ballot line")
            town_lines[town] = town_counts
        summed = Counter()
        for town_counts in town_lines.values():
            summed.update(town_counts)
        require(town_lines and dict(summed) == counts, "a statewide line differs from its town roll-up")
        by_name = {}
        for line in literal.values():
            by_name.setdefault(line["name"], []).append(line)
        groups, used_controls, candidates = votes(coendorsed.get(key, [])), set(), []
        for name, lines in by_name.items():
            major = [row for row in lines if row["party_code"] in "DR"]
            if len(lines) > 1:
                require(len(major) == 1 and len({row["party_code"] for row in lines}) == len(lines)
                        and all(row["party_code"] in {"D", "R", "IND", "WF"} for row in lines),
                        "ambiguous co-endorsement")
                primary = major[0]
                group_id = primary["candidate_id"]
                require(groups.get(group_id) == sum(row["votes"] for row in lines), "fusion total differs")
                used_controls.add(group_id)
            else:
                primary = lines[0]
            total = sum(row["votes"] for row in lines)
            candidates.append({**primary, "votes": total, "votes_literal": str(total),
                               "party_group": PARTIES[primary["party_code"]],
                               "role": "named_candidate",
                               "write_in": primary["party_code"] == "WI",
                               "ballot_line_ids": [row["candidate_id"] for row in lines]})
        require(set(groups) == used_controls and sum(row["votes"] for row in candidates) == sum(counts.values())
                and all(sum(row["party_group"] == major for row in candidates) == 1 for major in "DR"),
                "candidate or co-endorsement coverage differs")
        races.append({"state_code": "CT", "district": f"CT-0{seat}", "seat": seat,
                      "native_contest_id": key, "native_office_label": office["NM"],
                      "election_date": DATE, "election_kind": "regular", "stage": "general",
                      "native_status_literal": "Official Results" if official else "Unofficial Results",
                      "source_update_label": f"State publication version {number_version}",
                      "complete_reporting": parent_complete, "contest_total": sum(counts.values()),
                      "candidates": candidates, "native_ballot_lines": list(literal.values()),
                      "town_line_controls": town_lines, "fusion_controls": groups})
    require(sorted(race["seat"] for race in races) == list("12345"), "missing or duplicated congressional seat")
    return {"contract": CONTRACT, "election_date": DATE, "source_version": number_version, "races": races,
            "participation_observation_qualified": False, "candidate_votes_are_not_ballots_or_turnout": True,
            "provider_other_equivalence_qualified": False, "conditional_model_eligible": False}


def collect(collector):
    previous = (collector.prior.get(IDENTITY) or {}).get("data") or {}

    def parse(body):
        edition = version(body)
        require(edition >= previous.get("source_version", 0), "publication version regressed")
        inputs, pins = {}, {}
        for name in FILES:
            url = f"{ROOT}{edition}/{name}.json"
            original, _ = collector.acquire(url, refresh=False)
            require(0 < len(original) <= 4_000_000, "source exceeds reviewed size limit")
            inputs[name], pins[name] = json.loads(original), {"url": url, **pin(original)}
        after, _ = collector.acquire(URL, refresh=True)
        require(version(after) == edition, "version changed during acquisition")
        data = normalize(edition, inputs)
        require(not previous.get("races") or previous["races"][0]["native_status_literal"] != "Official Results"
                or data["races"][0]["native_status_literal"] == "Official Results", "certification status regressed")
        data["numerical_input_pins"] = pins
        require(edition != previous.get("source_version") or data == previous, "same-version facts conflict")
        return data

    return collector.capture(IDENTITY, URL, parse)
