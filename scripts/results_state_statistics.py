"""Refresh reviewed state-only participation without inferring an electorate."""

import copy
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from html.parser import HTMLParser
import re


URL = "https://scvotes.gov/state-election-commission-certifies-2026-statewide-general-election/"
OFFICIAL = {"SC": URL}
TITLE = "State Election Commission Certifies 2026 Statewide General Election"
HEADING = "2026 Statewide General Election Statistics"
PROFILE = "sc-native-state-participation-v1"
BASIS = "active_registration_exact_stock_not_supplied"
LABELS = (
    ("early", "Early Voting Turnout"),
    ("absentee", "Absentee Voting"),
    ("election_day", "Election Day Turnout"),
    ("total", "Total Voter Turnout"),
    ("active_registered_pct", "Turnout of Active Registered Voters"),
)
INTEGER = r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)"
PERCENT = r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?%"


class _Statistics(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tag = None
        self.parts = []
        self.headings = []
        self.paragraphs = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.ignored += 1
        if not self.ignored and tag in ("h1", "p"):
            if self.tag is not None:
                raise ValueError("Nested statistical paragraphs are ambiguous")
            self.tag, self.parts = tag, []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.ignored = max(0, self.ignored - 1)
        if not self.ignored and tag == self.tag:
            text = " ".join("".join(self.parts).split())
            (self.headings if tag == "h1" else self.paragraphs).append(text)
            self.tag, self.parts = None, []

    def handle_data(self, data):
        if self.tag and not self.ignored:
            self.parts.append(data)


def statistics(body, state):
    if state != "SC":
        raise ValueError("No reviewed state-only statistical profile")
    parser = _Statistics()
    parser.feed(body.decode("utf-8"))
    parser.close()
    if parser.tag is not None or parser.headings != [TITLE]:
        raise ValueError("State-only election title or HTML structure changed")
    if parser.paragraphs.count(HEADING) != 1:
        raise ValueError("State-only statistical section is missing or duplicated")
    start = parser.paragraphs.index(HEADING) + 1
    selected = parser.paragraphs[start:start + len(LABELS)]
    fields = {}
    for (name, label), text in zip(LABELS, selected):
        if sum(item.startswith(label + ":") for item in parser.paragraphs) != 1:
            raise ValueError("Native statistical label is missing or duplicated")
        pattern = (PERCENT if name == "active_registered_pct" else INTEGER
                   if name == "total" else INTEGER + r" \(" + PERCENT + r"\)")
        match = re.fullmatch(re.escape(label) + r": (" + pattern + r")", text)
        if match is None:
            raise ValueError("Native statistical count, percentage or column changed")
        literal = match[1]
        if name == "active_registered_pct":
            fields[name] = {"literal": literal, "value": literal}
        else:
            value = literal.split(" (")[0]
            count = int(value.replace(",", ""))
            if count > 2**53 - 1:
                raise ValueError("Native count is outside the exact browser integer range")
            fields[name] = {"literal": value, "value": count}
            if name != "total":
                fields[name]["percentage_literal"] = literal.split(" (")[1][:-1]
    if len(fields) != len(LABELS):
        raise ValueError("Incomplete native statewide statistics")
    if sum(fields[name]["value"] for name in ("early", "absentee", "election_day")) != (
            fields["total"]["value"]):
        raise ValueError("Native statewide participation components disagree")
    percentages = [fields[name]["percentage_literal"] for name in ("early", "absentee", "election_day")]
    if any(not 0 <= Decimal(value[:-1]) <= 100 for value in percentages + [
            fields["active_registered_pct"]["literal"]]):
        raise ValueError("Native percentage is outside its source scale")
    diagnostics = []
    for name in ("early", "absentee", "election_day"):
        expected = (str((Decimal(100) * fields[name]["value"] / fields["total"]["value"]).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP)) + "%") if fields["total"]["value"] else None
        diagnostics.append({"field": name, "native": fields[name]["percentage_literal"],
                            "count_implied_one_decimal": expected,
                            "native_value_repaired": False})
    return {
        "ballots": fields["total"]["value"], "denominator": None, "denominator_basis": BASIS,
        "published_pct": None, "validated_pct": None, "source_update_label": None,
        "source_date": None, "source_update_timezone": None,
        "reported_units": None, "total_units": None, "reporting_unit": None,
        "native_state_statistics": {
            "contract": "participation.native_state_statistics.v1", "profile": PROFILE,
            "state_code": state, "election_year": 2026, "source_url": URL,
            "native_title": TITLE, "fields": fields, "percentage_diagnostics": diagnostics,
            "count_clock_supplied": False, "registered_denominator_supplied": False,
            "certification_title_is_not_counting_clock_or_unique_person_validation": True,
            "whole_publisher_html_redistributed": False,
        },
        "quality": [
            "Native Total Voter Turnout is source-defined statewide participation, not candidate votes, separately qualified physical ballots or independently deduplicated people.",
            "The three native mode counts reconcile to the printed total; they are not added to that total again.",
            "The exact active-registration stock and native count-update clock are not supplied. No denominator, analytical rate, timezone or completion counter is inferred.",
            "Native printed mode percentages and any rounding disagreements are retained unrepaired.",
            "An article's publication or reported certification date is not a count-update clock.",
            "This state-only report supplies no new county, precinct, demographic or behavioral-model qualification.",
        ],
    }


