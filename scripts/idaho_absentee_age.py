"""Reconcile Idaho's published early and returned-absentee counts by age."""

import csv
from datetime import datetime, timezone, timedelta
from functools import partial
from html import unescape
import io
import json
import re

from scripts.participation_intake.contract import pin
from scripts.southeast_turnout import collect_report


FEED = "ID-2026-early-and-absentee-age"
CSV = "participation-id-2026-early-and-absentee-age.csv"
INDEX = "https://voteidaho.gov/data-and-dashboards/absentee-tracker/"
CONTROL = "https://archive.voteidaho.gov/data/absentee/absentee_totals_2026_general.json"
CHART = "https://datawrapper.dwcdn.net/"
ELECTION = "2026-11-03"
AGES = ("18-29", "30-44", "45-59", "60-74", "75+")
ROLES = ("total_issued", "returned", "return_rate", "update_time", "early_voting", "total_voted")
LIMIT = 2_000_000


def discover(body):
    if not 0 < len(body) <= LIMIT:
        raise ValueError("Idaho absentee dashboard exceeds bounds")
    text = unescape(body.decode("utf-8-sig"))
    if ("Absentee & Early Voting Stats - 2026 General Election" not in text
            or re.findall(r'var dataPath\s*=\s*"([^"]+)"', text) != [CONTROL]):
        raise ValueError("Idaho absentee dashboard election or controls changed")
    matches = re.findall(r"<h3>\s*Absentee & Early Voting By Age\s*</h3>\s*"
                         r'<div [^>]*id="datawrapper-vis-([A-Za-z0-9]{5})"><script [^>]*'
                         r'src="https://datawrapper\.dwcdn\.net/\1/embed\.js"', text)
    if len(matches) != 1:
        raise ValueError("Missing or ambiguous Idaho age chart")
    return matches[0]


def counts(body):
    if not 0 < len(body) <= 8192:
        raise ValueError("Idaho absentee controls exceed bounds")
    items = json.loads(body)
    if not isinstance(items, list) or not all(isinstance(item, dict) and set(item) == {"name", "value"}
                                              for item in items) or tuple(item["name"] for item in items) != ROLES:
        raise ValueError("Idaho absentee control schema changed")
    values = {row["name"]: row["value"] for row in items}
    literal = values.pop("update_time")
    if not isinstance(literal, str) or not re.fullmatch(r"\d\d/\d\d \d\d:\d\d [AP]M M[SD]T", literal):
        raise ValueError("Unexpected Idaho absentee source clock")
    local = datetime.strptime("2026 " + literal[:-4], "%Y %m/%d %I:%M %p")
    source_clock = local.replace(tzinfo=timezone(timedelta(hours=-7 if literal.endswith("MST") else -6)))
    if any(not isinstance(value, str) or not re.fullmatch(r"\d{1,9}", value) for value in values.values()):
        raise ValueError("Invalid Idaho absentee controls")
    numbers = {name: int(value) for name, value in values.items()}
    if (numbers["returned"] > numbers["total_issued"]
            or numbers["total_voted"] != numbers["returned"] + numbers["early_voting"]
            or not numbers["total_issued"]
            or abs(numbers["return_rate"] * numbers["total_issued"] - 100 * numbers["returned"])
            > numbers["total_issued"] / 2):
        raise ValueError("Idaho absentee mode controls do not reconcile")
    return {"source_clock_literal": literal, "source_clock": source_clock.isoformat(), **numbers}


def chart_metadata(body, *, chart):
    if not 0 < len(body) <= LIMIT:
        raise ValueError("Idaho age chart exceeds bounds")
    text = body.decode("utf-8")
    values = re.findall(r'"publicId":"' + re.escape(chart) + r'"[^{}]{0,400}'
                        r'"publishedAt":"([^"]+)","publicUrl":"([^"]+)","publicVersion":([1-9]\d*)'
                        r'[^{}]{0,500}"lastModifiedAt":"([^"]+)"', text)
    if len(values) != 1 or '"dataset.csv":{"load":true,"url":"dataset.csv"}' not in text:
        raise ValueError("Missing unique Idaho chart edition or declared dataset")
    published, base, version, modified = values[0]
    if (base != f"{CHART}{chart}/{version}/" or f'"nextPublicUrl":"{base}"' not in text
            or not all(re.fullmatch(r"2026-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", t)
                       and datetime.fromisoformat(t) for t in (published, modified))
            or modified < published):
        raise ValueError("Idaho chart edition or clocks disagree")
    return {"chart_id": chart, "chart_version": int(version), "chart_published_at": published,
            "chart_modified_at": modified, "csv_url": base + "dataset.csv"}


def validate_rows(rows, control):
    if [row[0] for row in rows] != list(AGES):
        raise ValueError("Idaho age group inventory changed")
    for _, absentee, early, total in rows:
        if any(type(n) is not int or n < 0 for n in (absentee, early, total)) or absentee + early != total:
            raise ValueError("Idaho age row does not reconcile")
    if [sum(row[i] for row in rows) for i in range(1, 4)] != [
            control["returned"], control["early_voting"], control["total_voted"]]:
        raise ValueError("Idaho age rows disagree with dashboard mode controls")
    return rows


