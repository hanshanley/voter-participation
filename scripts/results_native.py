"""Refresh reviewed statistical source families without assigning new geographic identities."""

from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, ROUND_HALF_UP
import html
import io
import json
import re
from urllib.parse import urlsplit

from scripts.participation_intake.contract import count, digest, pin
from scripts.results_granular import (
    CT_ROOT, MN_URL, NOT_RESULTS, PRIVATE_HEADERS, change, factual_tables,
    public_facts, selected_records, transport_url,
)


CA_URL = "https://media.sos.ca.gov/media/status_GG.json"
IN_URL = "https://enr.indianavoters.in.gov/site/data/statewideTurnout_B.json"
NM_URL = "https://electionresults.sos.nm.gov/VoterTurnoutDetails.aspx?map=PREC"
CO_WORKBOOK_URL = (
    "https://www.coloradosos.gov/pubs/newsRoom/pressReleases/2026/"
    "20261105GenElectionActivity.xlsx"
)
WAYNE_MAIN_URL = (
    "https://www.waynecountymi.gov/files/assets/mainsite/v/1/clerk/documents/"
    "elections/link-statementofvotescastrpt_un.xlsx"
)
WAYNE_SUPPLEMENT_URL = (
    "https://www.waynecountymi.gov/files/assets/mainsite/v/1/clerk/documents/"
    "elections/vbs-statementofvotescast.xlsx"
)
COUNTY_WORKBOOK_FIELDS = {
    "county": "A", "ACN": "B", "APV": "C", "CTR": "D", "DEM": "E", "FWD": "F",
    "GRN": "G", "LBR": "H", "NOL": "I", "REP": "J", "UAF": "K", "UNI": "L",
    "Grand Total": "M",
}
COUNTY_WORKBOOK_SHEETS = {
    "All_Returned_Ballots_By_County": "ALL RETURNED BALLOTS - MAIL AND IN PERSON COMBINED",
    "Returned_Mail_Ballots_By_County": "RETURNED MAIL BALLOTS",
    "In_Person_Ballots_By_County": "IN PERSON BALLOTS",
}
WORKBOOK_PROFILES = {
    CO_WORKBOOK_URL: {
        "state": "CO", "kind": "county_mode_tables",
        "query_id": "co-returned-processed-county-modes",
        "sheets": [
            "Voter_Counts", "All_Returned_Ballots_By_County",
            "All_Returned_Ballots_GenderAge", "Returned_Mail_Ballots_By_County",
            "Returned_Mail_Ballots_GenderAge", "In_Person_Ballots_By_County",
            "In_Person_Ballots_GenderAge",
        ],
        "clock": "11:59 PM November 5, 2026; timezone not supplied. Published November 6, 2026.",
        "measure": "Returned and processed ballots (native all-returned total)",
    },
    WAYNE_MAIN_URL: {
        "state": "MI", "kind": "statistical_mode_blocks", "product": "wayne-main",
        "query_id": "wayne-main-statistics", "sheet": "Stats", "first_row": 8,
        "modes": ["Early Voting", "Election Day", "Absentee", "Pre-Process Absentee"],
        "parents": ["Wayne County - Total", "County - Total"],
        "expected_units": 758,
    },
    WAYNE_SUPPLEMENT_URL: {
        "state": "MI", "kind": "statistical_mode_blocks",
        "product": "wayne-three-localities",
        "query_id": "wayne-three-localities-statistics", "sheet": "Sheet1",
        "first_row": 8, "modes": ["Early Voting", "Election Day", "Absentee"],
        "parents": ["Wayne County - Total", "County - Total"],
        "expected_units": 12,
    },
}
RECORD_PROFILES = {
    CA_URL: {
        "state": "CA", "query_id": "ca-all-status",
        "identity": "county", "name": "countyName", "count": "voterTurnout",
        "registered": "totalRegisteredVoters", "clock": "timestamp",
        "reported": "precinctsReporting", "total": "precinctsTotal",
        "template_identity": ("query", "county_id"),
        "parent": "59", "parent_name": "Statewide",
        "first_report": "firstReportTimestamp",
        "edition_clock": "lastReportTimestamp",
    },
    IN_URL: {
        "state": "IN", "query_id": "in-native-voters-voting",
        "items_path": "root.CountyTurnout",
        "identity": "County", "name": "County", "count": "VotersVoting",
        "registered": "REGISTERED_VOTERS", "template_identity": ("County",),
        "template_name": ("County",), "clock_path": ("root", "WriteTime"),
        "template_clock_prefix": "Voter statistics WriteTime: ",
        "row_guards": {"ElectionDateName": "Tuesday, November 3, 2026"},
        "parent": "Total", "parent_name": "Total",
        "independent_overrides": ["Cass", "Floyd", "Fulton", "Monroe", "Porter", "Posey", "Wayne"],
        "components": ["InPerson", "Absentee"], "positive_counts_only": True,
        "analytical_rates_qualified": False,
    },
}
SUMMARY_PROFILES = {
    "https://election-results-01.kingcounty.gov/results.pdf": {
        "state": "WA", "layout": "repeated_header", "level": "county",
        "name": "King County", "identity_field": "source_id",
        "identity": "king-current-native-summary",
        "measure": "Reported ballots (previously reviewed export label, not a new native qualification)",
        "title": "King County, November 2026 General Election, Nov 03, 2026",
    },
    **{
        "https://elections.hawaii.gov/wp-content/results/2026%20General/" + filename + ".pdf": {
            "state": "HI", "layout": "column_turnout", "level": "election_administration",
            "name": name, "identity_field": "source_administration_id", "identity": identity,
            "measure": "TOTAL TURNOUT (native report; not certified unique voters)",
            "title": "GENERAL ELECTION 2026 - State of Hawaii - " + title,
            "component_county_fips": counties,
        }
        for filename, name, identity, title, counties in (
            ("cch", "Honolulu election administration", "HI-HONOLULU",
             "City and County of Honolulu", ["15003"]),
            ("coh", "Hawaii election administration", "HI-HAWAII", "County of Hawaii", ["15001"]),
            ("cok", "Kauai election administration", "HI-KAUAI", "County of Kauai", ["15007"]),
            ("com", "Maui election administration (includes Kalawao)", "HI-MAUI",
             "County of Maui", ["15009", "15005"]),
        )
    },
}
PDF_MEASURES = {
    "Ballots Cast - Total", "Ballots Cast", "Total Ballots Cast", "Total Ballots",
    "Voters Cast", "Cards Cast", "TOTAL TURNOUT",
}
TX_RECONCILIATION_ROLES = {
    "i. total ballots counted (g+h)": {
        "form": "preliminary", "count_role": "I", "total_roles": ("C", "F", "I")},
    "m. total ballots counted (i+j+k+l)": {
        "form": "official", "count_role": "M", "total_roles": ("E", "H", "M")},
}
COUNT_LITERAL = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
ELECTION_DATE = re.compile(
    r"\b(?:11[/.]0?3[/.]2026|November\s+0?3,?\s+2026)\b", re.I)
REPORT_CLOCK = re.compile(
    r"\b(?:[01]?[0-9]/[0-3]?[0-9]/20[0-9]{2}|20[0-9]{2}-[01][0-9]-[0-3][0-9])"
    r"\s*(?:-\s*)?[0-2]?[0-9]:[0-5][0-9](?::[0-5][0-9])?\s*(?:AM|PM)?\b", re.I)
TOTAL_HEADER = re.compile(
    r"(?:Statistics\s+)?TOTAL(?:\s*(?:VOTE\s*%|%|Election\s*Day|Early(?:\s*Voting)?|Absentee|"
    r"Provisional|Mail|ED|EV|AB))*", re.I)


def native_identity(template, path):
    value = template["view"]["native_record"]
    for key in path:
        value = value[key]
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("A reviewed literal native record identity is required")
    return str(value)


