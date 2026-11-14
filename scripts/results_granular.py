"""Refresh source-native local counts without changing their geographic qualifications."""

import copy
import csv
import gzip
import io
import json
from pathlib import PurePosixPath
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit
import zipfile

from scripts.current import reporting_counts
from scripts.participation_intake.contract import count, digest, encoded, observation_id, pin, validate


MN_URL = "https://electionresultsfiles.sos.mn.gov/20261103/pctstats.txt"
CT_ROOT = "https://ctemspublic.tgstg.net/ng-app/data/"
CT_VERSION = CT_ROOT + "election/108/Version.json"
CT_ELECTIONS = CT_ROOT + "Elections.json"
MN_FIELDS = ("state", "county_id", "precinct_id", "precinct_name", "has_reported_statistics",
             "registered_7am", "registered_election_day", "roster_signatures",
             "regular_military_overseas_absentee", "federal_only_absentee",
             "president_only_absentee", "total_number_voted")
PRIVATE_HEADERS = re.compile(
    r"voter.?id|voter.?name|first.?name|last.?name|ncid|registration.?number|date.?of.?birth|birth.?date|"
    r"residen(?:ce|tial).?address|street.?address|email|phone|social.?security", re.I)
NOT_RESULTS = re.compile(
    r"primary|runoff|special|sample.?ballot|voter.?guide|voters.?pamphlet|cvr|cast.?vote.?record|"
    r"voter.?file|voter.?list|registration.?extract|poll.?book|candidate.?filing", re.I)


def selected_records(baseline, state):
    index = json.loads(baseline["index.json"])
    item = index["states"][state]
    shard = json.loads(gzip.decompress(baseline[item["file"]]))
    selected = {identity for frame in shard.get("views", {}).values()
                for partition in ("counties", "precincts", "nongeographic")
                for identity in frame.get(partition, [])}
    return [row for row in shard["records"] if row["id"] in selected]


def change(template, value, native, *, registered=None, clock=None,
           reported=None, total=None, rate_compatible=False):
    return {"id": template["id"], "value": value, "native": native,
            "registered": registered, "clock": clock, "reported_units": reported,
            "total_units": total, "rate_compatible": rate_compatible}


def north_carolina(body, templates):
    rows, audit = reporting_counts(json.loads(body))
    by_id = {row["county_id"]: row for row in rows}
    updates = []
    for template in templates:
        native = template.get("view", {}).get("native_record", {}).get("query", {})
        identity = str(native.get("county_id", ""))
        if not identity:
            continue
        row = by_id.get(identity)
        expected = "STATEWIDE" if identity == "0" else template["geography"]["name"]
        if row is None or row["county"] != expected:
            raise ValueError("Changed NC native county identity/name")
        updates.append(change(template, row["ballots_cast"], row,
            registered=row["registered_voters"], clock=row["source_update_label"],
            reported=row["precincts_reporting"], total=row["precincts_total"],
            rate_compatible=row["reported_ballot_fraction_pct"] is not None))
    return {"updates": updates, "complete_native_query": rows, "reconciliation": audit,
            "geographic_joins_changed": False}


