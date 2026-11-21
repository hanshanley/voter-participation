"""Extract Hawaii's native precinct turnout blocks, not candidate totals."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import re
from zoneinfo import ZoneInfo

from scripts.participation_intake.contract import digest, pin
from scripts.results_state_statistics import HI_ROOT, HI_URL, hawaii_report


FEED = "HI-2026-general-election-precinct-turnout"
CSV = "participation-hi-2026-native-precinct-turnout.csv"
URL = HI_ROOT + "precinct.pdf"
HISTORICAL_FEED = "HI-2024-general-election-precinct-turnout"
HISTORICAL_CSV = "participation-hi-2024-native-precinct-turnout.csv"
HISTORICAL_ROOT = "https://files.hawaii.gov/elections/files/results/2024/General/"
HISTORICAL_ROSTER = "ee25c7e36b9bdc295b62264ad8a15e35441ac14c80b663ee4b8af936a6c1f0c7"
LEGACY_ROSTERS = {
    2020: "ea46cc90cc1513a33aba5afdea24c31d454de8843b6da124ef633ac286e7006e",
    2022: "d7b01f2c58eeb0014c0902c2b9efe27c69fc990d3c04e4d8f7766d2e7f5f6442",
}
MAX_BYTES = 10_000_000
ROSTER = "9392e63c74bac626dee1917ad55ef3d5db603cc7460175713849771890775db3"
FOOTER = "PRECINCT REGISTRATION AND TURNOUT"
MODES = ("Mail", "In-Person")
ELECTIONS = {2020: "2020-11-03", 2022: "2022-11-08", 2024: "2024-11-05", 2026: "2026-11-03"}
NUMERAL = r"([0-9][0-9,]*)"
PERCENT = r"([0-9]{1,3}\.[0-9]%)"


def clock(value, year=2026):
    observed = datetime.strptime(value, "Printed on: %m/%d/%Y at %I:%M:%S %p")
    if observed.date().isoformat() < election_date(year):
        raise ValueError("Hawaii precinct report predates the election")
    return observed.replace(tzinfo=ZoneInfo("Pacific/Honolulu"))


def number(text):
    if not re.fullmatch(r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)", text):
        raise ValueError("Invalid Hawaii turnout number")
    return int(text.replace(",", ""))


def election_date(year):
    return ELECTIONS[year]


def feed_for(year):
    election_date(year)
    return f"HI-{year}-general-election-precinct-turnout"


def csv_for(year):
    return f"participation-hi-{year}-native-precinct-turnout.csv"


def sources(year):
    election_date(year)
    if year == 2026:
        return URL, HI_URL
    root = HISTORICAL_ROOT if year == 2024 else f"https://files.hawaii.gov/elections/files/results/{year}/general/"
    return root + "precinct.pdf", root + "histatewide.pdf"


def legacy_detail_page(text, page):
    header = re.match(
        r"\*\*FINAL REPORT\*\*November 3, 2020GENERAL ELECTION 2020\s+- State of Hawaii – Statewide"
        rf"(Printed on:\s+\d{{2}}/\d{{2}}/2020 at \d{{2}}:\d{{2}}:\d{{2}} [ap]m)PAGE {page}"
        r"(MAIL|IN-PERSON) ([0-9]{2}-[0-9]{2}|Presidential)", text)
    chunks = text.split(FOOTER)
    if not header or len(chunks) != 2:
        raise ValueError("Hawaii 2020 precinct election, mode or page sequence differs")
    report_clock, mode, unit = header.groups()
    pattern = (rf"{NUMERAL}PRECINCT REGISTRATION {PERCENT} {NUMERAL}\s+MAIL TURNOUT"
               if mode == "MAIL" else rf"{NUMERAL}\s+IN-PERSON TURNOUT")
    values = re.match(r"\*{80}GENERAL " + pattern + r"\s*\n", chunks[1])
    if not values:
        raise ValueError("Hawaii 2020 native turnout block differs")
    registration, printed, ballots = values.groups() if mode == "MAIL" else (None, None, values[1])
    return clock(" ".join(report_clock.split()), 2020), [unit, mode.title(), page, registration, ballots, printed]


def parse_detail(body, *, year=2026):
    from pypdf import PdfReader

    if not 0 < len(body) <= MAX_BYTES or not body.startswith(b"%PDF-") or not body.rstrip().endswith(b"%%EOF"):
        raise ValueError("Not a bounded Hawaii precinct PDF")
    pdf = PdfReader(BytesIO(body), strict=True)
    if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 1500:
        raise ValueError("Hawaii precinct PDF page inventory differs")
    source_clock = None
    records = []
    completed = set()
    previous = None
    title = f"GENERAL ELECTION {year} - State of Hawaii - Statewide Precinct" + {
        2022: " Detail", 2024: " Report"}.get(year, "")
    final = "FINAL REPORT" if year == 2022 else "FINAL"
    day = int(election_date(year)[-2:])
    for page_number, page in enumerate(pdf.pages, 1):
        if year == 2020:
            observed, record = legacy_detail_page(page.extract_text(), page_number)
            source_clock = source_clock or observed
            if observed != source_clock:
                raise ValueError("Hawaii precinct PDF mixes report clocks")
            records.append(record)
            continue
        lines = [" ".join(line.split()) for line in page.extract_text().splitlines() if line.strip()]
        if (len(lines) < 6 or lines[1] != title or lines[3] != f"November {day}, {year}"
                or lines[4].upper() != final or lines[-1] != f"PAGE {page_number}"):
            raise ValueError("Hawaii precinct PDF election, status or page sequence differs")
        observed = clock(lines[0], year)
        if source_clock is None:
            source_clock = observed
        if observed != source_clock:
            raise ValueError("Hawaii precinct PDF mixes report clocks")
        match = re.fullmatch(r"(Mail|In-Person) ([0-9]{2}-[0-9]{2}|OS [I]{1,2}|PRES)",
                             lines[2], re.IGNORECASE)
        if not match:
            raise ValueError("Hawaii precinct PDF mode or precinct identity differs")
        mode, unit = match[1].title(), match[2].upper()
        identity = (unit, mode)
        if identity != previous and previous is not None and previous not in completed:
            raise ValueError("Hawaii precinct mode is missing its native turnout block")
        if identity in completed:
            raise ValueError("Hawaii precinct report repeats a completed mode")
        previous = identity
        if FOOTER not in lines:
            continue
        index = lines.index(FOOTER)
        block = lines[index:index + 9]
        if (lines.count(FOOTER) != 1 or len(block) != 9 or not re.fullmatch(r"\*{20,50}", block[1])
                or block[2:5] != ["GENERAL", block[1], "PRECINCT REGISTRATION"]
                or block[6].upper() != f"{mode.upper()} TURNOUT"):
            raise ValueError("Hawaii native precinct turnout block differs")
        records.append([unit, mode, page_number, block[5], block[7], block[8]])
        completed.add(identity)
    if year != 2020 and previous not in completed:
        raise ValueError("Last Hawaii precinct mode is missing its native turnout block")
    facts = {"report_clock": source_clock.isoformat(), "pages": len(pdf.pages), "mode_blocks": records}
    detail_rows(facts, year=year)
    return facts


def detail_rows(detail, *, year=2026):
    units = {}
    previous_page = 0
    for unit, mode, page, native_reg, native_ballots, printed in detail["mode_blocks"]:
        legacy_in_person = year == 2020 and mode == "In-Person"
        ballots = number(native_ballots)
        reg = None if legacy_in_person else number(native_reg)
        if (mode not in MODES or type(page) is not int or not previous_page < page <= detail["pages"]
                or mode in units.setdefault(unit, {})
                or ((native_reg is not None or printed is not None) if legacy_in_person
                    else not re.fullmatch(PERCENT, printed))):
            raise ValueError("Hawaii turnout block identity or counts differ")
        percentage = (Decimal(100 * ballots) / reg).quantize(
            Decimal(".1"), rounding=ROUND_HALF_UP) if reg else Decimal(0)
        if not legacy_in_person and percentage != Decimal(printed[:-1]):
            raise ValueError("Hawaii turnout block printed rate differs")
        units[unit][mode] = (reg, ballots, page, printed)
        previous_page = page
    roster = LEGACY_ROSTERS.get(year, ROSTER if year == 2026 else HISTORICAL_ROSTER)
    if digest(("\n".join(sorted(units)) + "\n").encode()) != roster:
        raise ValueError("Hawaii precinct reporting roster differs")
    rows = []
    for unit, modes in sorted(units.items()):
        if set(modes) != set(MODES) or (year != 2020 and modes["Mail"][0] != modes["In-Person"][0]):
            raise ValueError("Hawaii precinct modes do not share one registration count")
        (reg, mail, mail_page, mail_pct), (_, in_person, in_person_page, in_person_pct) = (
            modes[mode] for mode in MODES)
        nongeographic = unit in {"OS I", "OS II", "PRES", "Presidential"}
        if nongeographic and (reg or mail or in_person):
            raise ValueError("Hawaii nongeographic reporting unit is no longer empty")
        rows.append({"native_unit": unit, "geography_level": "nongeographic" if nongeographic else "precinct",
                     "reported_registration": reg, "reported_mail": mail, "reported_in_person": in_person,
                     "reported_mode_sum": mail + in_person, "mail_report_page": mail_page,
                     "in_person_report_page": in_person_page, "printed_mail_pct": mail_pct,
                     "printed_in_person_pct": in_person_pct})
    return rows


def historical_statewide_control(body, year):
    from pypdf import PdfReader

    if not 0 < len(body) <= MAX_BYTES or not body.startswith(b"%PDF-") or not body.rstrip().endswith(b"%%EOF"):
        raise ValueError("Invalid Hawaii historical statewide summary PDF")
    pdf = PdfReader(BytesIO(body), strict=True)
    if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 100:
        raise ValueError("Hawaii historical statewide PDF page inventory differs")
    clocks = set()
    parents = []
    labels = ("TOTAL REGISTRATION", "TOTAL TURNOUT", "Mail TURNOUT", "In-Person TURNOUT")
    day = int(election_date(year)[-2:])
    final = "FINAL REPORT" if year == 2022 else "Final"
    for i, page in enumerate(pdf.pages, 1):
        text = page.extract_text()
        if year == 2020:
            head = re.match(
                r"(Printed on:\s+\d{2}/\d{2}/2020 at \d{2}:\d{2}:\d{2} [ap]m)"
                rf"GENERAL ELECTION 2020 - State of Hawaii – Statewide November 3, 2020"
                rf"\*\*FINAL SUMMARY REPORT\*\*SUMMARY REPORTPage {i}(?![0-9])", text)
            if not head:
                raise ValueError("Hawaii 2020 statewide summary header differs")
            clocks.add(clock(" ".join(head[1].split()), year))
            chunks = text.split("REGISTRATION AND TURNOUT")
            if len(chunks) == 1:
                continue
            values = re.match(rf"\*{{80}}GENERAL {NUMERAL}TOTAL REGISTRATION {PERCENT} {NUMERAL}TOTAL TURNOUT "
                              rf"{PERCENT} {NUMERAL}\s+MAIL TURNOUT {PERCENT} {NUMERAL}\s+IN-PERSON TURNOUT\s*\n",
                              chunks[1])
            if len(chunks) != 2 or not values:
                raise ValueError("Hawaii 2020 statewide native statistics columns differ")
            counts = dict(zip(labels, (number(values[j]) for j in (1, 3, 5, 7))))
            printed = [values[j] for j in (2, 4, 6)]
        else:
            lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
            if lines[:5] != [f"GENERAL ELECTION {year} - State of Hawaii - Statewide", f"November {day}, {year}",
                             "SUMMARY REPORT", final, f"Page {i}"]:
                raise ValueError("Hawaii historical statewide summary election, stage or page differs")
            clocks.add(clock(lines[5], year))
            if "REGISTRATION AND TURNOUT" not in lines:
                continue
            if lines.count("REGISTRATION AND TURNOUT") != 1:
                raise ValueError("Hawaii statewide summary repeats its turnout block")
            index = lines.index("REGISTRATION AND TURNOUT")
            cells = lines[index + 1:index + 12]
            if len(cells) != 11 or tuple(cells[j].upper() for j in (0, 2, 5, 8)) != tuple(s.upper() for s in labels):
                raise ValueError("Hawaii historical statewide statistics columns differ")
            counts = dict(zip(labels, (number(cells[j]) for j in (1, 3, 6, 9))))
            printed = [cells[j] for j in (4, 7, 10)]
        for label, percentage in zip(labels[1:], printed):
            denominator = counts[labels[0]]
            if (not denominator or not re.fullmatch(PERCENT, percentage)
                    or (Decimal(100 * counts[label]) / denominator).quantize(
                        Decimal(".1"), rounding=ROUND_HALF_UP) != Decimal(percentage[:-1])):
                raise ValueError("Hawaii statewide printed percentage differs")
        parents.append(counts)
    if len(clocks) != 1 or len(parents) != 1:
        raise ValueError("Hawaii statewide summary does not identify a unique edition and control")
    return {"report_clock": clocks.pop().isoformat(), "native_values": parents[0]}


def statewide_control(body, *, year=2026):
    if year != 2026:
        return historical_statewide_control(body, year)
    report = hawaii_report(body, "histatewide")
    pages = report["pages"]
    parents = [page for page in pages if "native_values" in page]
    if len(parents) != 1 or any(p["native_report_status_literal"] != "FINAL" for p in pages):
        raise ValueError("Hawaii statewide control is not a unique FINAL edition")
    parent, = parents
    if any(p["source_clock"] != parent["source_clock"] for p in pages):
        raise ValueError("Hawaii statewide control mixes report clocks")
    return {"report_clock": clock(parent["source_clock"]).isoformat(), "native_values": parent["native_values"]}


def reconcile(detail, control, *, year=2026):
    state = control["native_values"]
    detail_clock, state_clock = (datetime.fromisoformat(x["report_clock"]) for x in (detail, control))
    if (detail_clock.date() != state_clock.date() or abs((detail_clock - state_clock).total_seconds()) > 600
            or state["TOTAL TURNOUT"] != state["Mail TURNOUT"] + state["In-Person TURNOUT"]
            or not 0 < state["TOTAL TURNOUT"] <= state["TOTAL REGISTRATION"]):
        raise ValueError("Hawaii precinct and statewide reports are not comparable editions")
    rows = detail_rows(detail, year=year)
    differences = {field: sum(row[field] for row in rows) - state[native] for field, native in (
        ("reported_registration", "TOTAL REGISTRATION"), ("reported_mail", "Mail TURNOUT"),
        ("reported_in_person", "In-Person TURNOUT"), ("reported_mode_sum", "TOTAL TURNOUT"))}
    if differences["reported_registration"]:
        raise ValueError("Hawaii precinct registration does not reconcile to the statewide control")
    return rows, differences


def collect(collector, feed, *, reuse_checked_week=False):
    from scripts.southeast_turnout import collect_report

    prior = (collector.prior.get(feed) or {}).get("data") or {}
    year = next(year for year in ELECTIONS if feed == feed_for(year))
    url, control_url = sources(year)

    def checked(body, _):
        original, _ = collector.acquire(control_url)
        report, support = {"url": url, **pin(body)}, {"url": control_url, **pin(original)}
        if prior.get("report") == report and prior.get("supporting_report") == support:
            return prior
        detail, control = parse_detail(body, year=year), statewide_control(original, year=year)
        for key, current in (("detail", detail), ("control", control)):
            observed = datetime.fromisoformat(current["report_clock"])
            if observed > collector.observation_time() or (prior and observed < datetime.fromisoformat(
                    prior[key]["report_clock"])):
                raise ValueError("Hawaii turnout report clock is future-dated or regressed")
        reconcile(detail, control, year=year)
        return {"report": report, "supporting_report": support, "detail": detail, "control": control,
                "participation_observation_qualified": False}

    return collect_report(collector, feed, url, checked, reuse_checked_week=reuse_checked_week)


def exports(entries, *, year=2026):
    entry = entries.get(feed_for(year)) or {}
    if (data := entry.get("data")) is None:
        return []
    detail, control = data["detail"], data["control"]
    url, control_url = sources(year)
    if (entry["status"] not in {"reported", "retained_after_failure"}
            or data["report"]["url"] != url or data["supporting_report"]["url"] != control_url):
        raise ValueError("Invalid Hawaii precinct participation source")
    rows, differences = reconcile(detail, control, year=year)
    common = {"state_code": "HI", "election_date": election_date(year), "source_status": entry["status"],
              "native_status": {2020: "**FINAL REPORT**", 2022: "FINAL REPORT"}.get(year, "FINAL"),
              "certification_independently_verified": False,
              "detail_report_clock": detail["report_clock"],
              "state_report_clock": control["report_clock"], "detail_source_sha256": data["report"]["sha256"],
              "state_source_sha256": data["supporting_report"]["sha256"], "detail_source_url": url,
              "state_source_url": control_url, **{f"precinct_sum_minus_state_{field}": value
                                            for field, value in differences.items()}}
    for row in rows:
        hold = ("nongeographic_reporting_unit" if row["geography_level"] == "nongeographic"
                else "reported_ballots_exceed_registration" if row["reported_mode_sum"] > row["reported_registration"]
                else "precinct_and_state_ballot_counts_disagree" if any(differences.values())
                else "no_positive_registration_denominator" if not row["reported_registration"] else None)
        row.update(geography_match_qualified=False, rate_hold_reason=hold,
                   qualified_registration_fraction_pct=None if hold else
                   100 * row["reported_mode_sum"] / row["reported_registration"])
    return [{**common, **row} for row in rows]


def main():
    import argparse
    import json
    from pathlib import Path

    from scripts.participation_intake.contract import encoded
    from scripts.supported_analytical_release import csv_bytes

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, choices=ELECTIONS, default=2026)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--precinct", type=Path, required=True)
    parser.add_argument("--statewide", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url, control_url = sources(args.year)
    data = {}
    receipts = json.loads(args.receipts.read_bytes())
    for key, path, source, field, extract in (
        ("report", args.precinct, url, "detail", parse_detail),
        ("supporting_report", args.statewide, control_url, "control", statewide_control),
    ):
        with path.open("rb") as stream:
            body = stream.read(MAX_BYTES + 1)
        if receipts[key] != {"url": source, **pin(body)}:
            raise ValueError(f"Hawaii report differs from the original pin: {key}")
        data[key], data[field] = receipts[key], extract(body, year=args.year)
    data["participation_observation_qualified"] = False
    feed, filename = feed_for(args.year), csv_for(args.year)
    rows = exports({feed: {"status": "reported", "data": data}}, year=args.year)
    args.output.mkdir()
    (args.output / filename).write_bytes(csv_bytes(rows))
    (args.output / "complete-native-query.json").write_bytes(encoded(data))


if __name__ == "__main__":
    main()
