"""California semi-official canvass: separate ballot and candidate queries."""

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
import re
from zoneinfo import ZoneInfo

from scripts.participation_intake.contract import pin
from scripts.results_turnout_history import CA_COUNTIES, archive_link


INDEX = "https://media.sos.ca.gov/"
URLS = {kind: f"{INDEX}media/{kind}26GG.txt" for kind in "CRSV"}
ELECTION = "2026-11-03"
TURNOUT = "CA-2026-media-turnout"
HOUSE = "CA-2026-media-house"
FEEDS = (TURNOUT, HOUSE)
TURNOUT_CSV = "participation-ca-2026-media-turnout.csv"
HOUSE_CSV = "congressional-ca-2026-media-house.csv"
MAX_BYTES = 2_000_000
HOUSE_CODE = re.compile(r"110000(\d{2})0000")
REPORT_TYPES = {"", "R", "F", "U"}


def integer(raw):
    if not re.fullmatch(r"[0-9]{1,8}", raw):
        raise ValueError("Malformed California media integer")
    return int(raw)


def clock(raw, pattern):
    return datetime.strptime(raw, pattern).isoformat()


def frames(body, kinds, *, allow_trailing=False):
    if not 0 < len(body) <= MAX_BYTES:
        raise ValueError("Unexpected California media file size")
    lines = iter(body.decode("cp1252").splitlines())
    output = []
    previous_clock = None
    for kind in kinds:
        opening = next(lines, "")
        begin = opening[1:-1].split("|")
        if (not opening.startswith("[") or not opening.endswith("]")
                or len(begin) != 5 or begin[:3] != ["B", "CAS", "1"]
                or not re.fullmatch(r"\d{8}\|\d{7}", "|".join(begin[3:]))):
            raise ValueError("Invalid California transmission opening")
        start = clock(begin[3] + begin[4][:-1], "%Y%m%d%H%M%S")
        if previous_clock is not None and start < previous_clock:
            raise ValueError("California transmission clocks disagree")
        records = []
        for line in lines:
            match = re.fullmatch(r"\[([^\[\]]*)\]", line)
            if not match:
                raise ValueError("Invalid California media record delimiters")
            fields = match[1].split("|")
            if fields[1:3] != ["CAS", str(len(records) + 2)]:
                raise ValueError("Incomplete California transmission sequence")
            if fields[0] == "E":
                if len(fields) != 5 or not re.fullmatch(r"\d{8}\|\d{7}", "|".join(fields[3:])):
                    raise ValueError("Invalid California transmission closing")
                end = clock(fields[3] + fields[4][:-1], "%Y%m%d%H%M%S")
                if not records or end < start:
                    raise ValueError("Incomplete California transmission")
                output.append((start, end, records))
                previous_clock = start
                break
            if fields[0] != kind:
                raise ValueError("Unexpected California media message type")
            records.append(fields[3:])
        else:
            raise ValueError("Missing California transmission closing")
    if not allow_trailing and next(lines, None) is not None:
        raise ValueError("Unexpected extra California transmission")
    return output