def minnesota(body, templates):
    raw = list(csv.reader(io.StringIO(body.decode("utf-8-sig")), delimiter=";"))
    units = {}
    for values in raw:
        if (len(values) != len(MN_FIELDS) or values[0] != "MN"
                or values[4] not in ("0", "1") or not values[1] or not values[2]):
            raise ValueError("Changed Minnesota native statistical schema")
        row = dict(zip(MN_FIELDS, values[:5] + [count(value) for value in values[5:]]))
        if any(value is None for value in row.values()):
            raise ValueError("Missing native Minnesota count is not zero")
        key = row["county_id"], row["precinct_id"]
        if key in units:
            raise ValueError("Duplicate Minnesota county-scoped precinct")
        units[key] = row
    expected = {}
    for template in templates:
        native = template.get("view", {}).get("native_record", {})
        if "precinct_id" in native:
            expected[native["county_id"], native["precinct_id"]] = native["precinct_name"]
    if not expected or set(units) != set(expected):
        raise ValueError("Minnesota source/reference inventory changed; no inferred geographic join")
    if any(row["precinct_name"] != expected[key] for key, row in units.items()):
        raise ValueError("Minnesota native reporting-unit name changed")
    parents = {}
    for row in units.values():
        parent = parents.setdefault(row["county_id"], [])
        parent.append(row)
    queries, updates = [], []
    for template in templates:
        native = template.get("view", {}).get("native_record", {})
        if "precinct_id" in native:
            row = units[native["county_id"], native["precinct_id"]]
            value = row["total_number_voted"] if row["has_reported_statistics"] == "1" else None
            updates.append(change(template, value, row))
        elif native.get("native_county_id") in parents:
            all_rows = parents[native["native_county_id"]]
            reported = [row for row in all_rows if row["has_reported_statistics"] == "1"]
            complete = len(reported) == len(all_rows)
            subtotal = sum(row["total_number_voted"] for row in reported)
            registered = sum(row["registered_7am"] + row["registered_election_day"] for row in reported)
            conflicts = sum(row["total_number_voted"] != sum(row[key] for key in MN_FIELDS[7:11])
                            for row in reported)
            excesses = sum(row["total_number_voted"] > row["registered_7am"] + row["registered_election_day"]
                           for row in reported)
            query = {"native_county_id": native["native_county_id"],
                     "county": template["geography"]["name"],
                     "reported_statistics": len(reported), "reference_precincts": len(all_rows),
                     "reported_subtotal": subtotal, "all_statistics_reported": complete,
                     "native_component_conflicts": conflicts, "native_electorate_excesses": excesses,
                     "total_number_voted": subtotal if complete else None,
                     "derived_7am_plus_election_day_registration": registered if complete else None}
            queries.append(query)
            updates.append(change(template, query["total_number_voted"], query,
                registered=query["derived_7am_plus_election_day_registration"],
                reported=len(reported), total=len(all_rows),
                rate_compatible=complete and not conflicts and not excesses and registered > 0))
    return {"updates": updates, "complete_native_query": list(units.values()),
            "county_queries": queries, "geographic_joins_changed": False,
            "source_clock": None, "clock_qualification": "No count clock in native statistical TXT"}


def connecticut(turnout, election, elections, status, templates):
    event = [row for row in elections if row.get("ID") == "108"]
    if (len(event) != 1 or event[0].get("Name") != "11/03/2026 -- November 2026 State Election"
            or election.get("ID") != "108" or set(turnout) != {str(i) for i in range(1, 171)}
            or set(status) != {str(i) for i in range(1, 170)}
            or turnout["170"].get("NM") != "Total"):
        raise ValueError("Changed Connecticut election or complete native town inventory")
    fields = ("EV", "VV", "ABR", "ABC", "EBR", "EBC", "EDR", "EDC")
    for field in fields:
        total = count(turnout["170"].get(field))
        values = [count(turnout[str(i)].get(field)) for i in range(1, 170)]
        if total is None or any(value is None for value in values) or sum(values) != total:
            raise ValueError("Connecticut complete town/native Total discrepancy")
    if (count(election.get("BC")) != count(turnout["170"]["VV"])
            or count(election.get("RV")) != count(turnout["170"]["EV"])):
        raise ValueError("Connecticut separate election parent disagrees")
    updates = []
    for template in templates:
        identity = template.get("view", {}).get("source_town_id")
        if not identity:
            continue
        native = turnout.get(identity)
        if native is None or native.get("NM") != template["geography"]["name"]:
            raise ValueError("Changed literal Connecticut town identity")
        updates.append(change(template, count(native["VV"]),
            {**native, "source_town_id": identity, "town_status": status[identity]}))
    return {"updates": updates, "complete_native_query": turnout,
            "election_parent": election, "town_status": status,
            "geographic_joins_changed": False, "source_clock": None}


