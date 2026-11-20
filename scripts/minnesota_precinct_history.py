"""Reconcile Minnesota historical precinct participation workbooks."""

from collections import defaultdict
from io import BytesIO
import re
from zipfile import ZipFile

from scripts.participation_intake.contract import IntakeError, count

CONTROL_URL = ("https://www.sos.mn.gov/election-administration-campaigns/"
               "data-maps/historical-voter-turnout-statistics/")
# Media path, precinct inventory, statewide voters and same-day registrations.
EDITIONS = {
    "2016-11-08": ("www.sos.mn.gov/media/2806", 4120, 2968281, 353179),
    "2018-11-06": ("www.sos.mn.gov/media/3607", 4113, 2611365, 213999),
    "2020-11-03": ("www.sos.mn.gov/media/4373", 4110, 3292997, 259742),
    "2022-11-08": ("sos.mn.gov/media/5176", 4103, 2525873, 141095),
    "2024-11-05": ("www.sos.mn.gov/media/yt3llxwd", 4103, 3272414, 296287),
}
FIELDS = ("VTDID", "PCTNAME", "PCTCODE", "MCDNAME", "COUNTYNAME", "COUNTYCODE",
          "REG7AM", "EDR", "SIGNATURES", "AB_MB", "FEDONLYAB", "TOTVOTING")
RATE_HOLD = "pre_registration_excludes_same_day_registrants"
CSV = "participation-mn-historical-precinct-turnout.csv"
MAX_BYTES = 4_000_000


def route(election):
    return f"https://{EDITIONS[election][0]}/{election[:4]}-general-federal-state-results-by-precinct-official.xlsx"


def query(fields, precincts, county_roster, printed_total, election):
    _, expected_size, expected_voting, expected_edr = EDITIONS[election]
    allowed = (list(FIELDS), [*FIELDS, "PRESONLYAB"])
    if fields not in allowed or len(precincts) != expected_size:
        raise IntakeError("mn_inventory", "Unexpected Minnesota workbook fields or precinct inventory")
    if set(county_roster) != {str(i) for i in range(1, 88)}:
        raise IntakeError("mn_inventory", "Minnesota county roster is incomplete")
    if (any(not isinstance(n, str) or not n for n in county_roster.values())
            or len(set(county_roster.values())) != 87):
        raise IntakeError("mn_inventory", "Minnesota county names are not unique and complete")
    totals = defaultdict(lambda: [0, 0, 0])
    ids = set()
    sums = dict.fromkeys(fields[6:], 0)
    for row in precincts:
        if set(row) != set(fields):
            raise IntakeError("mn_schema", "Unexpected Minnesota precinct fields")
        key = str(row["COUNTYCODE"])
        p = row["PCTCODE"]
        if (key not in county_roster or not isinstance(row["COUNTYNAME"], str)
                or row["COUNTYNAME"].upper() != county_roster[key]
                or not isinstance(row["PCTNAME"], str) or not row["PCTNAME"].strip()
                or not isinstance(p, str) or not re.fullmatch(r"[0-9]{4}", p)
                or row["VTDID"] != f"27{int(key) * 2 - 1:03}{p}" or row["VTDID"] in ids):
            raise IntakeError("mn_precinct_identity", "Invalid or duplicate Minnesota precinct ID")
        ids.add(row["VTDID"])
        for field in sums:
            if type(row[field]) is not int or count(row[field]) is None:
                raise IntakeError("mn_count", f"Missing or non-integer Minnesota count: {field}")
            sums[field] += row[field]
        for i, field in enumerate(("TOTVOTING", "REG7AM", "EDR")):
            totals[key][i] += row[field]
    if (set(totals) != set(county_roster)
            or (sums["TOTVOTING"], sums["EDR"]) != (expected_voting, expected_edr)
            or (election[:4] in ("2016", "2018") and printed_total != sums)
            or (election[:4] not in ("2016", "2018") and printed_total is not None)):
        raise IntakeError("mn_state_control", "Minnesota precinct values disagree with statewide controls")

    def summary(name, voting, registration, edr):
        return {"county": name, "ballots_cast": voting, "registered": None,
                "registered_at_7am": registration, "same_day_registrations": edr,
                "rate_hold_reason": RATE_HOLD}

    return {"fields": fields, "precincts": precincts, "county_roster": county_roster,
            "printed_total": printed_total, "election_date": election, "control_url": CONTROL_URL,
            "counties": [summary(county_roster[k].title(), *totals[k]) for k in sorted(totals, key=int)],
            "total": summary("TOTAL", sums["TOTVOTING"], sums["REG7AM"], sums["EDR"]),
            "native_numerator": "total_voters", "registration_basis": "Pre-registered at 7 a.m.",
            "extraction_method": "official_precinct_workbook",
            "report_note": "Total people voting. No comparable all-voter registration denominator."}


