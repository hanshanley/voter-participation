"""Bulk congressional returns, independent of participation and behavioral models."""

import copy
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor

from scripts.participation_intake.contract import encoded, pin
from scripts.results_house import HOUSE_STATES


CONTRACT = "participation.congressional_results.v1"
ELECTION = "2026-11-03"
SAFE_INTEGER = 9007199254740991
PARTIES = {"Dem": "D", "GOP": "R"}
STAGES = {
    "General": ("regular", "general"),
    "Special General": ("special", "general"),
    "General Runoff": ("regular", "general_runoff"),
    "Special General Runoff": ("special", "general_runoff"),
    "Nonpartisan Election": ("regular", "nonpartisan_election"),
}
RACE_FIELDS = (
    "test", "id", "office", "officeName", "resultsType", "tabulationStatus",
    "type", "seatNumber", "seat", "rankedChoice", "round", "rcvResult",
    "runoff", "state", "level", "updated", "reporting", "precincts",
    "reportingPercent", "certified", "electionDate",
)
CANDIDATE_FIELDS = ("id", "first", "last", "party", "votes", "incumbent")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, label, nullable=False):
    require((nullable and value is None) or (
        type(value) is int and 0 <= value <= SAFE_INTEGER), "Invalid " + label)
    return value


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), "Missing " + label)
    return value


