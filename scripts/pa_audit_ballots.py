"""Preserve the Pennsylvania general-election audit universe and sample separately."""

import csv
from datetime import datetime, timezone
import io
import re

from scripts.participation_intake.contract import IntakeError, pin
from scripts.results_turnout_history import archive_link
from scripts.southeast_turnout import collect_report


FEED = "PA-2026-general-ballot-audit"
CSV = "participation-pa-2026-ballot-audit.csv"
INDEX = "https://www.pa.gov/agencies/vote/elections/post-election-audits"
ROUTE = (
    r"https://www\.pa\.gov/content/dam/copapwp-pagov/en/vote/elections/risk-limiting-audit-reports/"
    r"2026-general-election/audit-report-november-3-2026-general-election-(2026-\d{2}-\d{2}t\d{4}z)\.csv"
)
LABEL = r"View detailed results of the 2026 General Election risk-limiting audit\.?"
MAX_BYTES = 500_000


def integer(raw):
    if not re.fullmatch(r"\d{1,9}", raw):
        raise ValueError("Invalid Pennsylvania audit ballot count")
    return int(raw)


def edition(url):
    match = re.fullmatch(ROUTE, url)
    if not match:
        raise ValueError("Unreviewed Pennsylvania audit report route")
    return datetime.strptime(match[1], "%Y-%m-%dt%H%Mz").replace(tzinfo=timezone.utc)


def parse(body, *, url):
    if not 0 < len(body) <= MAX_BYTES:
        raise ValueError("Unexpected Pennsylvania audit report size")
    dates = edition(url)
    sections = {}
    section = None
    for row in csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""), strict=True):
        if not any(row):
            continue
        if len(row) == 1 and (match := re.fullmatch(r"######## ([A-Z ]+) ########", row[0])):
            section = match[1]
            if section in sections:
                raise ValueError("Duplicate Pennsylvania audit report section")
            sections[section] = []
        elif section:
            sections[section].append(row)
        else:
            raise ValueError("Missing Pennsylvania audit section")
    if set(sections) != {"ELECTION INFO", "CONTESTS", "AUDIT SETTINGS", "ROUNDS", "SAMPLED BATCHES"}:
        raise ValueError("Unexpected Pennsylvania audit report sections")
    if sections["ELECTION INFO"] != [
        ["Organization", "Election Name", "State"], ["Pennsylvania", "2026 General Election", "PA"]
    ]:
        raise ValueError("Not the Pennsylvania November 2026 general-election audit")
    head, contest = sections["CONTESTS"]
    if head != ["Contest Name", "Targeted?", "Number of Winners", "Votes Allowed", "Total Ballots Cast",
                "Vote Totals", "Vote Totals from Batches", "Pending Ballots"] or len(contest) != len(head) or (
                    contest[:4] != ["Governor", "Targeted", "1", "1"]):
        raise ValueError("Changed Pennsylvania audit contest or ballot fields")
    total, pending = integer(contest[4]), integer(contest[7])
    settings_head, settings = sections["AUDIT SETTINGS"]
    if settings_head[:3] != ["Audit Name", "Audit Type", "Audit Math Type"] or settings[:3] != [
        "November 3, 2026 General Election", "BATCH_COMPARISON", "MACRO"
    ]:
        raise ValueError("Changed Pennsylvania audit method or election")
    header, *rounds = sections["ROUNDS"]
    expected = ["Round Number", "Contest Name", "Targeted?", "Sample Size", "Risk Limit Met?", "P-Value",
                "Start Time", "End Time", "Audited Votes", "Batches Sampled", "Ballots Sampled"]
    if header[:11] != expected or not rounds or any(
        len(row) != len(header) or row[:3] != [str(i), "Governor", "Targeted"]
        or row[4] not in {"Yes", "No"} or
        not datetime(2026, 11, 3, tzinfo=timezone.utc) <= datetime.fromisoformat(row[6])
        <= datetime.fromisoformat(row[7]) <= dates
        for i, row in enumerate(rounds, 1)
    ):
        raise ValueError("Invalid Pennsylvania audit rounds")
    header, *batches, footer = sections["SAMPLED BATCHES"]
    if (header[:5] != ["Jurisdiction Name", "Batch Name", "Ballots in Batch", "Ticket Numbers: Governor", "Audited?"]
            or not batches or footer[:2] != ["Totals", ""] or any(
                len(row) != len(header) or not re.fullmatch(r"[A-Za-z ]+", row[0])
                or not row[1].strip() or row[4] not in {"Yes", "No"} for row in batches)
            or len({(row[0], row[1]) for row in batches}) != len(batches)):
        raise ValueError("Invalid Pennsylvania sampled-batch roster")
    # This edition enumerates the distinct physical batches, not individual sampling draws.
    sample = [[row[0], row[1], integer(row[2]), row[4]] for row in batches]
    sampled_ballots = sum(row[2] for row in sample)
    if (not 0 < sampled_ballots <= total or pending > total or sampled_ballots != integer(footer[2])
            or len(rounds) == 1 and (
                len(sample) != integer(rounds[0][9]) or sampled_ballots != integer(rounds[0][10]))):
        raise ValueError("Pennsylvania audit totals do not reconcile")
    return {
        "report_edition_utc": dates.isoformat(), "targeted_contest": contest[0],
        "audit_report_total_ballots_cast": total, "audit_report_pending_ballots": pending,
        "audit_rounds": len(rounds), "risk_limit_met": rounds[-1][4] == "Yes",
        "sample_distinct_batches": len(sample), "sample_ballots": sampled_ballots,
        "sample": sample, "participation_observation_qualified": False,
    }


def collect(collector, feed, *, reuse_checked_week=False):
    prior = (collector.prior.get(feed) or {}).get("data") or {}

    def checked(index, _):
        url = archive_link(index, INDEX, ROUTE, label=LABEL)
        if url is None:
            raise IntakeError("report_not_linked", "No 2026 general-election ballot audit report is linked")
        observed = edition(url)
        if observed > collector.observation_time() or prior and observed < edition(prior["report"]["url"]):
            raise ValueError("Pennsylvania audit report clock is future-dated or regressed")
        original, _ = collector.acquire(url)
        source = {"url": url, **pin(original)}
        if prior.get("report") == source:
            return prior
        return {**parse(original, url=url), "report": source}

    return collect_report(collector, feed, INDEX, checked, reuse_checked_week=reuse_checked_week)


def exports(entries):
    entry = entries.get(FEED) or {}
    data = entry.get("data")
    if data is None:
        return []
    report = data["report"]
    if (entry["status"] not in {"reported", "retained_after_failure"}
            or edition(report["url"]).isoformat() != data["report_edition_utc"]
            or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])):
        raise ValueError("Unreviewed Pennsylvania audit evidence")
    common = {
        "state_code": "PA", "election_date": "2026-11-03", "source_status": entry["status"],
        "report_edition_utc": data["report_edition_utc"], "targeted_contest": data["targeted_contest"],
        "source_url": report["url"], "source_sha256": report["sha256"],
        "final_turnout_qualified": False, "geographic_turnout_qualified": False,
    }
    return [
        {**common, "record_type": "audit_universe",
         **{key: data[key] for key in ("audit_report_total_ballots_cast", "audit_report_pending_ballots",
                                      "audit_rounds", "risk_limit_met", "sample_distinct_batches", "sample_ballots")}},
        *({**common, "record_type": "sampled_batch", "sample_jurisdiction": county, "sample_batch": batch,
           "sample_batch_ballots": ballots, "sample_batch_audited_literal": audited}
          for county, batch, ballots, audited in data["sample"]),
    ]