def record_statistics(body, templates, profile):
    from scripts.native_tabular import json_records

    if any(template["geography"]["state_code"] != profile["state"]
           or template["election"]["year"] != 2026
           or template["election"]["type"] != "general" for template in templates):
        raise ValueError("Reviewed native record state/election scope changed")
    table = json_records(body, items_path=profile.get("items_path"))
    public_facts(table)
    rows = [dict(zip(table["header"], item["values"])) for item in table["rows"]]
    required = {profile[key] for key in ("identity", "name", "count")}
    required.update(profile[key] for key in (
        "registered", "clock", "reported", "total", "first_report", "edition_clock")
        if profile.get(key))
    if not required <= set(table["header"]):
        raise ValueError("Reviewed native statistical columns changed")
    native = {}
    for row in rows:
        identity = row[profile["identity"]]
        if isinstance(identity, bool) or not isinstance(identity, (str, int)):
            raise ValueError("Invalid native statistical identity")
        identity = str(identity)
        if identity in native:
            raise ValueError("Duplicate native statistical identity")
        if any(row.get(key) != value for key, value in profile.get("row_guards", {}).items()):
            raise ValueError("Native statistical election declaration changed")
        if profile.get("first_report") and re.fullmatch(
                r"202611(?:0[3-9]|[12][0-9]|30)[0-2][0-9][0-5][0-9]",
                str(row[profile["first_report"]])) is None:
            raise ValueError("Native statistics are not bound to the reviewed November 2026 election")
        for key in ("count", "registered", "reported", "total"):
            if profile.get(key) and count(row[profile[key]]) is None:
                raise ValueError("An absent native statistic is not a recorded zero")
        native[identity] = row
        if profile.get("components") and (
                any(count(row.get(key)) is None for key in profile["components"])
                or sum(count(row[key]) for key in profile["components"]) != count(row[profile["count"]])):
            raise ValueError("Native participation components disagree")
    expected = {}
    for template in templates:
        identity = native_identity(template, profile["template_identity"])
        expected.setdefault(identity, []).append(template)
    parent = profile.get("parent")
    inventory = set(expected) | set(profile.get("independent_overrides", []))
    if not expected or set(native) != inventory | ({parent} if parent else set()):
        raise ValueError("Reviewed native statistical inventory changed")
    if parent:
        parent_row = native[parent]
        if parent_row[profile["name"]] != profile["parent_name"]:
            raise ValueError("Native statewide parent label changed")
        for key in ("count", "registered"):
            if profile.get(key) and sum(count(row[profile[key]]) for identity, row in native.items()
                    if identity != parent) != count(parent_row[profile[key]]):
                raise ValueError("Complete native counties disagree with the separate state parent")
    updates = []
    global_clock = None
    if profile.get("clock_path"):
        global_clock = json.loads(body)
        for key in profile["clock_path"]:
            global_clock = global_clock[key]
        datetime.strptime(global_clock, "%Y-%m-%dT%H:%M:%S.%f")
    for identity, targets in expected.items():
        row = native[identity]
        for template in targets:
            expected_name = (native_identity(template, profile["template_name"])
                             if profile.get("template_name") else template["geography"]["name"])
            if row[profile["name"]] != expected_name:
                raise ValueError("Changed literal native county identity/name")
            if template["count"]["status"] != "reported":
                continue
            if profile.get("positive_counts_only") and count(row[profile["count"]]) == 0:
                raise ValueError("A contradictory native zero requires review, not automatic promotion")
            if global_clock:
                prefix = profile["template_clock_prefix"]
                previous = template["source_clock"]["literal"]
                if not previous or not previous.startswith(prefix):
                    raise ValueError("Reviewed native statistical clock binding changed")
                previous = previous[len(prefix):].split(";", 1)[0]
                if datetime.fromisoformat(global_clock) < datetime.fromisoformat(previous):
                    raise ValueError("Native statistical edition regressed")
            if profile.get("edition_clock"):
                edition = str(row[profile["edition_clock"]])
                previous = (template["view"]["native_record"].get("query") or {}).get(
                    "last_report_timestamp")
                current_clock = datetime.strptime(edition, "%Y%m%d%H%M")
                if previous and current_clock < datetime.strptime(previous, "%Y%m%d%H%M"):
                    raise ValueError("Native statistical edition is older than the reviewed observation")
            value = count(row[profile["count"]])
            registered = count(row[profile["registered"]]) if profile.get("registered") else None
            clock = row[profile["clock"]] if profile.get("clock") else global_clock
            reported = count(row[profile["reported"]]) if profile.get("reported") else None
            total = count(row[profile["total"]]) if profile.get("total") else None
            query = {
                "query_id": profile["query_id"], "county_id": identity,
                "county_name": row[profile["name"]], "count": value,
                "registered": registered, "source_clock": clock,
                "reported_units": reported, "total_units": total,
                "selector": {profile["identity"]: row[profile["identity"]]},
            }
            if profile.get("edition_clock"):
                query["last_report_timestamp"] = str(row[profile["edition_clock"]])
                query["first_report_timestamp"] = str(row[profile["first_report"]])
            facts = {"query": query, "native_fields": row,
                     "private_original_pin": pin(body),
                     "whole_publisher_html_redistributed": False}
            updates.append(change(template, value, facts, registered=registered, clock=clock,
                reported=reported, total=total,
                rate_compatible=bool(registered and value <= registered
                                     and profile.get("analytical_rates_qualified", True))))
    return {"updates": updates, "complete_native_query": rows,
            "native_column_bindings": profile, "geographic_joins_changed": False,
            "native_measure_not_relabelled_as_ballots": True}


def workbook_table(workbook, name):
    matches = [table for table in workbook if table["name"] == name]
    if len(matches) != 1:
        raise ValueError("Reviewed native worksheet is absent or ambiguous")
    return matches[0]


def reviewed_count(value):
    if type(value) is not int or value < 0:
        raise ValueError("A blank, fractional, boolean or negative workbook cell is not a recorded zero")
    return value


def county_mode_statistics(body, templates, profile, workbook):
    from scripts.native_tabular import values

    if [table["name"] for table in workbook] != profile["sheets"]:
        raise ValueError("Colorado reviewed workbook sheet inventory changed")
    header = list(COUNTY_WORKBOOK_FIELDS)
    parsed = {}
    for sheet, title in COUNTY_WORKBOOK_SHEETS.items():
        table = workbook_table(workbook, sheet)
        if values(table, 1).get("A") != title:
            raise ValueError("Colorado reviewed workbook mode title changed")
        headings = values(table, 2)
        if [headings.get(COUNTY_WORKBOOK_FIELDS[field]) for field in header] != [
                "COUNTY", *header[1:]]:
            raise ValueError("Colorado reviewed workbook county columns changed")
        rows, parent, ended = [], None, False
        for item in table["rows"]:
            number = item["row"]
            if number <= 2:
                continue
            cells = values(table, number)
            label = cells.get("A")
            populated = {key: value for key, value in cells.items() if value not in (None, "")}
            if label == "end of worksheet":
                if parent is None or any(key != "A" for key in populated):
                    raise ValueError("Colorado workbook end marker changed")
                ended = True
                continue
            if ended:
                if populated:
                    raise ValueError("Colorado workbook has data after its reviewed end marker")
                continue
            if not isinstance(label, str) or not label:
                raise ValueError("Colorado workbook county row is blank or malformed")
            record = {field: reviewed_count(cells.get(column))
                      for field, column in COUNTY_WORKBOOK_FIELDS.items() if field != "county"}
            if sum(record[field] for field in header[1:-1]) != record["Grand Total"]:
                raise ValueError("Colorado workbook party cells disagree with the row total")
            row = {"county": label, "native_excel_row": number, "native_record": record}
            if label == "Grand Total":
                if parent is not None:
                    raise ValueError("Colorado workbook repeats its native parent")
                parent = row
            else:
                if parent is not None:
                    raise ValueError("Colorado workbook county appears after the native parent")
                rows.append(row)
        if not ended or parent is None or len(rows) != 64:
            raise ValueError("Colorado workbook county inventory changed")
        if any(sum(row["native_record"][field] for row in rows)
               != parent["native_record"][field] for field in header[1:]):
            raise ValueError("Colorado workbook counties disagree with the separate state parent")
        parsed[sheet] = {"rows": rows, "parent": parent}
    modes = list(COUNTY_WORKBOOK_SHEETS)
    for sheet in modes[1:]:
        if [(row["county"], row["native_excel_row"]) for row in parsed[sheet]["rows"]] != [
                (row["county"], row["native_excel_row"]) for row in parsed[modes[0]]["rows"]]:
            raise ValueError("Colorado workbook mode county identities or physical rows changed")
    for index, row in enumerate(parsed[modes[0]]["rows"]):
        returned = row["native_record"]
        mail = parsed[modes[1]]["rows"][index]["native_record"]
        in_person = parsed[modes[2]]["rows"][index]["native_record"]
        if any(returned[field] != mail[field] + in_person[field] for field in header[1:]):
            raise ValueError("Colorado returned mode is not the mail plus in-person native control")
    if any(parsed[modes[0]]["parent"]["native_record"][field]
           != parsed[modes[1]]["parent"]["native_record"][field]
           + parsed[modes[2]]["parent"]["native_record"][field] for field in header[1:]):
        raise ValueError("Colorado statewide returned modes disagree")

    expected = {}
    for template in templates:
        native = template.get("view", {}).get("native_record") or {}
        if (template["geography"]["state_code"] != "CO"
                or template["geography"]["level"] != "county"
                or template["election"]["year"] != 2026
                or template["election"]["type"] != "general"
                or template["measure"]["literal"] != profile["measure"]
                or set(native) != set(modes)):
            raise ValueError("Reviewed Colorado workbook template scope changed")
        selectors = []
        for sheet in modes:
            selected = native[sheet]
            if (not isinstance(selected, dict) or set(selected) != {
                    "county", "native_excel_row", "native_record"}):
                raise ValueError("Reviewed Colorado workbook selector changed")
            selectors.append((selected["county"], selected["native_excel_row"]))
        if len(set(selectors)) != 1:
            raise ValueError("Colorado template mode selectors no longer identify one county row")
        county, number = selectors[0]
        if county in expected or template["geography"]["name"] not in (
                county + " County", "City and County of " + county):
            raise ValueError("Reviewed Colorado workbook county identity changed")
        expected[county] = (number, template)
    observed = {row["county"]: row for row in parsed[modes[0]]["rows"]}
    if set(expected) != set(observed):
        raise ValueError("Reviewed Colorado workbook county inventory changed")

    updates = []
    for county, (number, template) in expected.items():
        source = observed[county]
        if source["native_excel_row"] != number:
            raise ValueError("Reviewed Colorado workbook physical county row changed")
        native = {sheet: parsed[sheet]["rows"][number - 3] for sheet in modes}
        if any(item["county"] != county or item["native_excel_row"] != number
               for item in native.values()):
            raise ValueError("Colorado workbook mode rows no longer identify the same county")
        value = native[modes[0]]["native_record"]["Grand Total"]
        updates.append(change(template, value, native, clock=profile["clock"]))
    complete = []
    for sheet in modes:
        complete.extend({"query_id": profile["query_id"], "mode": sheet, **row}
                        for row in parsed[sheet]["rows"] + [parsed[sheet]["parent"]])
    return {"updates": updates, "complete_native_query": complete,
            "native_column_bindings": {
                "county": "A", "count": "M", "party_components": list(header[1:-1]),
                "mode_sheets": modes,
            },
            "private_original_pin": pin(body), "geographic_joins_changed": False,
            "native_measure_not_relabelled_as_ballots": True,
            "returned_processed_frames_remain_distinct": True}


