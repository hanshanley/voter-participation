"""Replay Alaska's statewide age and reported gender voter-history tables."""
import io
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from html.parser import HTMLParser

from scripts.southeast_turnout import collect_report

ELECTIONS = dict(zip(range(1996, 2010, 2), (
    "1996-11-05", "1998-11-03", "2000-11-07", "2002-11-05", "2004-11-02", "2006-11-07", "2008-11-04",
)))
MODERN = {
    2016: ("2016-11-08", "2016/General", "A C D E G L N O P R T U"),
    2018: ("2018-11-06", "2018/General", "A C D E G H L N O P R T U V W"),
    2020: ("2020-11-03", "2020/General", "A C D E G H K L N O P R U V W"),
    2022: ("2022-11-08", "2022/genr", "A C D E F G H K L N O P R U V W"),
}
ELECTIONS.update({year: profile[0] for year, profile in MODERN.items()})
YEARS = {f"AK-{year}-general-age-voter-history": year for year in ELECTIONS}
BASE = "https://www.elections.alaska.gov/statistics/"
CSV = "participation-ak-general-age-voter-history.csv"
AGES = ("18-19", "20", "21", "22-24", "25-34", "35-44", "45-54", "55-59", "60-61", "62-64", "65-74")
ROLES = ("REGISTERED", "MALE", "FEMALE", "VOTED", "MALE", "FEMALE")
GENDERS = ("MALE", "FEMALE", "UNKNOWN GENDER")
NUMBER = r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)"


def source(year):
    if year in MODERN:
        return "https://www.elections.alaska.gov/election/" + MODERN[year][1] + "/VoterHistoryByAgeReport.pdf"
    return BASE + f"vi_vrs_stats_history_{year}g." + ("pdf" if year == 2008 else "htm")


class Table(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.text = [], []
        self.row = self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        self.text.extend(data.split())
        if self.cell is not None:
            self.cell.extend(data.split())

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(self.cell))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = self.cell = None


def html_query(body, year):
    report = Table()
    report.feed(body.decode("windows-1252"))
    report.close()
    if f"ALASKA VOTER HISTORY BY AGE, GENDER AND PARTY {year} GENERAL ELECTION" not in " ".join(report.text):
        raise ValueError("Alaska age-history report identity changed")
    groups, rows = [], []
    width = None
    has_rate = year >= 2000
    for row in report.rows:
        if len(row) >= 3 and row[:3] in ([age, cat, "TOTAL"] for age in ("AGES", "AGE") for cat in ("CATEGORIES", "CAT.")):
            if (not 7 <= len(row) <= 16 or (row[3] == "%") != has_rate
                    or (width is not None and width != len(row))):
                raise ValueError("Alaska voter-history field inventory changed")
            width = len(row)
            continue
        if width is None or (len(row) != width
                and not (year == 2006 and len(row) == width - 1 and row[:2] == ["", "FEMALE"])):
            raise ValueError("Unexpected Alaska voter-history table row")
        age, role, number = row[:3]
        role = role.upper()
        if age:
            age = {"75 +": "75+", "All": "TOTALS"}.get(age, age)
            rows = []
            groups.append([age, rows])
        if not groups:
            raise ValueError("Missing Alaska age label")
        rows.append(["REGISTERED" if role == "REG." else role, number, row[3] if has_rate else ""])
    return groups


def pdf_query(body):
    from pypdf import PdfReader

    if not body.startswith(b"%PDF-"):
        raise ValueError("Alaska age history is not a PDF")
    pdf = PdfReader(io.BytesIO(body), strict=True)
    if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 4:
        raise ValueError("Invalid Alaska voter-history report inventory")
    groups, rows = [], None
    edition = None
    ended = False
    for i, page in enumerate(pdf.pages, start=1):
        lines = [" ".join(line.split()) for line in page.extract_text(extraction_mode="layout").splitlines()
                 if line.strip()]
        if (len(lines) < 5 or "GVRR290P-R1 VOTER HISTORY BY AGE REPORT FOR 08GENR TIME:" not in lines[1]
                or lines[2:4] != [f"PAGE: {i}", "AGES TOTAL % A D L R N U G M V OTHER"]):
            raise ValueError("Alaska voter-history PDF columns, election or pages changed")
        if i == 1:
            stamp = re.fullmatch(r"VREMS - \(GBVREMS\) STATE OF ALASKA -- DIVISION OF ELECTIONS DATE: (\d\d/\d\d/2008)", lines[0])
            if not stamp:
                raise ValueError("Alaska voter-history PDF edition changed")
            edition = datetime.strptime(stamp[1], "%m/%d/%Y").date().isoformat()
        for line in lines[4:]:
            if ended:
                raise ValueError("Unexpected data after Alaska age report end")
            if line == "* VOTERS WITH UNKNOWN SEX CODES NOT INCLUDED IN MALE/FEMALE COUNTS":
                continue
            if line == "END OF REPORT - GVRR290P-R1":
                ended = True
            elif match := re.fullmatch(r"(TOTALS|ABOVE 75|\d+ THRU \d+|\d+) (\d+)(?: \d+)+", line):
                rows = [["REGISTERED", match[2], ""]]
                groups.append([match[1].replace(" THRU ", "-"), rows])
            elif rows is not None and (match := re.fullmatch(r"(MALE|FEMALE|VOTED) (\d+) (\d+\.\d)(?: \d+)+", line)):
                rows.append(list(match.groups()))
            else:
                raise ValueError("Unrecognized Alaska age-history PDF row")
    if not ended:
        raise ValueError("Missing Alaska age report end marker")
    return groups, edition


