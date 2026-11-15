"""Refresh reviewed single-measure county affiliation tables without filling blanks."""

import io
import re

from scripts.participation_intake.contract import pin
from scripts.results_granular import change


URL = (
    "https://oklahoma.gov/content/dam/ok/en/elections/"
    "absentee-in-person-totals-by-affiliation/2026-absentee-in-person-totals/"
    "absentee-inperson-totals-10312026.pdf"
)
PROFILES = {
    URL: {
        "state": "OK",
        "title": "MESA - Absentee In-person Totals by Affiliation",
        "election_date": "11/03/2026",
        "county_codes": [f"{number:02}" for number in range(1, 78)],
        "parent": ("99", "STATE"),
        "affiliations": ("Republican", "Democrat", "Libertarian", "Independent"),
        "footer": "ap2541",
        "measure": {
            "id": "native-absentee-in-person-ballots", "kind": "ballots_cast",
            "literal": "Absentee In-person", "mode": "in_person_early", "unit": "ballots",
        },
    },
}
INTEGER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"


def parse_pages(pages, profile):
    from scripts.results_native import REPORT_CLOCK, clock_value

    if len(pages) != len(profile["county_codes"]) + 1:
        raise ValueError("Native county report page inventory changed")
    rows = {}
    clocks = []
    for number, page in enumerate(pages, 1):
        lines = [" ".join(line.split()) for line in page.splitlines() if line.strip()]
        if len(lines) < 8 or not lines[0].startswith(profile["title"] + " "):
            raise ValueError("Native affiliation report heading changed")
        clock = lines[0][len(profile["title"]) + 1:]
        if not REPORT_CLOCK.fullmatch(clock):
            raise ValueError("Native affiliation report clock is missing")
        clocks.append(clock_value(clock))
        if (lines[1] != "Election Date: " + profile["election_date"]
                or lines[3:5] != ["Absentee", "Affiliation In-person"]
                or lines[-1] != f'{profile["footer"]} Page {number} of {len(pages)}'):
            raise ValueError("Native election, measure columns or page footer changed")
        county = re.fullmatch(r"County: ([0-9]{2}) (.+)", lines[2])
        if county is None or county[1] in rows:
            raise ValueError("Native county identity is missing or duplicated")
        printed = {}
        for line in lines[5:-2]:
            cell = re.fullmatch(r"(.+?) (" + INTEGER + r")", line)
            if cell is None or cell[1] not in profile["affiliations"] or cell[1] in printed:
                raise ValueError("Native affiliation count is missing, malformed or duplicated")
            printed[cell[1]] = {"literal": cell[2], "value": int(cell[2].replace(",", ""))}
        literal = lines[-2]
        if not printed or not re.fullmatch(INTEGER, literal):
            raise ValueError("Native county participation parent is missing")
        total = int(literal.replace(",", ""))
        if sum(item["value"] for item in printed.values()) != total:
            raise ValueError("Native affiliation cells disagree with the printed county total")
        rows[county[1]] = {
            "source_county_code": county[1], "source_county_literal": county[2],
            "source_county_code_is_not_declared_fips": True, "page": number,
            "count": total, "count_literal": literal,
            "total_in_person_absentee_ballots": total,
            "native_count_field": "Absentee In-person",
            "election_date_literal": profile["election_date"],
            "report_clock_literal": clock, "report_timezone": None,
            "categories": {name: printed.get(name) for name in profile["affiliations"]},
        }
    codes = set(profile["county_codes"])
    parent_code, parent_name = profile["parent"]
    if (set(rows) != codes | {parent_code}
            or rows[parent_code]["source_county_literal"] != parent_name
            or len(set(clocks)) != 1):
        raise ValueError("Native complete county/state inventory or report clocks disagree")
    parent = rows[parent_code]
    if sum(rows[code]["count"] for code in codes) != parent["count"]:
        raise ValueError("Native counties disagree with the separate printed statewide parent")
    return rows, {
        "county_rows": [rows[code] for code in profile["county_codes"]],
        "separate_printed_parent": parent,
        "missing_affiliation_cells_remain_unknown": True,
        "affiliations_are_administrative_accounting_not_candidate_choice": True,
        "county_totals_equal_printed_state_parent": True,
    }, parent["report_clock_literal"]


def statistics(body, templates, url):
    from pypdf import PdfReader
    from scripts.results_native import clock_value

    profile = PROFILES[url]
    reader = PdfReader(io.BytesIO(body))
    if reader.is_encrypted or len(reader.pages) != len(profile["county_codes"]) + 1:
        raise ValueError("Unqualified native county affiliation PDF")
    pages = [page.extract_text(extraction_mode="layout") for page in reader.pages]
    rows, queries, clock = parse_pages(pages, profile)
    if len(templates) != len(profile["county_codes"]):
        raise ValueError("Complete accepted county observation inventory is required")
    updates = []
    identities = set()
    for template in templates:
        view = template["view"]
        previous = view.get("native_record") or {}
        previous = previous.get("query", previous)
        code = previous.get("source_county_code")
        row = rows.get(code)
        if (code not in profile["county_codes"] or code in identities or row is None
                or previous.get("source_county_literal") != row["source_county_literal"]
                or template["geography"]["state_code"] != profile["state"]
                or template["geography"]["level"] != "county"
                or template["measure"] != profile["measure"]
                or template["election"]["year"] != 2026
                or template["election"]["type"] != "general"
                or template["count"]["status"] != "reported"
                or template.get("denominator") is not None
                or template["source"]["url"] != url or view.get("source_url") != url):
            raise ValueError("Reviewed county identity, mode, source or denominator changed")
        old_clock = previous.get("report_clock_literal")
        if not isinstance(old_clock, str) or clock_value(clock) < clock_value(old_clock):
            raise ValueError("Native affiliation report clock regressed or lost its prior binding")
        identities.add(code)
        native = {
            "statistical_pdf_layout": "county_affiliations", "query": row,
            "source_clock_literal": clock, "private_original_pin": pin(body),
            "retained_source_context_is_historical": True,
            "native_reporting_complete_qualified": False,
            "missing_affiliation_cells_remain_unknown": True,
            "early_mode_is_not_all_method_participation": True,
        }
        updates.append(change(template, row["count"], native, clock=clock))
    return {
        "updates": updates, "complete_native_query": queries,
        "geographic_joins_changed": False, "analytical_rates_promoted": False,
        "printed_state_parent_is_control_only_not_a_new_observation": True,
    }