def excel_clock(table, address):
    matches = [cell for row in table["rows"] for cell in row["cells"]
               if cell["address"] == address]
    if len(matches) != 1:
        raise ValueError("Reviewed native workbook clock cell is absent or ambiguous")
    cell = matches[0]
    literal = cell["cached_literal"]
    if (cell["storage_type"] != "n" or cell["formula"] is not None
            or not isinstance(literal, str)
            or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", literal) is None):
        raise ValueError("Reviewed native workbook clock cache changed")
    style = int(cell["attributes"].get("s", "-1"))
    if not 0 <= style < len(table["workbook_cell_formats"]):
        raise ValueError("Reviewed native workbook clock style changed")
    format_id = table["workbook_cell_formats"][style].get("numFmtId")
    number_format = table["workbook_number_formats"].get(format_id)
    if number_format != r"[$-10409]m/d/yyyy\ h:mm:ss\ AM/PM":
        raise ValueError("Reviewed native workbook clock number format changed")
    date1904 = table["workbook_properties"].get("date1904", "0")
    if date1904 not in ("0", "false"):
        raise ValueError("Reviewed Wayne workbook changed from the 1900 date system")
    value = Decimal(literal)
    if value < 61:
        raise ValueError("Reviewed native workbook clock is outside the supported Excel date range")
    milliseconds = int((value * Decimal(86400000)).quantize(Decimal("1"), ROUND_HALF_UP))
    decoded = datetime(1899, 12, 30) + timedelta(milliseconds=milliseconds)
    return {
        "cached_literal": literal, "cell": address, "date_system": "1900",
        "literal": decoded.isoformat(timespec="milliseconds")
            + " (decoded Excel cache; timezone not supplied)",
        "number_format": number_format,
        "qualification": "decoded_native_worksheet_cache_not_printed_text",
        "timezone": None,
    }


def decoded_excel_clock(literal):
    suffix = " (decoded Excel cache; timezone not supplied)"
    if not isinstance(literal, str) or not literal.endswith(suffix):
        raise ValueError("Reviewed native workbook clock qualification changed")
    return datetime.fromisoformat(literal[:-len(suffix)])


def statistical_workbook_statistics(body, templates, profile, workbook):
    from scripts.native_products import query, statistical_units

    table = workbook_table(workbook, profile["sheet"])
    product = {"tables": [dict(kind="worksheet", **item) for item in workbook]}
    selection = {
        "id": profile["query_id"], "product": profile["product"],
        "tables": [profile["sheet"]],
        "fields": {
            "column_A": "A", "column_B": "B", "column_C": "C", "column_D": "D",
            "column_E": "E", "column_F": "F", "column_G": "G", "column_H": "H",
            "native_row": "$row", "native_table": "$table",
        },
        "keys": ["native_table", "native_row"],
        "require": {"5": {
            "A": "Precinct", "B": "Registered\nVoters",
            "D": "Voters Cast", "F": "% Turnout",
        }},
    }
    source_query = query(product, selection)
    grouping = statistical_units(source_query, {
        "first_row": profile["first_row"], "modes": profile["modes"],
        "parents": profile["parents"],
        "fields": {
            "row": "native_row", "label": "column_A", "registered": "column_B",
            "cast": "column_D", "fraction": "column_F",
        },
    })
    if len(grouping["units"]) != profile["expected_units"]:
        raise ValueError("Wayne reviewed native unit inventory changed")
    clock = excel_clock(table, "H1")
    observed = {unit["unit"]: unit for unit in grouping["units"]}
    if len(observed) != len(grouping["units"]):
        raise ValueError("Wayne reviewed native unit labels are repeated")
    expected = {}
    for template in templates:
        native = template.get("view", {}).get("native_record") or {}
        old_unit = native.get("native_unit") or {}
        old_clock = native.get("native_clock") or {}
        if (template["geography"]["state_code"] != "MI"
                or template["geography"]["level"] != "reporting_unit"
                or template["election"]["year"] != 2026
                or template["election"]["type"] != "general"
                or template["measure"]["literal"] != "Voters Cast (reported statistical units)"
                or native.get("source_product") != profile["product"]
                or old_unit.get("unit") != template["geography"]["name"]
                or old_clock.get("cell") != "H1"
                or old_clock.get("date_system") != "1900"):
            raise ValueError("Reviewed Wayne workbook template scope or component role changed")
        name = old_unit["unit"]
        if name in expected:
            raise ValueError("Reviewed Wayne workbook template identity is repeated")
        expected[name] = (template, old_unit, old_clock)
    if set(expected) != set(observed):
        raise ValueError("Reviewed Wayne workbook unit inventory changed")
    previous_clocks = {old_clock["literal"] for _, _, old_clock in expected.values()}
    if (len(previous_clocks) != 1
            or decoded_excel_clock(clock["literal"])
            < decoded_excel_clock(previous_clocks.pop())):
        raise ValueError("Wayne native workbook clock regressed or lost its distinct component identity")

    updates = []
    for name, (template, old_unit, _) in expected.items():
        unit = observed[name]
        if (unit["source_rows"] != old_unit.get("source_rows")
                or unit["header_source_rows"] != old_unit.get("header_source_rows")):
            raise ValueError("Reviewed Wayne workbook physical unit row changed")
        denominator = template.get("denominator")
        registered, compatible = None, False
        if denominator is not None:
            if denominator.get("qualified"):
                if (denominator.get("value") != old_unit.get("registered")
                        or old_unit.get("registered") != unit["registered"]):
                    raise ValueError("Qualified native registration identity changed")
                registered = unit["registered"]
                compatible = bool(registered and unit["cast"] <= registered)
            else:
                registered = denominator.get("value")
        native = {
            "agreeing_native_parent_copies": grouping["agreeing_native_parent_copies"],
            "native_clock": clock, "native_parent": grouping["parent"],
            "native_unit": unit, "source_product": profile["product"],
        }
        updates.append(change(template, unit["cast"], native, registered=registered,
            clock=clock["literal"], rate_compatible=compatible))
    return {"updates": updates, "complete_native_query": source_query["rows"],
            "native_statistical_units": grouping, "private_original_pin": pin(body),
            "geographic_joins_changed": False,
            "native_parent_is_not_unique_people_or_a_printed_composite": True,
            "native_registration_and_fraction_context_not_promoted": True}


def workbook_statistics(body, templates, profile):
    from scripts.native_tabular import xlsx

    if (not templates or any(template["geography"]["state_code"] != profile["state"]
            for template in templates)):
        raise ValueError("Reviewed native workbook state scope changed")
    workbook = xlsx(body)
    public_facts(workbook)
    if profile["kind"] == "county_mode_tables":
        return county_mode_statistics(body, templates, profile, workbook)
    if profile["kind"] == "statistical_mode_blocks":
        return statistical_workbook_statistics(body, templates, profile, workbook)
    raise ValueError("Unreviewed native workbook profile")


def pdf_measure(template):
    native = template["view"].get("native_record") or {}
    label = native.get("selected_native_parent_literal") or template["measure"]["literal"]
    return label if isinstance(label, str) and label in PDF_MEASURES else None


def texas_reconciliation_role(template):
    if (template["geography"]["state_code"] != "TX"
            or template["geography"]["level"] != "county"
            or template["election"]["year"] != 2026
            or template["election"]["type"] not in ("general", "general_and_special")
            or template["election"].get("date") != "2026-11-03"):
        return None
    literal = template["measure"]["literal"]
    if not isinstance(literal, str):
        return None
    normalized = " ".join(literal.split()).lower()
    role = TX_RECONCILIATION_ROLES.get(normalized)
    native = template.get("view", {}).get("native_record") or {}
    source_county = native.get("source_county")
    election_date = native.get("native_election_date")
    ballots = native.get("ballots")
    if isinstance(native.get("full_native_measures"), list):
        matching = [row for row in native["full_native_measures"]
                    if isinstance(row, dict)
                    and " ".join(str(row.get("native_label", "")).split()).lower() == normalized
                    and row.get("category") == "counted_ballots"
                    and row.get("mode") == "total"]
        if len(matching) == 1:
            source_county = matching[0].get("county")
            election_date = matching[0].get("election_date")
            ballots = matching[0].get("count")
    if (role is None or not isinstance(source_county, str)
            or not isinstance(election_date, str)
            or count(ballots) != template["count"]["value"]):
        return None
    return {**role, "native_measure_literal": literal,
            "reviewed_source_county": source_county,
            "reviewed_election_date": election_date}


def _tx_lines(page):
    return [" ".join(line.split()) for line in page.splitlines() if line.strip()]


def _tx_compact(value):
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _tx_counts(line):
    return [(int(match.group(0).replace(",", "")), match.span())
            for match in re.finditer(COUNT_LITERAL, line)]


def _tx_selected_confidence(tokens, line, span):
    selected = [item["confidence"] for item in tokens[line]
                if item["start"] < span[1] and item["end"] > span[0]]
    if not selected:
        raise ValueError("Texas reconciliation count has no physical OCR token binding")
    result = min(selected)
    if result < .98:
        raise ValueError("Texas reconciliation selected count OCR confidence requires review")
    return result


def _tx_role_pattern(letter, kind):
    label = r"Total\s+voters?" if kind == "voters" else r"Total\s+ballots?"
    return re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(letter) + r"[^A-Za-z0-9]*" + label
        + r"\D*(" + COUNT_LITERAL + r")", re.I)


