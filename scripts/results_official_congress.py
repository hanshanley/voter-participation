"""Retain complete official candidate frames separately from national intake."""

import copy
import re
from html import unescape

from scripts.congressional_complete_categories import IDENTITY as COMPLETE_IDENTITY, URL as COMPLETE_URL
from scripts.protected_official_house import IDENTITY as PROTECTED_IDENTITY, URL as PROTECTED_URL
from scripts.protected_official_wyoming import IDENTITY as WY_IDENTITY, URL as WY_URL
from scripts.results_connecticut_congress import IDENTITY as CT_IDENTITY, URL as CT_URL


IDENTITY = "NE-official-house-candidates"
URL = "https://electionresults.nebraska.gov/resultsSW.aspx"
CONTRACT = "participation.official_congressional_candidate_evidence.v1"
CONFIG = {"contract": CONTRACT, "election_date": "2026-11-03",
          "sources": {IDENTITY: URL}}
COMPLETE_CONFIG = {**CONFIG, "sources": {IDENTITY: URL, COMPLETE_IDENTITY: COMPLETE_URL}}
SENATE_IDENTITY = "RI-official-senate-candidates"
SENATE_CONFIG = {**COMPLETE_CONFIG, "sources": {
    **COMPLETE_CONFIG["sources"], SENATE_IDENTITY: COMPLETE_URL}}
PROTECTED_CONFIG = {**SENATE_CONFIG, "sources": {
    **SENATE_CONFIG["sources"], PROTECTED_IDENTITY: PROTECTED_URL}}
WY_CONFIG = {**PROTECTED_CONFIG, "sources": {**PROTECTED_CONFIG["sources"], WY_IDENTITY: WY_URL}}
ASPX_IDENTITY = "OR-official-house-candidates"
ASPX_URL = "https://results.oregonvotes.gov/resultsSW.aspx?type=FED&map=CTY"
ASPX_CONFIG = {**WY_CONFIG, "sources": {**WY_CONFIG["sources"], ASPX_IDENTITY: ASPX_URL}}
JSON_IDENTITY = "UT-official-house-candidates"
JSON_URL = (
    "https://electionresults.utah.gov/results/public/api/elections/Utah/"
    "General11032026/data"
)
JSON_CONFIG = {**ASPX_CONFIG, "sources": {**ASPX_CONFIG["sources"], JSON_IDENTITY: JSON_URL}}
CLARITY_IDENTITY = "IA-official-statewide-results"
CLARITY_URL = "https://electionresults.iowa.gov/IA/127077/current_ver.txt"
CLARITY_CONFIG = {**JSON_CONFIG, "sources": {
    **JSON_CONFIG["sources"], CLARITY_IDENTITY: CLARITY_URL}}
CONNECTICUT_CONFIG = {**CLARITY_CONFIG, "sources": {
    **CLARITY_CONFIG["sources"], CT_IDENTITY: CT_URL}}
IDENTITIES = (IDENTITY, COMPLETE_IDENTITY, SENATE_IDENTITY, PROTECTED_IDENTITY, WY_IDENTITY,
              ASPX_IDENTITY, JSON_IDENTITY, CLARITY_IDENTITY, CT_IDENTITY, "VA-official-house-candidates")
