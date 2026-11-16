"""Refresh the reviewed upright Cole precinct-statistics grid, not contest votes."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import io
import re

from scripts.participation_intake.contract import observation_id, pin
from scripts.results_granular import change


URL = (
    "https://www.colecounty.org/DocumentCenter/View/14460/"
    "November-3-2026-Unofficial-Turnout-and-Abstract"
)
PROFILES = {URL: {"state": "MO"}}
TARGET = "285437c7e43623bf5587f5c2eb2573ca"
REVIEWED_SHA = "c6ee3bf75d40d6827759123ce387896353d8715799be0ec4d69208fee4acd299"
MEASURE = {
    "id": "native-ballots-cast-statistics", "kind": "ballots_cast",
    "literal": "Ballots Cast", "mode": "source_defined", "unit": "source_reported_ballots",
}
LOCALITIES = (
    "Ward 1 Precinct 1", "Ward 1 Precinct 2", "Ward 1 Precinct 3",
    "Ward 2 Precinct 1", "Ward 2 Precinct 2", "Ward 2 Precinct 3",
    "Ward 3 Precinct 1", "Ward 3 Precinct 2", "Ward 3 Precinct 3",
    "Ward 4 Precinct 1", "Ward 4 Precinct 2",
    "Ward 5 Precinct 1", "Ward 5 Precinct 2", "Ward 5 Precinct 3",
    "Clark/Brazito", "Clark/Eugene", "Jefferson/Apache Flats", "Jefferson/CC General",
    "Jefferson/Expressway Rentals", "Jefferson/JC Fairgrounds", "Jefferson/Scott Station",
    "Liberty/Taos", "Marion/Centertown", "Marion/St. Martins", "Moreau/Lohman",
    "Moreau/Russellville", "Osage/St. Thomas", "Osage/Wardsville",
)
UNITS = LOCALITIES + ("ABSENTEE", "Total")
INTEGER = re.compile(r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)")


def require(condition, message):
    if not condition:
        raise ValueError("Cole statistical grid: " + message)


def compact(value):
    return re.sub(r"[\s,]+", "", value).upper()


def clock_value(value):
    try:
        return datetime.strptime(value, "%m/%d/%Y %I:%M:%S %p")
    except (TypeError, ValueError) as error:
        raise ValueError("Cole statistical grid: native clock is missing or changed") from error


def validate_template(template):
    source, geography = template["source"], template["geography"]
    number = source["selector"].get("row")
    require(type(number) is int and 1 <= number <= 30, "reviewed physical row is missing")
    label = UNITS[number - 1]
    parent = number == 30
    identity = "native:MO:cole" + ("" if parent else f":statistical-row-{number}")
    require(
        template["id"] == observation_id(
            "cole-native-turnout-20261113", "missouri-2026-11-03-general",
            identity, MEASURE["id"], MEASURE["mode"])
        and template["election"] == {
            "date": "2026-11-03", "id": "missouri-2026-11-03-general",
            "qualification": "native", "type": "general", "year": 2026}
        and geography["id"] == identity and geography["state_code"] == "MO"
        and geography["level"] == ("county" if parent else "reporting_unit")
        and geography["name"] == ("Cole County" if parent else label)
        and geography["join"]["status"] == "unreviewed"
        and template["measure"] == MEASURE and template["denominator"] is None
        and template["count"]["status"] == "reported"
        and source["id"] == "cole-native-turnout-20261113"
        and source["url"] == template["view"]["source_url"] == URL
        and source["input_sha256"] == REVIEWED_SHA
        and source["selector"] == {
            "native_unit": label, "physical_page": 1, "row": number,
            "table_id": "cole-complete-native-turnout-statistics"}
        and source["fields"]["native_unit"] == label
        and template["view"]["maps_approved"] is False,
        "reviewed identity, source selector, measure or qualification changed",
    )
    return number


def factual_query(view, source_pin):
    rows = view.get("role_cells")
    receipt = view.get("receipt", {})
    require(receipt.get("text_angle_classifier_enabled") is False
            and receipt.get("rotation_degrees") == 0,
            "the reviewed upright OCR mode is required")
    require(isinstance(rows, list) and len(rows) == 39, "complete first-page inventory changed")
    require(all(isinstance(row, list) and row for row in rows), "a physical line is missing")
    text = [[cell["text"] for cell in row] for row in rows]
    require(
        list(map(compact, text[1][:1])) == ["GENERALELECTION"]
        and list(map(compact, text[2])) == ["COLECOUNTYMISSOURI"]
        and list(map(compact, text[3][:1])) == ["TUESDAYNOVEMBER32026"]
        and list(map(compact, text[4])) == ["ELECTIONRESULTS"]
        and list(map(compact, text[5])) == ["PAGE1/1"]
        and list(map(compact, text[6])) == ["VOTERTURNOUTBYPRECINCT"]
        and list(map(compact, text[7])) == ["OFFICIALRESULTS"]
        and list(map(compact, text[8])) == [
            "PRECINCTS", "BALLOTSCAST", "REGISTEREDVOTERS", "%TURNOUT"]
        and len(rows[1]) == len(rows[3]) == 2,
        "native election, county, status, page or column declaration changed",
    )
    date, time = compact(text[1][1]), compact(text[3][1])
    require(re.fullmatch(r"DATE:\d{1,2}/\d{1,2}/2026", date) is not None
            and re.fullmatch(r"TIME:\d{1,2}:\d{2}:\d{2}[AP]M", time) is not None,
            "native Date/Time fields changed")
    require(min(rows[1][1]["confidence"], rows[3][1]["confidence"]) >= .98,
            "native report-clock confidence requires review")
    date, time = date.removeprefix("DATE:"), time.removeprefix("TIME:")
    clock = date + " " + time[:-2] + " " + time[-2:]
    clock_value(clock)
    header = rows[8]
    require(all(header[i]["right"] < header[i + 1]["left"] for i in range(3)),
            "physical column headers overlap or changed order")
    boundaries = [(header[i]["right"] + header[i + 1]["left"]) / 2 for i in range(3)]
    statistics = []
    for number, (label, cells) in enumerate(zip(UNITS, rows[9:]), 1):
        require(len(cells) == 4 and compact(cells[0]["text"]) == compact(label),
                "native row identity or complete cell inventory changed")
        for column, cell in enumerate(cells):
            center = (cell["left"] + cell["right"]) / 2
            require((column == 0 or center > boundaries[column - 1])
                    and (column == 3 or center < boundaries[column]),
                    "a statistical cell moved into a different physical column")
        require(all(INTEGER.fullmatch(cell["text"]) for cell in cells[1:3]),
                "a native count is missing, negative or ambiguous")
        require(min(cell["confidence"] for cell in cells[1:3]) >= .98,
                "native count/register confidence requires review")
        count, registered = (int(cell["text"].replace(",", "")) for cell in cells[1:3])
        literal = cells[3]["text"]
        require(re.fullmatch(r"[0-9]+\.[0-9]{2}%", literal) is not None
                and cells[3]["confidence"] >= .95,
                "native printed-percentage literal requires review")
        if registered:
            require((Decimal(count) * 100 / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP) == Decimal(literal[:-1]),
                "a printed row percentage disagrees with the source counts")
        else:
            require(count == 0, "positive count with a zero register requires review")
        statistics.append({
            "row": number, "native_unit": label, "count": count, "registered": registered,
            "native_fraction_literal": literal,
            "fraction_reconciliation": "matched" if registered else "undefined_zero_register",
            "native_unit_kind": "nongeographic_absentee" if label == "ABSENTEE"
                else "county_parent" if label == "Total" else "native_locality_label",
            "source_physical_line": number + 9, "source_ocr_cells": cells,
        })
    parent, absentee = statistics[-1], statistics[-2]
    require(sum(row["count"] for row in statistics[:-1]) == parent["count"],
            "locality plus separate absentee counts disagree with the printed parent")
    require(sum(row["registered"] for row in statistics[:-2]) == parent["registered"]
            and absentee["registered"] == parent["registered"],
            "locality register stocks or the repeated absentee register changed")
    common = {
        "county": "Cole County", "native_measure_literal": "Ballots Cast",
        "pdf_report_clock_literal": clock, "pdf_report_timezone_literal": None,
        "native_report_status_literal": "OFFICIAL RESULTS",
        "native_election_date": "2026-11-03",
    }
    for row in statistics:
        row.update(common)
    parent = statistics[-1]
    return {
        "contract": "participation.cole_native_statistical_grid.v1",
        "source": {"url": URL, **source_pin}, "qualification_source_sha256": REVIEWED_SHA,
        "statistics": statistics, "parent": parent,
        "native_column_headers": text[8], "native_header_ocr_cells": rows[:9],
        "source_clock": clock, "source_clock_timezone": None,
        "absentee_registration_is_repeated_not_additive": True,
        "native_rows_are_not_qualified_precinct_geometry": True,
        "native_status_is_not_independent_certification": True,
    }


def statistics(body, templates, url=URL, prior=None):
    from pypdf import PdfReader
    from scripts.results_pdf_ocr import first_page_views

    require(url == URL, "unreviewed source URL")
    require(len(templates) == 30, "all thirty reviewed statistical rows are required")
    selected = {validate_template(template): template for template in templates}
    require(set(selected) == set(range(1, 31)), "reviewed statistical rows are missing or duplicated")
    reader = PdfReader(io.BytesIO(body))
    require(not reader.is_encrypted and len(reader.pages) == 24,
            "original report page inventory changed")
    require(not reader.pages[0].extract_text(extraction_mode="layout").strip(),
            "a newly supplied text layer requires separate review")
    views = first_page_views(body, strict_role_alignment=True, text_angle_classifier=False)
    require(len(views) == 2 and [view["receipt"]["dpi"] for view in views] == [180, 240],
            "both reviewed OCR resolutions are required")
    queries = [factual_query(view, pin(body)) for view in views]
    def vector(query):
        return query["source_clock"], [
            (row["native_unit"], row["count"], row["registered"], row["native_fraction_literal"])
            for row in query["statistics"]]
    require(vector(queries[0]) == vector(queries[1]), "OCR count, register, fraction or clock disagreement")
    query = queries[0]
    clocks = [template["source_clock"]["literal"] for template in templates]
    if prior and prior.get("data") is not None:
        old = prior["data"]
        updates = old.get("updates")
        previous = old.get("complete_native_query")
        require(isinstance(updates, list) and len(updates) == 30
                and isinstance(previous, dict)
                and previous.get("contract") == query["contract"]
                and previous.get("source") == prior.get("source")
                and previous["source"]["url"] == URL
                and len(previous.get("statistics", [])) == 30,
                "last-good source, identity or numerical query binding changed")
        previous_updates = {update.get("id"): update for update in updates}
        require(len(previous_updates) == 30, "last-good identities are duplicated")
        for number, template in selected.items():
            old_query = previous["statistics"][number - 1]
            old_update = previous_updates.get(template["id"], {})
            require(old_query.get("row") == number
                    and old_query.get("native_unit") == UNITS[number - 1]
                    and old_update.get("native", {}).get("query") == old_query
                    and old_update.get("value") == old_query["count"]
                    and old_update.get("registered") == old_query["registered"]
                    and old_update.get("clock") == previous["source_clock"],
                    "last-good numerical rows are not query-bound")
        clocks.append(previous["source_clock"])
    require(all(clock_value(query["source_clock"]) >= clock_value(old) for old in clocks),
            "native clock regressed behind the reviewed or last-good report")
    query["ocr"] = {
        "passes": [view["receipt"] for view in views],
        "same_engine_resolution_check_not_independent_validation": True,
        "all_integer_cells_minimum_confidence": .98,
        "printed_fraction_minimum_confidence": .95,
    }
    updates = []
    for number, template in selected.items():
        row = query["statistics"][number - 1]
        native = {
            **row, "query": row, "retained_source_context_is_historical": True,
            "native_reporting_complete_qualified": False, "registered_denominator_not_refreshed": True,
        }
        updates.append(change(template, row["count"], native, registered=row["registered"],
                              clock=query["source_clock"], rate_compatible=False))
    return {
        "updates": updates,
        "complete_native_query": query,
        "geographic_joins_changed": False, "analytical_rates_promoted": False,
    }