def age_rows(body, *, control):
    if not 0 < len(body) <= 8192:
        raise ValueError("Idaho age dataset exceeds bounds")
    reader = csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
    if next(reader, None) != ["AgeBin", "abs", "ev", "n"]:
        raise ValueError("Idaho age dataset schema changed")
    rows = []
    for row in reader:
        if len(row) != 4 or any(not re.fullmatch(r"\d{1,9}", v) for v in row[1:]):
            raise ValueError("Invalid Idaho age dataset row")
        rows.append([row[0], *map(int, row[1:])])
    return validate_rows(rows, control)


def collect(collector, *, reuse_checked_week=False):
    prior = (collector.prior.get(FEED) or {}).get("data") or {}

    def checked(page, _):
        chart = discover(page)
        if prior and chart != prior["chart"]["chart_id"]:
            raise ValueError("Replacement Idaho chart requires a separate identity review")
        control_url, embed_url = CONTROL, CHART + chart + "/embed.js"
        control_body, _ = collector.acquire(control_url)
        embed_body, _ = collector.acquire(embed_url)
        control = counts(control_body)
        meta = chart_metadata(embed_body, chart=chart)
        now = collector.observation_time()
        if (datetime.fromisoformat(control["source_clock"]) > now
                or datetime.fromisoformat(meta["chart_modified_at"]) > now):
            raise ValueError("Future-dated Idaho dashboard or chart")
        if prior and (datetime.fromisoformat(control["source_clock"]) < datetime.fromisoformat(prior["control"]["source_clock"])
                      or meta["chart_version"] < prior["chart"]["chart_version"]):
            raise ValueError("Idaho absentee source clock or chart edition regressed")
        raw, _ = collector.acquire(meta["csv_url"])
        rows = age_rows(raw, control=control)
        if prior and (control["source_clock"] == prior["control"]["source_clock"] and control != prior["control"]
                      or meta["chart_version"] == prior["chart"]["chart_version"] and rows != prior["rows"]):
            raise ValueError("Idaho absentee numbers changed without a new source edition")
        if prior and (control, meta, rows) == (prior["control"], prior["chart"], prior["rows"]):
            return prior
        evidence = {key: {"url": url, **pin(body)} for key, url, body in (
            ("control", control_url, control_body), ("embed", embed_url, embed_body),
            ("csv", meta["csv_url"], raw))}
        return {"control": control, "chart": meta, "rows": rows, "evidence": evidence,
                "participation_observation_qualified": False}

    return collect_report(collector, FEED, INDEX, checked, reuse_checked_week=reuse_checked_week)


def exports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is None:
        return
    chart, control, evidence = data["chart"], data["control"], data["evidence"]
    if (entry["status"] not in ("reported", "retained_after_failure") or entry["source"]["url"] != INDEX
            or not re.fullmatch(r"[A-Za-z0-9]{5}", chart["chart_id"])
            or evidence["csv"]["url"] != f'{CHART}{chart["chart_id"]}/{chart["chart_version"]}/dataset.csv'
            or evidence["csv"]["url"] != chart["csv_url"] or evidence["control"]["url"] != CONTROL):
        raise ValueError("Idaho age archive provenance differs")
    for age, absentee, early, total in validate_rows(data["rows"], control):
        yield {"state_code": "ID", "election_date": ELECTION, "age_group": age, "absentee_returns": absentee,
               "early_votes": early, "combined_source_reported_activity": total,
               "source_status": entry["status"], "source_clock": control["source_clock"],
               "source_clock_literal": control["source_clock_literal"], "chart_version": chart["chart_version"],
               "chart_published_at": chart["chart_published_at"], "chart_modified_at": chart["chart_modified_at"],
               "source_url": evidence["csv"]["url"], "source_sha256": evidence["csv"]["sha256"],
               "control_url": CONTROL, "control_sha256": evidence["control"]["sha256"],
               "not_all_mode_turnout_or_an_age_specific_turnout_rate": True}


def original_reports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is not None:
        chart, evidence = data["chart"], data["evidence"]
        embed = CHART + chart["chart_id"] + "/embed.js"
        yield FEED + "-dashboard", entry["source"], ".html", LIMIT, entry["source"]["url"] == INDEX, discover, chart["chart_id"]
        yield FEED + "-control", evidence["control"], ".json", 8192, evidence["control"]["url"] == CONTROL, counts, data["control"]
        yield (FEED + "-embed", evidence["embed"], ".js", LIMIT, evidence["embed"]["url"] == embed,
               partial(chart_metadata, chart=chart["chart_id"]), chart)
        yield (FEED + "-age", evidence["csv"], ".csv", 8192, evidence["csv"]["url"] == chart["csv_url"],
               partial(age_rows, control=data["control"]), data["rows"])
