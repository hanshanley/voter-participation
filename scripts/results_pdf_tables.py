"""Refresh reviewed statistical PDF tables without assigning new source identities."""

import copy
from datetime import datetime
from decimal import Decimal
import io
import json
from pathlib import Path
import re

from scripts.participation_intake.contract import pin
from scripts.results_granular import change


LEGACY = {
    "id": "previously-reviewed-participation-count", "kind": "participation_reported",
    "literal": "Reported ballots (previously reviewed export label, not a new native qualification)",
    "mode": "source_defined", "unit": "source_reported_count",
}
PROFILES = {
    "https://outside.vermont.gov/dept/sos/Elections_Division/election_info_resources/"
    "elections_results_data/2026_general_election_voter_turnout.pdf": {
        "state": "VT", "layout": "reporting_parts", "units": 247, "measure": LEGACY},
    "https://s3.amazonaws.com/somervillema-live/s3fs-public/"
    "election-results-preliminary-20261103.pdf": {
        "state": "MA", "layout": "ward_columns", "parent": "Somerville", "units": 32,
        "measure": {**LEGACY, "literal": "Native BALLOTS CAST - TOTAL", "mode": "all_methods"}},
    "https://www.dover.nh.gov/Assets/government/open-government/election-information/"
    "2026-general-election/turnout/2025.11.03_VoterTurnout.pdf": {
        "state": "NH", "layout": "ward_rows", "parent": "Dover", "units": 6,
        "measure": {**LEGACY, "literal": "Native Total Ballots Cast"}},
    **{
        url: {"state": "WV", "layout": "county_summary", "parent": name, "units": 0,
              "measure": {**LEGACY, "literal": "Native Ballots Cast \u00b7 independent county snapshot",
                          "mode": "all_methods"}}
        for url, name in (
            ("https://woodcountywv.com/files/docs/county-offices/county-clerk/"
             "election-voting-information/2026general/2026gen.pdf", "Wood County"),
            ("https://kanawha.us/wp-content/uploads/2026/11/Q-Final.pdf", "Kanawha County"))
    },
}
INTEGER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
PERCENT = r"[0-9]+(?:\.[0-9]+)?%"


def integer(value):
    if not isinstance(value, str) or not re.fullmatch(INTEGER, value):
        raise ValueError("A complete native integer cell is required")
    return int(value.replace(",", ""))


def fraction(numerator, denominator, literal):
    if not re.fullmatch(PERCENT, literal):
        raise ValueError("Native percentage literal changed")
    if denominator <= 0 or numerator > denominator:
        return "unqualified_native_fraction"
    printed = Decimal(literal[:-1])
    tolerance = Decimal(".5") * Decimal(10) ** printed.as_tuple().exponent
    if abs(Decimal(numerator) * 100 / denominator - printed) > tolerance:
        raise ValueError("Native statistical percentage disagrees")
    return "matched"


def lines(page):
    return [" ".join(value.split()) for value in page.splitlines() if value.strip()]


def only(pattern, text):
    matches = re.findall(pattern, text)
    if len(matches) != 1:
        raise ValueError("Native statistical declaration is absent or ambiguous")
    return matches[0]