def alabama(body, templates):
    import xlrd

    units, parents, queries = {}, {}, []
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        entries = archive.infolist()
        if (len(entries) > 500 or sum(item.file_size for item in entries) > 200_000_000
                or any(item.flag_bits & 1 for item in entries)):
            raise ValueError("Unqualified Alabama workbook archive inventory")
        for item in entries:
            name = PurePosixPath(item.filename).name
            match = re.fullmatch(r"2026_GENERAL_ELECTION-(.+)\.xls", name, re.I)
            if not match:
                continue
            county = match[1]
            workbook = xlrd.open_workbook(file_contents=archive.read(item))
            sheet = workbook.sheet_by_name("Precinct Results")
            if sheet.nrows < 3 or sheet.ncols < 4:
                raise ValueError("Incomplete Alabama statistics workbook")
            labels = [" ".join(str(sheet.cell_value(row, col)).upper().split())
                      for row in (1, 2) for col in range(3)]
            if not any("BALLOTS CAST" in label and "TOTAL" in label for label in labels[3:]):
                raise ValueError("Alabama physical statistic row/header changed")
            selected = []
            for col in range(3, sheet.ncols):
                label = sheet.cell_value(0, col)
                if label == "":
                    continue
                if not isinstance(label, str):
                    raise ValueError("Changed Alabama reporting-unit label")
                native_values = [sheet.cell_value(row, col) for row in (1, 2)]
                if any(value != "" and (type(value) not in (int, float)
                       or int(value) != value or value < 0) for value in native_values):
                    raise ValueError("Missing/fractional Alabama native statistical count")
                registered, ballots = (None if value == "" else int(value) for value in native_values)
                column, number = "", col + 1
                while number:
                    number, remainder = divmod(number - 1, 26)
                    column = chr(65 + remainder) + column
                row = {"county": county, "unit": label, "column": column,
                       "ballots": ballots, "registered": registered, "workbook": name,
                       "source_rows": [{"workbook": name, "table": "Precinct Results",
                                        "column": column,
                                        "rows_by_field": {"unit": 1, "registered": 2, "ballots": 3}}]}
                key = county, column
                if key in units:
                    raise ValueError("Duplicated Alabama workbook/physical column")
                units[key] = row
                selected.append(row)
            if not selected:
                raise ValueError("Empty Alabama statistical table")
            subtotal = sum(row["ballots"] for row in selected if row["ballots"] is not None)
            parents[county.upper()] = {"county": county,
                "ballots": subtotal if all(row["ballots"] is not None for row in selected) else None,
                "reported_subtotal": subtotal,
                "source_units": len(selected), "derived_source_column_sum": True,
                "native_printed_county_parent": False}
            queries.extend(selected)
    if not units:
        raise ValueError("No explicitly named 2026 general-election statistics workbooks")
    updates = []
    parent_sources = {}
    for template in templates:
        native = template.get("view", {}).get("native_record", {})
        for source in native.get("source_rows", []):
            match = re.fullmatch(r"2026_GENERAL_ELECTION-(.+)\.xls", source.get("workbook", ""), re.I)
            parent_id = template["geography"].get("parent_id")
            if match and parent_id:
                previous = parent_sources.setdefault(parent_id, match[1].upper())
                if previous != match[1].upper():
                    raise ValueError("An accepted Alabama parent points at conflicting native workbooks")
    for template in templates:
        native = template.get("view", {}).get("native_record", {})
        if template["geography"]["level"] == "county":
            source_county = parent_sources.get(template["geography"]["id"],
                                               template["geography"]["name"].upper())
            parent = parents.get(source_county)
            if parent:
                updates.append(change(template, parent["ballots"], parent))
        elif native.get("column") and native.get("source_rows"):
            source = native["source_rows"][0]
            match = re.fullmatch(r"2026_GENERAL_ELECTION-(.+)\.xls", source.get("workbook", ""), re.I)
            row = units.get((match[1], native["column"])) if match else None
            if row is None or row["unit"] != template["geography"]["name"]:
                raise ValueError("Changed Alabama native column identity; old unit is not reassigned")
            updates.append(change(template, row["ballots"], row))
    return {"updates": updates, "complete_native_query": queries, "county_queries": list(parents.values()),
            "geographic_joins_changed": False, "county_totals_are_explicit_derived_column_sums": True}


def eligible_product(link):
    url = urlsplit(link["url"])
    label = unquote(link.get("text", "") + " " + url.path + " " + url.query)
    return (url.scheme == "https" and not NOT_RESULTS.search(label)
            and bool(re.search(r"(?<!\d)2026(?!\d)", label))
            and bool(re.search(r"general|11[-_/]?03|nov(?:ember)?[ _-]*3", label, re.I)))


def transport_url(url):
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, quote(parsed.path, safe="/%:@"),
                      quote(parsed.query, safe="=&%+/:@"), ""))


