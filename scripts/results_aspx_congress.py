"""Strict selected federal candidate tables from reviewed statewide ASPX products."""

import copy
from datetime import datetime
from html import unescape
import re
from zoneinfo import ZoneInfo

from scripts.results_official_congress import CONTRACT, integer, label, require, single


IDENTITY = "OR-official-house-candidates"
URL = "https://results.oregonvotes.gov/resultsSW.aspx?type=FED&map=CTY"
FACT_CONTRACT = "participation.aspx_federal_candidate_facts.v1"
WRITE_IN_NOTICE = "Write-in results are not reported on this site."
PROFILE = {
    "state_code": "OR", "publisher": "Oregon Secretary of State",
    "districts": tuple(range(1, 7)),
    "office_pattern": r"US Representative, ([1-6])(?:st|nd|rd|th) District",
    "parties": {
        "Republican": "R", "Democrat": "D",
        "Democrat, Working Families": "D", "Democrat, Independent": "D",
        "Republican, Libertarian": "R",
        "Pacific Green": "O", "Pacific Green, Progressive": "O",
    },
}


def source_clock(value):
    require(isinstance(value, str), "Missing official ASPX source clock")
    try:
        parsed = datetime.strptime(value, "%m/%d/%Y | %I:%M %p PT")
    except ValueError as error:
        raise ValueError("Changed official ASPX source clock") from error
    require(datetime(2026, 11, 3) <= parsed < datetime(2027, 2, 1),
            "Official ASPX clock is outside the election")
    return parsed.replace(tzinfo=ZoneInfo("America/Los_Angeles"))


def normalized(facts):
    require(isinstance(facts, dict) and facts.get("contract") == FACT_CONTRACT
            and facts.get("publisher") == PROFILE["publisher"]
            and facts.get("election_label") == "General Election November 3, 2026"
            and facts.get("status_literal") in ("Unofficial", "Official")
            and facts.get("write_in_scope_notice") == WRITE_IN_NOTICE,
            "Official ASPX publisher, election or stage changed")
    source_clock(facts.get("source_update_label"))
    require(isinstance(facts.get("races"), list), "Missing official ASPX races")
    races = []
    for native in facts["races"]:
        require(isinstance(native, dict), "Invalid official ASPX race")
        match = re.fullmatch(PROFILE["office_pattern"], native["office_label"])
        require(match is not None, "Unreviewed official ASPX House district or stage")
        seat = int(match[1])
        require(re.fullmatch(r"[0-9]+", native["contest_id"]) is not None,
                "Missing official ASPX contest identity")
        reported, total = integer(native["reported_literal"]), integer(native["total_units_literal"])
        require(total > 0 and reported <= total, "Invalid native ASPX reporting counters")
        candidates = []
        for value in native["candidates"]:
            name, party = value["name_literal"], value["party_literal"]
            require(isinstance(name, str) and bool(label(name))
                    and isinstance(party, str)
                    and isinstance(value["candidate_id"], str)
                    and re.fullmatch(r"bar" + native["contest_id"] + r"[0-9]+",
                                     value["candidate_id"]) is not None,
                    "Missing native ASPX candidate identity")
            name, party = label(name), label(party)
            write_in = name == "Write-in"
            require((write_in and party == "") or (not write_in and party in PROFILE["parties"]),
                    "Unreviewed literal ASPX candidate party or write-in role")
            candidates.append({
                "candidate_id": value["candidate_id"], "native_id": None,
                "name": name, "name_literal": value["name_literal"], "literal_party": party,
                "party_literal": value["party_literal"],
                "party_group": "O" if write_in else PROFILE["parties"][party],
                "votes": integer(value["votes_literal"]), "votes_literal": value["votes_literal"],
                "role": "generic_write_in" if write_in else "named_candidate",
            })
        control = integer(native["contest_total_literal"])
        require(len({row["candidate_id"] for row in candidates}) == len(candidates)
                and len({(row["name"], row["literal_party"]) for row in candidates}) == len(candidates)
                and sum(row["votes"] for row in candidates) == control
                and sum(row["role"] == "generic_write_in" for row in candidates) == 1
                and all(sum(row["party_group"] == party for row in candidates) == 1 for party in "DR"),
                "Complete official ASPX candidate inventory does not reconcile")
        races.append({
            "state_code": PROFILE["state_code"], "district": f"OR-{seat:02d}", "seat": str(seat),
            "native_contest_id": native["contest_id"], "native_office_label": native["office_label"],
            "election_date": "2026-11-03", "stage": "general", "election_kind": "regular",
            "native_status_literal": facts["status_literal"],
            "source_update_label": facts["source_update_label"], "source_update_timezone": "PT",
            "reported_units": reported, "total_units": total, "partial_units": None,
            "complete_reporting": reported == total, "contest_total": control,
            "contest_total_literal": native["contest_total_literal"], "candidates": candidates,
        })
    require(len(races) == len(PROFILE["districts"])
            and {int(row["seat"]) for row in races} == set(PROFILE["districts"])
            and len({row["native_contest_id"] for row in races}) == len(races),
            "Incomplete or duplicate statewide ASPX House inventory")
    return {
        "contract": CONTRACT, "election_date": "2026-11-03",
        "source_updated_at": source_clock(facts["source_update_label"]).isoformat(),
        "races": sorted(races, key=lambda row: row["seat"]), "native_facts": copy.deepcopy(facts),
        "complete_printed_candidate_tables": True,
        "exhaustive_write_in_universe_qualified": False,
        "participation_observation_qualified": False, "candidate_votes_are_not_ballots_or_turnout": True,
        "provider_other_equivalence_qualified": False, "conditional_model_eligible": False,
        "holds": [
            "The native write-in notice does not establish an exhaustive counted write-in universe.",
            "Evidence alone does not grant model eligibility or combine provider counts.",
        ],
    }


