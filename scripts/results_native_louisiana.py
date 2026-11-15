"""Parse Louisiana's official 2026 post-election participation statistics."""

import copy
from decimal import Decimal, ROUND_HALF_UP
import gzip
from html.parser import HTMLParser
import json
import re
from urllib.parse import urljoin

from scripts.native_tabular import xlsx
from scripts.participation_intake.contract import digest, encoded, pin


ELECTION_DATES_URL = (
    "https://voterportal.sos.la.gov/ElectionResults/ElectionResults/"
    "Data?blob=ElectionDates.htm"
)
STATE_INDEX_URL = (
    "https://electionstatistics.sos.la.gov/default.aspx?"
    "Stats=Post_Election_Statistics&Type=Statewide"
)
PARISH_INDEX_URL = (
    "https://electionstatistics.sos.la.gov/default.aspx?"
    "Stats=Post_Election_Statistics&Type=Parish"
)
STATE_XLSX_URL = (
    "https://electionstatistics.sos.la.gov/Data/Post_Election_Statistics/"
    "statewide/2026_1103_sta.xlsx"
)
PARISH_XLSX_URL = (
    "https://electionstatistics.sos.la.gov/Data/Post_Election_Statistics/"
    "parish/2026_1103_par.xlsx"
)
URLS = (
    ELECTION_DATES_URL,
    STATE_INDEX_URL,
    PARISH_INDEX_URL,
    STATE_XLSX_URL,
    PARISH_XLSX_URL,
)
FIELDS = {
    "D": "total",
    "E": "white",
    "F": "black",
    "G": "other_race",
    "H": "democrat_total",
    "I": "democrat_white",
    "J": "democrat_black",
    "K": "democrat_other_race",
    "L": "republican_total",
    "M": "republican_white",
    "N": "republican_black",
    "O": "republican_other_race",
    "P": "other_parties_total",
    "Q": "other_parties_white",
    "R": "other_parties_black",
    "S": "other_parties_other_race",
}
IDENTITY_PIN = "4065d8fea24e487ce119fcccd73c8d1affce4c11e8872a83ad0b0b5fe5a3e0e1"


class _Links(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(urljoin(self.base, href.strip()))


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate Louisiana JSON property")
        result[key] = value
    return result


def _rows(table):
    result = {}
    for native_row in table["rows"]:
        values = {}
        for cell in native_row["cells"]:
            column = re.sub(r"[0-9]+$", "", cell["address"])
            if column in values:
                raise ValueError("Duplicate Louisiana worksheet column")
            values[column] = cell["value"]
        result[native_row["row"]] = values
    return result


def _integer(value, label):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]+", value) is None:
        raise ValueError("Missing or invalid Louisiana count is not zero: " + label)
    return int(value)


def _percent(value, label):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]+(?:\.[0-9]{2})", value) is None:
        raise ValueError("Missing or invalid Louisiana native percentage: " + label)
    return value


