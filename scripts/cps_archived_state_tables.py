"""Published statewide CPS tables from 1996, 1998 and 2000."""

import io
import json
import re
import zipfile

from scripts import cps_published_state_tables as cps
from scripts.nationwide import STATES
from scripts.participation_intake.contract import pin

CSV = "participation-cps-archived-state-tables.csv"
MANIFEST = "archived-sources.json"
BASE = "https://www2.census.gov/programs-surveys/cps/tables/p20/"
SOURCES = {
    (1996, "4a"): "504/tab4a.txt", (1996, "4b"): "504/tab4b.txt", (1996, "4c"): "504/tab4c.txt",
    (1998, "4"): "523-rv/tab04.txt",
    **{(2000, table): f"542/tab0{table}.xls" for table in ("4a", "4b", "4c")},
}
PLACES = {name.upper(): code for code, name in STATES.items()} | {"UNITED STATES": "US"}
GROUPS = {"Total": "Total", "Male": "Male", "Female": "Female", "White": "White", "Black": "Black",
          "N-H White": "Non-Hispanic White", "N-H Black": "Non-Hispanic Black",
          "API": "Asian and Pacific Islander", "N-H API": "Non-Hispanic Asian and Pacific Islander",
          "Hispanic": "Hispanic (any race)"}
AGES = {"18 TO 24 YEARS": "18 to 24", "25 TO 44 YEARS": "25 to 44",
        "45 TO 64 YEARS": "45 to 64", "65 YEARS AND OVER": "65+"}
COUNT_FIELDS = tuple(field for field in cps.FIELDS if field.endswith("_thousands"))
STANDARD_ERRORS = ("vap_registered_se_pp", "vap_voted_se_pp")


def filename(year, table):
    return f"{year}-table{table}.{SOURCES[year, table].rsplit('.', 1)[1]}"


def number(raw, count):
    if type(raw) in (float, int):
        value = raw
    elif isinstance(raw, str) and re.fullmatch(r"[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?", raw):
        value = float(raw.replace(",", ""))
    else:
        raise ValueError(f"Unknown archived CPS value: {raw!r}")
    if not 0 <= value <= (500_000 if count else 100) or (count and int(value) != value):
        raise ValueError(f"Invalid archived CPS value: {raw!r}")
    return int(value) if count else value


def record(year, table, state, native, group, dimension, basis, cells, uncertainty, source, sheet, line):
    fields = (*cps.FIELDS, *STANDARD_ERRORS)
    values, markers = dict.fromkeys(fields), {}
    for field in fields:
        raw = cells.get(field)
        if raw is None:
            markers[field] = "not_in_table"
        elif isinstance(raw, str) and raw.strip() in {"(B)", "-", "."}:
            markers[field] = raw.strip()
        else:
            values[field] = number(raw, field in COUNT_FIELDS)
    denominator = values[COUNT_FIELDS[0 if basis == "vap" else 1]]
    for measure in ("registered", "voted"):
        rate = f"{basis}_{measure}_pct"
        count = values[f"reported_{measure}_thousands"]
        point = values[rate]
        error = (f"{basis}_{measure}_moe_pp" if uncertainty == "margin_90" else
                 f"{basis}_{measure}_se_pp" if uncertainty == "standard_error" else None)
        if error and (point is None) != (values[error] is None):
            raise ValueError(f"Inconsistent CPS uncertainty {year}/{table}/{line}")
        if point is None:
            continue
        if (denominator in (0, None) or count is None or
                not 100 * (count - .5) / (denominator + .5) - .050001 <= point
                <= 100 * (count + .5) / (denominator - .5) + .050001):
            values[rate], markers[rate] = None, "invalid_published_rate"
            if error:
                values[error], markers[error] = None, "invalid_published_rate"
    return {"year": year, "election_type": "presidential" if year % 4 == 0 else "midterm",
            "state_code": state, "group": group, "native_group": native, "dimension": dimension,
            **values, "source_markers": markers, "confidence_level_pct": 90 if uncertainty == "margin_90" else None,
            "source_uncertainty": uncertainty, "source_table": table, "source_sheet": sheet,
            "source_row": line, "source_url": BASE + SOURCES[year, table], "source_sha256": source["sha256"]}


def cells_from(pop, citizen, registered, rp, voted, vp, basis, error_unit=None, re=None, ve=None):
    cells = dict(zip(COUNT_FIELDS, (pop, citizen, registered, voted), strict=True))
    cells.update({f"{basis}_registered_pct": rp, f"{basis}_voted_pct": vp})
    if error_unit:
        cells.update({f"{basis}_registered_{error_unit}_pp": re, f"{basis}_voted_{error_unit}_pp": ve})
    return cells