INTEGER = r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)"
PARTIES = {"Democratic": "D", "Republican": "R", "Libertarian": "O",
           "America First": "O", "Legal Marijuana Now": "O",
           "Nebraska Working People": "O", "By Petition": "O"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def label(value):
    return " ".join(unescape(re.sub(r"<[^>]*>", "", value)).split())


def integer(value):
    require(re.fullmatch(INTEGER, value) is not None, "Invalid native candidate count")
    result = int(value.replace(",", ""))
    require(result <= 2**53 - 1, "Unsafe native candidate count")
    return result


def single(pattern, text):
    values = re.findall(pattern, text, re.S)
    require(len(values) == 1, "Missing or ambiguous official candidate field")
    return values[0]


def nebraska_house(body):
    text = body.decode("utf-8-sig")
    require(label(single(r"<title>(.*?)</title>", text)) == "Nebraska Secretary of State"
            and len(re.findall(r"<h2>\s*General Election November 3, 2026\s*</h2>", text)) == 1,
            "Official candidate publisher or election changed")
    status = single(r"<h1>\s*((?:Unofficial|Official) Results)\s*</h1>", text)
    clock = label(single(r'<div class="last-updated">(.*?)</div>', text)) or None
    races = []
    sections = re.findall(
        r'<div class="display-results-box-a">\s*<h1>(.*?)</h1>(.*?)(?='
        r'<div class="display-results-box-a">|</form>)', text, re.S)
    for heading, block in sections:
        heading = label(heading)
        if "Representative in Congress" not in heading:
            continue
        match = re.fullmatch(
            r"For Representative in Congress - 2 Year Term - District (0[1-3])", heading)
        require(match is not None, "Unreviewed official House district or stage")
        seat = match[1]
        native_races = set(re.findall(r'\braceid="([0-9]+)"', block))
        require(len(native_races) == 1, "Ambiguous official contest identity")
        fully = single(r'<div class="precinct-fully">\s*Precincts Fully:\s*'
                       r'([0-9,]+)\s*/\s*([0-9,]+)\s*</div>', block)
        partial = single(r'<div class="precinct-partial">\s*Partially:\s*'
                         r'([0-9,]+)\s*/\s*([0-9,]+)\s*</div>', block)
        reported, total = map(integer, fully)
        partially, partial_total = map(integer, partial)
        require(total > 0 and partial_total == total and reported + partially <= total,
                "Official contest reporting counters disagree")
        candidates = []
        candidate_blocks = re.split(r'<div class="col display-results-box-d">', block)[1:]
        require(bool(candidate_blocks), "Official candidate inventory is missing")
        for candidate in candidate_blocks:
            name, party = single(
                r"^\s*<h1>(.*?)</h1>\s*<h2[^>]*>(.*?)</h2>", candidate)
            name_literal = unescape(re.sub(r"<[^>]*>", "", name))
            party_literal = unescape(re.sub(r"<[^>]*>", "", party))
            name, party = label(name), label(party)
            require(bool(name) and bool(party), "Official candidate identity is missing")
            literal = label(single(
                r'<div class="col display-results-box-f">\s*<h1>(.*?)</h1>', candidate))
            native_id = single(r'<div id="(bar[0-9]+)"></div>', candidate)
            candidates.append({
                "candidate_id": native_id, "name": name, "name_literal": name_literal,
                "literal_party": party, "party_literal": party_literal,
                "party_group": PARTIES.get(party, "U"), "votes": integer(literal),
                "votes_literal": literal,
                "role": ("generic_write_in" if name.casefold() in
                         ("write-in", "write-ins", "write in", "write ins")
                         else "named_candidate"),
            })
        control = label(single(
            r'<div class="col display-results-box-totalvotes">\s*<h2>total votes</h2>'
            r'\s*</div>\s*<div class="col display-results-box-total">\s*<h2>(.*?)</h2>', block))
        require(len({row["candidate_id"] for row in candidates}) == len(candidates)
                and len({(row["name"], row["literal_party"]) for row in candidates}) == len(candidates)
                and sum(row["votes"] for row in candidates) == integer(control),
                "Official named inventory does not reconcile to its printed total")
        races.append({
            "state_code": "NE", "district": "NE-" + seat, "seat": str(int(seat)),
            "native_contest_id": next(iter(native_races)), "native_office_label": heading,
            "election_date": "2026-11-03", "stage": "general", "election_kind": "regular",
            "native_status_literal": status, "source_update_label": clock,
            "source_update_timezone": None, "reported_units": reported, "total_units": total,
            "partial_units": partially, "complete_reporting": reported == total and partially == 0,
            "contest_total": integer(control), "contest_total_literal": control,
            "candidates": candidates,
        })
    require(len(races) == 3 and {row["district"] for row in races} == {"NE-01", "NE-02", "NE-03"},
            "Official statewide House inventory is incomplete or duplicated")
    return {
        "contract": CONTRACT, "election_date": "2026-11-03", "races": races,
        "participation_observation_qualified": False,
        "candidate_votes_are_not_ballots_or_turnout": True,
        "provider_other_equivalence_qualified": False, "conditional_model_eligible": False,
        "holds": [
            "Complete printed candidate tables do not establish an exhaustive counted write-in universe.",
            "National provider Other is not automatically equivalent to the official named-minor total.",
            "An independently reviewed candidate/source-frame bridge is still required for models.",
        ],
    }


def collect(collector, config):
    require(config == CONFIG, "Unreviewed official congressional source configuration")
    return collector.capture(IDENTITY, URL, nebraska_house)


def source_ids(config):
    require(config in (CONFIG, COMPLETE_CONFIG, SENATE_CONFIG, PROTECTED_CONFIG, WY_CONFIG,
                       ASPX_CONFIG, JSON_CONFIG, CLARITY_CONFIG, CONNECTICUT_CONFIG),
            "Unreviewed official congressional source configuration")
    return tuple(config["sources"])


def collect_sources(collector, config, selected=None):
    from scripts.congressional_complete_categories import parse, clock

    identities = source_ids(config)
    if selected is not None:
        require(set(selected) <= set(identities), "Unregistered official congressional source")
        identities = tuple(identity for identity in identities if identity in selected)
    result = {}
    if IDENTITY in identities:
        result[IDENTITY] = collect(collector, CONFIG)
    if PROTECTED_IDENTITY in identities:
        from scripts.protected_official_house import collect as collect_protected
        result[PROTECTED_IDENTITY] = collect_protected(collector)
    if WY_IDENTITY in identities:
        from scripts.protected_official_wyoming import collect as collect_wyoming
        result[WY_IDENTITY] = collect_wyoming(collector)
    if ASPX_IDENTITY in identities:
        from scripts.results_aspx_congress import collect as collect_aspx
        result[ASPX_IDENTITY] = collect_aspx(collector)
    if JSON_IDENTITY in identities:
        from scripts.results_json_congress import collect as collect_json
        result[JSON_IDENTITY] = collect_json(collector)
    if CLARITY_IDENTITY in identities:
        from scripts.results_clarity_congress import collect as collect_clarity
        result[CLARITY_IDENTITY] = collect_clarity(collector)
    if CT_IDENTITY in identities:
        from scripts.results_connecticut_congress import collect as collect_ct
        result[CT_IDENTITY] = collect_ct(collector)
    for source_id, chamber in ((COMPLETE_IDENTITY, "house"), (SENATE_IDENTITY, "senate")):
        if source_id not in identities:
            continue
        def guarded(body, source_id=source_id, chamber=chamber):
            data = parse(body, chamber)
            prior = (collector.prior.get(source_id) or {}).get("data") or {}
            require(clock(data["source_updated_at"]) <= collector.observation_time(),
                    "Official category clock is in the future")
            if prior:
                require(clock(data["source_updated_at"]) >= clock(prior["source_updated_at"]),
                        "Official category clock regressed")
            return data
        result[source_id] = collector.capture(source_id, COMPLETE_URL, guarded)
    return result


def attach(congress, feeds):
    result = copy.deepcopy(congress)
    evidence = {identity: copy.deepcopy(feeds[identity]) for identity in IDENTITIES if identity in feeds}
    if evidence:
        result["official_candidate_evidence"] = evidence
    return result


def reconciliation(congress):
    def votes(rows):
        counts = [row["votes"] for row in rows]
        return sum(counts) if counts and all(count is not None for count in counts) else None

    def difference(official, provider):
        return official - provider if official is not None and provider is not None else None

    result = []
    evidence = congress.get("official_candidate_evidence", {})
    for evidence_id, race in (
            (identity, race) for identity, entry in sorted(evidence.items())
            for race in (entry.get("data") or {}).get("races", [])):
        entry = evidence[evidence_id]
        chamber = race.get("chamber", "senate" if evidence_id == SENATE_IDENTITY else "house")
        matching = [
            (identity, candidate) for identity, candidate in congress.get("races", {}).items()
            if candidate.get("data") and all(candidate["data"].get(key) == value for key, value in {
                "chamber": chamber,
                "state_code": race["state_code"], "seat": race["seat"],
                "election_date": race["election_date"], "election_kind": race["election_kind"],
                "stage": race["stage"], "round": "not_ranked"}.items())]
        provider_id, provider = matching[0] if len(matching) == 1 else (None, {})
        candidates = (provider.get("data") or {}).get("candidates", [])
        other = [row for row in candidates if row["role"] == "provider_aggregate_other"]
        native_minor = [row for row in race["candidates"]
                        if row["party_group"] == "O" and row["role"] == "named_candidate"]
        provider_other = other[0]["votes"] if len(other) == 1 else None
        native_total = votes(native_minor) if native_minor else 0
        write_ins = votes(row for row in race["candidates"] if row["role"] == "generic_write_in")
        official_other_rows_total = native_total + write_ins if (
            native_total is not None and write_ins is not None) else None
        official_total = race["contest_total"]
        provider_total = votes(candidates)
        major = {}
        for party in ("D", "R"):
            totals = [votes(row for row in frame
                            if row["role"] == "named_candidate" and row.get("party_group") == party)
                      for frame in (race["candidates"], candidates)]
            major.update({
                f"official_{party.lower()}_named_votes": totals[0],
                f"provider_{party.lower()}_named_votes": totals[1],
                f"{party.lower()}_named_votes_difference": difference(*totals),
            })
        result.append({
            "evidence_id": evidence_id, "native_contest_id": race["native_contest_id"],
            "state_code": race["state_code"], "chamber": chamber,
            "seat": race["seat"], "stage": race["stage"],
            "election_date": race["election_date"], "election_kind": race["election_kind"],
            "district": race["district"], "official_status": entry.get("status"),
            "official_error": entry.get("error"),
            "official_source": entry.get("source"),
            "official_source_update_label": race["source_update_label"],
            "official_reporting_complete": race["complete_reporting"],
            "official_contest_vote_total": official_total,
            "official_named_minor_votes": native_total,
            "official_generic_write_in_votes": write_ins,
            "official_named_minor_plus_generic_write_in_votes": official_other_rows_total,
            "provider_race_id": provider_id, "provider_status": provider.get("status"),
            "provider_error": provider.get("error"),
            "provider_source": provider.get("source"),
            "provider_source_updated_at": (provider.get("data") or {}).get("source_updated_at"),
            "provider_match_count": len(matching),
            "provider_candidate_vote_sum": provider_total,
            "contest_vote_total_minus_provider_candidate_vote_sum": difference(official_total, provider_total),
            "provider_aggregate_other": provider_other,
            "named_minor_minus_provider_other": difference(native_total, provider_other),
            "named_minor_plus_generic_write_in_minus_provider_other": difference(
                official_other_rows_total, provider_other),
            **major,
            "synchronized_snapshots_qualified": False, "universe_equivalence_qualified": False,
            "counts_combined_or_replaced": False,
        })
    return result


def rows(congress, comparisons=None):
    result = []
    if comparisons is None:
        comparisons = reconciliation(congress)
    compared = {(row["evidence_id"], row["native_contest_id"]): row for row in comparisons}
    require(len(compared) == len(comparisons), "Duplicate official contest in candidate reconciliation")
    for identity, entry in sorted(congress.get("official_candidate_evidence", {}).items()):
        data = entry.get("data")
        if data is None:
            continue
        require(identity in IDENTITIES and data.get("contract") == CONTRACT
                and data.get("conditional_model_eligible") is False
                and data.get("provider_other_equivalence_qualified") is False,
                "Unreviewed official candidate evidence")
        for race in data["races"]:
            for candidate in race["candidates"]:
                result.append({
                    "evidence_id": identity, "source_status": entry["status"],
                    "source_error": entry.get("error"), "source": entry.get("source"),
                    "first_observed_at": entry.get("first_observed_at"),
                    **{key: copy.deepcopy(value) for key, value in race.items() if key != "candidates"},
                    **copy.deepcopy(candidate), "conditional_model_eligible": False,
                    "provider_other_equivalence_qualified": False,
                    "provider_reconciliation": copy.deepcopy(compared[identity, race["native_contest_id"]]),
                    **({"exhaustive_write_in_universe_qualified": False,
                        "write_in_scope_notice": data["native_facts"]["write_in_scope_notice"],
                        "source_scope_holds": copy.deepcopy(data["holds"])}
                       if identity == ASPX_IDENTITY else {}),
                    **({"exhaustive_write_in_universe_qualified": False,
                        "source_scope_holds": copy.deepcopy(data["holds"])}
                       if identity in (JSON_IDENTITY, CLARITY_IDENTITY) else {}),
                    **({"exhaustive_write_in_universe_qualified": False,
                        "numerical_input_pins": copy.deepcopy(data["numerical_input_pins"])}
                       if identity == CT_IDENTITY else {}),
                })
    return result