def validate(groups, year, edition):
    last = "ABOVE 75" if year == 2008 else "75+"
    expected = (*AGES, last, *(("UNKNOWN",) if year == 1996 else ()), "TOTALS")
    if (tuple(group[0] for group in groups) != expected
            or (year == 2008 and (not edition or not ELECTIONS[year] <= edition <= "2008-12-31"))
            or (year != 2008 and edition is not None)):
        raise ValueError("Incomplete Alaska age history or inconsistent edition")
    for group, rows in groups:
        if tuple(row[0] for row in rows) != ROLES or any(not re.fullmatch(NUMBER, row[1])
                or (row[2] and (not re.fullmatch(r"\d{1,3}(?:\.\d)?", row[2]) or Decimal(row[2]) > 100))
                for row in rows):
            raise ValueError("Missing registered, voted, or reported-gender role")
        fields = [int(row[1].replace(",", "")) for row in rows]
        if (not all(0 <= v <= n for n, v in zip(fields[:3], fields[3:]))
                or fields[1] + fields[2] > fields[0] or fields[4] + fields[5] > fields[3]):
            raise ValueError("Alaska age or reported-gender counts do not reconcile")
        yield group, fields, [row[2] for row in rows]


def facts(groups, year, edition):
    data = list(validate(groups, year, edition))
    control = data[-1][1]
    residuals = [sum(row[1][i] for row in data[:-1]) - value for i, value in enumerate(control)]
    if residuals != [0] * 6 and not (year == 2004 and residuals == [0, 0, 0, 0, -3, 0]):
        raise ValueError("Alaska age bands do not sum to all six printed statewide controls")
    return {"date": edition, "complete_native_query": groups, "age_minus_control": residuals,
            "participation_observation_qualified": False}


def modern_query(body, year):
    import pymupdf

    if not body.startswith(b"%PDF-"):
        raise ValueError("Alaska age history is not a PDF")
    columns = MODERN[year][2].split()
    rows, stamp = [], None
    with pymupdf.open(stream=body, filetype="pdf") as report:
        if report.needs_pass or len(report) != 3:
            raise ValueError("Alaska age history page inventory changed")
        for index, page in enumerate(report, 1):
            lines = [" ".join(line.split()) for line in page.get_text(sort=True).splitlines() if line.strip()]
            if (len(lines) < 6 or lines[0] != "STATE OF ALASKA - DIVISION OF ELECTIONS"
                    or lines[2:5] != ["VOTERS HISTORY BY AGE REPORT", f"{year % 100}GENR-{year} GENERAL ELECTION",
                                       "AGE TOTAL % " + " ".join(columns)]):
                raise ValueError("Alaska age history edition or columns changed")
            page_stamp = re.fullmatch(rf"(\d{{2}}/\d{{2}}/\d{{4}} \d{{1,2}}:\d{{2}}:\d{{2}}[AP]M) Page {index} of 3", lines[1])
            if not page_stamp or (stamp is not None and stamp != page_stamp[1]):
                raise ValueError("Inconsistent Alaska age history page stamp")
            stamp = page_stamp[1]
            for line in lines[5:]:
                fields = line.split()
                tail = fields[-len(columns):]
                main = fields[:-len(columns)]
                pct = main.pop() if main and re.fullmatch(r"\d{1,3}\.\d{2}", main[-1]) else ""
                if len(main) < 2:
                    raise ValueError("Short Alaska age history record")
                count = main.pop()
                rows.append([" ".join(main), count, pct, tail])
    return rows, datetime.strptime(stamp, "%m/%d/%Y %I:%M:%S%p").date().isoformat()