def _tx_text_total_row(lines, role):
    patterns = [
        _tx_role_pattern(role["total_roles"][0], "voters"),
        _tx_role_pattern(role["total_roles"][1], "ballots"),
        _tx_role_pattern(role["total_roles"][2], "ballots"),
    ]
    for position, line in enumerate(lines):
        matches = [pattern.search(line) for pattern in patterns]
        if (all(matches)
                and [match.start() for match in matches]
                == sorted(match.start() for match in matches)
                and len(_tx_counts(line)) == 3):
            return position, [
                (int(match.group(1).replace(",", "")), match.span(1))
                for match in matches
            ], {"roles": list(role["total_roles"]), "left_to_right": True,
                "counted_role_explicit": True, "binding": "literal_header_line"}
    raise ValueError("Texas reconciliation C/F/I or E/H/M parent headers are absent or swapped")


def _tx_cell_center(cell):
    return (cell["left"] + cell["right"]) / 2


def _tx_geometry_total_row(lines, role, role_cells):
    if len(role_cells) != len(lines):
        raise ValueError("Texas reconciliation OCR role geometry is incomplete")
    expected = role["total_roles"]
    section_prefixes = (("1voters",), ("2rejected", "2ballotsrejected"),
                        ("3countedballot",))
    sections = []
    for prefixes in section_prefixes:
        candidates = [cell for row in role_cells for cell in row
                      if _tx_compact(cell["text"]).startswith(prefixes)]
        if len(candidates) != 1:
            raise ValueError("Texas reconciliation voter/rejected/counted column headers changed")
        sections.append(candidates[0])
    section_centers = [_tx_cell_center(cell) for cell in sections]
    if section_centers != sorted(section_centers):
        raise ValueError("Texas reconciliation statistical columns are not left-to-right")
    boundaries = [(section_centers[i] + section_centers[i + 1]) / 2 for i in (0, 1)]
    roles = []
    for index, (letter, kind) in enumerate(zip(expected, ("voters", "ballots", "ballots"))):
        marker = letter.lower() + ("totalvoter" if kind == "voters" else "totalballot")
        candidates = [(position, cell) for position, row in enumerate(role_cells) for cell in row
                      if _tx_compact(cell["text"]).startswith(marker)]
        explicit = True
        if not candidates and index == 2:
            candidates = [(position, cell) for position, row in enumerate(role_cells)
                          for cell in row
                          if "totalballot" in _tx_compact(cell["text"])
                          and _tx_cell_center(cell) > boundaries[1]]
            explicit = False
        if len(candidates) != 1:
            raise ValueError("Texas reconciliation native total-role header is absent or ambiguous")
        position, cell = candidates[0]
        center = _tx_cell_center(cell)
        if ((index == 0 and center >= boundaries[0])
                or (index == 1 and not boundaries[0] < center < boundaries[1])
                or (index == 2 and center <= boundaries[1])):
            raise ValueError("Texas reconciliation native total roles changed physical columns")
        roles.append((position, cell, explicit))
    if [_tx_cell_center(item[1]) for item in roles] != sorted(
            _tx_cell_center(item[1]) for item in roles):
        raise ValueError("Texas reconciliation native total roles are not left-to-right")
    start = min(position for position, _cell, _explicit in roles)
    for position in range(start, min(len(role_cells), start + 5)):
        numeric = [cell for cell in role_cells[position]
                   if re.fullmatch(COUNT_LITERAL, cell["text"])]
        if len(numeric) != 3:
            continue
        columns = [[], [], []]
        for cell in numeric:
            center = _tx_cell_center(cell)
            index = 0 if center < boundaries[0] else 1 if center < boundaries[1] else 2
            columns[index].append(cell)
        if any(len(column) != 1 for column in columns):
            raise ValueError("Texas reconciliation total row has decoy or ambiguous numbers")
        return position, [
            (int(column[0]["text"].replace(",", "")),
             (column[0]["start"], column[0]["end"]))
            for column in columns
        ], {"roles": list(expected), "left_to_right": True,
            "counted_role_explicit": roles[2][2],
            "binding": "physical_voter_rejected_counted_columns"}
    raise ValueError("Texas reconciliation role-bound total values are absent or ambiguous")


def _tx_total_row(lines, role, role_cells=None):
    if role_cells is None:
        return _tx_text_total_row(lines, role)
    return _tx_geometry_total_row(lines, role, role_cells)


def _tx_registered(lines):
    for position, line in enumerate(lines):
        if "registeredvoters" in _tx_compact(line):
            matches = _tx_counts(line)
            if matches:
                return position, matches[0]
    return None, None


def _tx_difference(lines, start):
    signed = r"(?<![\w.])[-+]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?![\w.]|%)"
    for position in range(start + 1, min(len(lines), start + 10)):
        line = lines[position]
        compact = _tx_compact(line)
        if "attestation" in compact:
            break
        matches = [match for match in re.finditer(signed, line)
                   if not re.search(r"[*'×]\s*$", line[:match.start()])]
        if "differencebetween" in compact and matches:
            match = matches[-1]
            return position, int(match.group(0).replace(",", "")), match.span()
        if "%" in line and matches:
            match = matches[0]
            return position, int(match.group(0).replace(",", "")), match.span()
    return None, None, None


def _tx_election_line(lines):
    accepted = re.compile(
        r"(?:nov(?:ember)?|tuesdaynovember)?0?3,?2026|1103(?:20)?26", re.I)
    for position, line in enumerate(lines):
        compact = _tx_compact(line)
        if (("electiondate" in compact
             or "registeredvoters" in compact and "date" in compact)
                and accepted.search(compact)):
            return position, line
    raise ValueError("Texas reconciliation election date is absent or unreadable")


