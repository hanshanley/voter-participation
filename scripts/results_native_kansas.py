"""Reviewed source-defined county turnout equation; not ballots or unique people."""

from decimal import Decimal, ROUND_HALF_UP
import re

from scripts.automatic_native_refresh import reviewed_measure_label
from scripts.participation_intake.contract import pin
from scripts.results_granular import change, factual_tables


PROFILE = {
    "state": "KS", "kind": "county_turnout_equation",
    "url": ("https://greeleycountyks.gov/documents/elections/"
            "official-general-election-results-2026-11-03.xlsx"),
    "sheets": ["OfficialNational,State,Co", "OfficialQuestions&Referenda"],
}
REVIEWED_INPUT_SHA = "7e7218dc2fa05cccf9cf03f8d0b38c9ca10958d40d3717a7af63c8e847156790"


def statistics(body, templates, profile, workbook):
    if profile != PROFILE or len(templates) != 1:
        raise ValueError("Reviewed county turnout workbook profile changed")
    template = templates[0]
    label = reviewed_measure_label(template)
    if (label is None or template["source"]["input_sha256"] != REVIEWED_INPUT_SHA
            or template["view"].get("source_url") != PROFILE["url"]
            or template["source"].get("selector") != {
                "cells": ["A1", "A2", "A3"],
                "selected_field": "A3 reported turnout total",
                "sheet": PROFILE["sheets"][0]}
            or template["count"] != {"value": 460, "literal": 460, "status": "reported"}
            or template["denominator"]["value"] != 853
            or template["source_clock"]["literal"] is not None):
        raise ValueError("Reviewed county turnout identity, measure or source frame changed")
    if [sheet["name"] for sheet in workbook] != PROFILE["sheets"]:
        raise ValueError("Reviewed county turnout worksheet inventory changed")
    selected = {}
    for row in workbook[0]["rows"]:
        for cell in row["cells"]:
            address = cell["address"]
            if address in ("A1", "A2", "A3"):
                if (address in selected or cell.get("formula") is not None
                        or not isinstance(cell["value"], str)):
                    raise ValueError("Native turnout statistics require literal unambiguous cells")
                selected[address] = cell["value"]
    if set(selected) != {"A1", "A2", "A3"}:
        raise ValueError("Native turnout statistics are missing, not zero")
    first = re.fullmatch(
        r"2026\s+General Election\s+([0-9]+)\s+Registered Voters\s*", selected["A1"])
    second = re.fullmatch(
        r"([0-9]+) voted\s+([0-9]+) provisionals\s+([0-9]+) counted\s+"
        r"([0-9]+) new registrant did not\.\s+([0-9]+\.[0-9]{2})% turnout",
        selected["A2"])
    third = re.fullmatch(
        r"MSD-([0-9]+)\s+GSD-([0-9]+)\s+HC-([0-9]+)=([0-9]+)\s+"
        r"([0-9]+) provisionals\s*=\s*([0-9]+)", selected["A3"])
    if first is None or second is None or third is None:
        raise ValueError("Native election, measure or turnout-equation literals changed")
    registered = int(first[1])
    voted, cast, counted, other = (int(second[index]) for index in range(1, 5))
    msd, gsd, hc, subtotal, repeated, total = (
        int(third[index]) for index in range(1, 7))
    fraction = second[5]
    if (msd + gsd + hc != subtotal or subtotal != voted or cast != counted + other
            or repeated != counted or voted + counted != total):
        raise ValueError("Native turnout components and provisional totals do not reconcile")
    if (registered <= 0 or total > registered
            or (Decimal(total) * 100 / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(fraction)):
        raise ValueError("Native turnout fraction no longer matches its qualified registered frame")
    query = {
        "source_url": PROFILE["url"], "source_pin": pin(body),
        "state_code": "KS", "county": "Greeley County",
        "election_year": 2026, "election_type": "general",
        "reviewed_election_date": "2026-11-03",
        "sheet": PROFILE["sheets"][0], "native_literals": selected,
        "registered_voters": registered, "voted_before_counted_provisionals": voted,
        "provisionals_cast": cast, "provisionals_counted": counted,
        "other_provisional_literal_count": other, "MSD": msd, "GSD": gsd, "HC": hc,
        "administrative_subtotal": subtotal, "counted_provisionals_repeated": repeated,
        "reported_turnout_total": total, "native_count_literal": third[6],
        "current_native_equation": selected["A3"],
        "native_fraction_literal": fraction + "%",
        "native_report_status_literal": None,
        "reviewed_measure_presentation_label": label,
        "native_count_update_clock": None, "native_timezone": None,
        "abbreviations_not_interpreted_as_voting_modes": True,
        "cast_ballot_count_qualified": False, "unique_voter_count_qualified": False,
        "eligible_population_turnout_qualified": False,
    }
    native = {
        **query, "query": query, "retained_source_context_is_historical": True,
        "native_reporting_complete_qualified": False,
    }
    return {
        "updates": [change(template, total, native, registered=registered,
                           clock=None, rate_compatible=True)],
        "complete_native_query": [query], "factual_product": factual_tables(body, PROFILE["url"]),
        "numerical_data_qualified": True, "geographic_joins_changed": False,
        "analytical_rates_promoted": False, "new_denominator_qualification": False,
        "native_count_clock_not_supplied": True,
        "edition_order_not_inferred_without_native_evidence": True,
        "coverage": {"county_totals": 1, "county_totals_declared": 105,
                     "other_counties_unknown": 104, "statewide_total_available": False},
    }
