"""Bulk source-defined historical participation counts for Alabama and South Carolina."""
import io
import re
from datetime import timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zipfile import ZipFile

SC = "SC-general-election-participation-history"
AL = {year: f"AL-{year}-general-election-age-participation" for year in (2018, 2020, 2024)}
URLS = {
    SC: "https://scvotes.gov/wp-content/uploads/2026/11/Voter-Participation-History-1998-2026.pdf",
    AL[2018]: "https://www.sos.alabama.gov/sites/default/files/election-data/2019-01/2018GeneralTotalsByAge.xlsx",
    AL[2020]: "https://www.sos.alabama.gov/sites/default/files/election-data/2021-06/2020%20General%20Election%20Participation%20by%20Age.pdf",
    AL[2024]: "https://www.sos.alabama.gov/sites/default/files/election-data/2025-10/2024%20General%20Election%20Participation%20by%20Age.pdf",
}
SC_CSV = "participation-sc-general-election-history.csv"
AL_CSV = "participation-al-general-election-by-age.csv"
AGES = ("18-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80-89", "90-99", "100+")
COUNTIES = (
    "AUTAUGA BALDWIN BARBOUR BIBB BLOUNT BULLOCK BUTLER CALHOUN CHAMBERS CHEROKEE CHILTON CHOCTAW "
    "CLARKE CLAY CLEBURNE COFFEE COLBERT CONECUH COOSA COVINGTON CRENSHAW CULLMAN DALE DALLAS DEKALB "
    "ELMORE ESCAMBIA ETOWAH FAYETTE FRANKLIN GENEVA GREENE HALE HENRY HOUSTON JACKSON JEFFERSON LAMAR "
    "LAUDERDALE LAWRENCE LEE LIMESTONE LOWNDES MACON MADISON MARENGO MARION MARSHALL MOBILE MONROE "
    "MONTGOMERY MORGAN PERRY PICKENS PIKE RANDOLPH RUSSELL SHELBY ST_CLAIR SUMTER TALLADEGA TALLAPOOSA "
    "TUSCALOOSA WALKER WASHINGTON WILCOX WINSTON"
).split()
NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
AGE_HEADER = ("County", "Total Ballots Cast", *(f"Age {age}" for age in AGES))


def sc_query(lines):
    text = " ".join(lines)
    if not (lines and lines[0].startswith("Voter Participation History Total")
            and "Overall Participation" in lines[0] and "Registered" in lines[1]
            and "participation is calculated using Ballots Cast Method (BCM) uses actual ballots cast" in text
            and "Denotes participation calculated using Voter History Method (VHM)" in text):
        raise ValueError("South Carolina report scope or participation method changed")
    anchors = [(i, int(m[1])) for i, line in enumerate(lines)
               if (m := re.match(r"^(\d{4})(?: |$)", line))]
    results = []
    expected = list(range(2026, 1997, -2))
    for i, line in enumerate(lines):
        if not re.match(r"^(?:\d{4} )?General Election", line):
            continue
        match = re.fullmatch(rf"(?:\d{{4}} )?General Election(\*?) ({NUMBER}) ({NUMBER}) (\d{{1,3}}\.\d%)", line)
        if not match or len(results) >= len(expected):
            raise ValueError("Invalid South Carolina general-election row")
        year = expected[len(results)]
        if not any(anchor == year and abs(at - i) <= 1 for at, anchor in anchors):
            raise ValueError("South Carolina year label does not identify its general-election row")
        star, register, count, printed = match.groups()
        registered, participation = (int(value.replace(",", "")) for value in (register, count))
        if not 0 < participation <= registered or bool(star) != (year <= 2006):
            raise ValueError("South Carolina counts or ballot/history definition changed")
        fraction = Decimal(participation) / registered
        results.append({"year": year, "reported_registered": registered, "reported_participation": participation,
                        "numerator_basis": "voter_history_credits" if star else "ballots_cast",
                        "published_turnout_pct": printed,
                        "published_rate_matches_counts": (100 * fraction).quantize(
                            Decimal(".1"), rounding=ROUND_HALF_UP) == Decimal(printed[:-1]),
                        "participation_per_reported_registration": float(fraction)})
    if [r["year"] for r in results] != expected or [year for _, year in anchors] != expected:
        raise ValueError("Incomplete South Carolina election inventory")
    return results


def al_query(rows, year):
    if (len(rows) != len(COUNTIES) + 1 or [row[0] for row in rows] !=
            [*COUNTIES, "TOTAL" if year == 2018 else "TOTALS"]):
        raise ValueError("Alabama county or statewide roster changed")
    for row in rows:
        if (len(row) != len(AGE_HEADER)
                or not all(type(value) is int and value >= 0 or value is None and year == 2018
                           and index == len(AGES) + 1 and row[0] != "TOTAL"
                           for index, value in enumerate(row[1:], 1))
                or not row[1] or sum(value or 0 for value in row[2:]) != row[1]):
            raise ValueError("Alabama age counts do not reconcile to the county control")
    if any(sum(row[i] or 0 for row in rows[:-1]) != total for i, total in enumerate(rows[-1][1:], 1)):
        raise ValueError("Alabama county age counts do not reconcile to the statewide control")
    return rows