def parse(kind, body, *, turnout_only=False):
    if kind == "S":
        _, _, rows = frames(body, "S")[0]
        if rows != [[f"{i:02}", name] for i, name in enumerate([*CA_COUNTIES, "State of California"], 1)]:
            raise ValueError("California media county roster changed")
        return rows
    if kind == "R":
        _, _, rows = frames(body, "R")[0]
        result = {}
        for code, label, stage in rows:
            if match := HOUSE_CODE.fullmatch(code):
                if code in result or stage != "GG" or label != f"United States Representative District {int(match[1])}":
                    raise ValueError("California House office, stage or identity changed")
                result[code] = label
        if set(result) != {f"110000{i:02}0000" for i in range(1, 53)}:
            raise ValueError("Incomplete California House seat roster")
        return dict(sorted(result.items()))
    if kind == "C":
        _, _, rows = frames(body, "C")[0]
        result = defaultdict(dict)
        for code, *fields in rows:
            if not HOUSE_CODE.fullmatch(code):
                continue
            if len(fields) != 8 or not re.fullmatch(r"\d{1,5}", fields[0]) or not fields[6].strip():
                raise ValueError("Malformed California House candidate")
            native, prefix, last, first, suffix, party, name, extra = fields
            if native in result[code]:
                raise ValueError("Duplicate California House candidate")
            result[code][native] = {"candidate_name": name, "native_party_code": party, "name_parts": [
                prefix, last, first, suffix], "candidate_extra_literal": extra}
        return dict(sorted(result.items()))
    if kind != "V":
        raise ValueError("Unknown California media file")
    try:
        (start, turnout_end, a), (vote_start, end, v) = frames(body, "AV")
        if start < ELECTION:
            raise ValueError("California media transmission predates the election")
        if turnout_only and (vote_start, end) != (start, turnout_end):
            return {"edition": start, "end": turnout_end, "turnout": a, "house": []}
    except ValueError:
        if not turnout_only:
            raise
        # A is a self-contained numbered transmission; V is not a ballot-count control.
        (start, end, a), = frames(body, "A", allow_trailing=True)
        if start < ELECTION:
            raise ValueError("California turnout transmission predates the election")
        vote_start, v = start, []
    return {"edition": vote_start, "end": end, "turnout": a,
            "house": [row for row in v if HOUSE_CODE.fullmatch(row[0])]}


def turnout_rows(data):
    rows = {}
    for code, status, report, correction, reported, expected, precinct_pct, ballots, registered, pct, first, last in data["turnout"]:
        county = integer(code)
        if not 1 <= county <= 59 or county in rows or status not in REPORT_TYPES:
            raise ValueError("Invalid or duplicate California county reporting identity")
        n, d = (integer(ballots) if ballots else None), integer(registered)
        known, all_units = (integer(reported) if reported else None), integer(expected)
        if (not d or (n is None) != (pct == "") or n is not None and n > d
                or known is not None and known > all_units):
            raise ValueError("Incompatible California county turnout fields")
        if pct and (not re.fullmatch(r"\d{1,3}(?:\.\d)?", pct)
                    or abs(Decimal(n) * 100 / Decimal(d) - Decimal(pct)) > Decimal("0.05")):
            raise ValueError("California turnout percentage does not reconcile")
        if bool(first) != bool(last) or (last and not ELECTION <= clock(first, "%Y%m%d%H%M")
                                       <= clock(last, "%Y%m%d%H%M") <= data["end"]):
            raise ValueError("Invalid California county reporting clocks")
        rows[county] = {"county_code": county, "county": CA_COUNTIES[county - 1] if county < 59 else "State of California",
                        "geography_level": "state" if county == 59 else "county",
                        "reported_ballots_cast": n, "reported_registered_voters": d,
                        "printed_registration_fraction_pct": pct, "native_report_type": status,
                        "precincts_reporting": known, "total_precincts": all_units,
                        "native_precinct_percentage": precinct_pct, "native_report_number": report,
                        "native_correction_number": correction, "native_first_report": first, "native_last_report": last}
    if set(rows) != set(range(1, 60)):
        raise ValueError("Incomplete California county inventory")
    for field in ("reported_ballots_cast", "reported_registered_voters", "precincts_reporting", "total_precincts"):
        children = [rows[n][field] for n in range(1, 59)]
        total = rows[59][field]
        if all(value is not None for value in children) and (total is None or sum(children) != total):
            raise ValueError(f"California county-to-state control differs: {field}")
    return [rows[n] for n in sorted(rows)]


