"""Refresh reviewed state-only participation without inferring an electorate."""

import copy
from decimal import Decimal, ROUND_HALF_UP
from html import escape, unescape
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
WEBFORMS_STATE_PROFILES = {
    "https://electionresults.nebraska.gov/VoterTurnoutDetails.aspx?map=PREC": {
        "state_code": "NE", "name": "Nebraska", "title": "Nebraska Secretary of State",
        "source_id": "ne-sos-turnout-20261113",
        "observation_id": "c776dee50bc9a20b89b0291777f7ce96",
        "legacy_mirror_pin": {
            "bytes": 654, "sha256": "7178b5b2b73d31dc9e9c8c2face876f295c73c012ddfecdb77e4065be5110be5"},
    },
}


def webforms_header(body, title):
    text = body.decode("utf-8-sig")

    def label(value):
        return " ".join(unescape(re.sub(r"<[^>]*>", "", value)).split())

    titles = re.findall(r"<title>(.*?)</title>", text, re.S)
    if len(titles) != 1 or label(titles[0]) != title:
        raise ValueError("Native statistical publisher identity changed")
    if (len(re.findall(r"<h2>\s*General Election November 3, 2026\s*</h2>", text)) != 1
            or len(re.findall(r"<h1>\s*Unofficial Results\s*</h1>", text)) != 1):
        raise ValueError("Native statistical election/status changed")

    def field(css, expected=None):
        values = re.findall(r'<span class="' + css + r'">(.*?)</span>', text, re.S)
        if len(values) != 1:
            raise ValueError("Missing or repeated native statistical header")
        value = label(values[0])
        if expected is not None:
            if value != expected:
                raise ValueError("Native statistical measure changed")
        elif not re.fullmatch(INTEGER, value) or int(value.replace(",", "")) > 2**53 - 1:
            raise ValueError("Missing or unsafe native statistic is not a recorded zero")
        return value

    field("header-ballot-text", "Ballots Cast")
    field("header-voter-text", "Registered Voters")
    count, registered = field("header-ballot-number"), field("header-voter-number")
    partial, reported, total = [int(field(css).replace(",", "")) for css in (
        "header-partial-number", "header-total-number", "header-totalprecincts-text")]
    if partial != 0 or reported != total or total <= 0:
        raise ValueError("Native statistical reporting scope requires review")
    clocks = re.findall(r"Results last updated:</span><span>([^<]+)</span>", text)
    if len(clocks) > 1:
        raise ValueError("Conflicting native update clocks")
    percentages = re.findall(
        r'<canvas id="(voter-turnout(?:-mobile)?-canvas)"></canvas>\s*'
        r'<div class="dough-percent"><span class="int">([0-9]+)</span>'
        r'<span class="dec">((?:\.[0-9]+)?%)</span></div>', text)
    values = [integer + fraction for _, integer, fraction in percentages]
    if values and (len(values) != 2 or len(set(values)) != 1
                   or {identity for identity, _, _ in percentages} != {
                       "voter-turnout-canvas", "voter-turnout-mobile-canvas"}
                   or not 0 <= Decimal(values[0][:-1]) <= 100):
        raise ValueError("Native desktop/mobile turnout percentages conflict")
    return {
        "query_id": "native-webforms-state-statistics", "geography_level": "state",
        "native_measure_literal": "Ballots Cast", "native_report_status_literal": "Unofficial Results",
        "count": int(count.replace(",", "")), "count_literal": count,
        "registered": int(registered.replace(",", "")), "registered_literal": registered,
        "native_fraction_literal": values[0] if values else None,
        "source_clock": unescape(clocks[0]) if clocks else None,
        "reported_units": reported, "total_units": total,
    }


def webforms_state_template(template, url):
    profile = WEBFORMS_STATE_PROFILES.get(url)
    if profile is None or template.get("id") != profile["observation_id"]:
        return False
    measure = template.get("measure") or {}
    if (template.get("source", {}).get("id") != profile["source_id"]
            or template.get("source", {}).get("url") != url
            or template.get("view", {}).get("source_url") != url
            or template.get("geography", {}).get("level") != "state"
            or template["geography"].get("state_code") != profile["state_code"]
            or template["geography"].get("name") != profile["name"]
            or template.get("election", {}).get("year") != 2026
            or template["election"].get("type") != "general"
            or measure != {
                "id": "previously-reviewed-participation-count", "kind": "participation_reported",
                "literal": "Reported ballots (previously reviewed export label, not a new native qualification)",
                "mode": "source_defined", "unit": "source_reported_count"}):
        raise ValueError("Reviewed native statewide header scope or measure changed")
    return True


