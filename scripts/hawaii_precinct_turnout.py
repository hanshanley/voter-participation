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
MAX_BYTES = 10_000_000
ROSTER = "9392e63c74bac626dee1917ad55ef3d5db603cc7460175713849771890775db3"
FOOTER = "PRECINCT REGISTRATION AND TURNOUT"
MODES = ("Mail", "In-Person")


def clock(value):
    observed = datetime.strptime(value, "Printed on: %m/%d/%Y at %I:%M:%S %p")
    if observed.date().isoformat() < "2026-11-03":
        raise ValueError("Hawaii precinct report predates the election")
    return observed.replace(tzinfo=ZoneInfo("Pacific/Honolulu"))


def number(text):
    if not re.fullmatch(r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)", text):
        raise ValueError("Invalid Hawaii turnout number")
    return int(text.replace(",", ""))


def parse_detail(body):
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
    for page_number, page in enumerate(pdf.pages, 1):
        lines = [" ".join(line.split()) for line in page.extract_text().splitlines() if line.strip()]
        if (len(lines) < 6 or lines[1] != "GENERAL ELECTION 2026 - State of Hawaii - Statewide Precinct"
                or lines[3:5] != ["November 3, 2026", "FINAL"] or lines[-1] != f"PAGE {page_number}"):
            raise ValueError("Hawaii precinct PDF election, status or page sequence differs")
        observed = clock(lines[0])
        if source_clock is None:
            source_clock = observed
        if observed != source_clock:
            raise ValueError("Hawaii precinct PDF mixes report clocks")
        match = re.fullmatch(r"(Mail|In-Person) ([0-9]{2}-[0-9]{2}|OS [I]{1,2})", lines[2])
        if not match:
            raise ValueError("Hawaii precinct PDF mode or precinct identity differs")
        mode, unit = match.groups()
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
                or block[6] != f"{mode} TURNOUT"):
            raise ValueError("Hawaii native precinct turnout block differs")
        records.append([unit, mode, page_number, block[5], block[7], block[8]])
        completed.add(identity)
    if previous not in completed:
        raise ValueError("Last Hawaii precinct mode is missing its native turnout block")
    facts = {"report_clock": source_clock.isoformat(), "pages": len(pdf.pages), "mode_blocks": records}
    detail_rows(facts)
    return facts


def detail_rows(detail):
    units = {}
    previous_page = 0
    for unit, mode, page, native_reg, native_ballots, printed in detail["mode_blocks"]:
        reg, ballots = number(native_reg), number(native_ballots)
        if (mode not in MODES or type(page) is not int or not previous_page < page <= detail["pages"]
                or mode in units.setdefault(unit, {})
                or not re.fullmatch(r"[0-9]{1,3}\.[0-9]%", printed)):
            raise ValueError("Hawaii turnout block identity or counts differ")
        percentage = (Decimal(100 * ballots) / reg).quantize(
            Decimal(".1"), rounding=ROUND_HALF_UP) if reg else Decimal(0)
        if percentage != Decimal(printed[:-1]):
            raise ValueError("Hawaii turnout block printed rate differs")
        units[unit][mode] = (reg, ballots, page, printed)
        previous_page = page
    if digest(("\n".join(sorted(units)) + "\n").encode()) != ROSTER:
        raise ValueError("Hawaii precinct reporting roster differs")
    rows = []
    for unit, modes in sorted(units.items()):
        if set(modes) != set(MODES) or modes["Mail"][0] != modes["In-Person"][0]:
            raise ValueError("Hawaii precinct modes do not share one registration count")
        (reg, mail, mail_page, mail_pct), (_, in_person, in_person_page, in_person_pct) = (
            modes[mode] for mode in MODES)
        if unit.startswith("OS ") and (reg or mail or in_person):
            raise ValueError("Hawaii nongeographic reporting unit is no longer empty")
        rows.append({"native_unit": unit, "geography_level": "nongeographic" if unit.startswith("OS ") else "precinct",
                     "reported_registration": reg, "reported_mail": mail, "reported_in_person": in_person,
                     "reported_mode_sum": mail + in_person, "mail_report_page": mail_page,
                     "in_person_report_page": in_person_page, "printed_mail_pct": mail_pct,
                     "printed_in_person_pct": in_person_pct})
    return rows