def factual_tables(body, name):
    """Unrecognized numerical schemas stay factual queries, never turnout/model inputs."""
    from scripts.native_tabular import delimited, json_records, xlsx, xls

    suffix = PurePosixPath(urlsplit(name).path).suffix.lower()
    if suffix in (".csv", ".txt"):
        encoding = "utf-16" if body.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        text = body.decode(encoding)
        table = delimited(body, delimiter="\t" if "\t" in text[:4096] else ",", encoding=encoding)
        tables = [table]
    elif suffix == ".json":
        tables = [json_records(body)]
    elif suffix in (".xlsx", ".xls"):
        product = (xlsx if suffix == ".xlsx" else xls)(body)
        # Workbook facts are retained only after a source-specific semantic adapter exists.
        return {"status": "native_workbook_requires_measure_adapter",
                "native_inventory": [{"name": table["name"], "rows": table["nrows"],
                                      "columns": table["ncols"]} for table in product],
                "numerical_data_qualified": False}
    elif suffix == ".zip":
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            items = archive.infolist()
            if (len(items) > 1000 or sum(item.file_size for item in items) > 200_000_000
                    or any(item.flag_bits & 1 for item in items)):
                raise ValueError("Unqualified declared archive size/inventory")
            selected = {}
            for item in items:
                path = PurePosixPath(item.filename)
                if path.is_absolute() or ".." in path.parts or NOT_RESULTS.search(path.name):
                    continue
                if path.suffix.lower() in (".csv", ".txt", ".json"):
                    selected[item.filename] = factual_tables(archive.read(item), item.filename)
            return {"status": "complete_declared_tabular_queries", "members": selected,
                    "numerical_data_qualified": False}
    else:
        return {"status": "source_format_requires_measure_adapter", "numerical_data_qualified": False}
    for table in tables:
        if PRIVATE_HEADERS.search(json.dumps(table.get("header", []))):
            raise ValueError("Individual/contact schema is excluded from public numerical intake")
    return {"status": "complete_native_table_requires_measure_adapter", "tables": tables,
            "numerical_data_qualified": False, "candidate_votes_are_ballots": False}


def collect(collector, baseline):
    jobs = {}
    for state, parser in (("NC", north_carolina), ("MN", minnesota)):
        templates = selected_records(baseline, state)
        if not templates:
            continue
        url = ("https://er.ncsbe.gov/enr/20261103/data/county.txt" if state == "NC" else MN_URL)
        jobs[state + "-native-local"] = collector.capture(state + "-native-local", url,
            lambda body, parser=parser, templates=templates: parser(body, templates))
    templates = selected_records(baseline, "AL")
    urls = {row["view"].get("source_url") for row in templates
            if row.get("view", {}).get("native_record", {}).get("source_rows")
            and row["measure"]["kind"] == "ballots_cast"}
    for url in sorted(value for value in urls if value and value.lower().endswith(".zip")):
        key = "AL-native-local"
        jobs[key] = collector.capture(key, url, lambda body: alabama(body, templates))
    templates = selected_records(baseline, "CT")
    if templates:
        def capture_ct(version_body):
            elections, _ = collector.acquire(CT_ELECTIONS)
            number = json.loads(version_body).get("Version")
            if type(number) is not int or number < 52337:
                raise ValueError("Invalid/regressed Connecticut native source version")
            base = CT_ROOT + "election/108/" + str(number) + "/"
            inputs = {}
            for name in ("voterTurnout_Electiondata", "election_Electiondata", "townStatus_Electiondata"):
                body, _ = collector.acquire(base + name + ".json")
                inputs[name] = body
            after, _ = collector.acquire(CT_VERSION, refresh=True)
            if json.loads(after).get("Version") != number:
                raise ValueError("Connecticut version changed during capture; retain last consistent snapshot")
            result = connecticut(*(json.loads(inputs[name]) for name in
                ("voterTurnout_Electiondata", "election_Electiondata")),
                json.loads(elections), json.loads(inputs["townStatus_Electiondata"]), templates)
            result["source_version"] = number
            result["numerical_input_pins"] = {name: pin(body) for name, body in inputs.items()}
            result["source_url"] = base + "voterTurnout_Electiondata.json"
            return result
        jobs["CT-native-local"] = collector.capture("CT-native-local", CT_VERSION, capture_ct)
    return jobs


