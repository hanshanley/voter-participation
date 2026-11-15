"""Refresh the reviewed Boston 2026 statement without changing accepted identities."""

from datetime import datetime
import hashlib
import re

from scripts.participation_intake.contract import pin
from scripts.results_granular import change


URL = (
    "https://www.boston.gov/sites/default/files/file/2026/11/"
    "2026-Unofficial-Statement-Of-Votes-Cast.pdf"
)
QUALIFICATION_SOURCE = {
    "bytes": 2761513,
    "sha256": "df0501d565dafedd17448bc0e4380a320548efc8c25e3150860cb5d265fad4b9",
}
SELECTED_CONTEXT = "SENATOR IN CONGRESS (Vote for 1)"
SUMMARY_MEASURE = {
    "id": "previously-reviewed-participation-count",
    "kind": "participation_reported",
    "literal": "Native Ballots Cast / Times Cast",
    "mode": "all_methods",
    "unit": "source_reported_count",
}
UNIT_MEASURE = {
    "id": "previously-reviewed-participation-count",
    "kind": "participation_reported",
    "literal": "Native Times Cast",
    "mode": "all_methods",
    "unit": "source_reported_count",
}
MIN_CLOCK = datetime(2026, 11, 4, 11, 39, 2)
PAGE_COUNT = 353
SUMMARY_PAGE_COUNT = 8
TEMPLATE_COUNT = 276
UNIT_COUNT = 275
STATISTICS_PAGE_DIGEST = "aca8d2855bcf6f2a432be9e81eeca8dd6c72ea7ca8ab9974120532098fbbdb8a"
CONTEXTS = {
    "SENATOR IN CONGRESS (Vote for 1)": (9, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "GOVERNOR & LIEUTENANT GOVERNOR (Vote for 1)": (27, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "ATTORNEY GENERAL (Vote for 1)": (45, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "SECRETARY OF STATE (Vote for 1)": (63, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "TREASURER (Vote for 1)": (81, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "AUDITOR (Vote for 1)": (99, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "REPRESENTATIVE IN CONGRESS SEVENTH DISTRICT (Vote for 1)": (117, 189, "1bb15d0c6fd5c06de34f9a17be536cce570f6c7dbfa4118643b0ebc2ec08f519"),
    "REPRESENTATIVE IN CONGRESS EIGHTH DISTRICT (Vote for 1)": (124, 86, "a12515ae73ce72bb94bd0694e7c2b2422efc317c0952f0600ff8bebc8c9d07e0"),
    "COUNCILLOR THIRD DISTRICT (Vote for 1)": (130, 35, "b9d5869d2d62814b7e68bb9a71ff71bf61e63da925132930ac8f8c1216c063b7"),
    "COUNCILLOR FOURTH DISTRICT (Vote for 1)": (132, 195, "db13fd976177f6d3bed21dda8677e749fdb1efe77ba9e94b369e374fee0d709e"),
    "COUNCILLOR SIXTH DISTRICT (Vote for 1)": (139, 45, "c7386076ff97fc1f35af996a175e0d620bf086e68dda5ed25564103e28a6bd44"),
    "SENATOR IN GENERAL COURT FIRST SUFFOLK DISTRICT (Vote for 1)": (141, 83, "6c072efadbbbb3776b5fcef3fc37154d631d7ae4306e5a53c7ab884a3c81c4b9"),
    "SENATOR IN GENERAL COURT SECOND SUFFOLK DISTRICT (Vote for 1)": (144, 73, "4290c8e52db610dbe2bc0103f4dd46b3a7d51eb86e861bf9ce8239251e51b17b"),
    "SENATOR IN GENERAL COURT THIRD SUFFOLK DISTRICT (Vote for 1)": (147, 37, "043e2e857ccda222d2f7059070c861b0b87a9596ceb3323c9cc632dc4fdf5dc1"),
    "SENATOR IN GENERAL COURT MIDDLESEX & SUFFOLK DISTRICT (Vote for 1)": (149, 8, "cd8e05709788d442accd6843b368834f3e6ce01bea9784bfa3eddca6e76f8817"),
    "SENATOR IN GENERAL COURT NORFOLK & SUFFOLK DISTRICT (Vote for 1)": (150, 39, "77082497adc617e773eac224084d4a763328310c0b54932c5712c72e95256cd5"),
    "SENATOR IN GENERAL COURT SUFFOLK & MIDDLESEX DISTRICT (Vote for 1)": (152, 35, "b9d5869d2d62814b7e68bb9a71ff71bf61e63da925132930ac8f8c1216c063b7"),
    "REPRESENTATIVE IN GENERAL COURT FIRST SUFFOLK DISTRICT (Vote for 1)": (156, 14, "cec033a9ac591a23e2984dc112e6750b907f3f0e4216d9daa7f5d04e29865f80"),
    "REPRESENTATIVE IN GENERAL COURT SECOND SUFFOLK DISTRICT (Vote for 1)": (157, 11, "69254c05562ff0408020bd0b140886f40dcdf4e83eec53c33cf46287337b6d34"),
    "REPRESENTATIVE IN GENERAL COURT THIRD SUFFOLK DISTRICT (Vote for 1)": (158, 16, "35671071bb3cfd2c08c47a04e68f9bb83524a748cdcdede17ec7372a195b6b12"),
    "REPRESENTATIVE IN GENERAL COURT FOURTH SUFFOLK DISTRICT (Vote for 1)": (159, 20, "268bc94f92dd574824e1a79f82104a2cc6fe8d0136a696f6a837050fcfae1403"),
    "REPRESENTATIVE IN GENERAL COURT FIFTH SUFFOLK DISTRICT (Vote for 1)": (161, 19, "7776bef19ed97d419925fda0569bd6637e58030311cec903c10ac0332ff0d135"),
    "REPRESENTATIVE IN GENERAL COURT SIXTH SUFFOLK DISTRICT (Vote for 1)": (162, 20, "fce1a7d66db95e89305417672314ae24eaac58e46601b48dfa4f7a1450e2c8e8"),
    "REPRESENTATIVE IN GENERAL COURT SEVENTH SUFFOLK DISTRICT (Vote for 1)": (163, 17, "6334d3d974ecc6559e1bef8350a7f3310f299245d3e71a07cc30f994bb53a1ba"),
    "REPRESENTATIVE IN GENERAL COURT EIGHTH SUFFOLK DISTRICT (Vote for 1)": (164, 18, "f4cff3eea8b60d38e918e8d9ac57fdb1ca91ca6406a21c9a41a6afde896cfd00"),
    "REPRESENTATIVE IN GENERAL COURT NINTH SUFFOLK DISTRICT (Vote for 1)": (165, 17, "f7a93fc49221a3e0812ff0142dafb84c15f686b6d77a8cf27966ee064e7a049a"),
    "REPRESENTATIVE IN GENERAL COURT TENTH SUFFOLK DISTRICT (Vote for 1)": (166, 22, "8ce463015748ddbc8d400f77f7380a915b5eab23d157b6c375d4cbf2bc473ae3"),
    "REPRESENTATIVE IN GENERAL COURT TWELFTH SUFFOLK DISTRICT (Vote for 1)": (168, 16, "ab19f4aa799c6534f5d675ffe2e2c1f35eb33341d4bbcacc69d21f150cdac72f"),
    "REPRESENTATIVE IN GENERAL COURT THIRTEENTH SUFFOLK DISTRICT (Vote for 1)": (169, 19, "75e8870fa7024fab1f36fb8128403c6e9b86f15b63e299aa823863fe70c74fbd"),
    "REPRESENTATIVE IN GENERAL COURT FOURTEENTH SUFFOLK DISTRICT (Vote for 1)": (170, 19, "09b1b1d55d6a9e6f6cd811d18a92e0c861c6b4b626eea0f4061bcd1eb9beb3ca"),
    "REPRESENTATIVE IN GENERAL COURT FIFTEENTH SUFFOLK DISTRICT (Vote for 1)": (171, 19, "e285773fb6c0ce16466ef7f4461703e6a0e017dded251e9f393032dd709928df"),
    "REPRESENTATIVE IN GENERAL COURT SEVENTEENTH SUFFOLK DISTRICT (Vote for 1)": (172, 15, "bd6534d0112181543ac8a47343016313327afd7e2431ccc3f397ca28e962dee4"),
    "REPRESENTATIVE IN GENERAL COURT EIGHTEENTH SUFFOLK DISTRICT (Vote for 1)": (173, 13, "46e5911b04131def9c65b0a1e57009476e72dcf6890313c8793786e905e23cd4"),
    "DISTRICT ATTORNEY SUFFOLK DISTRICT (Vote for 1)": (174, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "REGISTER OF PROBATE SUFFOLK COUNTY (Vote for 1)": (183, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "QUESTION 1 (Vote for 1)": (192, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "QUESTION 2 (Vote for 1)": (210, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "QUESTION 3 (Vote for 1)": (228, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "QUESTION 4 (Vote for 1)": (246, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "QUESTION 5 (Vote for 1)": (264, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "QUESTION 6 (Vote for 1)": (282, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "QUESTION 7 (Vote for 1)": (300, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "QUESTION 8 (Vote for 1)": (318, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
    "QUESTION 9 (Vote for 1)": (336, 275, "215b1fdeb0b990434a633c64474270609dc193e37e9d2fd5f4460935c055491b"),
}
WARD = re.compile(r"WARD ([0-9]+), PRECINCT ([0-9]+)")


def _normalized(value):
    return " ".join(value.split())


def _cell(text, page, box):
    fact = text(page, box)
    fact["decoded_text"] = _normalized(fact["decoded_text"])
    return fact


def _integer(native_pdf, cell):
    return native_pdf.count(cell)["value"]


def _line_middles(native_pdf, page, box):
    groups = []
    for glyph in sorted(native_pdf.select(page, box), key=lambda item: (
            (item["reading_bbox"][1] + item["reading_bbox"][3]) / 2,
            item["reading_bbox"][0], item["id"])):
        middle = (glyph["reading_bbox"][1] + glyph["reading_bbox"][3]) / 2
        matching = [index for index, group in enumerate(groups)
                    if abs(group[0] - middle) <= 1]
        if len(matching) > 1:
            raise ValueError("Ambiguous Boston physical reading line")
        if matching:
            index = matching[0]
            groups[index] = ((groups[index][0] + middle) / 2, groups[index][1] + [glyph])
        else:
            groups.append((middle, [glyph]))
    return [middle for middle, glyphs in groups
            if _normalized("".join(item["text"] for item in
                sorted(glyphs, key=lambda item: (item["reading_bbox"][0], item["id"]))))]


def _row_cells(native_pdf, page, middle, columns):
    top, bottom = middle - 5.2, middle + 5.2
    return {name: _cell(native_pdf.text, page, [left, top, right, bottom])
            for name, left, right in columns}


def _coverage(native_pdf, page, rows, left, right):
    if not rows:
        raise ValueError("Empty Boston native table page")
    selected = {tuple(identity) for row in rows for cell in row["source_cells"].values()
                for identity in cell["source_glyph_ids"]}
    top = min(row["reading_middle"] for row in rows) - 5.2
    bottom = max(row["reading_middle"] for row in rows) + 5.2
    uncovered = [glyph for glyph in native_pdf.select(page, [left, top, right, bottom])
                 if (glyph["text"].isdigit() or glyph["text"] in (",", "%"))
                 and tuple(glyph["id"]) not in selected]
    if uncovered:
        raise ValueError("An unselected Boston native numerical cell requires review")


def _physical_rows(native_pdf, page, columns, first_page):
    rows = []
    for middle in _line_middles(native_pdf, page, [15, 55 if first_page else 30, 130, 600]):
        cells = _row_cells(native_pdf, page, middle, columns)
        label = cells["native_unit"]["decoded_text"]
        if not (WARD.fullmatch(label) or label in (
                "BOSTON", "BOSTON - Total", "Cumulative", "Cumulative - Total")):
            continue
        rows.append({"page": page["page"], "reading_middle": middle,
                     "native_unit": label, "source_cells": cells})
    _coverage(native_pdf, page, rows, 15, columns[-1][2])
    return rows


def _vertical_text(native_pdf, page, box):
    glyphs = native_pdf.select(page, box)
    return "".join(glyph["text"] for glyph in sorted(glyphs, key=lambda item: (
        -(item["reading_bbox"][1] + item["reading_bbox"][3]) / 2,
        item["reading_bbox"][0], item["id"])))


def _parse_summary(native_pdf, pages):
    columns = (
        ("native_unit", 15, 130), ("registered_voters", 130, 190),
        ("voters_cast", 190, 245), ("turnout", 245, 300),
    )
    units, controls, headers = [], [], []
    for page in pages[:SUMMARY_PAGE_COUNT]:
        for row in _physical_rows(native_pdf, page, columns, page["page"] == 1):
            label, cells = row["native_unit"], row["source_cells"]
            match = WARD.fullmatch(label)
            if match:
                registered = _integer(native_pdf, cells["registered_voters"])
                voters_cast = _integer(native_pdf, cells["voters_cast"])
                if cells["turnout"]["decoded_text"] != "N/A":
                    raise ValueError("Boston summary native turnout literal changed")
                units.append({**row, "ward": match[1], "precinct": match[2],
                              "registered_voters": registered, "voters_cast": voters_cast,
                              "turnout_literal": "N/A"})
            elif any(cells[name]["decoded_text"] for name in
                     ("registered_voters", "voters_cast", "turnout")):
                if cells["turnout"]["decoded_text"] != "N/A":
                    raise ValueError("Boston summary control turnout literal changed")
                controls.append({**row,
                    "registered_voters": _integer(native_pdf, cells["registered_voters"]),
                    "voters_cast": _integer(native_pdf, cells["voters_cast"]),
                    "turnout_literal": "N/A"})
            else:
                headers.append(row)
    identities = [f"{row['ward']}:{row['precinct']}" for row in units]
    digest = hashlib.sha256("\n".join(sorted(identities)).encode()).hexdigest()
    if (len(units) != UNIT_COUNT or len(set(identities)) != UNIT_COUNT
            or digest != CONTEXTS[SELECTED_CONTEXT][2]):
        raise ValueError("Boston summary unit inventory changed")
    parents = [row for row in controls if row["native_unit"] == "BOSTON - Total"]
    cumulative = [row for row in controls if row["native_unit"] in ("Cumulative", "Cumulative - Total")]
    derived_voters_cast = sum(row["voters_cast"] for row in units)
    if (len(parents) != 2 or len(cumulative) != 2
            or any(row["registered_voters"] != 0
                   or row["voters_cast"] != derived_voters_cast
                   for row in parents)
            or any(row["registered_voters"] != 0 or row["voters_cast"] != 0
                   for row in cumulative)
            or parents[0]["voters_cast"] != parents[1]["voters_cast"]):
        raise ValueError("Boston separate native Voters Cast summary controls changed")
    return {"rows": units, "controls": controls, "headers": headers,
            "derived_voters_cast_sum": derived_voters_cast,
            "native_summary_registered": 0, "native_summary_turnout_literal": "N/A"}


def _parse_contexts(native_pdf, pages):
    columns = (
        ("native_unit", 15, 130), ("times_cast", 130, 195),
        ("registered_voters", 195, 255), ("blanks", 255, 320),
    )
    contexts = {name: {"native_context": name, "rows": [], "controls": [], "headers": [],
                       "statistics_pages": []} for name in CONTEXTS}
    headings, statistics_pages, current = [], [], None
    for page in pages[SUMMARY_PAGE_COUNT:]:
        heading = _normalized(native_pdf.text(page, [15, 35, 780, 65])["decoded_text"])
        if "(Vote for" in heading:
            if heading not in CONTEXTS:
                raise ValueError("Boston contest context inventory changed")
            current = heading
            headings.append((page["page"], heading))
        is_statistics = "TimesCast" in _vertical_text(
            native_pdf, page, [165, 55, 182, 145]).replace(" ", "")
        if not is_statistics:
            continue
        if current is None:
            raise ValueError("Boston statistical page lacks a native contest context")
        statistics_pages.append(page["page"])
        context = contexts[current]
        context["statistics_pages"].append(page["page"])
        for row in _physical_rows(native_pdf, page, columns, page["page"] == CONTEXTS[current][0]):
            label, cells = row["native_unit"], row["source_cells"]
            match = WARD.fullmatch(label)
            if match:
                context["rows"].append({**row, "ward": match[1], "precinct": match[2],
                    "times_cast": _integer(native_pdf, cells["times_cast"]),
                    "registered_voters": _integer(native_pdf, cells["registered_voters"]),
                    "blanks": _integer(native_pdf, cells["blanks"])})
            elif any(cells[name]["decoded_text"] for name in
                     ("times_cast", "registered_voters", "blanks")):
                context["controls"].append({**row,
                    "times_cast": _integer(native_pdf, cells["times_cast"]),
                    "registered_voters": _integer(native_pdf, cells["registered_voters"]),
                    "blanks": _integer(native_pdf, cells["blanks"])})
            else:
                context["headers"].append(row)
    expected_headings = [(values[0], name) for name, values in CONTEXTS.items()]
    if headings != expected_headings:
        raise ValueError("Boston native contest heading/page binding changed")
    digest = hashlib.sha256(",".join(map(str, statistics_pages)).encode()).hexdigest()
    if digest != STATISTICS_PAGE_DIGEST:
        raise ValueError("Boston statistical/candidate physical page roles changed")
    for name, context in contexts.items():
        expected_count, expected_digest = CONTEXTS[name][1:]
        identities = [f"{row['ward']}:{row['precinct']}" for row in context["rows"]]
        actual_digest = hashlib.sha256("\n".join(sorted(identities)).encode()).hexdigest()
        if (len(identities) != expected_count or len(set(identities)) != expected_count
                or actual_digest != expected_digest):
            raise ValueError("Boston native context reporting-unit inventory changed")
        parents = [row for row in context["controls"] if row["native_unit"] == "BOSTON - Total"]
        cumulative = [row for row in context["controls"]
                      if row["native_unit"] in ("Cumulative", "Cumulative - Total")]
        total = sum(row["times_cast"] for row in context["rows"])
        if (len(parents) != 2 or len(cumulative) != 2
                or any(row["times_cast"] != total or row["registered_voters"] != 0
                       for row in parents)
                or any(row["times_cast"] != 0 or row["registered_voters"] != 0
                       or row["blanks"] != 0 for row in cumulative)):
            raise ValueError("Boston native context controls do not reconcile")
        context.update(derived_times_cast_sum=total,
                       native_declaring_ballots_cast=parents[0]["times_cast"],
                       native_registered_voters=parents[0]["registered_voters"],
                       native_blank_total=parents[0]["blanks"])
    return contexts, statistics_pages


def factual_query(body):
    from scripts import native_pdf

    facts = native_pdf.read(body)
    pages = facts["pages"]
    if len(pages) != PAGE_COUNT:
        raise ValueError("Boston statement page inventory changed")
    clocks = []
    for number, page in enumerate(pages, 1):
        page_literal = _normalized(native_pdf.text(page, [15, 15, 100, 35])["decoded_text"])
        clock = _normalized(native_pdf.text(page, [650, 15, 780, 35])["decoded_text"])
        if page_literal != f"Page: {number} of {PAGE_COUNT}":
            raise ValueError("Boston statement physical page numbering changed")
        try:
            parsed = datetime.strptime(clock, "%m/%d/%Y %I:%M:%S %p")
        except ValueError as error:
            raise ValueError("Boston statement native clock format changed") from error
        clocks.append((clock, parsed))
    if len({literal for literal, parsed in clocks}) != 1 or clocks[0][1] < MIN_CLOCK:
        raise ValueError("Boston statement page clocks disagree or regressed")
    title = _normalized(native_pdf.text(pages[0], [200, 35, 600, 70])["decoded_text"])
    if title != "Unofficial Election Results - City of Boston State Election - November 3, 2026":
        raise ValueError("Boston statement election, title or geography changed")
    summary = _parse_summary(native_pdf, pages)
    contexts, statistics_pages = _parse_contexts(native_pdf, pages)
    return {
        "contract": "participation.boston_statement_complete_native_query.v1",
        "source": {"url": URL, **pin(body)},
        "qualification_source": QUALIFICATION_SOURCE,
        "election": {"date": "2026-11-03", "year": 2026, "type": "general",
                     "title": "Unofficial Election Results - City of Boston"},
        "source_clock": clocks[0][0],
        "native_report_status_literal": "Unofficial",
        "page_count": PAGE_COUNT,
        "physical_columns": {
            "summary": ["native_unit", "registered_voters", "voters_cast", "turnout"],
            "contexts": ["native_unit", "times_cast", "registered_voters", "blanks"],
        },
        "summary": summary,
        "contexts": list(contexts.values()),
        "statistics_pages": statistics_pages,
        "candidate_vote_pages_not_selected_as_participation": True,
        "source_count_repairs": 0,
        "automatic_geographic_or_model_qualification": False,
    }


def _source_bound(template):
    source = template["source"]
    return source["url"] == URL or (
        source["url"] == "https://www.themarginoferror.com/participation-local/MA.json.gz"
        and source.get("fields", {}).get("source_url") == URL)


def statistics(body, templates, url=URL):
    if url != URL:
        raise ValueError("Unreviewed Boston statement source")
    query = factual_query(body)
    contexts = {item["native_context"]: item for item in query["contexts"]}
    selected = contexts[SELECTED_CONTEXT]
    selected_rows = {(row["ward"], row["precinct"]): row for row in selected["rows"]}
    if len(templates) != TEMPLATE_COUNT:
        raise ValueError("Reviewed Boston template inventory changed")
    parent = [row for row in templates if row["geography"]["level"] == "municipality"]
    units = [row for row in templates if row["geography"]["level"] == "reporting_unit"]
    if len(parent) != 1 or len(units) != UNIT_COUNT:
        raise ValueError("Reviewed Boston parent/reporting-unit inventory changed")
    updates, identities = [], set()
    for template in templates:
        geography, native = template["geography"], template["view"].get("native_record") or {}
        if (template["id"] in identities or geography["state_code"] != "MA"
                or template["election"].get("date") != "2026-11-03"
                or template["election"]["year"] != 2026
                or template["election"]["type"] != "general"
                or template["count"]["status"] != "reported"
                or template.get("denominator") is not None
                or template["view"].get("source_url") != URL
                or not _source_bound(template)):
            raise ValueError("Reviewed Boston identity, source or analytical-rate hold changed")
        identities.add(template["id"])
        if geography["level"] == "municipality":
            previous = native.get("query", native)
            if (geography["name"] != "Boston" or template["measure"] != SUMMARY_MEASURE
                    or previous.get("selected_context") != SELECTED_CONTEXT
                    or previous.get("native_count_field") != "Ballots Cast / Times Cast"):
                raise ValueError("Reviewed Boston parent native measure binding changed")
            parent_query = {
                "label": "Boston", "selected_context": SELECTED_CONTEXT,
                "native_count_field": "Ballots Cast / Times Cast",
                "count": selected["native_declaring_ballots_cast"],
                "derived_selected_context_sum": selected["derived_times_cast_sum"],
                "native_summary_voters_cast": query["summary"]["derived_voters_cast_sum"],
                "native_summary_registered": query["summary"]["native_summary_registered"],
                "native_summary_turnout_literal": query["summary"]["native_summary_turnout_literal"],
                "native_report_status_literal": query["native_report_status_literal"],
                "source_clock": query["source_clock"],
            }
            value = parent_query["count"]
            native_query = parent_query
        else:
            previous = native.get("query", native)
            ward, precinct = previous.get("ward"), previous.get("precinct")
            if (template["measure"] != UNIT_MEASURE or not isinstance(ward, str)
                    or not isinstance(precinct, str)
                    or previous.get("native_context") != SELECTED_CONTEXT
                    or geography["name"] != f"Ward {ward}, Precinct {precinct}"):
                raise ValueError("Reviewed Boston reporting-unit native measure binding changed")
            row = selected_rows.get((ward, precinct))
            if row is None:
                raise ValueError("Reviewed Boston reporting-unit identity disappeared")
            native_query = {
                "city": "Boston", "ward": ward, "precinct": precinct,
                "native_label": row["native_unit"], "native_context": SELECTED_CONTEXT,
                "times_cast_literal": row["times_cast"],
                "registered_voters_literal": row["registered_voters"],
                "blanks_literal": row["blanks"], "source_page": row["page"],
                "source_clock": query["source_clock"],
                "native_report_status_literal": query["native_report_status_literal"],
                "source_cells": row["source_cells"],
            }
            value = row["times_cast"]
        update_native = {
            "statistical_pdf_layout": "boston_statement",
            "query": native_query,
            "source_clock_literal": query["source_clock"],
            "private_original_pin": pin(body),
            "native_report_status_literal": query["native_report_status_literal"],
            "native_reporting_complete_qualified": False,
            "retained_source_context_is_historical": True,
        }
        updates.append(change(template, value, update_native, clock=query["source_clock"],
                              rate_compatible=False))
    if len({update["id"] for update in updates}) != TEMPLATE_COUNT:
        raise ValueError("Reviewed Boston update identity inventory changed")
    return {
        "updates": updates,
        "complete_native_query": query,
        "source_clock": query["source_clock"],
        "geographic_joins_changed": False,
        "native_measure_not_relabelled_as_unique_voters_or_candidate_votes": True,
        "zero_native_registration_not_promoted_to_denominator": True,
        "native_reporting_complete_qualified": False,
        "retained_source_context_is_historical": True,
    }