def parse(body, election):
    from openpyxl import load_workbook

    if not 0 < len(body) <= MAX_BYTES:
        raise IntakeError("mn_workbook_size", "Minnesota workbook exceeds size bound")
    try:
        with ZipFile(BytesIO(body)) as archive:
            if len(archive.infolist()) > 100 or sum(x.file_size for x in archive.infolist()) > 40_000_000:
                raise ValueError("Workbook expansion exceeds reviewed bounds")
        workbook = load_workbook(BytesIO(body), read_only=True, data_only=True)
        try:
            sheet = workbook["Results" if election.startswith("2016-") else "Precinct-Results"]
            if sheet.max_row > 5000 or sheet.max_column > 200:
                raise ValueError("Workbook dimensions exceed reviewed bounds")
            rows = iter(sheet.values)
            header = next(rows)
            fields = [*FIELDS, *(["PRESONLYAB"] if "PRESONLYAB" in header else [])]
            if any(header.count(k) != 1 for k in fields):
                raise ValueError("Precinct participation column missing or repeated")
            definitions = {r[0]: r[1] for r in workbook["Fields"].iter_rows(max_row=200, max_col=2, values_only=True)}
            if (definitions.get("TOTVOTING") != "Number of voters casting ballots"
                    or "7AM" not in definitions.get("REG7AM", "")
                    or "when they vote" not in definitions.get("EDR", "")):
                raise ValueError("Participation definitions changed")
            roster = {}
            for code, *columns in workbook["Counties"].iter_rows(min_row=2, max_row=100, max_col=4, values_only=True):
                parts = [v for v in columns if v is not None]
                if code is None and not parts:
                    continue
                if code == "End of worksheet" and not parts and len(roster) == 87:
                    continue
                k = str(code)
                if (not re.fullmatch(r"[1-9][0-9]?", k) or k in roster or len(parts) != 2
                        or parts[1] != 27000 + 2 * int(k) - 1):
                    raise ValueError("Invalid county reference row")
                roster[k] = parts[0]
            indices = [header.index(k) for k in fields]
            records, total, finished = [], None, False
            for row in rows:
                rec = dict(zip(fields, (row[i] for i in indices)))
                if not any(value is not None for value in rec.values()):
                    continue
                if finished:
                    raise ValueError("Unexpected data after worksheet terminator")
                if rec["VTDID"] == "End of worksheet" and all(rec[k] is None for k in fields[1:]):
                    finished = True
                elif rec["VTDID"] == "TOTAL" or rec["COUNTYNAME"] == "TOTAL":
                    if total is not None:
                        raise ValueError("Duplicate printed total")
                    total = {k: rec[k] for k in fields[6:]}
                elif total is None:
                    records.append(rec)
                else:
                    raise ValueError("Unexpected precinct after worksheet total")
        finally:
            workbook.close()
    except Exception as error:
        raise IntakeError("mn_workbook_schema", str(error)) from error
    return query(fields, records, roster, total, election)
