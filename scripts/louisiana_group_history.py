"""Collect and replay Louisiana's official post-election group history."""

import argparse
import copy
import csv
from datetime import timedelta, timezone
from functools import partial
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scripts.native_tabular import xls, xlsx
from scripts.participation_intake.contract import IntakeError, federal_general, pin
from scripts.results_native_louisiana import (
    ELECTION_DATES_URL, FIELDS, PARISH_INDEX_URL, STATE_INDEX_URL,
    _object, _rows, _sum_vectors, _validate_vector, _vector,
)


INDEXES = {"statewide": (STATE_INDEX_URL, "sta"), "parish": (PARISH_INDEX_URL, "par")}
FEEDS = {f"LA-{year}-general-election-group-history": year for year in range(1998, 2025, 2)}
CSV = "participation-la-historical-post-election-groups.csv"
PRECINCT_FEEDS = {f"LA-{year}-general-election-native-precinct-counts": year for year in range(1998, 2025, 2)}
PRECINCT_CSV = "participation-la-historical-native-precinct-counts.csv"
MAX_BYTES = 16_000_000


class _Catalog(HTMLParser):
    def __init__(self, base, body):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.hidden = {}
        self.years = set()
        self.selected = set()
        self.in_year = False
        self.links = set()
        self.feed(body.decode("utf-8", errors="strict"))
        self.close()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "select":
            self.in_year = a.get("name") == "cboYear"
        elif tag == "option" and self.in_year:
            if re.fullmatch(r"[0-9]{4}", a.get("value") or ""):
                self.years.add(a["value"])
                if "selected" in a:
                    self.selected.add(a["value"])
        elif tag == "input" and a.get("type") == "hidden" and a.get("name"):
            if a["name"] in self.hidden:
                raise ValueError("Duplicate Louisiana catalog form field")
            self.hidden[a["name"]] = a.get("value") or ""
        elif tag == "a" and a.get("href"):
            self.links.add(urljoin(self.base, a["href"]))

    def handle_endtag(self, tag):
        if tag == "select":
            self.in_year = False

    def selection(self, year):
        keys = {"__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"}
        if str(year) not in self.years or not keys <= self.hidden.keys():
            raise ValueError(f"Louisiana catalog does not declare the {year} year form")
        return urlencode({
            **{key: self.hidden[key] for key in sorted(keys)},
            "cboYear": str(year), "__EVENTTARGET": "cboYear", "__EVENTARGUMENT": "",
        }).encode("ascii")

    def workbook(self, scope, election):
        if self.selected != {str(election.year)}:
            raise ValueError(f"Louisiana catalog did not select {election.year}")
        directory = f"https://electionstatistics.sos.la.gov/Data/Post_Election_Statistics/{scope}/"
        stem = f"{election:%Y_%m%d}_{INDEXES[scope][1]}"
        candidates = sorted(self.links & {directory + stem + suffix for suffix in (".xls", ".xlsx")})
        if not candidates and directory + stem + ".txt" in self.links:
            return directory + stem + ".txt"
        if len(candidates) > 1:
            raise ValueError(f"Ambiguous Louisiana workbook: {scope} {election}")
        return candidates[0] if candidates else None


def federal_events(body, start, end):
    rows = json.loads(body, object_pairs_hook=_object)["Dates"]["Date"]
    for year in range(start + start % 2, end + 1, 2):
        election = federal_general(year)
        records = [row for row in rows if row.get("ElectionDate") == election.strftime("%m/%d/%Y")]
        if len(records) > 1:
            raise ValueError(f"Ambiguous Louisiana election inventory for {election}")
        row = records[0] if records else None
        admitted = (
            row and row.get("ResultsOfficial") == row.get("PostElectionStatsAvailable") == "1"
            and re.fullmatch(r"[0-9]+", str(row.get("PKElectionID")))
        )
        yield election, row, bool(admitted)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from scripts.participation_intake.engine import CHALLENGE_REDIRECT_HOSTS

        if urlsplit(newurl).hostname in CHALLENGE_REDIRECT_HOSTS:
            raise IntakeError("source_stopped", "Louisiana year catalog redirected to a challenge")
        return None