def parse(body):
    text = body.decode("utf-8-sig")
    headings = [label(re.sub(r"<br\s*/?>", " ", value, flags=re.I))
                for _, value in re.findall(r"<h([123])[^>]*>(.*?)</h\1>", text, re.S)]
    status = [value for value in headings if value in ("Unofficial", "Official")]
    require(label(single(r"<title>(.*?)</title>", text)) == PROFILE["publisher"]
            and headings.count("General Election November 3, 2026") == 1 and len(status) == 1
            and WRITE_IN_NOTICE in label(text),
            "Official ASPX publisher, election or stage changed")
    facts = {
        "contract": FACT_CONTRACT, "publisher": PROFILE["publisher"],
        "election_label": "General Election November 3, 2026", "status_literal": status[0],
        "write_in_scope_notice": WRITE_IN_NOTICE,
        "source_update_label": single(
            r'<div class="next-count">Results last updated: ([^<]+)</div>', text),
        "races": [],
    }
    sections = re.findall(
        r'<div class="display-results-box-a">\s*<h1>(.*?)</h1>(.*?)'
        r'(?=<div class="display-results-box-a">|</form>)', text, re.S)
    for heading, block in sections:
        heading = label(heading)
        if not heading.startswith("US Representative"):
            continue
        race_ids = set(re.findall(r'\braceid="([0-9]+)"', block))
        require(len(race_ids) == 1, "Ambiguous official ASPX contest identity")
        counters = label(single(r'<div class="precinct-fully">(.*?)</div>', block))
        counter = re.fullmatch(r"([0-9,]+) out of ([0-9,]+) Precincts Reported", counters)
        require(counter is not None, "Changed official ASPX reporting counters")
        hidden = re.findall(r'<div[^>]*id="writeins_[^"]*"[^>]*>(.*?)</div>', block, re.S)
        require(all(not label(value) for value in hidden),
                "New named write-in detail requires a complete reviewed inventory")
        candidates = []
        for candidate in re.split(r'<div class="col display-results-box-d">', block)[1:]:
            name, party = single(r"^\s*<h1>(.*?)</h1>\s*<h2[^>]*>(.*?)</h2>", candidate)
            candidates.append({
                "candidate_id": single(r'<div id="(bar[0-9]+)">\s*</div>', candidate),
                "name_literal": unescape(re.sub(r"<[^>]*>", "", name)),
                "party_literal": unescape(re.sub(r"<[^>]*>", "", party)),
                "votes_literal": label(single(
                    r'<div class="col display-results-box-f">\s*<div>(.*?)</div>', candidate)),
            })
        contest_id = next(iter(race_ids))
        total_id, total_literal = single(
            r'<div class="col display-results-box-totalvotes">\s*<div>total votes</div>'
            r'\s*</div>\s*<div class="col display-results-box-total">'
            r'\s*<div id="([0-9]+)totals">(.*?)</div>', block)
        require(total_id == contest_id, "Official ASPX printed total belongs to another contest")
        facts["races"].append({
            "office_label": heading, "contest_id": contest_id,
            "reported_literal": counter[1], "total_units_literal": counter[2],
            "contest_total_literal": label(total_literal),
            "candidates": candidates,
        })
    return normalized(facts)


def collect(collector):
    def guarded(body):
        data = parse(body)
        current = source_clock(data["native_facts"]["source_update_label"])
        require(current <= collector.observation_time(), "Official ASPX clock is in the future")
        previous = (collector.prior.get(IDENTITY) or {}).get("data")
        if previous is not None:
            require(isinstance(previous, dict) and
                    normalized(previous.get("native_facts")) == previous,
                    "Prior official ASPX evidence changed")
            require(current >= source_clock(previous["native_facts"]["source_update_label"]),
                    "Official ASPX clock regressed")
            old_races = {r["district"]: r for r in previous["races"]}
            for race in data["races"]:
                old = old_races[race["district"]]
                require(all(old[key] == race[key] for key in
                            ("native_contest_id", "native_office_label", "total_units")),
                        "Official ASPX contest identity or source universe changed")
                old_candidates = {c["candidate_id"]: c for c in old["candidates"]}
                new_candidates = {c["candidate_id"]: c for c in race["candidates"]}
                require(set(old_candidates) <= set(new_candidates) and
                        all(all(candidate[key] == new_candidates[identity][key] for key in
                                ("name", "literal_party", "role", "party_group"))
                            for identity, candidate in old_candidates.items()),
                        "Official ASPX candidate inventory lost or changed an identity")
        return data

    return collector.capture(IDENTITY, URL, guarded)