def _expected_percent(value, registered):
    if registered == 0:
        return "0.00"
    return str(
        (Decimal(value) * Decimal(100) / Decimal(registered)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )


def _validate_vector(vector, label):
    registered = vector["registered_voters"]
    voting = vector["voters_participating"]
    percentage = vector["percent_voting"]
    for values, role in ((registered, "registration"), (voting, "participation")):
        if values["total"] != values["white"] + values["black"] + values["other_race"]:
            raise ValueError("Louisiana " + role + " race subtotal differs: " + label)
        if values["total"] != (
            values["democrat_total"]
            + values["republican_total"]
            + values["other_parties_total"]
        ):
            raise ValueError("Louisiana " + role + " party subtotal differs: " + label)
        for prefix in ("democrat", "republican", "other_parties"):
            if values[prefix + "_total"] != (
                values[prefix + "_white"]
                + values[prefix + "_black"]
                + values[prefix + "_other_race"]
            ):
                raise ValueError("Louisiana " + role + " party/race subtotal differs: " + label)
    for field in FIELDS.values():
        if voting[field] > registered[field]:
            raise ValueError("Louisiana participation exceeds registration: " + label)
        if percentage[field] != _expected_percent(voting[field], registered[field]):
            raise ValueError("Louisiana printed percentage differs from counts: " + label)


def _vector(rows, identity_row, voting_row, percentage_row, label):
    if rows.get(voting_row, {}).get("B") != "# VOTING":
        raise ValueError("Louisiana # VOTING row is absent: " + label)
    if rows.get(percentage_row, {}).get("B") != "% VOTING":
        raise ValueError("Louisiana % VOTING row is absent: " + label)
    vector = {
        "registered_voters": {
            field: _integer(rows.get(identity_row, {}).get(column), label + " registered " + field)
            for column, field in FIELDS.items()
        },
        "voters_participating": {
            field: _integer(rows.get(voting_row, {}).get(column), label + " voting " + field)
            for column, field in FIELDS.items()
        },
        "percent_voting": {
            field: _percent(rows.get(percentage_row, {}).get(column), label + " percent " + field)
            for column, field in FIELDS.items()
        },
    }
    _validate_vector(vector, label)
    return vector


def _sum_vectors(records, role):
    return {
        field: sum(record["native_vectors"][role][field] for record in records)
        for field in FIELDS.values()
    }


def _observation(identity, name, level, parent, vector, status):
    return {
        "native_id": identity,
        "native_name": name,
        "native_level": level,
        "parent_native_id": parent,
        "election": {
            "native_election_id": "344",
            "date": "2026-11-03",
            "type": "general",
        },
        "count": {
            "value": vector["voters_participating"]["total"],
            "status": "reported",
            "literal": "# VOTING",
            "role": "native_voters_participating",
            "candidate_votes_used": False,
            "ballot_returns_used": False,
            "ballots_counted_claimed": False,
        },
        "registration_stock": {
            "value": vector["registered_voters"]["total"],
            "status": "reported",
            "literal": "REGISTERED VOTERS / TOTAL",
            "basis": "source_post_election_registered_voters",
            "active_inactive_scope_literal": "Status Active and Inactive",
        },
        "native_percent_voting": vector["percent_voting"]["total"],
        "native_vectors": vector,
        "source_clock": {
            "literal": None,
            "timezone": None,
            "qualification": "No count update clock supplied by either workbook",
        },
        "reporting_status": {
            "source_status_literal": status["literal"],
            "official": status["official"],
            "complete": None,
            "source_scope_record_present": True,
            "source_file_availability_is_not_completion_or_certification": True,
        },
        "analytical_rate_promoted": False,
        "maps_approved": False,
        "geographic_identity": "native_louisiana_identifier_only",
    }


def _event(body):
    data = json.loads(body, object_pairs_hook=_object)
    dates = data.get("Dates", {}).get("Date")
    if not isinstance(dates, list):
        raise ValueError("Louisiana election inventory changed")
    selected = [
        row
        for row in dates
        if isinstance(row, dict)
        and row.get("PKElectionID") == "344"
        and row.get("ElectionDate") == "11/03/2026"
    ]
    if len(selected) != 1:
        raise ValueError("Louisiana 2026 general election declaration is absent or ambiguous")
    row = selected[0]
    required = {
        "DisplayTurnoutStats": "1",
        "PWPStatsExist": "1",
        "PostElectionStatsAvailable": "1",
        "RaceStatsExist": "1",
    }
    if any(row.get(key) != value for key, value in required.items()):
        raise ValueError("Louisiana declared post-election statistics availability changed")
    if row.get("ResultsOfficial") not in ("0", "1"):
        raise ValueError("Louisiana official/unofficial status is absent")
    return {
        "record": row,
        "official": row["ResultsOfficial"] == "1",
        "literal": "Official" if row["ResultsOfficial"] == "1" else "Unofficial",
    }


def _require_link(body, base, expected):
    parser = _Links(base)
    parser.feed(body.decode("utf-8", errors="strict"))
    if expected not in parser.links:
        raise ValueError("Louisiana declared workbook link is absent: " + expected)


def _physical_query(workbook):
    result = []
    for table in workbook:
        rows = []
        for native_row in table["rows"]:
            cells = []
            for cell in native_row["cells"]:
                if cell["value"] in (None, "") and cell["formula"] is None:
                    continue
                cells.append(
                    {
                        "address": cell["address"],
                        "value": cell["value"],
                        "formula": cell["formula"],
                        "storage_type": cell["storage_type"],
                    }
                )
            if cells:
                rows.append({"row": native_row["row"], "cells": cells})
        result.append({"name": table["name"], "member": table["member"], "rows": rows})
    return result


def _workbooks(state_body, parish_body, status):
    state_book = xlsx(state_body)
    parish_book = xlsx(parish_body)
    if len(state_book) != 9 or [table["name"] for table in state_book] != [
        "Sheet" + str(index) for index in range(1, 10)
    ]:
        raise ValueError("Louisiana statewide workbook inventory changed")
    if len(parish_book) != 64 or [table["name"] for table in parish_book] != [
        "Sheet" + str(index) for index in range(1, 65)
    ]:
        raise ValueError("Louisiana parish workbook inventory changed")
    for table in state_book:
        rows = _rows(table)
        if (
            rows.get(1, {}).get("A") != "Louisiana Secretary of State"
            or rows.get(3, {}).get("A") != "State Wide Post Election Statistical Report"
            or rows.get(5, {}).get("A") != "Election Date 11/03/2026 AND <ALL>"
        ):
            raise ValueError("Louisiana statewide workbook event declaration changed")
    state_rows = _rows(state_book[0])
    state_vector = _vector(state_rows, 11, 12, 13, "STATE")
    state = _observation("STATE", "Louisiana", "state", None, state_vector, status)
    state_parishes = {}
    for number in range(1, 65):
        row = 14 + (number - 1) * 3
        identity = "PAR " + str(number).zfill(2)
        if state_rows.get(row, {}).get("B") != identity:
            raise ValueError("Louisiana statewide parish inventory changed")
        state_parishes[identity] = _vector(
            state_rows, row, row + 1, row + 2, "statewide " + identity
        )

    parishes = []
    precincts = []
    for number, table in enumerate(parish_book, 1):
        rows = _rows(table)
        identity = "PAR " + str(number).zfill(2)
        name = rows.get(10, {}).get("B")
        if (
            rows.get(1, {}).get("A") != "Louisiana Secretary of State"
            or rows.get(3, {}).get("A") != "PostElection Statistics"
            or rows.get(5, {}).get("A")
            != "Election Date 11/03/2026 AND <ALL> AND Status Active and Inactive"
            or rows.get(11, {}).get("B") != identity
            or not isinstance(name, str)
            or not name
        ):
            raise ValueError("Louisiana parish workbook event or native identity changed")
        parish_vector = _vector(rows, 11, 12, 13, identity)
        if parish_vector != state_parishes[identity]:
            raise ValueError("Louisiana statewide and parish parent records differ")
        parish = _observation(identity, name, "parish", "STATE", parish_vector, status)
        parishes.append(parish)
        children = []
        for row in sorted(rows):
            if row <= 12 or rows[row].get("B") != "# VOTING":
                continue
            native_id = rows.get(row - 1, {}).get("B")
            if (
                not isinstance(native_id, str)
                or re.fullmatch(r"PAR [0-9]{2} W [A-Z0-9-]+ P [A-Z0-9-]+", native_id)
                is None
                or not native_id.startswith(identity + " ")
            ):
                raise ValueError("Louisiana native precinct identity changed")
            vector = _vector(rows, row - 1, row, row + 1, native_id)
            child = _observation(
                native_id, native_id, "precinct", identity, vector, status
            )
            children.append(child)
            precincts.append(child)
        if not children:
            raise ValueError("Louisiana parish has no reported native precinct records")
        for role in ("registered_voters", "voters_participating"):
            if _sum_vectors(children, role) != parish_vector[role]:
                raise ValueError("Louisiana precincts do not reconcile to parish: " + identity)

    for role in ("registered_voters", "voters_participating"):
        if _sum_vectors(parishes, role) != state_vector[role]:
            raise ValueError("Louisiana parishes do not reconcile to statewide totals")
    identities = [
        {
            "native_id": row["native_id"],
            "native_name": row["native_name"],
            "native_level": row["native_level"],
            "parent_native_id": row["parent_native_id"],
        }
        for row in [state, *parishes, *precincts]
    ]
    identity_pin = digest(encoded(identities))
    if IDENTITY_PIN != "TO_BE_FILLED" and identity_pin != IDENTITY_PIN:
        raise ValueError("Louisiana complete native identity frame changed")
    return {
        "state": state,
        "parishes": parishes,
        "precincts": precincts,
        "identity_pin": identity_pin,
        "physical_query": {
            "statewide_workbook": _physical_query(state_book),
            "parish_workbook": _physical_query(parish_book),
        },
    }


def statistics(bodies, prior=None):
    if set(bodies) != set(URLS):
        raise ValueError("Exactly the declared Louisiana source family is required")
    status = _event(bodies[ELECTION_DATES_URL])
    _require_link(bodies[STATE_INDEX_URL], STATE_INDEX_URL, STATE_XLSX_URL)
    _require_link(bodies[PARISH_INDEX_URL], PARISH_INDEX_URL, PARISH_XLSX_URL)
    parsed = _workbooks(bodies[STATE_XLSX_URL], bodies[PARISH_XLSX_URL], status)
    observations = [parsed["state"], *parsed["parishes"], *parsed["precincts"]]
    changed = []
    if prior is not None:
        if (
            prior.get("identity_pin") != parsed["identity_pin"]
            or prior.get("source_clock") != {"literal": None, "timezone": None}
        ):
            raise ValueError("Louisiana prior identity or no-clock qualification changed")
        old_status = prior.get("source_status", {}).get("official")
        if old_status is True and status["official"] is False:
            raise ValueError("Louisiana official source status regressed")
        previous = {
            row["native_id"]: row["count"]["value"]
            for row in prior.get("observations", [])
        }
        if set(previous) != {row["native_id"] for row in observations}:
            raise ValueError("Louisiana prior observation frame changed")
        changed = [
            {
                "native_id": row["native_id"],
                "previous": previous[row["native_id"]],
                "current": row["count"]["value"],
            }
            for row in observations
            if previous[row["native_id"]] != row["count"]["value"]
        ]
    result = {
        "contract": "participation.louisiana_native_candidate.v1",
        "source_status": status,
        "source_clock": {"literal": None, "timezone": None},
        "identity_pin": parsed["identity_pin"],
        "observations": observations,
        "state_observations": 1,
        "parish_observations": len(parsed["parishes"]),
        "precinct_observations": len(parsed["precincts"]),
        "reported_zero_observations": sum(
            row["count"]["value"] == 0 for row in observations
        ),
        "changed_counts": changed,
        "complete_native_query": {
            "event_inventory_record": status["record"],
            "selected_observations": observations,
            "physical_tables": parsed["physical_query"],
        },
        "source_roles": {
            "count": "# VOTING = native voters participating",
            "registration": "REGISTERED VOTERS / TOTAL = registration stock",
            "percentage": "% VOTING retained and count-validated, not promoted",
            "excluded": [
                "candidate vote totals",
                "ballot returns",
                "rounded percent multiplied by registration",
            ],
        },
        "integration_status": "controlled_onboarding_required",
        "canonical_updates": 0,
        "geographic_joins_changed": False,
        "maps_approved": False,
    }
    return result


def collect(acquire, prior=None):
    bodies = {}
    receipts = {}
    for url in URLS:
        body, receipt = acquire(url)
        bodies[url] = body
        receipts[url] = receipt
    return {"data": statistics(bodies, prior=prior), "receipts": receipts}


def assess_accepted_frame(body):
    raw = gzip.decompress(body) if body.startswith(b"\x1f\x8b") else body
    shard = json.loads(raw, object_pairs_hook=_object)
    if shard.get("state_code") != "LA":
        raise ValueError("Accepted frame is not Louisiana")
    selected = {
        identity
        for frame in shard.get("views", {}).values()
        for partition in ("counties", "precincts", "nongeographic")
        for identity in frame.get(partition, [])
    }
    records = shard.get("records")
    if not isinstance(records, list):
        raise ValueError("Accepted Louisiana records are absent")
    families = {}
    compatible = []
    for row in records:
        source_id = row.get("source", {}).get("id")
        key = (
            row.get("measure", {}).get("kind"),
            row.get("measure", {}).get("mode"),
            source_id,
        )
        families[key] = families.get(key, 0) + 1
        if (
            row.get("election", {}).get("year") == 2026
            and row.get("election", {}).get("type") == "general"
            and row.get("measure", {}).get("kind") == "voters_participating"
        ):
            compatible.append(row["id"])
    return {
        "accepted_frame": pin(body),
        "records": len(records),
        "selected_unique_records": len(selected),
        "selected_view_references": sum(
            len(frame.get(partition, []))
            for frame in shard.get("views", {}).values()
            for partition in ("counties", "precincts", "nongeographic")
        ),
        "families": [
            {
                "measure_kind": key[0],
                "measure_mode": key[1],
                "source_id": key[2],
                "records": value,
            }
            for key, value in sorted(families.items(), key=lambda item: str(item[0]))
        ],
        "compatible_voters_participating_slots": compatible,
        "compatible_slot_count": len(compatible),
        "controlled_onboarding_requirement": (
            "Create new reviewed state/parish/precinct observation identities for native "
            "# VOTING. Existing Louisiana records are early-activity or returned-activity "
            "contexts and cannot be relabeled or overwritten."
        ),
    }