def parse(body, feed):
    if not 0 < len(body) <= 5_000_000:
        raise ValueError("Southeast report exceeds reviewed bounds")
    if feed == AL[2018]:
        from openpyxl import load_workbook

        with ZipFile(io.BytesIO(body)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 20_000_000:
                raise ValueError("Alabama age workbook exceeds expanded size limit")
        book = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
        try:
            if book.sheetnames != ["Ages_Crosstab"]:
                raise ValueError("Alabama age workbook worksheet changed")
            table = iter(book.active.values)
            if next(table, None) != AGE_HEADER:
                raise ValueError("Alabama age workbook columns changed")
            native = [list(row) for row in table]
        finally:
            book.close()
    else:
        from pypdf import PdfReader

        if not body.startswith(b"%PDF-"):
            raise ValueError("Historical report is not a PDF")
        pages = PdfReader(io.BytesIO(body), strict=True).pages
        if len(pages) != (1 if feed == SC else 3):
            raise ValueError("Historical report page layout changed")
        lines = []
        for page in pages:
            page.transfer_rotation_to_content()
            lines.extend(" ".join(line.split()) for line in page.extract_text(extraction_mode="layout").splitlines()
                         if line.strip())
        if feed == SC:
            native = lines
        else:
            year = next(year for year, identity in AL.items() if identity == feed)
            title = f"{year} General Election Participation by Age"
            columns = " ".join(AGE_HEADER)
            layout = [title, columns] if year == 2024 else [
                title, columns.replace("Total Ballots Cast", "Total"), "Ballots Cast"]
            if lines[:len(layout)] != layout:
                raise ValueError("Alabama PDF age columns or election identity changed")
            native = []
            for line in lines[len(layout):]:
                match = re.fullmatch(rf"([A-Z_]+)((?: {NUMBER}){{10}})", line)
                if not match:
                    raise ValueError("Invalid Alabama age row")
                native.append([match[1], *(int(v.replace(",", "")) for v in match[2].split())])
    return facts(native, feed)


def facts(native, feed):
    if feed == SC:
        rows = sc_query(native)
    else:
        rows = al_query(native, next(year for year, identity in AL.items() if identity == feed))
    return {"complete_native_query": rows, "native_lines": native if feed == SC else None,
            "participation_observation_qualified": False}


def collect_report(collector, feed, url, parser, *, reuse_checked_week=False, shared_acquisition=False):
    day = collector.now.astimezone(timezone.utc).date()
    week = (day - timedelta(days=day.weekday())).isoformat()
    old = collector.prior.get(feed) or {}
    if (reuse_checked_week and not collector.offline and old.get("archive_check_week_utc") == week
            and old.get("status") == "reported" and old.get("data") is not None):
        return old
    entry = collector.capture(feed, url, lambda body: parser(body, feed), equivalent=lambda a, b: a == b,
                              **({"shared_acquisition": True} if shared_acquisition else {}))
    if not collector.offline:
        entry["archive_check_week_utc"] = week
    return entry


def collect(collector, feed, *, reuse_checked_week=False):
    return collect_report(collector, feed, URLS[feed], parse, reuse_checked_week=reuse_checked_week)


def exports(entries):
    sc, al = [], []
    for feed, url in URLS.items():
        entry = entries.get(feed, {})
        data = entry.get("data")
        if data is None or entry.get("status") not in ("reported", "retained_after_failure"):
            continue
        rows = data["complete_native_query"]
        if entry["source"]["url"] != url or data != facts(data["native_lines"] if feed == SC else rows, feed):
            raise ValueError("Historical participation differs from the retained native query")
        provenance = {"source_url": url, "source_sha256": entry["source"]["sha256"],
                      "source_status": entry["status"], "checked_week_utc": entry.get("archive_check_week_utc")}
        if feed == SC:
            sc.extend({"state_code": "SC", **row, **provenance} for row in rows)
        else:
            year = next(year for year, identity in AL.items() if identity == feed)
            al.extend({"state_code": "AL", "year": year,
                       "geography_level": "state" if name.startswith("TOTAL") else "county",
                       "geography": "Alabama" if name.startswith("TOTAL") else name,
                       "age_group": group, "reported_ballots": count,
                       "age_report_ballots_all_ages": total, **provenance}
                      for name, total, *counts in rows for group, count in zip(("all", *AGES), (total, *counts)))
    return sc, al