def _tx_parse_view(page, template, pages, confidence=None, tokens=None, role_cells=None):
    role = texas_reconciliation_role(template)
    if role is None:
        raise ValueError("Texas reconciliation requires a reviewed statistical-parent role")
    lines = _tx_lines(page)
    compact = _tx_compact(" ".join(lines))
    if ("electionreconciliation" not in compact
            or ("officialtotals" not in compact and "unofficialtotals" not in compact)):
        raise ValueError("Texas reconciliation form title/status changed")
    if role["form"] == "preliminary" and "preliminaryelectionreconciliation" not in compact:
        raise ValueError("Texas preliminary reconciliation role changed")
    if (role["form"] == "official"
            and ("electionreconciliationofficialtotals" not in compact
                 or "preliminaryelectionreconciliation" in compact)):
        raise ValueError("Texas official reconciliation role changed")
    expected_county = role["reviewed_source_county"]
    county_lines = [line for line in lines if "county" in line.lower()
                    and re.search(r"(?<!\w)" + re.escape(expected_county) + r"(?!\w)", line, re.I)]
    if not county_lines:
        raise ValueError("Texas reconciliation literal county identity is absent or unreadable")
    _election_position, election_line = _tx_election_line(lines)
    total_position, total_matches, role_evidence = _tx_total_row(lines, role, role_cells)
    values = [item[0] for item in total_matches]
    total_voters, total_rejected, ballots = values
    if ballots < 0 or total_voters < 0 or total_rejected < 0:
        raise ValueError("Texas reconciliation counts must remain nonnegative")
    selected_confidence = None
    if tokens is not None:
        selected_confidence = _tx_selected_confidence(
            tokens, total_position, total_matches[2][1])
    elif confidence is not None and confidence[total_position] < .98:
        raise ValueError("Texas reconciliation selected count OCR confidence requires review")
    registered_position, registered_match = _tx_registered(lines)
    registered = registered_match[0] if registered_match else None
    difference_position, printed_difference, _difference_span = _tx_difference(
        lines, total_position)
    computed_difference = total_voters - total_rejected - ballots
    discrepancy = None
    if printed_difference is not None and printed_difference != computed_difference:
        discrepancy = {
            "code": "native_reconciliation_difference_disagrees",
            "repaired": False, "actual_native": printed_difference,
            "computed": computed_difference,
            "expression": "-".join(role["total_roles"]),
        }
    native = {
        "native_measure_literal": role["native_measure_literal"],
        "selected_physical_role": role["count_role"] + ". Total ballots counted",
        "form": role["form"], "county": expected_county,
        "election_date_line": election_line, "status_literal": (
            "Preliminary Election Reconciliation - Unofficial Totals"
            if role["form"] == "preliminary"
            else "Election Reconciliation - Official Totals"),
        "registered_raw": registered,
        "registered_denominator_not_promoted": True,
        "total_voters": total_voters, "total_rejected": total_rejected,
        "count": ballots, "printed_difference": printed_difference,
        "computed_difference": computed_difference, "discrepancy": discrepancy,
        "native_total_role_evidence": role_evidence,
        "statistical_parent_line": lines[total_position],
        "registered_line": lines[registered_position] if registered_position is not None else None,
        "difference_line": lines[difference_position] if difference_position is not None else None,
        "pdf_pages": pages, "source_clock": None,
        "attestation_date_is_not_count_update_clock": True,
    }
    if selected_confidence is not None:
        native["ocr_selected_count_minimum_confidence"] = selected_confidence
    return native, lines


def texas_reconciliation_statistics(body, templates):
    from pypdf import PdfReader

    if len(templates) != 1:
        raise ValueError("A Texas reconciliation parent must bind one reviewed county observation")
    reader = PdfReader(io.BytesIO(body))
    if reader.is_encrypted or not reader.pages or len(reader.pages) > 10:
        raise ValueError("Unqualified Texas reconciliation PDF")
    template = templates[0]
    page = reader.pages[0].extract_text(extraction_mode="layout") or ""
    ocr, complete_ocr_views = None, None
    if page.strip():
        native, lines = _tx_parse_view(page, template, len(reader.pages))
    else:
        from scripts.results_pdf_ocr import first_page_views

        views = first_page_views(body, strict_role_alignment=True)
        parsed = [_tx_parse_view(view["text"], template, len(reader.pages),
                                 view["confidence"], view.get("tokens"),
                                 view.get("role_cells"))
                  for view in views]
        vectors = [(item[0]["county"], item[0]["election_date_line"],
                    item[0]["registered_raw"], item[0]["total_voters"],
                    item[0]["total_rejected"], item[0]["count"],
                    item[0]["printed_difference"], item[0]["computed_difference"])
                   for item in parsed]
        if len(parsed) != 2 or vectors[0] != vectors[1]:
            raise ValueError("Texas reconciliation OCR statistical fields disagree")
        if not any(item[0]["native_total_role_evidence"]["counted_role_explicit"]
                   for item in parsed):
            raise ValueError("Texas reconciliation counted-parent role is unreadable")
        native, lines = parsed[0]
        ocr = {"passes": [view["receipt"] for view in views],
               "same_engine_resolution_check_not_independent_validation": True,
               "native_total_role_evidence": [
                   item[0]["native_total_role_evidence"] for item in parsed]}
        complete_ocr_views = [
            {"text": view["text"], "confidence": view["confidence"]}
            for view in views]
    compact = {"query": native, "private_original_pin": pin(body),
               "whole_publisher_pdf_redistributed": False,
               "reviewed_prior_native_role": {
                   "source_county": texas_reconciliation_role(template)["reviewed_source_county"],
                   "native_election_date": texas_reconciliation_role(
                       template)["reviewed_election_date"],
                   "native_measure_literal": template["measure"]["literal"],
               }}
    update = change(template, native["count"], compact, registered=None, clock=None,
                    rate_compatible=False)
    complete = {**native, "complete_first_page_lines": lines,
                "private_original_pin": pin(body)}
    if complete_ocr_views is not None:
        complete["complete_ocr_views"] = complete_ocr_views
    result = {"updates": [update], "complete_native_query": [complete],
              "geographic_joins_changed": False, "analytical_rates_promoted": False,
              "count_only_unknown_denominator_retained": True,
              "attestation_clock_not_reused_as_count_update_clock": True}
    if ocr is not None:
        result["ocr"] = ocr
    return result