def county_summary(pages, profile):
    from scripts.results_native import REPORT_CLOCK, clock_value

    queries, clocks = [], []
    for number, page in enumerate(pages, 1):
        text = "\n".join(lines(page))
        if not (text.startswith("Summary Results Report")
                and re.search(r"(?m)^General Election$", text)
                and re.search(r"(?m)^November 3, 2026(?: " + re.escape(profile["parent"])
                              + r", WV)?$", text)
                and re.search(r"\b" + re.escape(profile["parent"]) + r", WV\b", text)
                and len(re.findall(r"\bUNOFFICIAL RESULTS\b", text)) == 1):
            raise ValueError("Native county PDF election, geography or status changed")
        # Layout extraction can place the status and county beside the heading.
        footer = only(r"(?m)^(Election Summary - [^\n]+)$", text)
        clock = only(REPORT_CLOCK.pattern, footer)
        clocks.append(clock_value(clock))
        if not re.search(r"(?:Page )?" + str(number) + r" of " + str(len(pages)) + r"$", footer):
            raise ValueError("Native county PDF page inventory changed")
        queries.append({"page": number, "source_clock": clock,
                        "native_report_status_literal": "UNOFFICIAL RESULTS"})
    if len(set(clocks)) != 1:
        raise ValueError("Native county PDF page clocks disagree")
    text = "\n".join(lines(pages[0]))
    statistics = text.split("Statistics TOTAL", 1)
    if len(statistics) != 2:
        raise ValueError("Native county statistical column is missing")
    # Candidate rows and their Total Votes Cast are never participation parents.
    block = statistics[1].split("Election Summary -", 1)[0]
    block = re.split(r"(?m)^(?:FOR |Vote For )", block)[0]
    values = {}
    for label, key in (("Registered Voters - Total", "registered"),
                       ("Ballots Cast - Total", "count"), ("Ballots Cast - Blank", "blank")):
        values[key] = integer(only(r"(?m)^" + re.escape(label) + r"\s+(" + INTEGER + r")$", block))
    pct = only(r"(?m)^Voter Turnout - Total\s+(" + PERCENT + r")$", block)
    if values["blank"] > values["count"]:
        raise ValueError("Native blank ballots exceed the printed parent")
    fraction(values["count"], values["registered"], pct)
    counters = {}
    for label, reported, total in re.findall(
            r"(?m)^([A-Za-z/ ]+?)\s+([0-9]+) of ([0-9]+)$", block):
        if label in counters or int(reported) > int(total):
            raise ValueError("Native county reporting counters are ambiguous")
        counters[label] = {"reported": int(reported), "total": int(total)}
    if not {"Election Day Precincts Reporting", "Absentee/ Early Precincts Reporting"} <= set(counters):
        raise ValueError("Native county reporting scope is missing")
    if ("Precincts Complete" in counters) != ("Precincts Partially Reported" in counters):
        raise ValueError("Incomplete native complete/partial counter pair")
    if "Precincts Complete" in counters:
        complete, partial = counters["Precincts Complete"], counters["Precincts Partially Reported"]
        if complete["total"] != partial["total"] or complete["reported"] + partial["reported"] != complete["total"]:
            raise ValueError("Native complete/partial reporting counters disagree")
    query = {"label": profile["parent"], **values, "source_clock": queries[0]["source_clock"],
             "native_fraction_literal": pct, "native_report_status_literal": "UNOFFICIAL RESULTS",
             "reporting_counters": counters, "native_count_field": "Ballots Cast - Total",
             "page": 1}
    return {profile["parent"]: query}, {"statistics": [query], "pages": queries}, query["source_clock"]


def ward_columns(pages, profile):
    rows = [lines(page) for page in pages]
    title = "Somerville UnOfficial Election Totals - Tuesday November 3, 2026"
    groups = [["1", "2", "3", "4", "4A"], ["1", "1A", "2", "3", "4"],
              ["1", "2", "3", "4"], ["1", "2", "2A", "3", "4"],
              ["1", "2", "3", "4"], ["1", "2", "3", "3A", "4"],
              ["1", "2", "3", "4"]]
    headings = "Precinct " + " ".join(
        " ".join(group + ["TOTAL"]) for group in groups) + " Total"
    for number, page in enumerate(rows, 1):
        if (page[0] != title or page[1] != "Ward 1 Ward 2 Ward 3 Ward 4 Ward 5 Ward 6 Ward 7 Grand"
                or page[2] != headings
                or page[-1] != f"Tuesday, November 3, 2026 Page {number} of {len(pages)}"):
            raise ValueError("Native ward-column PDF election, units or page headers changed")
    parsed = {}
    text = "\n".join(rows[0])
    for label, field in (("REGISTERED VOTERS - TOTAL", "registered"),
                         ("BALLOTS CAST - TOTAL", "count")):
        values = only(r"(?m)^" + re.escape(label) + r" (" + INTEGER
                      + r"(?: " + INTEGER + r")*)$", text).split()
        if len(values) != profile["units"] + 8:
            raise ValueError("Native statistical row is missing a ward or grand-total cell")
        parsed[field] = [integer(value) for value in values]
    result, wards, position = {}, [], 0
    for ward, group in enumerate(groups, 1):
        children = []
        for precinct in group:
            label = f"Ward {ward}, Precinct {precinct}"
            query = {"label": label, "ward": str(ward), "precinct": precinct,
                     **{field: values[position] for field, values in parsed.items()},
                     "page": 1, "column": position + 1}
            children.append(query)
            result[f"{ward}:{precinct}"] = query
            position += 1
        parent = {"label": f"Ward {ward}",
                  **{field: values[position] for field, values in parsed.items()},
                  "page": 1, "column": position + 1}
        for field in parsed:
            if sum(row[field] for row in children) != parent[field]:
                raise ValueError("Native ward statistical cells do not reconcile")
        wards.append(parent)
        position += 1
    parent = {"label": profile["parent"], **{field: values[-1] for field, values in parsed.items()},
              "page": 1, "column": position + 1}
    if any(sum(row[field] for row in wards) != parent[field] for field in parsed):
        raise ValueError("Native ward and city parents do not reconcile")
    result[profile["parent"]] = parent
    for query in result.values():
        query["native_report_status_literal"] = "UnOfficial"
    return result, {"statistics": list(result.values()), "ward_parents": wards,
                    "native_report_status_literal": "UnOfficial", "source_clock": None}, None