def collect(directory, start, end, *, stopped):
    """Fetch only the official catalog's exact linked workbook pair per event."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    opener = build_opener(_NoRedirect())
    inventory = {"sources": {}, "events": {}, "stops": {}, "stopped_hosts": []}
    stopped_urls = set(stopped["urls"])
    stopped_prefixes = tuple(stopped["prefixes"])
    stopped_hosts = set(stopped["hosts"])

    def fetch(name, url, data=None, year=None):
        host = urlsplit(url).hostname
        if (url in stopped_urls or url in inventory["stops"] or url.startswith(stopped_prefixes)
                or host in stopped_hosts or host in inventory["stopped_hosts"]):
            raise ValueError(f"Louisiana source already stopped: {url}")
        try:
            with opener.open(Request(url, data=data), timeout=30) as response:
                body = response.read(64 * 1024 * 1024 + 1)
                if len(body) > 64 * 1024 * 1024:
                    raise ValueError("Louisiana source exceeds size limit")
                if b"<title>Just a moment" in body[:8192] or response.headers.get("cf-mitigated") == "challenge":
                    inventory["stops"][url] = "challenge"
                    raise ValueError("Louisiana source presented an access challenge")
        except OSError as exc:
            if getattr(exc, "code", None) in (401, 403, 429):
                inventory["stops"][url] = exc.code
                if exc.code == 429:
                    inventory["stopped_hosts"].append(host)
            raise
        except IntakeError as exc:
            if exc.code == "source_stopped":
                inventory["stops"][url] = "challenge"
            raise
        (directory / name).write_bytes(body)
        inventory["sources"][name] = {
            "url": url, "method": "POST" if data is not None else "GET",
            "year_selection": year, "bytes": len(body), "sha256": sha256(body).hexdigest(),
        }
        return body

    try:
        events = fetch("election-dates.json", ELECTION_DATES_URL)
        catalogs = {
            scope: _Catalog(url, fetch(f"{scope}-catalog.html", url))
            for scope, (url, _) in INDEXES.items()
        }
        for election, record, admitted in federal_events(events, start, end):
            entry = {"official_event": record, "files": {}, "status": "no_official_event_with_statistics"}
            inventory["events"][str(election)] = entry
            if not admitted:
                continue
            errors = {}
            for scope, (url, _) in INDEXES.items():
                try:
                    name = f"{scope}-{election.year}.html"
                    first = catalogs[scope]
                    catalog = first if first.selected == {str(election.year)} else _Catalog(
                        url, fetch(name, url, first.selection(election.year), election.year)
                    )
                    link = catalog.workbook(scope, election)
                    if not link:
                        raise ValueError("Catalog does not list a supported spreadsheet")
                    name = link.rsplit("/", 1)[1]
                    fetch(name, link)
                    entry["files"][scope] = name
                except (OSError, ValueError) as exc:
                    errors[scope] = str(exc)
            entry["status"] = "held" if errors else "workbook_pair_fetched"
            if errors:
                entry["holds"] = errors
    finally:
        (directory / "inventory.json").write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    return inventory


def _layout(table, election, scope):
    rows = _rows(table)
    if rows.get(1, {}).get("A") == "Louisiana Secretary of State Elections Division":
        title_row, date_row, parent_row = 2, 3, 10
        scopes = ("STATE AND Status Active and Inactive",)
        parish_title = "Post Election Statistical Report"
    elif rows.get(1, {}).get("A") == "Louisiana Secretary of State":
        title_row, date_row, parent_row = 3, 5, 11
        scopes = ("<ALL> AND Status Active and Inactive",)
        if scope == "statewide":
            scopes += ("<ALL>",)
        parish_title = "PostElection Statistics"
        if not rows.get(title_row, {}).get("A") and not rows.get(date_row, {}).get("A"):
            # Earlier BIFF reports put the title and date one row higher.
            title_row, date_row = 2, 4
    else:
        raise ValueError("Unrecognized Louisiana workbook publisher heading")
    title = "State Wide Post Election Statistical Report" if scope == "statewide" else parish_title
    expected_dates = {f"Election Date {election:%m/%d/%Y} AND {suffix}" for suffix in scopes}
    if rows.get(title_row, {}).get("A") != title or rows.get(date_row, {}).get("A") not in expected_dates:
        raise ValueError("Louisiana workbook title, event date or registration scope differs")
    group_header = rows[parent_row - 3]
    names = ("REGISTERED VOTERS", "DEMOCRATS", "REPUBLICANS", "OTHER PARTIES")
    if tuple(str(group_header.get(key, "")).strip("- ") for key in "DHLP") != names:
        raise ValueError("Louisiana registration group header differs")
    race_header = rows[parent_row - 2]
    if tuple(race_header.get(key) for key in FIELDS) != ("TOTAL", "WHITE", "BLACK", "OTHER") * 4:
        raise ValueError("Louisiana race header differs")
    return rows, parent_row


def _book(body, suffix):
    if suffix == ".xls":
        return xls(body)
    if suffix == ".xlsx":
        return xlsx(body)
    raise ValueError("Unsupported Louisiana workbook container")


def _group_vector(rows, row, identity):
    vector = _vector(rows, row, row + 1, row + 2, identity)
    return _cross_cells(vector, identity)


def _cross_cells(vector, identity):
    for role in ("registered_voters", "voters_participating"):
        counts = vector[role]
        for race in ("white", "black", "other_race"):
            if counts[race] != sum(counts[party + "_" + race] for party in
                                   ("democrat", "republican", "other_parties")):
                raise ValueError(f"Louisiana {role} party-by-race subtotals differ: {identity}")
    return vector


def statewide_groups(state_book, election):
    state_rows, start = _layout(state_book[0], election, "statewide")
    if state_rows[start - 1].get("B") != "STATE" or state_rows[start].get("B", "").strip() != "STATE":
        raise ValueError("First Louisiana statewide sheet is not the unduplicated statewide frame")
    expected = {f"PAR {number:02}" for number in range(1, 65)}
    statewide = {}
    state = _group_vector(state_rows, start, "STATE")
    for row in sorted(state_rows):
        identity = state_rows[row].get("B")
        if not isinstance(identity, str) or not re.fullmatch(r"PAR [0-9]{2}", identity):
            continue
        if identity in statewide or identity not in expected:
            raise ValueError("Unexpected or duplicate statewide parish control")
        statewide[identity] = _group_vector(state_rows, row, identity)
    if set(statewide) != expected:
        raise ValueError("Statewide parish controls are incomplete")
    return {"STATE": ["Louisiana", state_book[0]["name"], start, state],
            **{key: ["", "", 0, value] for key, value in statewide.items()}}


def parish_groups(parish_book, election, *, precincts=False):
    expected = {f"PAR {number:02}" for number in range(1, 65)}
    parishes = {}
    for table in parish_book:
        rows, row = _layout(table, election, "parish")
        identity = rows.get(row, {}).get("B")
        name = rows.get(row - 1, {}).get("B")
        # The legacy pagination sheet contains only the report header and no observations.
        if (len(parish_book) == 65 and table is parish_book[-1] and not any(
                value not in (None, "") for number, cells in rows.items()
                if number >= row - 1 for value in cells.values())):
            continue
        if identity not in expected or identity in parishes or not isinstance(name, str) or not name.strip():
            raise ValueError("Missing or duplicate Louisiana parish identity")
        vector = _group_vector(rows, row, identity)
        data = [name.strip(), table["name"], row, vector]
        if precincts:
            data.append(precinct_counts(rows, row, identity, vector))
        parishes[identity] = data
    if set(parishes) != expected or len({area[0] for area in parishes.values()}) != len(expected):
        raise ValueError("Louisiana parish workbook coverage or names differ")
    return dict(sorted(parishes.items()))


def precinct_counts(rows, parent_row, parish, parent):
    seen, units, children = set(), [], []
    for row in sorted(rows):
        if row <= parent_row + 1 or rows[row].get("B") != "# VOTING":
            continue
        literal = rows.get(row - 1, {}).get("B")
        identity = literal.strip() if isinstance(literal, str) else ""
        if (not re.fullmatch(r"PAR [0-9]{2} W [A-Z0-9-]+ P [A-Z0-9-]+", identity)
                or not identity.startswith(parish + " ") or identity in seen):
            raise ValueError(f"Unknown or duplicate Louisiana historical precinct identity: {literal!r}")
        seen.add(identity)
        vector = _group_vector(rows, row - 1, identity)
        children.append({"native_vectors": vector})
        units.append([identity, literal, row, vector["voters_participating"]["total"]])
    if not units or any(_sum_vectors(children, role) != parent[role]
                        for role in ("registered_voters", "voters_participating")):
        raise ValueError(f"Historical Louisiana precincts do not sum to parish: {parish}")
    return units


def precinct_rows(election, record, workbooks, sources):
    state, parishes = workbooks["statewide"], workbooks["parish"]
    if set(state) != set(parishes) | {"STATE"} or len(parishes) != 64:
        raise ValueError("Incomplete Louisiana historical precinct control inventory")
    total = state["STATE"][3]["voters_participating"]["total"]
    if sum(area[3]["voters_participating"]["total"] for key, area in state.items() if key != "STATE") != total:
        raise ValueError("Statewide Louisiana precinct count controls do not sum to their total")
    for parish, (name, sheet, parent_row, parent, units) in sorted(parishes.items()):
        printed = parent["voters_participating"]["total"]
        control = state[parish][3]["voters_participating"]["total"]
        if not units or sum(unit[3] for unit in units) != printed:
            raise ValueError(f"Retained Louisiana native precinct counts differ from the parish: {parish}")
        for identity, literal, row, count in units:
            text = sheet == "fixed_width_text"
            yield {
                "election_date": str(election), "native_election_id": record["PKElectionID"],
                "election_cycle": "presidential" if election.year % 4 == 0 else "midterm",
                "native_parish_id": parish, "parish": name, "native_precinct_id": identity,
                "native_precinct_literal": literal, "voters_voting": count,
                "parish_file_voting_control": printed, "statewide_file_parish_voting_control": control,
                "control_status": "parish_and_statewide_counts_agree" if printed == control else
                                  "parish_rows_reconcile_statewide_control_differs",
                "geometry_qualified": "false", "rate_qualified": "false",
                "source_url": sources["parish"]["url"], "source_sha256": sources["parish"]["sha256"],
                "control_url": sources["statewide"]["url"], "control_sha256": sources["statewide"]["sha256"],
                "source_sheet": sheet, "voting_cell": f"line {row} field 1" if text else f"D{row}",
                "parish_control_cell": f"line {parent_row + 1} field 1" if text else f"D{parent_row + 1}",
            }


def reconcile(statewide, parishes):
    state = statewide["STATE"][3]
    if set(statewide) != set(parishes) | {"STATE"} or len(parishes) != 64:
        raise ValueError("Louisiana parish inventories differ")
    for identity, area in parishes.items():
        vector, control = area[3], statewide[identity][3]
        if vector != control:
            changed = [
                f"{group} {role}: {vector[role][group]} vs {control[role][group]}"
                for role in ("registered_voters", "voters_participating")
                for group in FIELDS.values() if vector[role][group] != control[role][group]
            ]
            raise ValueError(f"Louisiana parish workbook differs from statewide control: {identity} "
                             f"({'; '.join(changed)})")
    regions = [{"native_vectors": area[3]} for area in parishes.values()]
    for role in ("registered_voters", "voters_participating"):
        if _sum_vectors(regions, role) != state[role]:
            raise ValueError(f"Louisiana parish {role} does not reconcile to the state")
    return {"STATE": statewide["STATE"], **dict(sorted(parishes.items()))}


def legacy_groups(body, scope, election, *, precincts=False):
    lines = body.decode("ascii").splitlines()
    statewide = scope == "statewide"
    title = (f"STATE WIDE POST ELECTION STATISTICAL REPORT FOR ELECTION OF {election:%m/%d/%Y}"
             if statewide else f"POST ELECTION STATISTICS FOR ELECTION OF {election:%m/%d/%y}")
    title += " * (ACTIVE & INACTIVE)"
    group_header = ("REGISTERED VOTERS", "DEMOCRATS", "REPUBLICANS", "OTHER PARTIES")
    field_header = ["REG", "WHITE", "BLACK", "OTHER"] + ["TOTAL", "WHITE", "BLACK", "OTHER"] * 3
    expected = {f"PAR {number:02}" for number in range(1, 65)}
    data = {}

    def vector(start, identity, registered):
        labels = ("VOTED", "% VOTED") if statewide else ("# VOTING", "% VOTING")
        tail = []
        for line, label in zip(lines[start + 1:start + 3], labels, strict=True):
            line = line.strip()
            if not line.startswith(label + " "):
                raise ValueError(f"Legacy Louisiana voting line differs: {identity}")
            tail.append(line[len(label):].split())
        voting, pct = tail
        if (any(len(items) != len(FIELDS) for items in (registered, voting, pct))
                or any(not re.fullmatch(r"[0-9]+(?:,[0-9]{3})*", n) for n in registered + voting)
                or any(not re.fullmatch(r"[0-9]*\.[0-9]", n) for n in pct)):
            raise ValueError(f"Legacy Louisiana printed group fields differ: {identity}")
        if precincts:
            return {"voters_participating": {"total": int(voting[0].replace(",", ""))}}
        values = {
            "registered_voters": dict(zip(FIELDS.values(), [int(n.replace(",", "")) for n in registered])),
            "voters_participating": dict(zip(FIELDS.values(), [int(n.replace(",", "")) for n in voting])),
            "percent_voting": dict(zip(FIELDS.values(), ["0" + n if n.startswith(".") else n for n in pct])),
        }
        _validate_vector(values, identity, percent_places=1)
        return _cross_cells(values, identity)

    region, parish, seen = None, None, set()
    for i, line in enumerate(lines):
        line = line.strip()
        if line == title:
            label = lines[i + 1].strip()
            if statewide and not re.fullmatch(r"BY\s+PARISH", label):
                if data:
                    break
                raise ValueError("Legacy Louisiana statewide parish report is not first")
            if not statewide and not label.startswith("IN "):
                raise ValueError("Legacy Louisiana parish name is absent")
            if (tuple(part.strip() for part in re.split(r"\*+", lines[i + 2]) if part.strip()) != group_header
                    or lines[i + 4].split() != (["PARISH"] if statewide else []) + field_header):
                raise ValueError("Legacy Louisiana field header differs")
            region = label[3:] if not statewide else "Louisiana"
            parish = None
            continue
        pattern = r"^(STATE|\d{2})\s+(.+)$" if statewide else r"^PAR\s+(\d{2})\s+(.+)$"
        if region and (match := re.fullmatch(pattern, line)):
            ident, values = match.groups()
            if ident != "STATE":
                ident = "PAR " + ident
            if ident in data or (ident not in expected and not (statewide and ident == "STATE")):
                raise ValueError(f"Legacy Louisiana parish identity differs: {ident}")
            data[ident] = [region, "fixed_width_text", i + 1, vector(i, ident, values.split())]
            if not statewide:
                if precincts:
                    data[ident].append([])
                    parish = ident
                region = None
            continue
        if precincts and not statewide and line.startswith("# VOTING"):
            previous = lines[i - 1].strip()
            if re.fullmatch(r"PAR\s+[0-9]{2}\s+.+", previous) and parish is not None and data[parish][2] == i:
                continue
            unit = re.fullmatch(r"(W\s+([A-Z0-9-]+)\s+P\s+([A-Z0-9-]+))\s+(.+)", previous)
            if parish is None or unit is None:
                raise ValueError("Unknown legacy Louisiana historical precinct identity")
            literal, ward, precinct, registered = unit.groups()
            identity = f"{parish} W {ward} P {precinct}"
            if identity in seen:
                raise ValueError(f"Duplicate legacy Louisiana historical precinct identity: {identity}")
            seen.add(identity)
            count = vector(i - 1, identity, registered.split())["voters_participating"]["total"]
            data[parish][4].append([identity, literal, i + 1, count])
    if set(data) != expected | ({"STATE"} if statewide else set()):
        raise ValueError("Legacy Louisiana parish inventory is incomplete")
    return data


def rows(election, record, areas, sources):
    for identity, (name, sheet, row, vector) in areas.items():
        scope = "statewide" if identity == "STATE" else "parish"
        for field, (col, group) in enumerate(FIELDS.items(), 1):
            stock = vector["registered_voters"][group]
            def address(line):
                return f"line {line} field {field}" if sheet == "fixed_width_text" else f"{col}{line}"
            yield {
                "election_date": str(election),
                "election_cycle": "presidential" if election.year % 4 == 0 else "midterm",
                "native_election_id": record["PKElectionID"],
                "native_id": identity, "area_name": name, "group": group,
                "voters_voting": vector["voters_participating"][group],
                "post_election_active_inactive_registered": stock,
                "native_percent_voting": vector["percent_voting"][group],
                "observed_percent_voting": vector["percent_voting"][group] if stock else "",
                "analytical_rate_promoted": "false",
                "source_url": sources[scope]["url"], "source_sha256": sources[scope]["sha256"],
                "source_sheet": sheet, "registered_cell": address(row),
                "voting_cell": address(row + 1), "percent_cell": address(row + 2),
            }


def catalog_facts(body, scope, election):
    url = INDEXES[scope][0]
    link = _Catalog(url, body).workbook(scope, election)
    if not link:
        raise IntakeError("not_reported", "The selected year catalog has no supported spreadsheet")
    return {"year": election.year, "workbook_url": link}


def event_facts(body, year):
    _, record, admitted = next(federal_events(body, year, year))
    if not admitted:
        raise IntakeError("not_reported", "No official November event with published post-election statistics")
    return record


def workbook_facts(body, scope, election, url, *, precincts=False):
    if Path(url).suffix == ".txt":
        return legacy_groups(body, scope, election, precincts=precincts)
    query = statewide_groups if scope == "statewide" else partial(parish_groups, precincts=precincts)
    return query(_book(body, Path(url).suffix), election)


def acquire_catalog_form(collector, url, selection):
    from scripts.results_intake import CHALLENGES
    from scripts.participation_intake.engine import Store

    if url not in (STATE_INDEX_URL, PARISH_INDEX_URL):
        raise ValueError("Unregistered Louisiana catalog form")
    collector.guard(url)
    if collector.offline:
        raise IntakeError("offline", "Use the retained Louisiana catalog original for replay")
    cache_key = (url, selection)
    if (cached := collector.bodies.get(cache_key)) is not None:
        return cached
    try:
        request = Request(url, data=selection)
        with build_opener(_NoRedirect()).open(request, timeout=30) as response:
            limit = 1_000_000
            body = response.read(limit + 1)
            if (response.headers.get("cf-mitigated") == "challenge"
                    or any(re.search(pattern, body.decode("utf-8", errors="replace"), re.I)
                           for pattern in [*CHALLENGES, r"<title>Just a moment"])):
                raise IntakeError("source_stopped", "Louisiana year catalog presented a challenge")
            if response.status != 200 or len(body) > limit:
                raise IntakeError("source_access", "Incomplete Louisiana year catalog response")
    except (HTTPError, URLError, TimeoutError) as original:
        try:
            raise IntakeError("source_access", "Louisiana year catalog transport failed") from original
        except IntakeError as error:
            collector.remember_stop(url, error)
            raise
    except IntakeError as error:
        collector.remember_stop(url, error)
        raise
    if not hasattr(collector.context, "store"):
        collector.context.store = Store(collector.work / "cache")
    collector.context.store.object(body)
    collector.bodies[cache_key] = body
    return body


def collect_year(collector, feed, *, reuse_checked_week=False):
    from scripts.results_intake import source_error

    precincts = feed in PRECINCT_FEEDS
    year = (PRECINCT_FEEDS if precincts else FEEDS)[feed]
    election = federal_general(year)
    old = collector.prior.get(feed) or {}
    day = collector.now.astimezone(timezone.utc).date()
    week = (day - timedelta(days=day.weekday())).isoformat()
    if reuse_checked_week and not collector.offline and old.get("archive_check_week_utc") == week:
        return old
    stage, url = "election_inventory", ELECTION_DATES_URL
    try:
        inventory, _ = collector.acquire(url)
        record = event_facts(inventory, year)
        sources = {"event": {"url": url, **pin(inventory)}}
        catalogs, workbooks = {}, {}
        for scope, (url, _) in INDEXES.items():
            stage = scope + "_catalog"
            body, _ = collector.acquire(url)
            default = _Catalog(url, body)
            if default.selected != {str(year)}:
                body = acquire_catalog_form(collector, url, default.selection(year))
            catalog = catalogs[scope] = catalog_facts(body, scope, election)
            sources[scope + "_catalog"] = {"url": url, **pin(body)}
            stage, url = scope + "_workbook", catalog["workbook_url"]
            body, _ = collector.acquire(url)
            if len(body) > MAX_BYTES:
                raise ValueError("Louisiana workbook exceeds the size limit")
            sources[scope] = {"url": url, **pin(body)}
            workbooks[scope] = workbook_facts(body, scope, election, url, **({"precincts": True} if precincts else {}))
        stage = "reconciliation"
        if precincts:
            for _ in precinct_rows(election, record, workbooks, sources):
                pass
        else:
            reconcile(workbooks["statewide"], workbooks["parish"])
        data = {"record": record, "sources": sources, "catalogs": catalogs, "workbooks": workbooks,
                "participation_observation_qualified": False}
        prior = old.get("data") or {}
        if (all(prior.get(key) == data[key] for key in ("record", "catalogs", "workbooks"))
                and all(prior["sources"][scope] == sources[scope] for scope in INDEXES)):
            # ASP.NET form and inventory bytes can change independently of the selected facts.
            entry = copy.deepcopy(old)
        else:
            entry = {"data": data, "source": sources["statewide"], "first_observed_at": collector.now.isoformat()}
        entry.update(status="reported", error=None, error_detail=None, error_stage=None)
    except Exception as exc:
        code = source_error(exc)
        entry = copy.deepcopy(old) if old.get("data") is not None else {
            "data": None, "source": None, "first_observed_at": None,
        }
        entry.update(status="retained_after_failure" if entry["data"] is not None else code,
                     error=code, error_stage=stage,
                     error_detail=str(exc) if isinstance(exc, (ValueError, IntakeError)) else None)
    entry.update(attempted_source_url=url)
    if not collector.offline:
        entry["archive_check_week_utc"] = week
    collector.attempts.append({"id": feed, "url": url, "status": entry["status"]})
    return entry


def exports(entries):
    for feed, year in FEEDS.items():
        entry = entries.get(feed) or {}
        data = entry.get("data")
        if data is None:
            continue
        if entry["status"] not in {"reported", "retained_after_failure"}:
            raise ValueError("Louisiana retained history has an invalid source status")
        election = federal_general(year)
        areas = reconcile(data["workbooks"]["statewide"], data["workbooks"]["parish"])
        for row in rows(election, data["record"], areas, data["sources"]):
            yield {**row, "source_status": entry["status"],
                   "checked_week_utc": entry.get("archive_check_week_utc")}


def precinct_exports(entries):
    for feed, year in PRECINCT_FEEDS.items():
        entry = entries.get(feed) or {}
        data = entry.get("data")
        if data is None:
            continue
        if entry["status"] not in {"reported", "retained_after_failure"}:
            raise ValueError("Louisiana retained precinct history has an invalid source status")
        for row in precinct_rows(federal_general(year), data["record"], data["workbooks"], data["sources"]):
            yield {**row, "source_status": entry["status"],
                   "checked_week_utc": entry.get("archive_check_week_utc")}


def original_reports(entries):
    for feed, year in (FEEDS | PRECINCT_FEEDS).items():
        if (data := (entries.get(feed) or {}).get("data")) is None:
            continue
        election = federal_general(year)
        sources = data["sources"]
        event = sources["event"]
        yield (feed + "-event", event, ".json", MAX_BYTES, event["url"] == ELECTION_DATES_URL,
               partial(event_facts, year=year), data["record"])
        for scope, (url, _) in INDEXES.items():
            catalog, source = sources[scope + "_catalog"], sources[scope]
            link = data["catalogs"][scope]["workbook_url"]
            suffix = Path(link).suffix
            yield (feed + "-" + scope + "-catalog", catalog, ".html", 1_000_000, catalog["url"] == url,
                   partial(catalog_facts, scope=scope, election=election), data["catalogs"][scope])
            yield (feed + "-" + scope, source, suffix, MAX_BYTES,
                   source["url"] == link and suffix in (".xls", ".xlsx", ".txt"),
                   partial(workbook_facts, scope=scope, election=election, url=link,
                           precincts=feed in PRECINCT_FEEDS), data["workbooks"][scope])


def replay(directory, output, *, precincts=False):
    directory = Path(directory)
    inventory = json.loads((directory / "inventory.json").read_text(), object_pairs_hook=_object)

    def verified(name):
        if Path(name).name != name:
            raise ValueError("Unexpected Louisiana original member name")
        body = (directory / name).read_bytes()
        source = inventory["sources"][name]
        if len(body) != source["bytes"] or sha256(body).hexdigest() != source["sha256"]:
            raise ValueError(f"Louisiana original bytes differ: {name}")
        return body, source

    events, event_source = verified("election-dates.json")
    if event_source["url"] != ELECTION_DATES_URL:
        raise ValueError("Louisiana election inventory provenance differs")
    status = {}
    observations = []
    for election, record, admitted in federal_events(events, 1998, 9998):
        entry = inventory["events"].get(str(election))
        if not entry:
            continue
        status[str(election)] = entry["status"]
        if entry["status"] != "workbook_pair_fetched":
            continue
        if not admitted or record != entry["official_event"]:
            raise ValueError("Louisiana selected event differs from official inventory")
        books = {}
        sources = {}
        for scope, (url, _) in INDEXES.items():
            name = entry["files"][scope]
            body, source = verified(name)
            catalog_name = f"{scope}-{election.year}.html"
            if catalog_name not in inventory["sources"]:
                catalog_name = f"{scope}-catalog.html"
            catalog, catalog_source = verified(catalog_name)
            if catalog_source["url"] != url or _Catalog(url, catalog).workbook(scope, election) != source["url"]:
                raise ValueError("Louisiana workbook is not declared by the official year catalog")
            sources[scope] = source
            books[scope] = body
        try:
            parsed = {scope: workbook_facts(books[scope], scope, election, sources[scope]["url"], precincts=precincts)
                      for scope in INDEXES}
            result = (list(precinct_rows(election, record, parsed, sources)) if precincts else
                      list(rows(election, record, reconcile(parsed["statewide"], parsed["parish"]), sources)))
        except ValueError as exc:
            status[str(election)] = f"workbook_validation_held: {exc}"
            continue
        status[str(election)] = "parish_native_counts_reconciled" if precincts else "count_vectors_reconciled"
        observations.extend(result)
    if not observations:
        raise ValueError("No compatible Louisiana historical election observations")
    with Path(output).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=observations[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(observations)
    return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--start", type=int, default=1998)
    parser.add_argument("--end", type=int, default=2024)
    parser.add_argument("--source-stops", type=Path)
    parser.add_argument("--replay", type=Path, metavar="OUTPUT_CSV")
    parser.add_argument("--precincts", action="store_true", help="Replay native precinct counts for workbook years")
    args = parser.parse_args()
    if args.replay:
        print(json.dumps(replay(args.directory, args.replay, precincts=args.precincts), indent=2))
    else:
        if not args.source_stops:
            parser.error("--source-stops is required for collection")
        result = collect(args.directory, args.start, args.end, stopped=json.loads(args.source_stops.read_text()))
        for election, entry in result["events"].items():
            print(election, entry["status"], entry.get("holds", ""))