def apply_webforms_state_context(old, row, source):
    from scripts.participation_intake.contract import encoded, pin

    native = copy.deepcopy(row["view"]["native_record"])
    row["view"]["native_record"] = native
    query = native.get("query") or {}
    url = source.get("url")
    if (not webforms_state_template(old, url)
            or query.get("query_id") != "native-webforms-state-statistics"
            or query.get("geography_level") != "state"
            or query.get("native_measure_literal") != "Ballots Cast"
            or query.get("native_report_status_literal") != "Unofficial Results"
            or query.get("count") != row["count"]["value"]
            or int(query.get("count_literal", "").replace(",", "")) != query["count"]
            or type(query["count"]) is not int or query["count"] < 0
            or type(query.get("registered")) is not int or query["registered"] < 0
            or int(query.get("registered_literal", "").replace(",", "")) != query["registered"]
            or query.get("source_clock") != row["source_clock"]["literal"]
            or native.get("private_original_pin") != {
                "bytes": source.get("bytes"), "sha256": source.get("sha256")}
            or query.get("reported_units") != row["reporting_status"]["reported_units"]
            or query.get("total_units") != row["reporting_status"]["total_units"]):
        raise ValueError("Native statewide header differs from its captured query")
    fraction = query.get("native_fraction_literal")
    if not isinstance(fraction, str) or re.fullmatch(PERCENT, fraction) is None:
        raise ValueError("Native statewide turnout percentage is missing")
    view = row["view"]
    rate = view["reported_pct"]
    view.setdefault("accepted_source_provenance", {
        name: copy.deepcopy(old["view"].get(name)) for name in (
            "source_snapshot", "source_sha256", "source_retrieved_at",
            "source_date", "source_update_label", "source_update_timezone")})
    native["state_reference"] = {
        "count": query["count"], "registered": query["registered"],
        "published_pct": fraction, "source_clock": query["source_clock"],
        "reported_units": query["reported_units"], "total_units": query["total_units"],
    }
    view.update(
        published_pct=float(Decimal(fraction[:-1])), validated_pct=rate,
        native_published_pct=fraction, native_printed_pct=fraction,
        source_status_literal=query["native_report_status_literal"],
        source_snapshot="automatic-native:" + source["sha256"],
        source_date=None, source_update_timezone=None,
        source_retrieved_at=source.get("retrieved_at"),
        state_reference=copy.deepcopy(native["state_reference"]),
        statewide_header_binding={
            "contract": "participation.native_statewide_header_binding.v1",
            "observation_id": old["id"], "source_id": old["source"]["id"],
            "source_pin": native["private_original_pin"], "query_pin": pin(encoded(query)),
            "state_and_reporting_unit_counts_not_added_or_allocated": True,
            "reporting_completion_is_not_certification_or_unique_person_validation": True,
        })


def refresh_webforms_mirror(row, record, previous_record):
    from scripts.participation_intake.contract import encoded, pin

    profile = WEBFORMS_STATE_PROFILES.get(row.get("source_url"))
    if profile is None or row.get("state_code") != profile["state_code"]:
        return False
    source, view = record["source"], record["view"]
    prior = previous_record["view"]
    old_binding = row.get("statewide_header_binding")
    if old_binding is None:
        if pin(encoded(row)) != profile["legacy_mirror_pin"]:
            raise ValueError("Unreviewed legacy statewide mirror preimage")
    elif (old_binding != prior.get("statewide_header_binding")
            or any(row.get(name) != prior.get(name) for name in (
                "ballots", "denominator", "denominator_basis", "source_sha256",
                "source_update_label", "published_pct", "validated_pct"))):
        raise ValueError("Independently changed statewide mirror cannot be overwritten")
    if (not webforms_state_template(record, row["source_url"])
            or not view.get("automatic_source_refresh")
            or row.get("denominator_basis") != view.get("denominator_basis")
            or view.get("statewide_header_binding", {}).get("observation_id") != record["id"]):
        raise ValueError("Unbound native statewide header mirror")
    checked = copy.deepcopy(record)
    apply_webforms_state_context(record, checked, {
        "url": source["url"], "sha256": source["input_sha256"],
        "bytes": view["native_record"]["private_original_pin"]["bytes"]})
    if checked["view"] != view:
        raise ValueError("Statewide header query or binding changed")
    row.setdefault("accepted_source_provenance", {
        name: copy.deepcopy(row.get(name)) for name in (
            "source_snapshot", "source_sha256", "source_retrieved_at",
            "source_date", "source_update_label", "source_update_timezone")})
    fields = (
        "ballots", "denominator", "denominator_basis", "published_pct", "validated_pct",
        "reported_units", "total_units", "source_update_label", "source_update_timezone",
        "source_date", "source_retrieved_at", "source_sha256", "source_snapshot",
        "native_published_pct", "native_printed_pct", "source_status_literal",
        "state_reference", "statewide_header_binding", "source_reporting_label",
    )
    row.update({name: copy.deepcopy(view.get(name)) for name in fields})
    row["source_sha256"] = source["input_sha256"]
    row["source_snapshot"] = "automatic-native:" + source["input_sha256"]
    row["automatic_source_refresh"] = True
    return True


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