def ward_rows(body, profile):
    import fitz

    with fitz.open(stream=body, filetype="pdf") as document:
        if len(document) != 1:
            raise ValueError("Native ward-row PDF page inventory changed")
        page = document[0]
        raw = page.get_text("text")
        native_words = page.get_text("words")
    words = [value.strip() for value in raw.splitlines() if value.strip()]
    text = " ".join(words)
    ballot_header = ("Ward Polling Place Ballots Absentee Ballots Total Ballots Cast "
                     "All Registered Voters Turnout")
    registration_header = (
        "Ward Checklist Registered Republicans New Republican Registrations Checklist Registered "
        "Democratic New Democratic Registrations Checklist Registered Undeclared New Undeclared "
        "Registrations All Checklist Registered Voters Total New Voters Registrations "
        "Checklist and Election Registered Voters")
    if ("REGISTERED VOTERS/TURNOUT" not in text
            or "NOVEMBER 3, 2026 GENERAL ELECTION" not in text
            or "City of Dover, New Hampshire" not in text
            or words.count("Turnout") != 1
            or ballot_header not in text or registration_header not in text
            or "* Turnout is total ballots cast divided by total checklist and election day registered voters"
            not in text):
        raise ValueError("Native ward-row PDF election or denominator description changed")
    start = words.index("Turnout") + 1
    ballot_words = words[start:start + 7 * 6]
    if len(ballot_words) != 42:
        raise ValueError("Native ward ballot cells are incomplete")
    result = {}
    for position in range(7):
        row = ballot_words[position * 6:(position + 1) * 6]
        ward = str(position + 1) if position < 6 else "TOTAL"
        if row[0] != ward:
            raise ValueError("Native ward-row identity changed")
        polling, absentee, total, registered = map(integer, row[1:5])
        if polling + absentee != total:
            raise ValueError("Native ward ballot-method components disagree")
        fraction(total, registered, row[5])
        label = "Ward " + ward if position < 6 else profile["parent"]
        result[label] = {"label": label, "ward": ward, "polling_place": polling,
                         "absentee": absentee, "count": total, "registered": registered,
                         "native_fraction_literal": row[5], "native_report_status_literal": None,
                         "page": 1, "native_count_field": "Total Ballots Cast"}
    for field in ("polling_place", "absentee", "count", "registered"):
        if sum(row[field] for key, row in result.items() if key != profile["parent"]) != result[profile["parent"]][field]:
            raise ValueError("Native ward and city statistical parents disagree")
    if only(r"VOTER TURNOUT (" + PERCENT + r")", text) != result[profile["parent"]]["native_fraction_literal"]:
        raise ValueError("Native city headline and ballot-table percentages disagree")
    fields = ("checklist_republican", "new_republican", "checklist_democratic",
              "new_democratic", "checklist_undeclared", "new_undeclared",
              "all_checklist_registered", "total_new_registrations", "registered")
    start = words.index("Voters", words.index("Checklist and")) + 1
    registration_words = words[start:start + 70]
    registrations = []
    for position in range(7):
        row = registration_words[position * 10:(position + 1) * 10]
        ward = str(position + 1) if position < 6 else "TOTAL"
        if len(row) != 10 or row[0] != ward:
            raise ValueError("Native registration row identity or columns changed")
        values = dict(zip(fields, map(integer, row[1:])))
        if (sum(values["checklist_" + key] for key in ("republican", "democratic", "undeclared"))
                != values["all_checklist_registered"]
                or sum(values["new_" + key] for key in ("republican", "democratic", "undeclared"))
                != values["total_new_registrations"]
                or values["all_checklist_registered"] + values["total_new_registrations"]
                != values["registered"]):
            raise ValueError("Native registration components disagree")
        label = "Ward " + ward if position < 6 else profile["parent"]
        if values["registered"] != result[label]["registered"]:
            raise ValueError("Native ballot and registration tables disagree")
        registrations.append({"ward": ward, **values})
    if any(sum(row[field] for row in registrations[:-1]) != registrations[-1][field]
           for field in fields):
        raise ValueError("Native registration parents disagree")
    # Bind every digit to its physical column, including Dover's adjacent 647/32 cells.
    for top, bottom, boundaries, expected in (
            (205, 295, (140, 180, 250, 305, 362, 425, 480), ballot_words),
            (440, 530, (30, 65, 130, 195, 245, 305, 360, 420, 475, 535, 590),
             registration_words)):
        selected = [word for word in native_words if top <= (word[1] + word[3]) / 2 < bottom
                    and boundaries[0] <= (word[0] + word[2]) / 2 < boundaries[-1]]
        anchors = sorted(word[1] for word in selected if
                         boundaries[0] <= (word[0] + word[2]) / 2 < boundaries[1])
        if len(anchors) != 7:
            raise ValueError("Native ward physical row inventory changed")
        physical = []
        for anchor in anchors:
            for left, right in zip(boundaries, boundaries[1:]):
                cell = [word[4] for word in selected if abs(word[1] - anchor) < 1
                        and left <= (word[0] + word[2]) / 2 < right]
                if len(cell) != 1:
                    raise ValueError("Native ward physical statistical column changed")
                physical.extend(cell)
        if physical != expected:
            raise ValueError("Native ward text reading and physical cells disagree")
    return result, {"statistics": list(result.values()), "registrations": registrations,
                    "registration_affiliation_is_not_vote_choice": True, "source_clock": None}, None