def statewide_control(body):
    report = hawaii_report(body, "histatewide")
    pages = report["pages"]
    parents = [page for page in pages if "native_values" in page]
    if len(parents) != 1 or any(p["native_report_status_literal"] != "FINAL" for p in pages):
        raise ValueError("Hawaii statewide control is not a unique FINAL edition")
    parent, = parents
    if any(p["source_clock"] != parent["source_clock"] for p in pages):
        raise ValueError("Hawaii statewide control mixes report clocks")
    return {"report_clock": clock(parent["source_clock"]).isoformat(), "native_values": parent["native_values"]}


def reconcile(detail, control):
    state = control["native_values"]
    detail_clock, state_clock = (datetime.fromisoformat(x["report_clock"]) for x in (detail, control))
    if (detail_clock.date() != state_clock.date() or abs((detail_clock - state_clock).total_seconds()) > 600
            or state["TOTAL TURNOUT"] != state["Mail TURNOUT"] + state["In-Person TURNOUT"]
            or not 0 < state["TOTAL TURNOUT"] <= state["TOTAL REGISTRATION"]):
        raise ValueError("Hawaii precinct and statewide reports are not comparable editions")
    rows = detail_rows(detail)
    differences = {field: sum(row[field] for row in rows) - state[native] for field, native in (
        ("reported_registration", "TOTAL REGISTRATION"), ("reported_mail", "Mail TURNOUT"),
        ("reported_in_person", "In-Person TURNOUT"), ("reported_mode_sum", "TOTAL TURNOUT"))}
    if differences["reported_registration"]:
        raise ValueError("Hawaii precinct registration does not reconcile to the statewide control")
    return rows, differences


def collect(collector, feed, *, reuse_checked_week=False):
    from scripts.southeast_turnout import collect_report

    prior = (collector.prior.get(feed) or {}).get("data") or {}

    def checked(body, _):
        original, _ = collector.acquire(HI_URL)
        report, support = {"url": URL, **pin(body)}, {"url": HI_URL, **pin(original)}
        if prior.get("report") == report and prior.get("supporting_report") == support:
            return prior
        detail, control = parse_detail(body), statewide_control(original)
        for key, current in (("detail", detail), ("control", control)):
            observed = datetime.fromisoformat(current["report_clock"])
            if observed > collector.observation_time() or (prior and observed < datetime.fromisoformat(
                    prior[key]["report_clock"])):
                raise ValueError("Hawaii turnout report clock is future-dated or regressed")
        reconcile(detail, control)
        return {"report": report, "supporting_report": support, "detail": detail, "control": control,
                "participation_observation_qualified": False}

    return collect_report(collector, feed, URL, checked, reuse_checked_week=reuse_checked_week)


def exports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is None:
        return []
    detail, control = data["detail"], data["control"]
    if (entry["status"] not in {"reported", "retained_after_failure"}
            or data["report"]["url"] != URL or data["supporting_report"]["url"] != HI_URL):
        raise ValueError("Invalid Hawaii precinct participation source")
    rows, differences = reconcile(detail, control)
    common = {"state_code": "HI", "election_date": "2026-11-03", "source_status": entry["status"],
              "native_status": "FINAL", "certification_independently_verified": False,
              "detail_report_clock": detail["report_clock"],
              "state_report_clock": control["report_clock"], "detail_source_sha256": data["report"]["sha256"],
              "state_source_sha256": data["supporting_report"]["sha256"], "detail_source_url": URL,
              "state_source_url": HI_URL, **{f"precinct_sum_minus_state_{field}": value
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
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--precinct", type=Path, required=True)
    parser.add_argument("--statewide", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = {}
    receipts = json.loads(args.receipts.read_bytes())
    for key, path, source, field, extract in (
        ("report", args.precinct, URL, "detail", parse_detail),
        ("supporting_report", args.statewide, HI_URL, "control", statewide_control),
    ):
        with path.open("rb") as stream:
            body = stream.read(MAX_BYTES + 1)
        if receipts[key] != {"url": source, **pin(body)}:
            raise ValueError(f"Hawaii report differs from the original pin: {key}")
        data[key], data[field] = receipts[key], extract(body)
    data["participation_observation_qualified"] = False
    rows = exports({FEED: {"status": "reported", "data": data}})
    args.output.mkdir()
    (args.output / CSV).write_bytes(csv_bytes(rows))
    (args.output / "complete-native-query.json").write_bytes(encoded(data))


if __name__ == "__main__":
    main()