def clock_value(literal):
    literal = literal.strip()
    try:
        return datetime.fromisoformat(literal)
    except ValueError:
        pass
    matches = list(REPORT_CLOCK.finditer(literal))
    if len(matches) == 1:
        literal = matches[0].group(0)
    literal = re.sub(r"(20[0-9]{2})(?=[0-9]{1,2}:)", r"\1 ", literal)
    literal = " ".join(literal.replace(" - ", " ").split()).upper()
    for format_string in ("%m/%d/%Y %I:%M:%S%p", "%m/%d/%Y %I:%M:%S %p",
                          "%m/%d/%Y %I:%M%p", "%m/%d/%Y %I:%M %p",
                          "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S",
                          "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(literal, format_string)
        except ValueError:
            pass
    raise ValueError("Unreviewed native report-clock format")


def pdf_text_statistics(page, templates, pages, confidence=None, tokens=None):
    if len({(row["geography"]["state_code"], row["geography"]["name"])
            for row in templates}) != 1:
        raise ValueError("A shared PDF county parent cannot stand in for multiple counties")
    lines = [" ".join(line.split()) for line in page.splitlines() if line.strip()]
    text = "\n".join(lines)
    if (not ELECTION_DATE.search(text)
            or not re.search(r"\bGeneral(?:\s+State)?\s+Election\b", text, re.I)
            or re.search(r"\b(?:TEST RESULTS|PRIMARY ELECTION|RUNOFF ELECTION)\b", text, re.I)):
        raise ValueError("Native statistical PDF election scope changed or needs visual review")
    if PRIVATE_HEADERS.search(text):
        raise ValueError("Individual/contact PDF is excluded from numerical intake")
    if (re.search(r"\b(?:Election Day|Early Voting|Absentee|Mail)\s+Only\b", text, re.I)
            or "Summary for:" in text and not re.search(
                r"Summary for:\s*All Contests,\s*All Districts,\s*All Tabulators", text, re.I)):
        raise ValueError("Native statistical PDF ballot-method/geography scope changed")
    clocks = {match.group(0).strip() for match in REPORT_CLOCK.finditer(text)}
    dates = re.findall(r"\bDate:\s*(\d{1,2}/\d{1,2}/20\d{2})\b", text)
    times = re.findall(r"\bTime:\s*(\d{1,2}:\d{2}:\d{2}\s*[AP]M(?:\s+[ECMP][SD]T)?)\b", text)
    if dates or times:
        if len(set(dates)) != 1 or len(set(times)) != 1:
            raise ValueError("Ambiguous native report Date/Time fields")
        clocks.add(dates[0] + " " + times[0])
    decoded_clocks = {clock_value(item): item for item in sorted(clocks)}
    if len(decoded_clocks) > 1:
        raise ValueError("Ambiguous native first-page report clocks")
    clock = next(iter(decoded_clocks.values()), None)
    updates, queries = [], []
    for template in templates:
        if template["count"]["status"] != "reported":
            continue
        if template["election"]["year"] != 2026 or template["election"]["type"] != "general":
            raise ValueError("Reviewed native PDF election scope changed")
        label = pdf_measure(template)
        name = template["geography"]["name"]
        if (template["geography"]["level"] != "county" or not label
                or not re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.I)):
            raise ValueError("Native PDF county scope requires an explicit reviewed parent")
        matches = []
        label_pattern = r"\s*-\s*".join(
            r"\s+".join(map(re.escape, part.split())) for part in label.split("-"))
        for position, line in enumerate(lines):
            inline = re.fullmatch(
                r"Registered\s+Voters\s+(" + COUNT_LITERAL + r")\s*-\s*Total\s+Ballots\s+("
                + COUNT_LITERAL + r")\s*:?\s*([0-9]+\.[0-9]+)%\s*-\s*Blank\s+Ballots\s+("
                + COUNT_LITERAL + r")\s+([0-9]+)\s+of\s+([0-9]+)\s+Precincts\s+Reporting\s+"
                r"([0-9]+\.[0-9]+)%", line, re.I)
            if inline and label == "Total Ballots":
                registered, value = (int(inline.group(i).replace(",", "")) for i in (1, 2))
                if (not registered or int(inline.group(4).replace(",", "")) > value
                        or int(inline.group(5)) > int(inline.group(6))
                        or (Decimal(value) * 100 / registered).quantize(
                            Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(inline.group(3))):
                    raise ValueError("Native inline ballot/register/blank statistics disagree")
                matches.append((position + 1, inline.group(2), inline.span(2)))
                continue
            fraction = re.fullmatch(re.escape(label) + r":\s*(" + COUNT_LITERAL
                + r")\s+of\s+(" + COUNT_LITERAL + r")\s+\(([0-9]+\.[0-9]+)%\)",
                line, re.I)
            if fraction:
                numerator, denominator = (int(fraction.group(i).replace(",", "")) for i in (1, 2))
                if not denominator or (Decimal(numerator) * 100 / denominator).quantize(
                        Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(fraction.group(3)):
                    raise ValueError("Native PDF statistical fraction disagrees")
                matches.append((position + 1, fraction.group(1), fraction.span(1)))
                continue
            match = re.fullmatch(label_pattern + r"\s+(" + COUNT_LITERAL
                                 + r")((?:\s+" + COUNT_LITERAL + r")*)"
                                 + r"(?:\s+[0-9]+\.[0-9]+%)?", line, re.I)
            if match:
                header = lines[:position]
                if any(re.search(r"\b(?:Election\s*Day|Absentee|Early\s*Voting)\b.*\bTOTAL\b",
                                 item, re.I) for item in header):
                    raise ValueError("Native statistical total is not the first count column")
                single_total = ("total" in label.lower()
                    and re.fullmatch(label_pattern + r"\s+" + COUNT_LITERAL, line, re.I))
                if not single_total and not any(TOTAL_HEADER.fullmatch(item) for item in header):
                    raise ValueError("Native statistical total column is not explicitly identified")
                components = match.group(2).split()
                if components and sum(int(item.replace(",", "")) for item in components) != int(
                        match.group(1).replace(",", "")):
                    raise ValueError("Native statistical ballot components disagree with total")
                matches.append((position + 1, match.group(1), match.span(1)))
        if len(matches) != 1:
            raise ValueError("Native PDF statistic is absent or ambiguous; no candidate-vote substitution")
        previous_clock = template["source_clock"]["literal"]
        if previous_clock:
            if clock is None or clock_value(clock) < clock_value(previous_clock):
                raise ValueError("Native PDF clock is missing or older than the reviewed observation")
        value = int(matches[0][1].replace(",", ""))
        registered = None
        denominator = template.get("denominator")
        registration_line = None
        if denominator and denominator["qualified"]:
            literal = denominator["literal"]
            pattern = r"\s*-\s*".join(
                r"\s+".join(map(re.escape, part.split())) for part in literal.split("-"))
            registrations = [(position, match) for position, line in enumerate(lines)
                             for match in [re.fullmatch(pattern + r"\s+(" + COUNT_LITERAL + r")",
                                                       line, re.I)] if match]
            if len(registrations) != 1:
                raise ValueError("A qualified PDF fraction requires its literal native register")
            position, registration_match = registrations[0]
            registered = int(registration_match.group(1).replace(",", ""))
            if not registered or value > registered:
                raise ValueError("Native PDF count exceeds its qualified register")
            registration_line = lines[position]
            if tokens is not None:
                start, end = registration_match.span(1)
                selected = [item["confidence"] for item in tokens[position]
                            if item["start"] < end and item["end"] > start]
                if not selected or min(selected) < .98:
                    raise ValueError("Native PDF register OCR confidence requires review")
            elif confidence is not None and confidence[position] < .98:
                raise ValueError("Native PDF register OCR confidence requires review")
        numeric_confidence = confidence[matches[0][0] - 1] if confidence is not None else None
        if tokens is not None:
            start, end = matches[0][2]
            selected = [item["confidence"] for item in tokens[matches[0][0] - 1]
                        if item["start"] < end and item["end"] > start]
            if not selected:
                raise ValueError("Native PDF OCR count has no physical token binding")
            numeric_confidence = min(selected)
        if numeric_confidence is not None and numeric_confidence < .98:
            raise ValueError("Native PDF count OCR confidence requires review")
        query = {"native_measure_literal": label, "native_count_literal": matches[0][1],
                 "count": value, "county": name, "page": 1, "statistic_line": matches[0][0],
                 "pdf_pages": pages, "pdf_report_clock_literal": clock,
                 "native_statistical_line": lines[matches[0][0] - 1],
                 "election_date": "2026-11-03", "native_scope": "county_statistical_parent",
                 "registered_denominator_not_refreshed": registered is None}
        if registered is not None:
            query.update(registered=registered, native_registration_line=registration_line)
        zone = re.search(r"\b(?:[ECMP][SD]T|UTC|GMT)\b", clock or "")
        query["pdf_report_timezone_literal"] = zone.group(0) if zone else None
        if numeric_confidence is not None:
            query["ocr_selected_count_minimum_confidence"] = numeric_confidence
        queries.append(query)
        updates.append(change(template, value, query, registered=registered, clock=clock,
                              rate_compatible=registered is not None))
    return {"updates": updates, "complete_native_query": queries,
            "geographic_joins_changed": False, "analytical_rates_promoted": False,
            "pdf_report_clock_is_not_certification": True}


def pdf_parent_statistics(body, templates):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(body))
    if reader.is_encrypted or not reader.pages or len(reader.pages) > 6000:
        raise ValueError("Unqualified native statistical PDF")
    page = reader.pages[0].extract_text(extraction_mode="layout")
    if page.strip():
        return pdf_text_statistics(page, templates, len(reader.pages))
    from scripts.results_pdf_ocr import first_page_views

    views = first_page_views(body)
    results = [pdf_text_statistics(view["text"], templates, len(reader.pages),
                                   view["confidence"], view.get("tokens")) for view in views]
    vectors = [[(row["id"], row["value"], row["registered"],
                 clock_value(row["clock"]) if row["clock"] else None)
                for row in result["updates"]]
               for result in results]
    if len(results) != 2 or vectors[0] != vectors[1]:
        raise ValueError("Native PDF OCR count/clock disagreement requires review")
    result = results[0]
    result["ocr"] = {"passes": [view["receipt"] for view in views],
                     "same_engine_resolution_check_not_independent_validation": True}
    return result


def summary_page_statistics(page, number, pages, profile):
    lines = [" ".join(line.split()) for line in page.splitlines() if line.strip()]
    if (PRIVATE_HEADERS.search(page) or len(lines) < 4
            or re.search(r"\b(?:TEST RESULTS|PRIMARY ELECTION|RUNOFF ELECTION)\b",
                         "\n".join(lines[:4]), re.I)):
        raise ValueError("Unqualified native summary page")
    if profile["layout"] == "repeated_header":
        scope = ("All Precincts, All Districts, All Counter Groups, All ScanStations, "
                 "All Contests, All Boxes")
        title = re.fullmatch(re.escape(profile["title"]) + r" (\d{4}-\d{2}-\d{2})", lines[1])
        counters = re.fullmatch(re.escape(scope) + r" (\d{2}:\d{2}:\d{2})", lines[2])
        parent = re.fullmatch(
            r"Total Ballots Cast: (" + COUNT_LITERAL + r"), Registered Voters: ("
            + COUNT_LITERAL + r"), Overall Turnout: ([0-9]+\.[0-9]+)%", lines[3])
        if (lines[0] != f"Statement of Votes Cast by Geography Page: {number} of {pages}"
                or not title or not counters or not parent):
            raise ValueError("Native summary election, whole-report scope or parent changed")
        value, registered = (int(parent.group(i).replace(",", "")) for i in (1, 2))
        fraction = parent.group(3)
        clock = title.group(1) + " " + counters.group(1)
        clock_value(clock)
        if not registered or (Decimal(value) * 100 / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(fraction):
            raise ValueError("Native summary parent fraction disagrees")
        return {"count": value, "registered": registered, "source_clock": clock,
                "native_fraction_literal": fraction + "%", "page": number}
    if profile["layout"] != "column_turnout":
        raise ValueError("Unreviewed native summary layout")
    title = re.fullmatch(re.escape(profile["title"]) + r" Page " + str(number), lines[0])
    clock = re.fullmatch(
        r"November 3, 2026 (Printed on: \d{2}/\d{2}/20\d{2} at \d{2}:\d{2}:\d{2} [ap]m)",
        lines[1])
    if not title or not clock or lines[2] != "SUMMARY REPORT" or not re.fullmatch(
            r"REPORT [0-9]+|FINAL", lines[3]):
        raise ValueError("Native summary election, administration or report clock changed")
    datetime.strptime(clock.group(1), "Printed on: %m/%d/%Y at %I:%M:%S %p")
    cells = {}
    for label in ("TOTAL REGISTRATION", "TOTAL TURNOUT", "Mail TURNOUT", "In-Person TURNOUT"):
        pattern = (r"(?<!\S)" + re.escape(label) + r"\s+(" + COUNT_LITERAL + r")"
                   + (r"\s+([0-9]+\.[0-9]+)%" if label != "TOTAL REGISTRATION" else "")
                   + r"\s*$")
        matches = [(index + 1, match) for index, line in enumerate(page.splitlines())
                   for match in [re.search(pattern, line)] if match]
        if len(matches) > 1:
            raise ValueError("Ambiguous native summary statistical parent")
        if matches:
            index, match = matches[0]
            cells[label] = {"value": int(match.group(1).replace(",", "")),
                            "column": match.start(), "line": index,
                            "fraction": match.group(2) if label != "TOTAL REGISTRATION" else None}
    if not cells:
        return {"source_clock": clock.group(1), "page": number,
                "native_report_status_literal": lines[3]}
    columns = [cell["column"] for cell in cells.values()]
    # Layout extraction shifts some same-column labels by one character.
    if len(cells) != 4 or max(columns) - min(columns) > 1:
        raise ValueError("Native summary statistical column is incomplete or misaligned")
    registered, value, mail, in_person = (cells[label]["value"] for label in (
        "TOTAL REGISTRATION", "TOTAL TURNOUT", "Mail TURNOUT", "In-Person TURNOUT"))
    if not registered or value != mail + in_person:
        raise ValueError("Native summary turnout components disagree")
    for label in ("TOTAL TURNOUT", "Mail TURNOUT", "In-Person TURNOUT"):
        if (Decimal(cells[label]["value"]) * 100 / registered).quantize(
                Decimal(".1"), rounding=ROUND_HALF_UP) != Decimal(cells[label]["fraction"]):
            raise ValueError("Native summary printed fraction disagrees")
    return {"count": value, "registered": registered, "source_clock": clock.group(1),
            "native_values": {label: cell["value"] for label, cell in cells.items()},
            "native_fraction_literal": cells["TOTAL TURNOUT"]["fraction"] + "%",
            "statistical_cells": cells, "page": number,
            "native_report_status_literal": lines[3]}


def summary_statistics(body, templates, profile):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(body))
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
        raise ValueError("Unqualified native summary PDF")
    queries = [summary_page_statistics(page.extract_text(extraction_mode="layout"),
               index + 1, len(reader.pages), profile) for index, page in enumerate(reader.pages)]
    parents = [query for query in queries if "count" in query]
    vectors = {(row["count"], row["registered"], row["source_clock"]) for row in parents}
    if (len(vectors) != 1 or len({row["source_clock"] for row in queries}) != 1
            or profile["layout"] == "column_turnout" and (
                len(parents) != 1
                or len({row["native_report_status_literal"] for row in queries}) != 1)):
        raise ValueError("Native summary repeated parents or clocks disagree")
    query = parents[0]
    clock_key = "native_pdf_clock" if profile["layout"] == "repeated_header" else "source_clock_literal"
    updates = []
    for template in templates:
        old = template["view"].get("native_record") or {}
        old_value = (old.get("native_ballots") if profile["layout"] == "repeated_header"
                     else (old.get("native_values") or {}).get("TOTAL TURNOUT"))
        if (template["geography"]["state_code"] != profile["state"]
                or template["geography"]["level"] != profile["level"]
                or template["geography"]["name"] != profile["name"]
                or template["election"]["year"] != 2026
                or template["election"]["type"] != "general"
                or template["measure"]["literal"] != profile["measure"]
                or old.get(profile["identity_field"]) != profile["identity"]
                or template["count"]["status"] != "reported"
                or count(old_value) != template["count"]["value"]
                or (template.get("denominator") or {}).get("qualified")):
            raise ValueError("Reviewed native summary identity, measure or qualification changed")
        previous = old.get(clock_key)
        if not isinstance(previous, str) or not template["source_clock"]["literal"].startswith(previous):
            raise ValueError("Reviewed native summary clock binding changed")
        if profile["layout"] == "repeated_header":
            if (old.get("selected_native_parent_literal") != "Total Ballots Cast:"
                    or old.get("source_role") != "native_registration_ballot_reported_turnout_statistics"):
                raise ValueError("Reviewed native summary parent role changed")
            current_clock, prior_clock = clock_value(query["source_clock"]), clock_value(previous)
            native = {"source_id": profile["identity"],
                      "source_role": old["source_role"],
                      "selected_native_parent_literal": "Total Ballots Cast:",
                      "native_ballots": query["count"], "native_registered": query["registered"],
                      "native_fraction_literal": query["native_fraction_literal"],
                      "native_global_parent_copies": len(parents)}
        else:
            if old.get("component_county_fips") != profile["component_county_fips"]:
                raise ValueError("Reviewed election-administration membership changed")
            current_clock, prior_clock = (datetime.strptime(literal,
                "Printed on: %m/%d/%Y at %I:%M:%S %p") for literal in (query["source_clock"], previous))
            native = {"source_administration_id": profile["identity"],
                      "administration": profile["name"],
                      "component_county_fips": old["component_county_fips"],
                      "native_values": query["native_values"],
                      "native_report_status_literal": query["native_report_status_literal"]}
        if current_clock < prior_clock:
            raise ValueError("Native summary edition regressed")
        native.update({clock_key: query["source_clock"], "query": query,
                       "native_fraction_literal": query["native_fraction_literal"],
                       "private_original_pin": pin(body),
                       "whole_publisher_html_redistributed": False})
        updates.append(change(template, query["count"], native, registered=query["registered"],
                              clock=query["source_clock"], rate_compatible=False))
    if not updates:
        raise ValueError("Native summary has no reviewed parent")
    return {"updates": updates, "complete_native_query": queries,
            "date": current_clock.isoformat(),
            "clock_qualification": "literal_native_report_clock_not_retrieval_or_certification",
            "geographic_joins_changed": False, "analytical_rates_promoted": False,
            "native_measure_not_relabelled_as_ballots": True}


def webforms_statistics(body, templates):
    text = body.decode("utf-8-sig")
    if not re.search(r">\s*GENERAL 2026\s*<", text) or not re.search(
            r">\s*November 3, 2026\s*<", text):
        raise ValueError("Native turnout HTML election scope changed")
    updated = re.search(r"Results last updated:</span><span>([^<]+)</span>", text)
    parent = re.search(
        r'header-ballot-number">(' + COUNT_LITERAL + r')</span><br /><span class="header-voter-text">'
        r'Eligible Voters</span><span class="header-voter-number">(' + COUNT_LITERAL + r')</span>', text)
    coverage = re.search(r'header-partial-number">(\d+)</span>.*?header-total-number">(\d+)</span>'
                         r'.*?header-totalprecincts-text">(\d+)</span>', text, re.S)
    if not updated or not parent or not coverage:
        raise ValueError("Native turnout HTML statistical header changed")
    clock = html.unescape(updated.group(1))
    current_clock = clock_value(clock)
    partial, reported, total = map(int, coverage.groups())
    if partial != 0 or reported != total:
        raise ValueError("Incomplete native turnout inventory requires review")
    sections = re.findall(r'<div class="col turnout-results-box-a">\s*<h1>(.*?)</h1>(.*?)(?='
                          r'<div class="col turnout-results-box-a">|</form>)', text, re.S)
    pattern = (r'<div class="(?:odd|even)">\s*<div class="county-precinct">(.*?)</div>\s*'
               r'<div class="county-cast">\s*<span>(' + COUNT_LITERAL + r')</span>\s*</div>\s*'
               r'<div class="county-counted">\s*<span>(' + COUNT_LITERAL + r')</span>')
    facts, identities = [], set()
    for label, block in sections:
        county = html.unescape(re.sub(r"<[^>]+>", "", label)).strip()
        identity = re.search(r'countyid="(\d+)"', block)
        rows = re.findall(pattern, block, re.S)
        declared_rows = len(re.findall(r'<div class="county-precinct">', block))
        if not identity or not rows or len(rows) != declared_rows:
            raise ValueError("Native turnout HTML has missing/unreadable statistical rows")
        children = []
        for unit, value, registered in rows:
            unit = html.unescape(re.sub(r"<[^>]+>", "", unit)).strip()
            key = identity.group(1), unit
            if not unit or key in identities:
                raise ValueError("Duplicate native county-scoped reporting unit")
            identities.add(key)
            children.append({"county_id": key[0], "county": county, "unit": unit,
                "geography_level": "reporting_unit", "count": int(value.replace(",", "")),
                "registered": int(registered.replace(",", "")), "source_clock": clock})
        facts.append({"county_id": identity.group(1), "county": county, "unit": "",
            "geography_level": "county", "count": sum(row["count"] for row in children),
            "registered": sum(row["registered"] for row in children), "source_clock": clock,
            "reported_units": len(children), "total_units": len(children)})
        facts.extend(children)
    if len(identities) != total:
        raise ValueError("Native turnout HTML reporting inventory changed")
    counties = [row for row in facts if row["geography_level"] == "county"]
    parent_count, parent_registered = (int(value.replace(",", "")) for value in parent.groups())
    if (sum(row["count"] for row in counties) != parent_count
            or sum(row["registered"] for row in counties) != parent_registered):
        raise ValueError("Native turnout HTML counties disagree with the separate state parent")
    expected = {}
    for template in templates:
        query = template["view"]["native_record"]["query"]
        if (template["geography"]["state_code"] != "NM" or template["election"]["year"] != 2026
                or template["election"]["type"] != "general" or query["query_id"] != "nm-all-turnout"):
            raise ValueError("Reviewed turnout HTML source/election scope changed")
        key = query["geography_level"], query["county_id"], query["unit"]
        expected.setdefault(key, []).append(template)
    observed = {(row["geography_level"], row["county_id"], row["unit"]): row for row in facts}
    if not expected or len(observed) != len(facts) or set(observed) != set(expected):
        raise ValueError("Reviewed turnout HTML native identities changed")
    updates = []
    for key, targets in expected.items():
        row = observed[key]
        for template in targets:
            old = template["view"]["native_record"]["query"]
            if row["county"] != old["county"] or row["unit"] != old["unit"]:
                raise ValueError("Literal native turnout HTML geography changed")
            if current_clock < clock_value(old["source_clock"]):
                raise ValueError("Native turnout HTML edition regressed")
            if template["count"]["status"] != "reported":
                continue
            query = {**row, "query_id": old["query_id"], "selector": old["selector"]}
            native = {"query": query, "private_original_pin": pin(body),
                      "whole_publisher_html_redistributed": False}
            updates.append(change(template, row["count"], native, registered=row["registered"],
                clock=clock, reported=row.get("reported_units"), total=row.get("total_units"),
                rate_compatible=bool(row["registered"] and row["count"] <= row["registered"])))
    facts.append({"geography_level": "state", "count": parent_count, "registered": parent_registered,
                  "source_clock": clock, "reported_units": reported, "total_units": total})
    return {"updates": updates, "complete_native_query": facts, "geographic_joins_changed": False,
            "native_measure_not_relabelled_as_ballots": True}


def source_plan(baseline):
    index = json.loads(baseline["index.json"])
    result = {}
    for state in sorted(index["states"]):
        templates = selected_records(baseline, state)
        sources = {}
        for template in templates:
            view = template.get("view") or {}
            url = view.get("source_url")
            if not isinstance(url, str):
                continue
            parsed = urlsplit(url)
            if (parsed.scheme != "https" or parsed.hostname in (
                    "raw.githubusercontent.com", "github.com", "www.themarginoferror.com",
                    "themarginoferror.com", "civicapi.org")
                    or parsed.hostname and parsed.hostname.endswith(".civicapi.org")
                    or NOT_RESULTS.search(parsed.path)):
                continue
            if (url == MN_URL or url.startswith(CT_ROOT)
                    or parsed.hostname == "er.ncsbe.gov"
                    or state == "AL" and parsed.path.lower().endswith(".zip")):
                continue
            profile = RECORD_PROFILES.get(url)
            workbook_profile = WORKBOOK_PROFILES.get(url)
            summary_profile = SUMMARY_PROFILES.get(url)
            native = view.get("native_record") or {}
            if summary_profile and state == summary_profile["state"]:
                adapter = "reviewed_summary_statistics"
            elif workbook_profile and state == workbook_profile["state"]:
                adapter = "reviewed_workbook_statistics"
            elif profile and state == profile["state"] and (
                    (native.get("query") or {}).get("query_id") == profile["query_id"]
                    or url == IN_URL and "VotersVoting" in native):
                adapter = "reviewed_record_statistics"
            elif (url == NM_URL and state == "NM"
                  and (native.get("query") or {}).get("query_id") == "nm-all-turnout"):
                adapter = "reviewed_webforms_statistics"
            elif texas_reconciliation_role(template):
                adapter = "reviewed_texas_reconciliation_parent"
            elif (template["geography"]["level"] == "county" and pdf_measure(template)
                  and (parsed.path.lower().endswith(".pdf") or "/DocumentCenter/View/" in parsed.path
                       or native.get("complete_native_pdf_pages") or native.get("pdf_metadata"))):
                adapter = "reviewed_pdf_county_parent"
            else:
                adapter = "unadapted_primary_product"
            key = state + "-registered-" + digest(url.encode())[:16]
            source = sources.setdefault(key, {"url": url, "adapter": adapter, "templates": []})
            if source["adapter"] != adapter:
                if source["adapter"] == "unadapted_primary_product":
                    source["adapter"] = adapter
                    source["templates"] = []
                else:
                    continue
            if adapter == "unadapted_primary_product" and source["templates"]:
                continue
            source["templates"].append(template)
        result[state] = sources
    return result


def collect_sources(collector, baseline):
    def collect_url(group):
        result = {}
        for identity, source in group:
            url, templates = source["url"], source["templates"]
            if source["adapter"] == "reviewed_record_statistics":
                def parse(body, templates=templates, profile=RECORD_PROFILES[url]):
                    return record_statistics(body, templates, profile)
            elif source["adapter"] == "reviewed_workbook_statistics":
                def parse(body, templates=templates, profile=WORKBOOK_PROFILES[url]):
                    return workbook_statistics(body, templates, profile)
            elif source["adapter"] == "reviewed_summary_statistics":
                def parse(body, templates=templates, profile=SUMMARY_PROFILES[url]):
                    return summary_statistics(body, templates, profile)
            elif source["adapter"] == "reviewed_pdf_county_parent":
                def parse(body, templates=templates):
                    return pdf_parent_statistics(body, templates)
            elif source["adapter"] == "reviewed_texas_reconciliation_parent":
                def parse(body, templates=templates):
                    return texas_reconciliation_statistics(body, templates)
            elif source["adapter"] == "reviewed_webforms_statistics":
                def parse(body, templates=templates):
                    return webforms_statistics(body, templates)
            else:
                def parse(body, url=url):
                    return {"updates": [], "factual_product": factual_tables(body, url),
                            "numerical_data_qualified": False,
                            "semantic_review_required_before_projection": True}
            entry = collector.capture(identity, transport_url(url), parse)
            entry["adapter"] = source["adapter"]
            entry["reviewed_record_count"] = len(templates)
            result[identity] = entry
        return result
    groups = {}
    for sources in source_plan(baseline).values():
        for identity, source in sources.items():
            groups.setdefault(transport_url(source["url"]), []).append((identity, source))
    result = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for entries in pool.map(collect_url, groups.values()):
            result.update(entries)
    return result
