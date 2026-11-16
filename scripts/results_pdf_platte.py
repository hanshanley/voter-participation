"""Read the reviewed Platte turnout block, not its cover or adjacent proposition."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import io
import re

from scripts.participation_intake.contract import pin
from scripts.results_granular import change


URL = (
    "https://static1.squarespace.com/static/561e88cee4b06543191f1ad2/"
    "t/6af23af021c0b06150d541d1/1794259696860/11032026Official_Results.pdf"
)
PROFILES = {URL: {"state": "MO"}}
TARGET = "1e2b2d572acbe4b4078e1003055ddb23"
REVIEWED_SHA = "7a765178a6a277e67b5b3451117b08b41241d1aa60f3c46e42550c9be91d9982"
PAGE_INDEX = 20
CLOCK_REGION = (.8, 0, 1, .13)
UNITS = ("05 Parkville", "45 Parkville West", "ABSENTEE", "Total")
MEASURE = {
    "id": "ballots-cast", "kind": "ballots_cast", "literal": "Ballots Cast",
    "mode": "source_defined", "unit": "source_reported_count",
}
INTEGER = re.compile(r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)")


def require(condition, message):
    if not condition:
        raise ValueError("Platte statistical grid: " + message)


def compact(value):
    return re.sub(r"[\s,]+", "", value).upper()


def clock_value(value):
    return datetime.strptime(value, "%m/%d/%Y %I:%M:%S %p")


def validate_template(template):
    source, geography = template["source"], template["geography"]
    require(
        template["id"] == TARGET
        and template["election"] == {
            "date": "2026-11-03", "id": "mo-2026-11-03-general",
            "qualification": "native", "type": "general", "year": 2026}
        and geography["id"] == "native:MO:county:platte-county"
        and geography["level"] == "county" and geography["state_code"] == "MO"
        and geography["name"] == "Platte County"
        and geography["join"]["status"] == "unreviewed"
        and template["measure"] == MEASURE and template["denominator"] is None
        and template["count"]["status"] == "reported"
        and source["id"] == "mo-platte-official-20261113"
        and source["url"] == template["view"]["source_url"] == URL
        and source["input_sha256"] == REVIEWED_SHA
        and source["selector"] == {"physical_page": 20, "row": "Total"}
        and tuple(row["unit"] for row in source["fields"]["selected_physical_table"]) == UNITS
        and source["fields"]["visual_review_image"]["sha256"]
            == "027bc593028516045697a0273f979a9f08dde359a05e0fdc74a808d9b06a5aa0"
        and template["view"]["maps_approved"] is False,
        "reviewed source, selector, identity or qualification changed",
    )


def native_clock(view):
    rows = view["role_cells"]
    require(len(rows) == 3 and all(len(row) == 1 for row in rows),
            "native Date/Time region changed")
    date, time, folio = [compact(row[0]["text"]) for row in rows]
    require(re.fullmatch(r"DATE:\d{1,2}/\d{1,2}/20\d{2}", date) is not None
            and re.fullmatch(r"TIME:\d{1,2}:\d{2}:\d{2}[AP]MCST", time) is not None
            and folio == "PAGE20/26", "native clock, timezone or printed page changed")
    require(min(rows[0][0]["confidence"], rows[1][0]["confidence"]) >= .98,
            "native report-clock confidence requires review")
    date, time = date.removeprefix("DATE:"), time.removeprefix("TIME:").removesuffix("CST")
    clock = date + " " + time[:-2] + " " + time[-2:]
    clock_value(clock)
    return clock


def factual_query(view, clock_view, source_pin):
    for selected, region in ((view, None), (clock_view, list(CLOCK_REGION))):
        receipt = selected["receipt"]
        require(receipt.get("page") == PAGE_INDEX + 1
                and receipt.get("rotation_degrees") == 0
                and receipt.get("text_angle_classifier_enabled") is False
                and receipt.get("normalized_region") == region,
                "reviewed upright page or clock region changed")
    rows = view["role_cells"]
    require(len(rows) == 14 and all(rows), "reviewed statistical page inventory changed")
    text = [[cell["text"] for cell in row] for row in rows]
    require(
        compact(" ".join(text[0])) == "STATEMENTOFVOTESCAST"
        and len(rows[1]) == len(rows[2]) == 2
        and compact(text[1][0]) == "GENERALELECTION"
        and compact(text[2][0]) == "PLATTECOUNTYMISSOURI"
        and compact(" ".join(text[3])) == "NOVEMBER32026"
        and compact(" ".join(text[4])) == "11032026_1PAGE20/26"
        and list(map(compact, text[5])) == ["OFFICIALRESULTS"]
        and len(rows[6]) == 2 and compact(text[6][0]) == "TURNOUT"
        and list(map(compact, text[7][:5])) == ["REG.", "BALLOTS", "%", "REG.", "TOTAL"]
        and list(map(compact, text[8][:3])) == ["VOTERS", "CAST", "TURNOUTVOTERS"]
        and compact(" ".join(text[9])) == "JURISDICTIONWIDE",
        "election, county, folio, turnout declaration or adjacent-column roles changed",
    )
    clock = native_clock(clock_view)
    require(compact(text[1][1]) == compact(clock_view["role_cells"][0][0]["text"])
            and compact(text[2][1]) == compact(clock_view["role_cells"][1][0]["text"]),
            "full-page and clock-region readings disagree")
    header = rows[7][:4]
    require(all(header[i]["right"] < header[i + 1]["left"] for i in range(3)),
            "physical turnout columns overlap or changed order")
    boundaries = [(header[i]["right"] + header[i + 1]["left"]) / 2 for i in range(3)]
    statistics = []
    for label, cells in zip(UNITS, rows[10:]):
        lanes = [[], [], []]
        labels = []
        for cell in cells:
            center = (cell["left"] + cell["right"]) / 2
            if center < header[0]["left"]:
                labels.append(cell)
            elif center < boundaries[2]:
                lane = sum(center >= boundary for boundary in boundaries[:2])
                lanes[lane].append(cell)
        require(len(labels) == 1 and compact(labels[0]["text"]) == compact(label),
                "statistical row identity changed")
        require(len(lanes[1]) == 1 and all(len(lane) <= 1 for lane in lanes),
                "native turnout cell is missing or duplicated")
        absentee = label == "ABSENTEE"
        require((not lanes[0] and not lanes[2]) if absentee else all(lanes),
                "missing registration/percentage is not zero")
        integers = lanes[0] + lanes[1]
        require(all(INTEGER.fullmatch(cell["text"]) for cell in integers)
                and min(cell["confidence"] for cell in integers) >= .98,
                "count/register is unknown, ambiguous or below confidence threshold")
        count = int(lanes[1][0]["text"].replace(",", ""))
        registered = int(lanes[0][0]["text"].replace(",", "")) if lanes[0] else None
        fraction = lanes[2][0]["text"] if lanes[2] else None
        if fraction is not None:
            require(re.fullmatch(r"[0-9]+\.[0-9]{2}%", fraction) is not None
                    and lanes[2][0]["confidence"] >= .95,
                    "printed turnout fraction requires review")
            require((registered and (Decimal(count) * 100 / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP) == Decimal(fraction[:-1]))
                or registered == count == 0, "printed row fraction disagrees with counts")
        statistics.append({
            "native_unit": label, "count": count, "registered": registered,
            "native_fraction_literal": fraction,
            "source_ocr_cells": labels + [cell for lane in lanes for cell in lane],
            "county": "Platte County", "native_measure_literal": "Ballots Cast",
            "pdf_report_clock_literal": clock, "pdf_report_timezone_literal": "CST",
            "native_report_status_literal": "Official Results", "page": PAGE_INDEX + 1,
            "native_printed_page": 20, "election_date": "2026-11-03",
        })
    return {
        "contract": "participation.platte_native_statistical_grid.v1",
        "source": {"url": URL, **source_pin}, "qualification_source_sha256": REVIEWED_SHA,
        "statistics": statistics, "parent": statistics[-1], "source_clock": clock,
        "source_clock_timezone": "CST", "native_header_ocr_cells": rows[:10],
        "selected_rows_are_not_a_complete_county_partition": True,
        "adjacent_contest_votes_not_selected": True,
        "reviewed_selector_preserved_verbatim": {"physical_page": 20, "row": "Total"},
        "reviewed_physical_page": 21, "native_status_is_not_independent_certification": True,
    }


def statistics(body, templates, url=URL, prior=None):
    from pypdf import PdfReader
    from scripts.results_pdf_ocr import page_views

    require(url == URL and len(templates) == 1, "one reviewed county parent is required")
    template = templates[0]
    validate_template(template)
    reader = PdfReader(io.BytesIO(body))
    require(not reader.is_encrypted and len(reader.pages) == 27,
            "reviewed report page inventory changed")
    require(not reader.pages[PAGE_INDEX].extract_text(extraction_mode="layout").strip(),
            "new text layer requires separate review")
    options = {"page_index": PAGE_INDEX, "strict_role_alignment": True,
               "text_angle_classifier": False}
    views = page_views(body, **options)
    clocks = page_views(body, region=CLOCK_REGION, **options)
    require(len(views) == len(clocks) == 2
            and [view["receipt"]["dpi"] for view in views] == [180, 240]
            and [view["receipt"]["dpi"] for view in clocks] == [180, 240],
            "both reviewed page and clock-region resolutions are required")
    queries = [factual_query(view, clock, pin(body)) for view, clock in zip(views, clocks)]
    def vector(query):
        return query["source_clock"], [(row["native_unit"], row["count"], row["registered"],
                                       row["native_fraction_literal"]) for row in query["statistics"]]
    require(vector(queries[0]) == vector(queries[1]), "OCR count, fraction or clock disagreement")
    query = queries[0]
    previous_clocks = [template["source_clock"]["literal"]]
    if prior and prior.get("data") is not None:
        old = prior["data"]
        previous = old.get("complete_native_query")
        updates = old.get("updates")
        require(isinstance(previous, dict) and previous.get("contract") == query["contract"]
                and previous.get("source") == prior.get("source")
                and previous["source"]["url"] == URL
                and len(previous.get("statistics", [])) == 4
                and previous.get("parent") == previous["statistics"][-1]
                and isinstance(updates, list) and len(updates) == 1,
                "last-good source or complete query binding changed")
        update, = updates
        parent = previous["parent"]
        require(update.get("id") == TARGET and update.get("native", {}).get("query") == parent
                and update.get("value") == parent["count"]
                and update.get("registered") == parent["registered"]
                and update.get("clock") == parent["pdf_report_clock_literal"]
                    == previous["source_clock"],
                "last-good numerical facts are not query-bound")
        previous_clocks.append(previous["source_clock"])
    require(all(clock_value(query["source_clock"]) >= clock_value(old) for old in previous_clocks),
            "native clock regressed behind the reviewed or last-good report")
    query["ocr"] = {
        "passes": [view["receipt"] for view in views],
        "clock_region_passes": [view["receipt"] for view in clocks],
        "same_engine_resolution_check_not_independent_validation": True,
        "integer_and_clock_minimum_confidence": .98, "printed_fraction_minimum_confidence": .95,
    }
    parent = query["parent"]
    native = {
        **parent, "query": parent, "retained_source_context_is_historical": True,
        "native_reporting_complete_qualified": False, "registered_denominator_not_refreshed": True,
    }
    return {
        "updates": [change(template, parent["count"], native, registered=parent["registered"],
                           clock=query["source_clock"], rate_compatible=False)],
        "complete_native_query": query,
        "geographic_joins_changed": False, "analytical_rates_promoted": False,
    }