def text_1996(body, table, source):
    text = body.decode("ascii")
    if not text.splitlines()[0].upper().startswith(f"TABLE {table.upper()}.") or "August 17, 1998" not in text:
        raise ValueError("Unexpected 1996 CPS edition")
    state, label, seen, rows = None, None, set(), []
    if table == "4c":
        if "Among Citizens, by Gender" not in text or "(November 1996.  Numbers in thousands)" not in text:
            raise ValueError("Changed 1996 citizen table denominator")
        for line, raw in enumerate(text.splitlines(), 1):
            data = [v.strip() for v in raw.split("|")[1:-1]]
            if len(data) == 14 and data[0] == "ALL" and data[1].isdigit():
                state, label, values = "US", "Total", data[1:]
            elif len(data) == 15 and data[1] in cps.SEX:
                if data[0]:
                    state = "DC" if data[0] == "District of" else PLACES.get(data[0].upper())
                label, values = data[1], data[2:]
            else:
                continue
            if state is None or (state, label) in seen:
                raise ValueError(f"Unknown or duplicate 1996 citizen table entry: {raw}")
            seen.add((state, label))
            c = cells_from(None, values[0], values[2], values[5], values[8], values[11], "cvap")
            rows.append(record(1996, table, state, label, label, "overall" if label == "Total" else "sex",
                               "cvap", c, "not_published", source, "text", line))
        if seen != {(code, sex) for code in STATES for sex in cps.SEX} | {("US", "Total")}:
            raise ValueError("Incomplete 1996 CPS citizen table")
        return rows
    if "* PERSONS * NUMBER  * PERCENT * NUMBER  * PERCENT *" not in text:
        raise ValueError("Changed 1996 total-population table")
    group_map = {"ALL RACES": "Total", "WHITE": "White", "BLACK": "Black", "HISPANIC ORIGIN": "Hispanic (any race)"} \
        if table == "4a" else {"BOTH SEXES": "Total", "MALE": "Male", "FEMALE": "Female"}
    for line, raw in enumerate(text.splitlines(), 1):
        value = raw.strip()
        if value in PLACES or value == "TOTAL":
            state, label = PLACES.get(value, "US"), None
        elif value in group_map:
            label = value
        elif re.match(r"^(TOTAL AGE|\d+ (?:TO|YEARS))", value):
            heading, *values = re.split(r" {2,}", value, maxsplit=1)
            age = heading.replace(".", "").strip()
            bits = values[0].split() if values else []
            if state is None or label is None or age not in {*AGES, "TOTAL AGE 18 AND OVER"} or len(bits) != 10 \
                    or (state, label, age) in seen:
                raise ValueError(f"Unexpected 1996 CPS age entry at line {line}")
            seen.add((state, label, age))
            overall = age == "TOTAL AGE 18 AND OVER"
            if not overall and (table != "4b" or label != "BOTH SEXES"):
                continue
            group = group_map[label] if overall else AGES[age]
            dimension = ("age" if not overall else "overall" if group == "Total" else
                         "sex" if table == "4b" else "race_or_hispanic_origin")
            row = cells_from(bits[0], None, bits[1], bits[2], bits[3], bits[4], "vap")
            rows.append(record(1996, table, state, heading if not overall else label, group, dimension,
                               "vap", row, "not_published", source, "text", line))
    if seen != {(code, group, age) for code in PLACES.values() for group in group_map
                for age in {*AGES, "TOTAL AGE 18 AND OVER"}}:
        raise ValueError("Incomplete 1996 CPS age roster")
    return rows


def text_1998(body, source):
    text = body.decode("ascii")
    if "for States: November 1998" not in text or "18 and over | citizen" not in text or "Standard |" not in text:
        raise ValueError("Changed 1998 CPS total-population table")
    state, rows = None, []
    for line, raw in enumerate(text.splitlines(), 1):
        # Two-word historic labels occupy a fixed-width field.
        native = raw[24:43].strip()
        if native not in GROUPS:
            continue
        if raw[:24].strip():
            state = PLACES.get(raw[:24].strip())
        group = GROUPS[native]
        values = raw[43:].split()
        if state is None or len(values) != 10:
            raise ValueError(f"Malformed 1998 CPS row {line}")
        row = cells_from(values[0], values[1], values[4], values[5], values[7], values[8],
                         "vap", "se", values[6], values[9])
        dimension = "overall" if group == "Total" else "sex" if group in cps.SEX else "race_or_hispanic_origin"
        rows.append(record(1998, "4", state, native, group, dimension, "vap", row, "standard_error", source, "text", line))
    expected = {group for native, group in GROUPS.items() if native != "API"}
    if len(rows) != len(PLACES) * len(expected) or {(r["state_code"], r["group"]) for r in rows} != {
            (state, group) for state in PLACES.values() for group in expected}:
        raise ValueError("Incomplete 1998 CPS roster")
    return rows