def decode(body):
    if body[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
            body = stream.read(25_000_001)
    require(len(body) <= 25_000_000, "Oversized national congressional feed")
    return json.loads(body)


def catalog(body):
    source = decode(body)
    require(isinstance(source, dict) and isinstance(source.get("results"), list)
            and bool(source["results"]), "Missing national race inventory")
    rows = []
    for row in source["results"]:
        if not isinstance(row, dict):
            rows.append({"invalid_declaration_type": type(row).__name__})
            continue
        selected = {key: copy.deepcopy(row[key]) for key in RACE_FIELDS if key in row}
        candidates = row.get("candidates")
        selected["candidates"] = [
            {key: copy.deepcopy(candidate[key]) for key in CANDIDATE_FIELDS if key in candidate}
            if isinstance(candidate, dict) else candidate for candidate in candidates
        ] if isinstance(candidates, list) else candidates
        rows.append(selected)
    return {"rows": rows}


def normalize(row, chamber):
    require(row.get("test") is False, "Test election is not a production result")
    require(row.get("office") == {"house": "H", "senate": "S"}[chamber]
            and row.get("officeName") == {"house": "U.S. House", "senate": "U.S. Senate"}[chamber],
            "Office identity differs")
    require(row.get("level") == "state" and row.get("state") in HOUSE_STATES | {"DC", "PR", "GU", "VI", "AS", "MP"},
            "Wrong national race geography")
    require(chamber == "house" or row["state"] in HOUSE_STATES, "Senate geography differs")
    require(row.get("electionDate", ELECTION)[:10] == ELECTION, "Election date differs")
    status = row.get("tabulationStatus")
    require(status is None or isinstance(status, str) and bool(status.strip()),
            "Invalid native tabulation status")
    kind, stage = STAGES.get(row.get("type"), (None, None))
    require(stage is not None, "Unreviewed election stage")
    native_id = text(row.get("id"), "provider race ID")
    require(re.fullmatch(r"[A-Za-z0-9_-]+", native_id) is not None, "Unsafe provider race ID")
    seat = text(row.get("seatNumber"), "seat number")
    require(seat.isdigit() and int(seat) > 0, "Invalid seat identity")
    seat_label = text(row.get("seat"), "seat label")
    if chamber == "senate":
        require(seat in ("1", "2", "3") and seat_label in (
            {"1": "Class I", "2": "Class II", "3": "Class III"}[seat],
            {"1": "Class I", "2": "Class II", "3": "Class III"}[seat] + " Unexpired Term"),
            "Senate class and seat disagree")
        require(("Unexpired" in seat_label) == (kind == "special"),
                "Senate regular/special seat identity differs")
    else:
        require(seat_label == "District " + seat, "House district label differs")
    ranked = row.get("rankedChoice", False)
    require(type(ranked) is bool, "Invalid ranked-choice declaration")
    require(row.get("rcvResult") in (None, "pending", "final"), "Unreviewed RCV result phase")
    require(row.get("runoff") is None or type(row["runoff"]) is bool, "Invalid runoff flag")
    for field in ("reporting", "precincts"):
        integer(row.get(field), field, nullable=True)
    if row.get("reporting") is not None and row.get("precincts") is not None:
        require(row["reporting"] <= row["precincts"], "Reporting exceeds native precinct inventory")
    if "round" in row:
        integer(row["round"], "round")
        require(row["round"] > 0, "Invalid zero round")
        round_id = "round-" + str(row["round"])
    else:
        round_id = ("rcv-" + str(row.get("rcvResult", "unspecified"))) if ranked else "not_ranked"
    updated = integer(row.get("updated"), "native update epoch")
    clock = datetime.fromtimestamp(updated / 1000, timezone.utc).isoformat(timespec="milliseconds")
    require(datetime.fromisoformat(ELECTION).replace(tzinfo=timezone.utc) <=
            datetime.fromtimestamp(updated / 1000, timezone.utc), "Count clock predates the election")
    candidates, identities = [], set()
    require(isinstance(row.get("candidates"), list) and bool(row["candidates"]),
            "Missing candidate inventory")
    for candidate in row["candidates"]:
        require(isinstance(candidate, dict), "Invalid candidate record")
        cid = text(candidate.get("id"), "native candidate ID")
        require(cid not in identities, "Duplicate candidate identity")
        identities.add(cid)
        first, last = candidate.get("first", ""), text(candidate.get("last"), "candidate name")
        require(isinstance(first, str), "Invalid candidate first name")
        party = candidate.get("party")
        require(party is None or isinstance(party, str), "Invalid literal party")
        require("votes" in candidate, "Missing candidate count field")
        votes = integer(candidate["votes"], "candidate votes", nullable=True)
        candidates.append({
            "candidate_id": cid, "first": first, "last": last,
            "name": " ".join(value for value in (first, last) if value),
            "literal_party": party, "party_group": PARTIES.get(party, "O") if party else "U",
            "votes": votes, "count_status": "unknown" if votes is None else "reported",
            "role": "provider_aggregate_other" if cid == "other-" + native_id else "named_candidate",
        })
    candidates.sort(key=lambda candidate: candidate["candidate_id"])
    identity = ":".join(("npr", chamber, row["state"], seat, kind, stage, round_id))
    return {
        "id": identity, "provider_race_id": native_id, "chamber": chamber,
        "state_code": row["state"], "seat": seat, "seat_label": seat_label,
        "voting_house_seat": chamber == "house" and row["state"] in HOUSE_STATES,
        "election_date": ELECTION, "election_date_basis": "reviewed_2026_national_index_context",
        "election_kind": kind, "stage": stage, "native_type": row["type"],
        "ranked_choice": ranked, "round": round_id,
        "native_round": row.get("round"), "native_rcv_result": row.get("rcvResult"),
        "native_runoff": row.get("runoff"),
        "source_updated_epoch_ms": updated, "source_updated_at": clock,
        "native_results_type": row.get("resultsType"),
        "native_certified": row.get("certified"),
        "reporting": row.get("reporting"), "precincts": row.get("precincts"),
        "candidates": candidates, "native_facts": copy.deepcopy(row),
        "candidate_votes_are_not_ballots_or_turnout": True,
    }


def check_revision(old, new, *, allow_additions=False):
    if not old:
        return
    require(old["provider_race_id"] == new["provider_race_id"], "Provider race identity changed")
    before = {row["candidate_id"]: row for row in old["candidates"]}
    after = {row["candidate_id"]: row for row in new["candidates"]}
    require(before.keys() <= after.keys() if allow_additions else before.keys() == after.keys(),
            "Candidate inventory changed or incomplete")
    for key in before:
        require(all(before[key][field] == after[key][field] for field in
                    ("first", "last", "literal_party", "role")), "Candidate identity changed")
        require(before[key]["votes"] is None or after[key]["votes"] is not None,
                "Candidate count missing; last-good counts retained")
    prior_clock, clock = old["source_updated_epoch_ms"], new["source_updated_epoch_ms"]
    require(clock >= prior_clock, "Native source clock regressed")
    if clock == prior_clock:
        before, after = copy.deepcopy(old), copy.deepcopy(new)
        # Descriptive tabulation status can advance independently of the count clock.
        for data in (before, after):
            data["native_facts"].pop("tabulationStatus", None)
        require(before == after, "Counts or source facts changed without a newer native version")


def collect(collector, previous, configuration):
    from scripts.results_intake import Collector

    previous = previous or {}
    prior_races = previous.get("races", {})
    feeds, races = {}, {}
    reader = Collector(collector.work, {
        "congress-catalog-" + chamber: entry
        for chamber, entry in previous.get("feeds", {}).items()
    }, collector.stopped, collector.now, offline=collector.offline)
    reader.acquire, reader.guard, reader.lock = collector.acquire, collector.guard, collector.lock

    def capture(item):
        chamber, declaration = item
        key = "congress-catalog-" + chamber
        entry = reader.capture(key, declaration["url"], catalog)
        return chamber, entry

    with ThreadPoolExecutor(max_workers=2) as pool:
        feeds.update(pool.map(capture, sorted(configuration["feeds"].items())))
    collector.attempts.extend(reader.attempts)
    seen_provider = set()
    for chamber, feed in sorted(feeds.items()):
        if feed["status"] != "reported":
            continue
        def declaration_key(row):
            return json.dumps([row.get(key) for key in
                               ("id", "type", "rankedChoice", "round", "rcvResult")], sort_keys=True)

        frequencies = Counter(declaration_key(row) for row in feed["data"]["rows"])
        for index, row in enumerate(feed["data"]["rows"]):
            provider_key = (chamber, row.get("id"))
            matching_old = [(key, entry) for key, entry in prior_races.items()
                            if entry.get("data") and
                            (entry["data"]["chamber"], entry["data"]["provider_race_id"]) == provider_key]
            identity, data = "invalid:" + chamber + ":" + str(index), None
            try:
                key = declaration_key(row)
                require(frequencies[key] == 1, "Duplicate provider race declaration")
                require((chamber, key) not in seen_provider, "Duplicate provider race declaration")
                seen_provider.add((chamber, key))
                data = normalize(row, chamber)
                for _, prior in matching_old:
                    require(all(data[field] == prior["data"][field] for field in
                                ("chamber", "state_code", "seat", "election_kind", "election_date")),
                            "Provider contest geography or seat identity changed")
                    require(data["source_updated_epoch_ms"] >= prior["data"]["source_updated_epoch_ms"],
                            "Native source clock regressed across stages or rounds")
                require(data["source_updated_epoch_ms"] <= collector.observation_time().timestamp() * 1000 + 300_000,
                        "Native count clock is in the future")
                identity = data["id"]
                require(identity not in races, "Duplicate contest seat/stage/round")
                old = prior_races.get(identity)
                check_revision(old.get("data") if old else None, data, allow_additions=True)
                races[identity] = {
                    "data": data, "source": feed["source"], "status": "reported",
                    "freshness": "source_verified", "advertised": True, "error": None,
                }
            except (ValueError, TypeError, KeyError, OverflowError, OSError) as error:
                old_key, old = matching_old[0] if len(matching_old) == 1 else (
                    identity, prior_races.get(identity, {}))
                races[old_key] = {
                    **copy.deepcopy(old), "status": "retained_after_failure" if old.get("data") else "held",
                    "data": copy.deepcopy(old.get("data")), "freshness": "retained_last_good" if old.get("data") else "unavailable",
                    "advertised": True, "error": str(error), "chamber": chamber,
                    "attempted_facts": row, "attempted_source": feed["source"],
                }
    for key, old in prior_races.items():
        if key in races:
            continue
        chamber = (old.get("data") or {}).get("chamber", old.get("chamber"))
        failed = feeds.get(chamber, {}).get("status") != "reported"
        races[key] = {**copy.deepcopy(old),
                      "status": "retained_after_failure" if old.get("data") else "held",
                      "freshness": "retained_last_good" if old.get("data") else "unavailable",
                      "advertised": False,
                      "error": "National feed unavailable" if failed else "Race no longer advertised"}
    return {"contract": CONTRACT, "election_date": ELECTION,
            "configuration": configuration, "feeds": feeds, "races": dict(sorted(races.items()))}


def totals(data):
    values = {party: 0 for party in "DROU"}
    for candidate in data["candidates"]:
        group = candidate["party_group"]
        if candidate["votes"] is None:
            values[group] = None
        elif values[group] is not None:
            values[group] += candidate["votes"]
    d, r = values["D"], values["R"]
    denominator = d + r if d is not None and r is not None else None
    return {**values, "D_two_party_share_pct": 100 * d / denominator if denominator else None,
            "R_two_party_share_pct": 100 * r / denominator if denominator else None,
            "D_minus_R_margin_pp": 100 * (d - r) / denominator if denominator else None}


def rcv_supersessions(congress):
    def frame(data):
        return tuple(data[key] for key in ("provider_race_id", "chamber", "state_code", "seat",
                                          "election_date", "election_kind", "stage"))

    finals = {}
    for identity, entry in congress["races"].items():
        data = entry.get("data") or {}
        if (entry["status"] == "reported" and entry["advertised"] and data.get("ranked_choice")
                and data["native_rcv_result"] == "final"
                and all(candidate["votes"] is not None for candidate in data["candidates"])):
            finals.setdefault(frame(data), []).append((identity, data))
    out = {}
    for identity, entry in congress["races"].items():
        data = entry.get("data") or {}
        if (entry["status"] != "retained_after_failure" or entry["advertised"]
                or entry.get("error") != "Race no longer advertised" or not data.get("ranked_choice")
                or data["native_rcv_result"] != "pending"):
            continue
        replacements = finals.get(frame(data), [])
        if len(replacements) == 1:
            target, final = replacements[0]
            if final["source_updated_epoch_ms"] > data["source_updated_epoch_ms"]:
                out[identity] = target
    return out


def tables(congress):
    races, candidates, coverage = [], [], []
    superseded = rcv_supersessions(congress)
    for identity, entry in sorted(congress["races"].items()):
        data = entry.get("data")
        base = {"id": identity, "chamber": data["chamber"] if data else entry.get("chamber"),
                "status": entry["status"], "freshness": entry["freshness"],
                "advertised": entry["advertised"], "hold_reason": entry.get("error")}
        if identity in superseded:
            base["superseded_by_race_id"] = superseded[identity]
        coverage.append({**base, "state_code": data["state_code"] if data else None,
                         "source_url": (entry.get("source") or entry.get("attempted_source") or {}).get("url"),
                         "source_updated_at": data["source_updated_at"] if data else None})
        if not data:
            continue
        race = {**base, **{key: value for key, value in data.items()
                           if key not in ("candidates", "native_facts")}, **totals(data),
                "source": entry["source"],
                "candidate_ids": [candidate["candidate_id"] for candidate in data["candidates"]],
                "count_coverage_complete": all(c["votes"] is not None for c in data["candidates"])}
        races.append(race)
        candidates.extend({**base, "state_code": data["state_code"], "seat": data["seat"],
                           "stage": data["stage"], "round": data["round"], **candidate,
                           "source": entry["source"], "source_updated_at": data["source_updated_at"]}
                          for candidate in data["candidates"])
    return races, candidates, coverage


def summary(congress):
    races, _, coverage = tables(congress)
    return {chamber: {
        "discovered": sum(row["chamber"] == chamber and row["advertised"] for row in coverage),
        "refreshed": sum(row["chamber"] == chamber and row["status"] == "reported" for row in races),
        "retained": sum(row["chamber"] == chamber and row["status"] != "reported" for row in races),
        "superseded_rcv_records": sum(row["chamber"] == chamber and "superseded_by_race_id" in row
                                      for row in races),
        "held": sum(row["chamber"] == chamber and row["status"] == "held" for row in coverage),
        "unknown_count_races": sum(row["chamber"] == chamber and not row["count_coverage_complete"] for row in races),
        "nonvoting_house_seats": sum(row["chamber"] == "house" and not row["voting_house_seat"]
                                    for row in races) if chamber == "house" else 0,
    } for chamber in ("house", "senate")}


def csv_bytes(rows):
    fields = sorted(set().union(*(row.keys() for row in rows))) if rows else ["id"]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({key: json.dumps(value, sort_keys=True, separators=(",", ":"))
                     if isinstance(value, (dict, list)) else value for key, value in row.items()}
                    for row in rows)
    return output.getvalue().encode()


def compressed(value):
    body = gzip.compress(encoded(value), mtime=0)
    return body[:9] + bytes([3]) + body[10:]


def exports(congress):
    races, candidates, coverage = tables(congress)
    result = {"congress-" + name + ".csv": csv_bytes(rows) for name, rows in (
        ("races", races), ("candidates", candidates), ("coverage", coverage))}
    if "official_candidate_evidence" in congress:
        from scripts.results_official_congress import rows
        result["congress-official-candidates.csv"] = csv_bytes(rows(congress))
    return result


def comparisons(congress, review, historical_senate=None, boundary_review=None):
    if boundary_review is not None:
        from scripts.congressional_geography import validate_review
        validate_review(boundary_review)
    previous_house = {row["district"]: row for row in review["previous_district_queries"]}
    old_models = json.loads(review["frozen_inputs"]["existing_other_office_models"]["body"])
    previous_senate = {row["state_code"]: row for row in old_models["rows"] if row["office"] == "senate"}
    district_counts = {}
    for district in previous_house:
        district_counts[district[:2]] = district_counts.get(district[:2], 0) + 1
    result = []
    for race in tables(congress)[0]:
        entry = congress["races"][race["id"]]
        data = entry["data"]
        reasons, previous, baseline, previous_candidates = [], None, {}, []
        if race["chamber"] == "house":
            key = race["state_code"] + "-" + (
                "AL" if district_counts.get(race["state_code"]) == 1 else race["seat"].zfill(2))
            query = previous_house.get(key)
            if query:
                baseline = {"year": 2024, "stage": "general", "seat": race["seat"],
                            "district": key, "query": query["previous"]}
                previous = query["previous"]["reported_counts"]
                previous_candidates = query["previous"]["source_candidate_rows"]
                if query["previous"]["multiple_same_party_nominees"]:
                    reasons.append("Previous multiple same-party nominees or fusion ambiguity")
                if query["previous"]["missing_major_party_counts"]:
                    reasons.append("Previous native candidate counts missing")
                present = {party: any(c["party_group"] == party and c["role"] == "named_candidate"
                                      for c in data["candidates"]) for party in "DR"}
                if present != query["previous"]["major_party_presence"]:
                    reasons.append("Major-party candidate coverage changed")
                if boundary_review is not None:
                    from scripts.congressional_geography import comparison_decision
                    boundary = comparison_decision(boundary_review, key, race)
                    baseline["boundary_eligibility"] = copy.deepcopy(boundary)
                    if not boundary["boundary_compatible"]:
                        reasons.extend("House boundary hold: " + reason for reason in boundary["holds"])
                elif not query.get("geographic_boundary_stability_independently_qualified", False):
                    reasons.append("Cross-year district boundary stability is not independently qualified")
            else:
                reasons.append("No reviewed previous same-district House query")
        else:
            source = (previous_senate.get(race["state_code"]) or {}).get("reported_comparison", {})
            if historical_senate is not None:
                from scripts.congressional_baselines import select_reference
                reference = select_reference(historical_senate, race["state_code"], race["seat"])
                if reference is None:
                    reasons.append("No reviewed same-seat historical election")
                else:
                    previous = reference["counts"]
                    previous_candidates = reference["candidate_facts"]
                    baseline = {
                        "year": reference["year"], "cycle_year": reference["cycle_year"],
                        "stage": reference["stage"], "seat": reference["seat"],
                        "election_kind": reference["election_kind"],
                        "source_urls": reference["source_urls"],
                        "comparison_policy": "latest_completed_same_seat_final_election_to_final_election",
                        "previous_stage_differs": reference["stage"] != race["stage"],
                        "previous_regular_special_differs": reference["election_kind"] != race["election_kind"],
                    }
                    if reference["ranked_choice"]:
                        reasons.append("Previous RCV round is not qualified")
                    for party in "DR":
                        if reference["major_party_nominees"][party] != 1:
                            reasons.append("Previous " + party + " nominee is absent or not unique")
            elif (race["seat"] == "2" and race["election_kind"] == "regular"
                    and source.get("baseline_cycle_year") == 2020
                    and source.get("scope") == "Statewide regular-seat candidate counts; special/unexpired seat rows excluded"):
                previous = source["previous"]
                previous_candidates = source["native_candidate_facts"]
                baseline = {"year": source["baseline_year"], "stage": source["baseline_stage"],
                            "seat": "2", "seat_qualification": source["qualification"],
                            "source_url": source["baseline_source_url"]}
                if baseline["stage"] != race["stage"]:
                    reasons.append("Previous and current election stages differ")
            else:
                reasons.append(source.get("reason") or
                               "No reviewed qualified previous election for this Senate seat class and election kind")
        if entry["status"] != "reported":
            reasons.append("Current source retained, not refreshed: " + str(entry.get("error")))
        if race["stage"] != "general":
            reasons.append("Current stage is not a qualified general-election comparison")
        if race["ranked_choice"]:
            reasons.append("A matching previous/current RCV round has not been qualified")
        if race["native_runoff"]:
            reasons.append("Native source flags a runoff; this stage is not a final-stage comparison")
        if not race["count_coverage_complete"]:
            reasons.append("Current native candidate count unknown")
        if any(c["party_group"] == "U" for c in data["candidates"]):
            reasons.append("Native candidate party is unknown; no affiliation inferred")
        for party in "DR":
            named = [c for c in data["candidates"] if c["party_group"] == party
                     and c["role"] == "named_candidate"]
            if len(named) != 1:
                reasons.append("Current " + party + " nominee is absent or not unique")
        previous_metrics = None
        if previous is not None:
            if any(type(previous.get(party)) is not int or previous[party] <= 0 for party in "DR"):
                reasons.append("Previous D/R contest is unopposed, missing or nonpositive")
            if (all(type(previous.get(party)) is int and previous[party] >= 0 for party in "DR")
                    and previous["D"] + previous["R"] > 0):
                denominator = previous["D"] + previous["R"]
                previous_metrics = {**previous,
                    "D_two_party_share_pct": 100 * previous["D"] / denominator,
                    "R_two_party_share_pct": 100 * previous["R"] / denominator,
                    "D_minus_R_margin_pp": 100 * (previous["D"] - previous["R"]) / denominator}
        if race["D"] is None or race["R"] is None or not race["D"] or not race["R"]:
            reasons.append("Current D/R counts are unknown or nonpositive")
        raw = (race["D_minus_R_margin_pp"] - previous_metrics["D_minus_R_margin_pp"]
               if previous_metrics and race["D_minus_R_margin_pp"] is not None else None)
        result.append({**race, "previous": previous_metrics, "baseline": baseline,
                       "previous_candidates": previous_candidates,
                       "raw_recorded_margin_change_pp": raw,
                       "raw_recorded_D_share_change_pp": raw / 2 if raw is not None else None,
                       "qualified_comparison": not reasons and previous_metrics is not None,
                       "qualified_margin_change_pp": raw if not reasons else None,
                       "comparison_holds": sorted(set(reasons)),
                       "comparison_scope": "recorded_same_office_source_identifiers_not_certified_boundary_stability",
                       "behavioral_estimate_updated": False,
                       "behavioral_prerequisite": "Separately reviewed model candidate/source/frame eligibility; no model refit or automatic promotion"})
    return result


def house_state_comparisons(congress, review):
    races, candidates, _ = tables(congress)
    queries = {}
    for row in review["previous_district_queries"]:
        queries.setdefault(row["district"][:2], []).append(row)
    result = []
    for state, previous_rows in sorted(queries.items()):
        selected = [row for row in races if row["chamber"] == "house"
                    and row["state_code"] == state and row["voting_house_seat"]]
        advertised = [row for row in selected if row["advertised"]]
        if advertised:
            selected = advertised
        expected = {str(int(row["district"][3:])) if row["district"][3:] != "AL" else "1"
                    for row in previous_rows}
        complete = len(selected) == len(expected) and {row["seat"] for row in selected} == expected
        reasons = [] if complete else ["Incomplete or ambiguous seat/stage/round inventory; no overlapping frames summed"]
        before, after = {}, {}
        for party in "DRO":
            values = [row["previous"]["reported_counts"].get(party) for row in previous_rows]
            before[party] = sum(values) if all(type(value) is int and value >= 0 for value in values) else None
        for party in "DROU":
            values = [row[party] for row in selected]
            after[party] = sum(values) if complete and all(type(value) is int for value in values) else None
        by_seat = {row["seat"]: row for row in selected} if complete else {}
        for query in previous_rows:
            seat = "1" if query["district"][3:] == "AL" else str(int(query["district"][3:]))
            race = by_seat.get(seat)
            if not race:
                continue
            current_candidates = [row for row in candidates if row["id"] == race["id"]]
            present = {party: any(row["party_group"] == party and row["role"] == "named_candidate"
                                  for row in current_candidates) for party in "DR"}
            previous = query["previous"]
            if present != previous["major_party_presence"]:
                reasons.append("Major-party candidate coverage changed: " + query["district"])
            if previous["multiple_same_party_nominees"] or any(
                    sum(row["party_group"] == party and row["role"] == "named_candidate"
                        for row in current_candidates) > 1 for party in "DR"):
                reasons.append("Multiple same-party nominees: " + query["district"])
            if previous["missing_major_party_counts"] or not race["count_coverage_complete"]:
                reasons.append("Candidate counts missing: " + query["district"])
            if any(row["party_group"] == "U" for row in current_candidates):
                reasons.append("Native party unknown: " + query["district"])
            if race["stage"] != "general" or race["ranked_choice"] or race["native_runoff"]:
                reasons.append("Stage or RCV round not qualified: " + query["district"])
            if race["status"] != "reported":
                reasons.append("Source retained, not refreshed: " + query["district"])
        def metrics(values):
            d, r = values["D"], values["R"]
            denominator = d + r if d is not None and r is not None else None
            return {**values,
                    "D_two_party_share_pct": 100 * d / denominator if denominator else None,
                    "D_minus_R_margin_pp": 100 * (d - r) / denominator if denominator else None}
        before, after = metrics(before), metrics(after)
        if not before["D"] or not before["R"] or not after["D"] or not after["R"]:
            reasons.append("Statewide D/R counts unknown or nonpositive")
        raw = (after["D_minus_R_margin_pp"] - before["D_minus_R_margin_pp"]
               if before["D_minus_R_margin_pp"] is not None and after["D_minus_R_margin_pp"] is not None else None)
        result.append({
            "state_code": state, "office": "house", "previous_year": 2024, "current_year": 2026,
            "previous": before, "current": after, "expected_voting_seats": len(expected),
            "selected_race_ids": [row["id"] for row in selected],
            "source_updated_at_by_contest": {row["id"]: row["source_updated_at"] for row in selected},
            "raw_recorded_margin_change_pp": raw,
            "raw_recorded_D_share_change_pp": raw / 2 if raw is not None else None,
            "qualified_comparison": not reasons, "qualified_margin_change_pp": raw if not reasons else None,
            "comparison_holds": sorted(set(reasons)),
            "comparison_scope": "statewide_complete_same_office_not_cross_year_district_or_individual_identity",
            "behavioral_estimate_updated": False,
        })
    return result


def legacy_comparison_view(rows):
    result = copy.deepcopy(rows)
    for row in result:
        if (row["qualified_comparison"] and row["chamber"] == "senate"
                and (row["seat"] != "2" or row["election_kind"] != "regular"
                     or row["baseline"]["seat"] != "2"
                     or row["baseline"]["stage"] != row["stage"])):
            row.update(
                reviewed_qualified_comparison=True,
                reviewed_qualified_margin_change_pp=row["qualified_margin_change_pp"],
                qualified_comparison=False, qualified_margin_change_pp=None,
                comparison_holds=[
                    "Reviewed same-seat comparison is qualified in congress-comparisons.csv; "
                    "the deployed v1 reader can badge only regular Class II, same-stage comparisons. "
                    "Raw counts and changes remain available here."
                ],
                legacy_reader_display_limit=True,
            )
    return result


def runtime(congress, review, analytical_review=None, estimates=None):
    history = analytical_review["historical_senate"] if analytical_review else None
    boundaries = analytical_review.get("house_boundaries") if analytical_review else None
    compared = comparisons(congress, review, history, boundaries)
    states = house_state_comparisons(congress, review)
    races, candidates, coverage = tables(congress)
    payload = {"contract": CONTRACT, "election_date": ELECTION, "races": compared,
               "candidates": candidates, "coverage": coverage, "summary": summary(congress),
               "house_states": states,
               "source_models_refitted": False, "observed_individual_behavior": False}
    if "official_candidate_evidence" in congress:
        from scripts.results_official_congress import reconciliation
        payload["official_candidate_evidence"] = copy.deepcopy(congress["official_candidate_evidence"])
        payload["official_candidate_reconciliation"] = reconciliation(congress)
    files = {"congressional/results.json.gz": compressed(payload),
             "congressional/queries.json.gz": compressed({
                 "congressional_sources": congress,
                 "previous_house_queries": review["previous_district_queries"],
                 "previous_senate_queries": [row for row in json.loads(
                     review["frozen_inputs"]["existing_other_office_models"]["body"])["rows"]
                     if row["office"] == "senate"]}),
             **{"congressional/" + name: body for name, body in exports(congress).items()},
             "congressional/congress-comparisons.csv": csv_bytes(compared),
             "congressional/congress-house-states.csv": csv_bytes(states)}
    if boundaries is not None:
        files.update({
            "congressional/house-boundary-queries.json.gz": compressed(boundaries),
            "congressional/congress-house-boundaries.csv": csv_bytes(
                list(boundaries["decisions"].values())),
        })
        payload["house_boundary_review"] = {
            "contract": boundaries["contract"], "version": boundaries["version"],
            "evidence": boundaries["evidence"], "districts": len(boundaries["decisions"]),
            "boundary_compatible": sum(row["boundary_compatible"]
                                       for row in boundaries["decisions"].values()),
            "qualified_recorded_comparisons": sum(row["chamber"] == "house"
                                                  and row["qualified_comparison"] for row in compared),
        }
    if analytical_review is not None:
        from scripts.congressional_analytical_bridge import state_guard_matrix

        decisions = (estimates or {}).get("decisions", {}).get("states", [])
        handoff = (estimates or {}).get("congressional_analytical_handoff", {})
        guard_matrix = state_guard_matrix(handoff)
        guard_rows = {row["state_code"]: row for row in guard_matrix["states"]}
        exported_decisions = copy.deepcopy(decisions)
        for row in exported_decisions:
            guard = guard_rows.get(row["state_code"])
            if guard is not None:
                row["overlapping_guard_families"] = guard["overlapping_guard_families"]
                row["missing_evidence"] = guard["missing_evidence"]
        next_seed = (estimates or {}).get("artifacts", {}).get("rolling/next-seed.json.gz", {}).get("content", {})
        current_models = {key: scenario["accepted_result"] for key, scenario in next_seed.get("scenarios", {}).items()}
        files.update({
            "congressional/analytical-review.json.gz": compressed(analytical_review),
            "congressional/congress-candidate-crosswalk.csv": csv_bytes(analytical_review["candidate_crosswalk"]),
            "congressional/congress-analytical-decisions.csv": csv_bytes(exported_decisions),
            "congressional/congress-race-analytical-decisions.csv": csv_bytes(
                list(handoff.get("races", {}).values())),
            "congressional/congress-scientific-eligibility.csv": csv_bytes([
                {"state_code": state, **decision} for state, decision in analytical_review["states"].items()]),
            "congressional/senate-historical-queries.json.gz": compressed(history),
            "congressional/senate-historical-candidates.csv": csv_bytes([
                row for dataset in history["datasets"] for row in dataset["candidate_stage_records"]]),
            "congressional/conditional-results.json.gz": compressed(current_models),
        })
        query = decode(files["congressional/queries.json.gz"])
        query.update(
            reviewed_analytical_policy=analytical_review,
            current_analytical_decisions={
                "states": handoff.get("states", {}), "races": handoff.get("races", {})},
            state_guard_matrix=guard_matrix,
            reviewed_race_comparisons=compared,
            conditional_results=current_models,
        )
        files["congressional/queries.json.gz"] = compressed(query)
        payload["analytical_handoff"] = {
            "review_version": analytical_review["version"], "states": decisions,
            "state_guard_matrix": guard_matrix,
            "Senate_models": analytical_review["Senate_models"],
            "legacy_candidates_preserved": len(analytical_review["legacy_candidates_preserved"]),
        }
        payload["reviewed_races"] = compared
        payload["races"] = legacy_comparison_view(compared)
        payload["scientific_comparison_coverage"] = {
            "reviewed_qualified_senate": sum(
                row["chamber"] == "senate" and row["qualified_comparison"] for row in compared),
            "legacy_reader_qualified_senate": sum(
                row["chamber"] == "senate" and row["qualified_comparison"] for row in payload["races"]),
            "reviewed_qualified_house_states": sum(row["qualified_comparison"] for row in states),
        }
        if boundaries is not None:
            payload["scientific_comparison_coverage"]["reviewed_qualified_house_districts"] = sum(
                row["chamber"] == "house" and row["qualified_comparison"] for row in compared)
    senate = (estimates or {}).get("senate_legacy_handoff")
    if senate is not None:
        payload["senate_partial_scenarios"] = {
            "contract": senate["result"]["contract"], "summary": senate["result"]["summary"],
            "current_other_writeins_unknown": True, "strict_legacy_models_refreshed": 0,
            "empirical_senate_models_added": 0,
        }
    files["congressional/results.json.gz"] = compressed(payload)
    decoded = encoded(payload)
    descriptor = {"contract": CONTRACT, "path": "congressional/results.json.gz",
                  **pin(files["congressional/results.json.gz"]), "compression": "gzip",
                  "media_type": "application/json", "decoded_bytes": len(decoded),
                  "decoded_sha256": pin(decoded)["sha256"], "summary": payload["summary"],
                  "downloads": {name: pin(body) for name, body in files.items()}}
    return files, descriptor