def refresh(row, data, provenance):
    facts = data.get("native_state_statistics") or {}
    if (facts.get("profile") != PROFILE or facts.get("state_code") != "SC"
            or facts.get("election_year") != 2026 or facts.get("source_url") != URL
            or row.get("state_code") != "SC" or row.get("source_url") != URL
            or row.get("county_id") != "native:SC:statewide"
            or row.get("geography_level") != "statewide" or row.get("mode") != "official"
            or row.get("participation_measure_kind") != "source_defined_participation_count"
            or row.get("cast_ballot_count_qualified") is not False
            or row.get("unique_voter_count_qualified") is not False
            or row.get("maps_approved") is not False
            or row.get("denominator_basis") != BASIS or row.get("denominator") is not None
            or data.get("denominator") is not None or data.get("validated_pct") is not None
            or data.get("source_update_label") is not None
            or provenance.get("url") != URL
            or not re.fullmatch(r"[a-f0-9]{64}", provenance.get("sha256", ""))):
        raise ValueError("Reviewed state-only source, measure or qualification changed")
    fields = facts.get("fields") or {}
    value = data.get("ballots")
    if (type(value) is not int or value < 0
            or fields.get("total", {}).get("value") != value
            or set(fields) != {name for name, _ in LABELS}):
        raise ValueError("State-only count differs from its full native statistical query")
    if any(not isinstance(fields[name], dict) or type(fields[name].get("value")) is not int
           for name in ("early", "absentee", "election_day", "total")):
        raise ValueError("State-only native values must remain literal integer counts")
    # Revalidate the complete selected factual query, not excluded publisher HTML.
    paragraphs = []
    for name, label in LABELS:
        field = fields[name]
        literal = field.get("literal", "")
        if name not in ("total", "active_registered_pct"):
            literal += " (" + field.get("percentage_literal", "") + ")"
        paragraphs.append("<p>" + label + ": " + escape(literal) + "</p>")
    selected = ("<h1>" + TITLE + "</h1><p>" + HEADING + "</p>" + "".join(paragraphs)).encode()
    if statistics(selected, "SC") != data:
        raise ValueError("State-only native values, literal fields or qualifications disagree")
    result = copy.deepcopy(row)
    result.setdefault("accepted_source_provenance", {
        name: copy.deepcopy(row.get(name)) for name in (
            "source_sha256", "source_snapshot", "source_date", "source_retrieved_at",
            "source_update_label", "source_update_timezone", "native_statistics", "quality")})
    result.update(
        ballots=value, native_statistics=copy.deepcopy(facts),
        native_printed_pct=fields["active_registered_pct"]["literal"],
        native_published_pct=fields["active_registered_pct"]["literal"],
        source_status_literal=TITLE, source_sha256=provenance["sha256"],
        source_snapshot="automatic-native:" + provenance["sha256"],
        source_date=None, source_retrieved_at=None, source_update_label=None,
        source_update_timezone=None, reported_pct=None, validated_pct=None,
        reported_units=None, total_units=None, quality=copy.deepcopy(data["quality"]),
        source_reporting_label="; ".join(data["quality"]), automatic_source_refresh=True)
    return result