def xls_2000(body, table, source):
    sheet, data = cps.workbook_rows(body, True, 12 if table == "4a" else 11)
    heading = data[0 if table == "4a" else 1][0]
    basis = "cvap" if table == "4c" else "vap"
    title = "Citizen Voting-Age Population" if basis == "cvap" else "Total Voting-Age Population"
    first = {"4a": 10, "4b": 6, "4c": 6}[table]
    groups = {name for native, name in GROUPS.items() if native != "N-H API"} if table == "4a" \
        else {"Total", *cps.AGES_2010} if table == "4b" else {"Total"}
    # Table 4c reuses the workbook's (18+) column subheading. The title and
    # independent population ratios identify its published citizen denominator.
    if sheet != f"Table {table}" or not all(v in heading for v in (f"Table {table}.", "November 2000", title)):
        raise ValueError("Changed 2000 CPS workbook identity")
    upper, lower = data[7:9] if table == "4a" else data[4:6]
    if (upper[-6:], lower[-6:]) != (
            (("Total", "registered", "Confidence", "Total", "voted", "Confidence"),
             ("registered", "(18+)", "interval", "voted", "(18+)", "interval")) if table == "4a" else
            (("Total registered", None, None, "Total voted", None, None),
             ("Total", "Percent registered (18+)", "Confidence interval",
              "Total", "Percent voted (18+)", "Confidence interval"))):
        raise ValueError("Changed 2000 CPS measure columns")
    state, rows = None, []
    for line, entry in enumerate(data[first:], first + 1):
        if table == "4a":
            place, label, *values = entry
            if not label and all(v is None for v in values):
                continue
            if place:
                state = PLACES.get(place.strip())
            group = GROUPS.get(label)
        else:
            label, *values = entry
            if table == "4b" and all(v is None for v in values):
                if label in PLACES:
                    state = PLACES[label]
                continue
            if all(v is None for v in values):
                continue
            if table == "4c":
                state, group = PLACES.get(label), "Total"
            else:
                group = label.lstrip(".").strip() if label else None
        if state is None or group not in groups:
            raise ValueError(f"Unexpected 2000 CPS identity {table}/{line}")
        values = [v.strip() if isinstance(v, str) else v for v in values]
        row = cells_from(values[0], values[1], values[4], values[5], values[7], values[8],
                         basis, "moe", values[6], values[9])
        dimension = ("overall" if group == "Total" else "age" if table == "4b" else
                     "sex" if group in cps.SEX else "race_or_hispanic_origin")
        rows.append(record(2000, table, state, label, group, dimension, basis, row, "margin_90", source, sheet, line))
    if len(rows) != len(groups) * len(PLACES) or {(r["state_code"], r["group"]) for r in rows} != {
            (state, group) for state in PLACES.values() for group in groups}:
        raise ValueError("Incomplete 2000 CPS roster")
    return rows


def build(bundle):
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        if MANIFEST not in archive.namelist():
            return []
        sources = json.loads(archive.read(MANIFEST))
        if set(sources) != {filename(year, table) for year, table in SOURCES}:
            raise ValueError("Incomplete older CPS source inventory")
        frames = {}
        for (year, table), url in SOURCES.items():
            name = filename(year, table)
            raw, source = archive.read(name), sources[name]
            if source != {"url": BASE + url, **pin(raw)}:
                raise ValueError(f"Archived CPS source differs: {name}")
            fn = text_1998 if year == 1998 else text_1996 if year == 1996 else xls_2000
            frames[year, table] = fn(raw, source) if year == 1998 else fn(raw, table, source)

    def totals(year, table):
        return {r["state_code"]: tuple(r[field] for field in COUNT_FIELDS)
                for r in frames[year, table] if r["group"] == "Total"}

    for year in (1996, 2000):
        if totals(year, "4a") != totals(year, "4b"):
            raise ValueError(f"Archived CPS VAP controls differ: {year}")
    if totals(2000, "4a") != totals(2000, "4c"):
        raise ValueError("2000 CPS citizen and total-population controls differ")
    standard = {(r["state_code"], r["group"]): r for r in frames[1996, "4b"]}
    for row in frames[1996, "4c"]:
        prior = standard[row["state_code"], row["group"]]
        if row["reported_voted_thousands"] != prior["reported_voted_thousands"]:
            raise ValueError("1996 CPS citizen voting totals differ by sex")
        if row["reported_registered_thousands"] != prior["reported_registered_thousands"]:
            for key in ("reported_registered_thousands", "cvap_registered_pct"):
                row[key], row["source_markers"][key] = None, "source_control_disagreement"
    return [row for frame in frames.values() for row in frame]