def house_rows(data, offices, candidates):
    if set(offices) != set(candidates):
        raise ValueError("California House candidate and contest inventories differ")
    races = defaultdict(dict)
    for contest, county, reported, expected, status, *fields in data["house"]:
        geography = integer(county)
        if (contest not in offices or not 1 <= geography <= 59 or geography in races[contest]
                or status not in REPORT_TYPES or len(fields) % 4
                or reported and integer(reported) > integer(expected)):
            raise ValueError("Invalid California House return frame")
        counts = {}
        for native, votes, unit_pct, share_pct in zip(*(iter(fields),) * 4, strict=True):
            if native not in candidates[contest] or native in counts:
                raise ValueError("Unknown or duplicate California House return candidate")
            counts[native] = (integer(votes) if votes else None, unit_pct, share_pct)
        races[contest][geography] = (reported, expected, status, counts)
    if set(races) != set(offices):
        raise ValueError("California House return inventory differs from contest inventory")
    for contest, frames_by_county in sorted(races.items()):
        if 59 not in frames_by_county or len(frames_by_county) < 2:
            raise ValueError("California House return missing parent or county records")
        statewide = frames_by_county[59][3]
        children = Counter()
        complete = set(statewide) == set(candidates[contest])
        for geography, (_, _, _, counts) in frames_by_county.items():
            complete &= set(counts) == set(statewide) and all(t[0] is not None for t in counts.values())
            if geography != 59:
                children.update({native: v[0] for native, v in counts.items() if v[0] is not None})
        reconciled = complete and dict(children) == {native: v[0] for native, v in statewide.items()}
        for geography, (reported, expected, status, counts) in sorted(frames_by_county.items()):
            for native, identity in sorted(candidates[contest].items()):
                votes, unit_pct, share_pct = counts.get(native, (None, None, None))
                yield {"district": "CA-" + HOUSE_CODE.fullmatch(contest)[1], "native_contest": contest,
                       "native_office": offices[contest], "county_code": geography, "candidate_id": native,
                       **identity, "votes": votes, "native_candidate_units_pct": unit_pct,
                       "native_candidate_share_pct": share_pct, "native_report_type": status,
                       "precincts_reporting": reported, "total_precincts": expected,
                       "listed_vote_counts_reconcile": reconciled,
                       "exhaustive_write_in_universe_verified": False}


def collect(collector, feed):
    if feed not in FEEDS:
        raise ValueError("Unregistered California media feed")
    kinds = "SV" if feed == TURNOUT else "RCV"
    prior = (collector.prior.get(feed) or {}).get("data") or {}

    def collect_reports(index):
        if b"November 3, 2026, California General Election Results" not in index:
            raise ValueError("California media election identity changed")
        reports = {}
        for kind in kinds:
            url = URLS[kind]
            if not archive_link(index, INDEX, re.escape(url)):
                raise ValueError("California media report is not linked: " + kind)
            body, _ = collector.acquire(url)
            source = {"url": url, **pin(body)}
            previous = prior.get("reports", {}).get(kind)
            reports[kind] = previous if previous and previous["source"] == source else {
                "source": source, "facts": parse(kind, body, turnout_only=feed == TURNOUT)}
        data = reports["V"]["facts"]
        end = datetime.fromisoformat(data["end"]).replace(tzinfo=ZoneInfo("America/Los_Angeles"))
        if end > collector.observation_time():
            raise ValueError("California media transmission is future-dated")
        if feed == TURNOUT:
            turnout_rows(data)
        else:
            list(house_rows(data, reports["R"]["facts"], reports["C"]["facts"]))
        return {"date": data["edition"], "reports": reports, "participation_observation_qualified": False}

    return collector.capture(feed, INDEX, collect_reports, equivalent=lambda old, new: old == new,
                             shared_acquisition=True)


def exports(entries):
    tables = []
    for feed, kinds in zip(FEEDS, ("SV", "RCV"), strict=True):
        entry = entries.get(feed) or {}
        data = entry.get("data")
        tables.append([])
        if data is None:
            continue
        reports = data["reports"]
        if (set(reports) != set(kinds) or entry["status"] not in ("reported", "retained_after_failure")
                or any(reports[kind]["source"]["url"] != URLS[kind] for kind in kinds)):
            raise ValueError("Unexpected California media provenance")
        results = reports["V"]["facts"]
        rows = (turnout_rows(results) if feed == TURNOUT
                else house_rows(results, reports["R"]["facts"], reports["C"]["facts"]))
        provenance = {"election_date": ELECTION, "state_code": "CA", "source_status": entry["status"],
                      "media_edition": data["date"], "media_clock_timezone": "America/Los_Angeles",
                      "reporting_stage": "semi_official_canvass",
                      **{f"{kind.lower()}_source_sha256": reports[kind]["source"]["sha256"] for kind in kinds},
                      **{f"{kind.lower()}_source_url": URLS[kind] for kind in kinds}}
        tables[-1].extend({**provenance, **row} for row in rows)
    return tuple(tables)