def modern_facts(rows, year, edition):
    election = date.fromisoformat(ELECTIONS[year])
    if not election <= date.fromisoformat(edition) <= election + timedelta(days=366):
        raise ValueError("Alaska age history edition date outside the reviewed interval")
    ages = ("UNKNOWN DOB", *(age.replace("-", " THRU ") for age in AGES), "ABOVE 75", "TOTALS")
    if len(rows) != len(ages) * 8:
        raise ValueError("Incomplete Alaska age and reported-gender inventory")
    groups, holds = [], {}
    for offset, age in enumerate(ages):
        group = rows[offset * 8:(offset + 1) * 8]
        if tuple(row[0] for row in group) != (age, *GENDERS, "VOTED", *GENDERS):
            raise ValueError("Alaska age or reported-gender order changed")
        counts = []
        for index, (_, count, pct, components) in enumerate(group):
            if (len(components) != len(MODERN[year][2].split())
                    or not all(re.fullmatch(r"\d+", cell) for cell in (count, *components))
                    or sum(map(int, components)) != int(count)
                    or (pct != "" if index == 0 else
                        not re.fullmatch(r"\d{1,3}\.\d{2}", pct) or Decimal(pct) > 100)):
                raise ValueError("Alaska age table row fails its printed controls")
            counts.append(int(count))
        if (sum(counts[1:4]) != counts[0] or sum(counts[5:8]) != counts[4]
                or any(credited > registered for registered, credited in zip(counts[:4], counts[4:]))):
            raise ValueError("Alaska reported-gender rows do not reconcile")
        for index, count in enumerate(counts[1:], 1):
            denominator = counts[4 if index > 4 else 0]
            expected = Decimal(count) * 100 / denominator if denominator else Decimal(0)
            if abs(expected - Decimal(group[index][2])) > Decimal(".005"):
                if index == 4:
                    holds[age] = "printed_percent_disagrees_with_counts"
                else:
                    raise ValueError("Alaska age source category share fails its printed control")
        groups.append(counts)
    if [sum(group[i] for group in groups[:-1]) for i in range(8)] != groups[-1]:
        raise ValueError("Alaska age bands do not sum to all eight printed statewide controls")
    return {"date": edition, "complete_native_query": rows, "rate_holds": holds,
            "participation_observation_qualified": False}


def parse(body, year):
    if not 0 < len(body) <= 1_000_000:
        raise ValueError("Alaska age-history source exceeds bounds")
    if year in MODERN:
        rows, date = modern_query(body, year)
        return modern_facts(rows, year, date)
    groups, date = pdf_query(body) if year == 2008 else (html_query(body, year), None)
    return facts(groups, year, date)


def collect(collector, feed, *, reuse_checked_week=False):
    return collect_report(collector, feed, source(YEARS[feed]), lambda body, _: parse(body, YEARS[feed]),
                          reuse_checked_week=reuse_checked_week)


def exports(entries):
    for feed, year in YEARS.items():
        entry = entries.get(feed, {})
        data = entry.get("data")
        if data is None or entry.get("status") not in {"reported", "retained_after_failure"}:
            continue
        groups, edition = data["complete_native_query"], data["date"]
        if year in MODERN:
            if entry["source"]["url"] != source(year) or data != modern_facts(groups, year, edition):
                raise ValueError("Alaska digital age-history provenance or query changed")
            for offset in range(0, len(groups), 8):
                group = groups[offset:offset + 8]
                source_age = group[0][0]
                age = source_age.replace(" THRU ", "-")
                for i, gender in enumerate(("all", "male", "female", "unknown")):
                    yield export_row(entry, year, age, gender, int(group[i][1]), int(group[i + 4][1]),
                                     data["rate_holds"].get(source_age, "") if i == 0 else "",
                                     group[4][2] if i == 0 else None, edition,
                                     int(group[3][1]) if i == 0 else None, int(group[7][1]) if i == 0 else None)
            continue
        if entry["source"]["url"] != source(year) or data != facts(groups, year, edition):
            raise ValueError("Alaska voter-history provenance or query changed")
        for age, counts, printed in validate(groups, year, edition):
            for i, gender in enumerate(("all", "male", "female")):
                registered, credited = counts[i], counts[i + 3]
                hold = "age_band_credits_differ_from_state_control" if data["age_minus_control"][i + 3] else ""
                yield export_row(entry, year, age, gender, registered, credited, hold,
                                 printed[i + 3] if i == 0 else None, edition,
                                 counts[0] - counts[1] - counts[2] if i == 0 else None,
                                 counts[3] - counts[4] - counts[5] if i == 0 else None)


def export_row(entry, year, age, gender, registered, credited, hold, printed, edition, unclassified, credits):
    return {
        "state_code": "AK", "election_date": ELECTIONS[year], "age_group": age, "reported_gender": gender,
        "registered_in_report": registered, "voter_history_credits": credited,
        "history_per_registered": str((Decimal(credited) / registered).quantize(Decimal(".00000001")))
        if registered and not hold else None,
        "rate_hold_reason": hold, "source_reported_percent": printed,
        "unclassified_registration_residual": unclassified, "unclassified_credit_residual": credits,
        "report_edition_date": edition, "source_status": entry["status"],
        "checked_week_utc": entry.get("archive_check_week_utc"), "source_url": source(year),
        "source_sha256": entry["source"]["sha256"],
    }