def reporting_parts(body):
    from scripts.native_pdf import project, read, text
    from scripts.pdf_group_queries import build

    spec = json.loads(Path(__file__).with_name("results_pdf_grids.json").read_bytes())
    facts = read(body)
    source = spec["source"]
    if len(facts["pages"]) != source["expected_pages"]:
        raise ValueError("Native reporting-part PDF page inventory changed")
    literal = text(facts["pages"][0], spec["clock_box"])["decoded_text"]
    datetime.strptime(literal, "%m/%d/%Y")
    tables = []
    for original in source["grids"]:
        grid = copy.deepcopy(original)
        page = facts["pages"][grid["page"] - 1]
        if text(page, spec["clock_box"])["decoded_text"] != literal:
            raise ValueError("Native reporting-part PDF page clocks disagree")
        grid["source_annotations"]["native_report_date"] = literal
        tables.append(project(facts, grid))
    # A new zero-valued row outside a reviewed band must not disappear.
    for page in facts["pages"]:
        selected = {tuple(identity) for table in tables if table["source_page"] == page["page"]
                    for row in table["rows"] for cell in row["cells"].values()
                    for identity in cell["source_glyph_ids"]}
        for glyph in page["glyphs"]:
            box = glyph["reading_bbox"]
            if (glyph["text"].isdigit() and 20 <= (box[0] + box[2]) / 2 < 590
                    and 180 <= (box[1] + box[3]) / 2 < 750
                    and tuple(glyph["id"]) not in selected):
                raise ValueError("An unselected native numerical reporting row requires review")
    grids = {"contract": "participation.reviewed_pdf_factual_grids.v1",
             "products": [{"source": {"id": source["id"]}, "tables": tables}]}
    grouped = build(grids, spec["grouping"])
    query = grouped["queries"]
    fields = spec["grouping"]["count_fields"]
    for parent in query["parent_controls"]["rows"]:
        children = [row for row in query["parts"]["rows"] if row["parent"] == parent["parent"]]
        peer, = [row for row in query["summary_parents"]["rows"] if row["parent"] == parent["parent"]]
        if any(sum(row[field] for row in children) != parent[field] or peer[field] != parent[field]
               for field in fields):
            raise ValueError("Native reporting parts and printed county controls disagree")
    total, = query["summary_total"]["rows"]
    if any(sum(row[field] for row in query["summary_parents"]["rows"]) != total[field]
           for field in fields) or any(row["status"] == "discrepancy" for row in grouped["native_rate_checks"]):
        raise ValueError("Native reporting summaries or printed percentages disagree")
    result = {}
    for row in query["grouped_units"]["rows"]:
        name = row["native_unit"]
        if name in result:
            raise ValueError("Native town identity is ambiguous across parent counties")
        parts = [part for part in query["parts"]["rows"]
                 if part["parent"] == row["parent"] and part["native_unit"] == name]
        result[name] = {**row, "label": name, "count": row["total_votes_cast_includes_absentee"],
                        "registered": row["registered_voters"], "source_parts": parts}
    return result, {"groups": grouped, "factual_grids": grids}, literal