def project(baseline, granular):
    """Create successor bodies, preserving old versions, IDs, views and join decisions."""
    result = dict(baseline)
    index = json.loads(baseline["index.json"])
    changed = []
    by_state = {}
    for key, entry in granular.items():
        if entry.get("status") == "reported" and entry.get("data") is not None:
            by_state.setdefault(key.split("-")[0], []).append(entry)
    for state, entries in by_state.items():
        path = index["states"][state]["file"]
        shard = json.loads(gzip.decompress(baseline[path]))
        rows = {row["id"]: row for row in shard["records"]}
        state_changed = False
        for entry in entries:
            for update in entry["data"].get("updates", []):
                old = rows.get(update["id"])
                if old is None:
                    raise ValueError("A local refresh cannot invent an existing native identity")
                row = copy.deepcopy(old)
                value, native = update["value"], update["native"]
                row["count"] = {"value": value, "literal": value,
                                "status": "reported" if value is not None else "unknown"}
                source = entry["source"]
                numerical_pin = entry["data"].get("numerical_input_pins", {}).get(
                    "voterTurnout_Electiondata", source)
                url = entry["data"].get("source_url", source["url"])
                row["source"].update(url=url, input_sha256=numerical_pin["sha256"],
                                     selector={"native_refresh": native})
                row["source_clock"] = {"literal": update["clock"], "timezone": None,
                                      "qualification": "native_clock_or_explicitly_not_supplied"}
                denominator = row["denominator"]
                if denominator is not None:
                    denominator["value"] = update["registered"]
                    denominator["qualified"] = bool(denominator["qualified"] and update["rate_compatible"]
                        and value is not None and update["registered"] and value <= update["registered"])
                row["reporting_status"].update(reported_units=update["reported_units"],
                    total_units=update["total_units"],
                    complete=(update["reported_units"] == update["total_units"])
                    if update["total_units"] is not None else None)
                view = row["view"]
                view.update(ballots=value, native_record=native, source_url=url,
                    source_sha256=numerical_pin["sha256"], source_update_label=update["clock"],
                    denominator=update["registered"] if denominator else None,
                    reported_pct=100 * value / update["registered"] if denominator
                    and denominator["qualified"] else None,
                    reported_units=update["reported_units"], total_units=update["total_units"],
                    native_printed_pct=None)
                view["source_reporting_label"] = (
                    "Automatic same-source native statistical refresh. Missing reporting stays unknown; "
                    "source counts are not certification or independently observed people. "
                    "Prior geographic qualifications retained; no new boundary join or local model.")
                view["automatic_source_refresh"] = True
                row["source"]["fields"] = copy.deepcopy(view)
                validate(row)
                if row != old:
                    state_changed = True
                    changed.append({"state_code": state, "id": row["id"],
                                    "previous": old["count"]["value"], "current": value,
                                    "source_status": entry["status"]})
                rows[row["id"]] = row
        if not state_changed:
            continue
        shard["records"] = [rows[row["id"]] for row in shard["records"]]
        raw = bytearray(gzip.compress(encoded(shard), compresslevel=6, mtime=0))
        raw[9] = 3
        result[path] = bytes(raw)
        index["states"][state].update(pin(result[path]))
        declaration = index["states"][state]
        for mode, frame in shard.get("views", {}).items():
            description = declaration.get("views", {}).get(mode, {})
            for partition in ("counties", "precincts", "nongeographic"):
                selected = [rows[identity] for identity in frame.get(partition, [])]
                disposition = description.get("dispositions", {}).get(partition)
                if disposition is not None:
                    disposition.update(
                        reported=sum(row["count"]["status"] == "reported" for row in selected),
                        unknown=sum(row["count"]["status"] == "unknown" for row in selected),
                        withheld=sum(row["count"]["status"] == "withheld" for row in selected),
                        qualified_fractions=sum(bool(row["denominator"] and row["denominator"]["qualified"])
                                                for row in selected),
                        geography_levels=sorted({row["geography"]["level"] for row in selected}))
        if state in index.get("coverage", {}):
            records = shard["records"]
            index["coverage"][state].update(
                records=len(records),
                reported=sum(row["count"]["status"] == "reported" for row in records),
                unknown=sum(row["count"]["status"] == "unknown" for row in records),
                withheld=sum(row["count"]["status"] == "withheld" for row in records),
                zeros=sum(row["count"]["value"] == 0 for row in records),
                qualified_fractions=sum(bool(row["denominator"] and row["denominator"]["qualified"])
                                        for row in records))
    if changed:
        result["index.json"] = encoded(index)
    return result, changed
