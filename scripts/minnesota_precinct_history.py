"""Reconcile Minnesota historical precinct participation workbooks."""

from collections import defaultdict
from io import BytesIO
import re
from zipfile import ZipFile

from scripts.participation_intake.contract import IntakeError, count

CONTROL_URL = ("https://www.sos.mn.gov/election-administration-campaigns/"
               "data-maps/historical-voter-turnout-statistics/")
LEGACY_CONTROL = "https://www.sos.mn.gov/media/gevnwetp/minnesota-election-statistics-1950-to-2024.pdf"
# Media path, precinct inventory, statewide voters and same-day registrations.
EDITIONS = {
    "1994-11-08": ("sos.mn.gov/media/1977", 4033, 1794618, 179360),
    "1996-11-05": ("sos.mn.gov/media/1976", 4047, 2211161, 337297),
    "2002-11-05": ("sos.mn.gov/media/1548", 4106, 2282860, 342978),
    "2004-11-02": ("sos.mn.gov/media/1688", 4108, 2842912, 581904),
    "2006-11-07": ("sos.state.mn.us/media/1694", 4123, 2217818, 292168),
    "2008-11-04": ("sos.mn.gov/media/1695", 4130, 2921498, 542257),
    "2010-11-02": ("sos.mn.gov/media/1696", 4136, 2123369, 227857),
    "2012-11-06": ("www.sos.mn.gov/media/1450", 4102, 2950780, 527867),
    "2014-11-04": ("www.sos.mn.gov/media/1448", 4106, 1992566, 152101),
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
MAX_BYTES = 5_000_000
EARLY_EDITIONS = {"1994-11-08", "1996-11-05", "2002-11-05", "2004-11-02"}
LEGACY_NAMES = {
    "1994-11-08": "1994_results.xls",
    "1996-11-05": "1996_results.xls",
    "2002-11-05": "2002_general_results.xls",
    "2004-11-02": "2004_general_results.xls",
    "2006-11-07": "2006_general_results.xls",
    "2008-11-04": "2008_general_results.xls",
    "2010-11-02": "2010_general_results_final.xls",
}
CENTRAL_2008 = {"0005": "STATE ABSENTEE COUNT JAN 3RD", "0010": "STATE COURT CONTEST APR 7TH"}
EARLY_COUNTIES = (
    "AITKIN|ANOKA|BECKER|BELTRAMI|BENTON|BIG STONE|BLUE EARTH|BROWN|CARLTON|CARVER|CASS|CHIPPEWA|"
    "CHISAGO|CLAY|CLEARWATER|COOK|COTTONWOOD|CROW WING|DAKOTA|DODGE|DOUGLAS|FARIBAULT|FILLMORE|"
    "FREEBORN|GOODHUE|GRANT|HENNEPIN|HOUSTON|HUBBARD|ISANTI|ITASCA|JACKSON|KANABEC|KANDIYOHI|"
    "KITTSON|KOOCHICHING|LAC QUI PARLE|LAKE|LAKE OF THE WOODS|LE SUEUR|LINCOLN|LYON|MCLEOD|"
    "MAHNOMEN|MARSHALL|MARTIN|MEEKER|MILLE LACS|MORRISON|MOWER|MURRAY|NICOLLET|NOBLES|NORMAN|"
    "OLMSTED|OTTER TAIL|PENNINGTON|PINE|PIPESTONE|POLK|POPE|RAMSEY|RED LAKE|REDWOOD|RENVILLE|RICE|"
    "ROCK|ROSEAU|ST. LOUIS|SCOTT|SHERBURNE|SIBLEY|STEARNS|STEELE|STEVENS|SWIFT|TODD|TRAVERSE|"
    "WABASHA|WADENA|WASECA|WASHINGTON|WATONWAN|WILKIN|WINONA|WRIGHT|YELLOW MEDICINE"
).split("|")


def route(election):
    if election in LEGACY_NAMES:
        return f"https://{EDITIONS[election][0]}/{LEGACY_NAMES[election]}"
    if election == "2012-11-06":
        return "https://www.sos.mn.gov/media/1450/2012mngeneralelectionresults_official_postrecounts.xlsx"
    return f"https://{EDITIONS[election][0]}/{election[:4]}-general-federal-state-results-by-precinct-official.xlsx"


def aliases(election):
    if election in EARLY_EDITIONS:
        year = election[:4]
        if year in ("1994", "1996"):
            labels = ("FIPS_VTD", "Precinct Name", "PRCT", "", "", "CC" if year == "1994" else "FIPS",
                      "7am", "EDR", "Signatures", "AB-Reg", "AB-Fed", "Ballots", "AB-Pres")
        elif year == "2002":
            labels = ("FIPS", "PRECINCT NAME", "PRCT", "MCD NAME", "", "CC",
                      "7am", "EDR", "Signatures", "AB-reg", "AB-fed", "Ballots")
        else:
            labels = ("", "PrecinctName", "PRCT", "McdName", "", "CC",
                      "7AM", "EDR", "Sigs", "RegMilAb", "FedAb", "TotVoters", "PresAb")
        return dict(zip(FIELDS + (("PRESONLYAB",) if len(labels) > len(FIELDS) else ()), labels, strict=True))
    if election == "2006-11-07":
        return dict(zip(FIELDS + ("PRESONLYAB",), (
            "", "Precinct\nName", "PRCT", "MCDName", "", "County_ID", "Registered\nat 7AM",
            "EDR", "Signature", "RegMilAB", "FEDAB", "TotVoters", "PresAB",
        )))
    if election in LEGACY_NAMES:
        old = election == "2008-11-04"
        return dict(zip(FIELDS + ("PRESONLYAB",), (
            "", "Precinct Name", "PRCT" if old else "Precinct Code", "MCDName" if old else "",
            "" if old else "County", "CountyID", "7AM", "EDR", "Signatures",
            "RegMilAB", "FedAB", "TotVoters", "PresAB",
        )))
    return {"REG7AM": "7AM", "AB_MB": "REGMILOVAB"} if election.startswith("2012-") else {}


def precinct_key(row, election):
    return str(row["VTDID"]) if election.startswith("2014-") else row["VTDID"]


def query(fields, precincts, county_roster, printed_total, election, *, statewide_unallocated=None):
    _, expected_size, expected_voting, expected_edr = EDITIONS[election]
    allowed = (list(FIELDS), [*FIELDS, "PRESONLYAB"])
    if fields not in allowed or len(precincts) != expected_size:
        raise IntakeError("mn_inventory", "Unexpected Minnesota workbook fields or precinct inventory")
    if set(county_roster) != {str(i) for i in range(1, 88)}:
        raise IntakeError("mn_inventory", "Minnesota county roster is incomplete")
    if election in EARLY_EDITIONS and any(
        county_roster[str(i)] != name for i, name in enumerate(EARLY_COUNTIES, 1)
    ):
        raise IntakeError("mn_inventory", "Early Minnesota county roster differs")
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
        if election == "2006-11-07" and re.fullmatch(r"[0-9]{2}", key):
            key = str(int(key))
        p = row["PCTCODE"]
        vtd = precinct_key(row, election)
        if (key not in county_roster or not isinstance(row["COUNTYNAME"], str)
                or row["COUNTYNAME"].upper() != county_roster[key]
                or not isinstance(row["PCTNAME"], str) or not row["PCTNAME"].strip()
                or not isinstance(p, str) or not re.fullmatch(r"[0-9]{4}", p)
                or vtd != f"27{int(key) * 2 - 1:03}{p}" or vtd in ids):
            raise IntakeError("mn_precinct_identity", "Invalid or duplicate Minnesota precinct ID")
        ids.add(vtd)
        for field in sums:
            if type(row[field]) is not int or count(row[field]) is None:
                raise IntakeError("mn_count", f"Missing or non-integer Minnesota count: {field}")
            sums[field] += row[field]
        for i, field in enumerate(("TOTVOTING", "REG7AM", "EDR")):
            totals[key][i] += row[field]
    if election == "2008-11-04":
        if (not isinstance(statewide_unallocated, list) or len(statewide_unallocated) != len(CENTRAL_2008)
                or {row["PCTCODE"]: row["PCTNAME"] for row in statewide_unallocated} != CENTRAL_2008):
            raise IntakeError("mn_inventory", "Unexpected Minnesota statewide unallocated rows")
        for row in statewide_unallocated:
            if (set(row) != {"PCTCODE", "PCTNAME", *sums}
                    or row["REG7AM"] or row["SIGNATURES"]
                    or any(type(row[key]) is not int or count(row[key]) is None for key in sums)):
                raise IntakeError("mn_schema", "Unexpected statewide Minnesota count fields")
            for key in sums:
                sums[key] += row[key]
    elif statewide_unallocated is not None:
        raise IntakeError("mn_inventory", "No statewide unallocated row is expected for this workbook")
    has_printed_total = (election in LEGACY_NAMES and election not in EARLY_EDITIONS
                         or election[:4] in ("2012", "2016", "2018"))
    if (set(totals) != set(county_roster)
            or (sums["TOTVOTING"], sums["EDR"]) != (expected_voting, expected_edr)
            or printed_total != (sums if has_printed_total else None)):
        raise IntakeError("mn_state_control", "Minnesota precinct values disagree with statewide controls")

    def summary(name, voting, registration, edr):
        return {"county": name, "ballots_cast": voting, "registered": None,
                "registered_at_7am": registration, "same_day_registrations": edr,
                "rate_hold_reason": RATE_HOLD}

    return {"fields": fields, "precincts": precincts, "county_roster": county_roster,
            **({"native_column_aliases": aliases(election)} if aliases(election) else {}),
            "printed_total": printed_total, "election_date": election,
            "control_url": LEGACY_CONTROL if election[:4] in ("1994", "1996") else CONTROL_URL,
            "counties": [summary(county_roster[k].title(), *totals[k]) for k in sorted(totals, key=int)],
            "total": summary("TOTAL", sums["TOTVOTING"], sums["REG7AM"], sums["EDR"]),
            "native_numerator": "total_voters", "registration_basis": "Pre-registered at 7 a.m.",
            "extraction_method": "official_precinct_workbook",
            "report_note": "Total people voting. No comparable all-voter registration denominator.",
            **({"statewide_unallocated": statewide_unallocated} if statewide_unallocated else {})}


def parse_early(book, election):
    year = election[:4]
    reference = {str(i): name for i, name in enumerate(EARLY_COUNTIES, 1)}
    sheet = book.sheet_by_name(f"{year}_Vote_Stats" if int(year) < 2000 else "Results")
    first = 3 if year == "2002" else 1
    expected = EDITIONS[election][1]
    if sheet.nrows != expected + first or not 1 <= sheet.ncols <= 160:
        raise ValueError("Unexpected early Minnesota workbook dimensions")
    names = aliases(election)
    if first == 3:
        descriptions = book.sheet_by_name("Fields")
        report_roster = book.sheet_by_name("Counties")
        label = "Number of ballots cast"
        if (sheet.cell_value(0, 18) != "1 (County Statistics)"
                or sheet.row_values(1)[18:24] != list(range(1, 7))
                or descriptions.row_values(23)[:2] != ["Ballots", label]
                or report_roster.nrows != 88
                or any(report_roster.row_values(i) != [i, "", reference[str(i)], 27000 + 2 * i - 1]
                       for i in range(1, 88))):
            raise ValueError("Early Minnesota county roster or turnout definitions changed")
    header = sheet.row_values(first - 1)
    indices = {field: header.index(name) for field, name in names.items()
               if name and header.count(name) == 1}
    if set(indices) != {key for key, name in names.items() if name}:
        raise ValueError("Early Minnesota workbook fields changed")

    def integer(value):
        if type(value) not in (int, float) or not 0 <= value <= 2**53 - 1 or int(value) != value:
            raise ValueError("Invalid early Minnesota numeric count")
        return int(value)

    def code(value):
        return int(value) if isinstance(value, str) and re.fullmatch(r"[0-9]+", value) else integer(value)

    records = []
    for i in range(first, sheet.nrows):
        row = {field: sheet.cell_value(i, index) for field, index in indices.items()}
        native = code(row["COUNTYCODE"])
        if year == "1996":
            if not 1 <= native <= 173 or native % 2 != 1:
                raise ValueError("Invalid early Minnesota county FIPS")
            native = (native + 1) // 2
        county = str(native)
        p = f"{code(row['PCTCODE']):04}"
        vtd = f"27{2 * native - 1:03}{p}"
        if "VTDID" in row and code(row["VTDID"]) != int(vtd if year == "2002" else vtd[2:]):
            raise ValueError("Early Minnesota composite precinct code differs")
        if county not in reference or not isinstance(row["PCTNAME"], str):
            raise ValueError("Invalid early Minnesota precinct identity")
        counts = {field: integer(row[field]) for field in list(names)[6:]}
        records.append({"VTDID": vtd, "PCTNAME": row["PCTNAME"], "PCTCODE": p,
                        "MCDNAME": row.get("MCDNAME", ""), "COUNTYNAME": reference[county],
                        "COUNTYCODE": county, **counts})
    return query(list(names), records, reference, None, election)


def parse_2008_2010(book, election):
    results, definitions = (book.sheet_by_name(name) for name in ("Results", "Fields"))
    old = election == "2008-11-04"
    expected = EDITIONS[election][1]
    n_central = len(CENTRAL_2008) if old else 0
    if results.nrows != expected + 2 + n_central or results.ncols > 100 or definitions.nrows > 200:
        raise ValueError("Unexpected legacy workbook dimensions")
    fields = [*FIELDS, "PRESONLYAB"]
    names = {field: name for field, name in aliases(election).items() if name}
    header = results.row_values(0)
    if any(header.count(name) != 1 for name in names.values()):
        raise ValueError("Legacy Minnesota participation fields changed")
    indices = {field: header.index(name) for field, name in names.items()}
    legend = {definitions.cell_value(i, 0): definitions.cell_value(i, 1) for i in range(definitions.nrows)}
    status = "submitted" if old else "accepted"
    if (legend.get("TotVoters") != "Number of voters casting ballots"
            or "pre-registered" not in legend.get("7AM", "")
            or "in the polling place on election day" not in legend.get("EDR", "")
            or not legend.get("RegMilAb", "").endswith(f"absentee ballots {status}")
            or not legend.get("FedAb", "").startswith(f"Absentee ballots with federal offices only {status} (")):
        raise ValueError("Legacy Minnesota participation definitions changed")

    def integer(value):
        if type(value) not in (int, float) or not 0 <= value <= 2**53 - 1 or int(value) != value:
            raise ValueError("Invalid legacy numeric worksheet cell")
        return int(value)

    roster, records, central = {}, [], []
    if old:
        reference = book.sheet_by_name("Counties")
        if (reference.nrows != 90 or reference.row_values(88) != [""] * 4
                or reference.row_values(89) != [89.0, "", "STATE ABSENTEE BALLOT", "Not Applicable"]):
            raise ValueError("Unexpected statewide reporting category")
        for i in range(1, 88):
            code, blank, name, fips = reference.row_values(i)
            if integer(code) != i or blank or integer(fips) != 27000 + 2 * i - 1:
                raise ValueError("Legacy county reference differs")
            roster[str(i)] = name
    for i in range(1, results.nrows - 1):
        row = {field: results.cell_value(i, j) for field, j in indices.items()}
        native = row["COUNTYCODE"]
        if old and isinstance(native, str) and re.fullmatch(r"[1-9]\d?", native):
            native = int(native)
        code = str(integer(native))
        p = row["PCTCODE"]
        if not old:
            p = f"{integer(p):04}"
        if not isinstance(p, str) or not re.fullmatch(r"\d{4}", p):
            raise ValueError("Invalid legacy Minnesota precinct code")
        counts = {field: integer(row[field]) for field in fields[6:]}
        if old and code == "89" and i > expected:
            central.append({"PCTCODE": p, "PCTNAME": row["PCTNAME"], **counts})
            continue
        if i > expected or not 1 <= int(code) <= 87:
            raise ValueError("A statewide Minnesota row cannot be assigned to a county")
        name = roster[code] if old else row["COUNTYNAME"]
        if not isinstance(name, str) or not name or roster.setdefault(code, name) != name:
            raise ValueError("Conflicting Minnesota county names")
        records.append({"VTDID": f"27{2 * int(code) - 1:03}{p}", "PCTNAME": row["PCTNAME"],
                        "PCTCODE": p, "MCDNAME": row.get("MCDNAME", ""), "COUNTYNAME": name,
                        "COUNTYCODE": code, **counts})
    footer = results.row_values(results.nrows - 1)
    if (footer[indices["PCTNAME"]] != ("Statewide Totals" if old else "TOTALS")
            or any(footer[j] for field, j in indices.items() if field in FIELDS[2:6])):
        raise ValueError("Unexpected legacy Minnesota statewide total")
    total = {field: integer(footer[indices[field]]) for field in fields[6:]}
    return query(fields, records, roster, total, election, statewide_unallocated=central if old else None)


def parse_legacy(body, election):
    import xlrd

    def integer(value):
        if type(value) not in (int, float) or not 0 <= value <= 2**53 - 1 or int(value) != value:
            raise ValueError("Invalid 2006 numeric worksheet cell")
        return int(value)

    try:
        if not body.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            raise ValueError("Expected the legacy XLS container")
        book = xlrd.open_workbook(file_contents=body, on_demand=True)
        try:
            if election in EARLY_EDITIONS:
                return parse_early(book, election)
            if election != "2006-11-07":
                return parse_2008_2010(book, election)
            results, reference, definitions = (book.sheet_by_name(name) for name in ("Results", "Counties", "Fields"))
            if not (results.nrows == EDITIONS[election][1] + 3 and results.ncols <= 100
                    and reference.nrows == 88 and definitions.nrows <= 200):
                raise ValueError("Unexpected legacy workbook dimensions")
            legend = {definitions.cell_value(i, 0): definitions.cell_value(i, 1)
                      for i in range(definitions.nrows)}
            if (legend.get("TotVoters") != "Number of voters casting ballots"
                    or "pre-registered" not in legend.get("Registered at 7AM", "")
                    or "in the polling place on election day" not in legend.get("EDR", "")
                    or not legend.get("RegMilAB", "").endswith("absentee ballots submitted")):
                raise ValueError("Legacy participation definitions changed")
            roster = {}
            for i in range(1, reference.nrows):
                code, blank, name, fips = reference.row_values(i)
                key = str(integer(code))
                if key in roster or blank or integer(fips) != 27000 + 2 * int(key) - 1:
                    raise ValueError("Legacy county reference differs")
                roster[key] = name
            fields = list(FIELDS) + ["PRESONLYAB"]
            names = aliases(election)
            header = results.row_values(0)
            if header != results.row_values(results.nrows - 2) or any(
                    header.count(label) != 1 for label in names.values() if label):
                raise ValueError("Legacy participation columns changed")
            indices = {key: header.index(label) for key, label in names.items() if label}
            records = []
            for i in range(1, results.nrows - 2):
                row = results.row_values(i)
                record = {key: row[j] for key, j in indices.items()}
                county = record["COUNTYCODE"]
                if not re.fullmatch(r"[0-9]{2}", county):
                    raise ValueError("Invalid literal legacy county code")
                key = str(int(county))
                record["COUNTYNAME"] = roster[key]
                record["VTDID"] = f"27{2 * int(key) - 1:03}{record['PCTCODE']}"
                for measure in fields[6:]:
                    record[measure] = integer(record[measure])
                records.append(record)
            footer = results.row_values(results.nrows - 1)
            if any(footer[j] for key, j in indices.items() if key in fields[:6]):
                raise ValueError("Invalid legacy turnout summary row")
            total = {field: integer(footer[indices[field]]) for field in fields[6:]}
        finally:
            book.release_resources()
    except Exception as error:
        raise IntakeError("mn_workbook_schema", str(error)) from error
    return query(fields, records, roster, total, election)


def parse(body, election):
    from openpyxl import load_workbook

    if not 0 < len(body) <= (MAX_BYTES if election == "2002-11-05" else 4_000_000):
        raise IntakeError("mn_workbook_size", "Minnesota workbook exceeds size bound")
    if election in LEGACY_NAMES:
        return parse_legacy(body, election)
    try:
        with ZipFile(BytesIO(body)) as archive:
            if len(archive.infolist()) > 100 or sum(x.file_size for x in archive.infolist()) > 40_000_000:
                raise ValueError("Workbook expansion exceeds reviewed bounds")
        workbook = load_workbook(BytesIO(body), read_only=True, data_only=True)
        try:
            sheet = workbook["Results" if election[:4] in ("2012", "2014", "2016") else "Precinct-Results"]
            if sheet.max_row > 5000 or sheet.max_column > 200:
                raise ValueError("Workbook dimensions exceed reviewed bounds")
            rows = iter(sheet.values)
            header = next(rows)
            fields = [*FIELDS, *(["PRESONLYAB"] if "PRESONLYAB" in header else [])]
            native = [aliases(election).get(k, k) for k in fields]
            if any(header.count(k) != 1 for k in native):
                raise ValueError("Precinct participation column missing or repeated")
            definitions = {r[0]: r[1] for r in workbook["Fields"].iter_rows(max_row=200, max_col=2, values_only=True)}
            if (definitions.get("TOTVOTING") != "Number of voters casting ballots"
                    or "7AM" not in definitions.get(aliases(election).get("REG7AM", "REG7AM"), "")
                    or not any(marker in definitions.get("EDR", "")
                               for marker in ("when they vote", "in the polling place on election day"))):
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
            indices = [header.index(k) for k in native]
            records, total, finished = [], None, False
            for row in rows:
                rec = dict(zip(fields, (row[i] for i in indices)))
                if not any(value is not None for value in rec.values()):
                    continue
                if finished:
                    raise ValueError("Unexpected data after worksheet terminator")
                if rec["VTDID"] == "End of worksheet" and all(rec[k] is None for k in fields[1:]):
                    finished = True
                elif (rec["VTDID"] == "TOTAL" or rec["COUNTYNAME"] == "TOTAL"
                      or election.startswith("2012-") and rec["VTDID"] is None and rec["PCTNAME"] == "TOTALS"):
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