def statistics(body, templates, url):
    from pypdf import PdfReader
    from scripts.results_native import REPORT_CLOCK, clock_value

    profile = PROFILES[url]
    reader = PdfReader(io.BytesIO(body))
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
        raise ValueError("Unqualified statistical PDF")
    if profile["layout"] == "reporting_parts":
        rows, queries, clock = reporting_parts(body)
    elif profile["layout"] == "ward_rows":
        rows, queries, clock = ward_rows(body, profile)
    else:
        pages = [page.extract_text(extraction_mode="layout") for page in reader.pages]
        parser = county_summary if profile["layout"] == "county_summary" else ward_columns
        rows, queries, clock = parser(pages, profile)
    if clock is None and any(REPORT_CLOCK.search(page.extract_text()) for page in reader.pages):
        raise ValueError("A newly supplied native update clock requires separate qualification")
    def key(template):
        name = template["geography"]["name"]
        if profile["layout"] != "ward_columns" or name == profile["parent"]:
            return name
        native = template["view"].get("native_record") or {}
        native = native.get("query", native)
        ward, precinct = native.get("ward"), native.get("precinct")
        if not (isinstance(ward, str) and isinstance(precinct, str)
                and name in (f"Ward {ward}, Precinct {precinct}", f"Ward {ward}, Subprecinct {precinct}")):
            raise ValueError("Reviewed native ward/precinct identity is missing")
        return ward + ":" + precinct
    expected_names = {key(template) for template in templates}
    if (len(templates) != profile["units"] + (profile["layout"] != "reporting_parts")
            or len(expected_names) != len(templates) or expected_names != set(rows)):
        raise ValueError("Reviewed PDF statistical unit inventory changed")
    updates = []
    for template in templates:
        name = template["geography"]["name"]
        source = template["source"]
        legacy = ("https://www.themarginoferror.com/participation-local/"
                  + profile["state"] + ".json.gz")
        source_bound = source["url"] == url or (
            source["url"] == legacy and source.get("fields", {}).get("source_url") == url)
        level = ("county" if profile["layout"] == "county_summary" else "municipality"
                 if profile["layout"] == "reporting_parts" or name == profile.get("parent")
                 else "reporting_unit")
        if (template["geography"]["state_code"] != profile["state"]
                or template["geography"]["level"] != level
                or template["measure"] != profile["measure"]
                or template["election"]["year"] != 2026
                or template["election"]["type"] != "general"
                or template["count"]["status"] != "reported"
                or not source_bound
                or template["view"].get("source_url") != url):
            raise ValueError("Reviewed PDF identity, measure or source binding changed")
        previous = template["view"].get("native_record") or {}
        previous_clock = previous.get("source_clock_literal") if previous.get(
            "statistical_pdf_layout") else template["source_clock"]["literal"]
        if clock is not None:
            current_value = (datetime.strptime(clock, "%m/%d/%Y") if profile["layout"] == "reporting_parts"
                             else clock_value(clock))
            old_value = (datetime.strptime(previous_clock, "%m/%d/%Y")
                         if profile["layout"] == "reporting_parts" else clock_value(previous_clock))
            if current_value < old_value:
                raise ValueError("Native PDF statistical report clock regressed")
        query = rows[key(template)]
        if profile["layout"] == "reporting_parts":
            old_parts = previous.get("source_parts") or []
            identity = lambda row: (row["parent"], row["native_unit"],
                                    " ".join(row["rep_district"].split()),
                                    " ".join(row["senate_district"].split()))
            if sorted(map(identity, old_parts)) != sorted(map(identity, query["source_parts"])):
                raise ValueError("Native legislative reporting-part identities changed")
        native = {"statistical_pdf_layout": profile["layout"], "query": query,
                  "source_clock_literal": clock, "private_original_pin": pin(body),
                  "native_reporting_complete_qualified": False,
                  "retained_source_context_is_historical": True}
        if "native_report_status_literal" in query:
            native["native_report_status_literal"] = query["native_report_status_literal"]
        if profile["layout"] == "reporting_parts":
            native["source_parts"] = query["source_parts"]
        if "native_fraction_literal" in query:
            native.update(native_fraction_literal=query["native_fraction_literal"],
                          native_report_status_literal=query["native_report_status_literal"])
        denominator = template.get("denominator")
        compatible = (profile["layout"] == "reporting_parts" and denominator is not None
                      and denominator["qualified"] and denominator["value"] == query["registered"])
        updates.append(change(template, query["count"], native,
                              registered=query["registered"], clock=clock, rate_compatible=compatible))
    return {"updates": updates, "complete_native_query": queries, "source_clock": clock,
            "native_missing_clock_is_not_retrieval_date": clock is None,
            "geographic_joins_changed": False, "analytical_rates_promoted": False}
