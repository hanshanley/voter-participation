"""Refresh reviewed statistical source families without assigning new geographic identities."""

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, ROUND_HALF_UP
import html
import io
import json
import re
from urllib.parse import urlsplit

from scripts.participation_intake.contract import count, digest, pin
from scripts.results_granular import (
    CT_ROOT, MN_URL, NOT_RESULTS, PRIVATE_HEADERS, change, factual_tables,
    public_facts, selected_records, transport_url,
)


CA_URL = "https://media.sos.ca.gov/media/status_GG.json"
IN_URL = "https://enr.indianavoters.in.gov/site/data/statewideTurnout_B.json"
NM_URL = "https://electionresults.sos.nm.gov/VoterTurnoutDetails.aspx?map=PREC"
RECORD_PROFILES = {
    CA_URL: {
        "state": "CA", "query_id": "ca-all-status",
        "identity": "county", "name": "countyName", "count": "voterTurnout",
        "registered": "totalRegisteredVoters", "clock": "timestamp",
        "reported": "precinctsReporting", "total": "precinctsTotal",
        "template_identity": ("query", "county_id"),
        "parent": "59", "parent_name": "Statewide",
        "first_report": "firstReportTimestamp",
        "edition_clock": "lastReportTimestamp",
    },
    IN_URL: {
        "state": "IN", "query_id": "in-native-voters-voting",
        "items_path": "root.CountyTurnout",
        "identity": "County", "name": "County", "count": "VotersVoting",
        "registered": "REGISTERED_VOTERS", "template_identity": ("County",),
        "template_name": ("County",), "clock_path": ("root", "WriteTime"),
        "template_clock_prefix": "Voter statistics WriteTime: ",
        "row_guards": {"ElectionDateName": "Tuesday, November 3, 2026"},
        "parent": "Total", "parent_name": "Total",
        "independent_overrides": ["Cass", "Floyd", "Fulton", "Monroe", "Porter", "Posey", "Wayne"],
        "components": ["InPerson", "Absentee"], "positive_counts_only": True,
        "analytical_rates_qualified": False,
    },
}
PDF_MEASURES = {
    "Ballots Cast - Total", "Ballots Cast", "Total Ballots Cast", "Total Ballots",
    "Voters Cast", "Cards Cast", "TOTAL TURNOUT",
}
COUNT_LITERAL = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
ELECTION_DATE = re.compile(
    r"\b(?:11[/.]0?3[/.]2026|November\s+0?3,?\s+2026)\b", re.I)
REPORT_CLOCK = re.compile(
    r"\b(?:[01]?[0-9]/[0-3]?[0-9]/20[0-9]{2}|20[0-9]{2}-[01][0-9]-[0-3][0-9])"
    r"\s*(?:-\s*)?[0-2]?[0-9]:[0-5][0-9](?::[0-5][0-9])?\s*(?:AM|PM)?\b", re.I)
TOTAL_HEADER = re.compile(
    r"(?:Statistics\s+)?TOTAL(?:\s*(?:VOTE\s*%|%|Election\s*Day|Early(?:\s*Voting)?|Absentee|"
    r"Provisional|Mail|ED|EV|AB))*", re.I)


def native_identity(template, path):
    value = template["view"]["native_record"]
    for key in path:
        value = value[key]
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("A reviewed literal native record identity is required")
    return str(value)


def record_statistics(body, templates, profile):
    from scripts.native_tabular import json_records

    if any(template["geography"]["state_code"] != profile["state"]
           or template["election"]["year"] != 2026
           or template["election"]["type"] != "general" for template in templates):
        raise ValueError("Reviewed native record state/election scope changed")
    table = json_records(body, items_path=profile.get("items_path"))
    public_facts(table)
    rows = [dict(zip(table["header"], item["values"])) for item in table["rows"]]
    required = {profile[key] for key in ("identity", "name", "count")}
    required.update(profile[key] for key in (
        "registered", "clock", "reported", "total", "first_report", "edition_clock")
        if profile.get(key))
    if not required <= set(table["header"]):
        raise ValueError("Reviewed native statistical columns changed")
    native = {}
    for row in rows:
        identity = row[profile["identity"]]
        if isinstance(identity, bool) or not isinstance(identity, (str, int)):
            raise ValueError("Invalid native statistical identity")
        identity = str(identity)
        if identity in native:
            raise ValueError("Duplicate native statistical identity")
        if any(row.get(key) != value for key, value in profile.get("row_guards", {}).items()):
            raise ValueError("Native statistical election declaration changed")
        if profile.get("first_report") and re.fullmatch(
                r"202611(?:0[3-9]|[12][0-9]|30)[0-2][0-9][0-5][0-9]",
                str(row[profile["first_report"]])) is None:
            raise ValueError("Native statistics are not bound to the reviewed November 2026 election")
        for key in ("count", "registered", "reported", "total"):
            if profile.get(key) and count(row[profile[key]]) is None:
                raise ValueError("An absent native statistic is not a recorded zero")
        native[identity] = row
        if profile.get("components") and (
                any(count(row.get(key)) is None for key in profile["components"])
                or sum(count(row[key]) for key in profile["components"]) != count(row[profile["count"]])):
            raise ValueError("Native participation components disagree")
    expected = {}
    for template in templates:
        identity = native_identity(template, profile["template_identity"])
        expected.setdefault(identity, []).append(template)
    parent = profile.get("parent")
    inventory = set(expected) | set(profile.get("independent_overrides", []))
    if not expected or set(native) != inventory | ({parent} if parent else set()):
        raise ValueError("Reviewed native statistical inventory changed")
    if parent:
        parent_row = native[parent]
        if parent_row[profile["name"]] != profile["parent_name"]:
            raise ValueError("Native statewide parent label changed")
        for key in ("count", "registered"):
            if profile.get(key) and sum(count(row[profile[key]]) for identity, row in native.items()
                    if identity != parent) != count(parent_row[profile[key]]):
                raise ValueError("Complete native counties disagree with the separate state parent")
    updates = []
    global_clock = None
    if profile.get("clock_path"):
        global_clock = json.loads(body)
        for key in profile["clock_path"]:
            global_clock = global_clock[key]
        datetime.strptime(global_clock, "%Y-%m-%dT%H:%M:%S.%f")
    for identity, targets in expected.items():
        row = native[identity]
        for template in targets:
            expected_name = (native_identity(template, profile["template_name"])
                             if profile.get("template_name") else template["geography"]["name"])
            if row[profile["name"]] != expected_name:
                raise ValueError("Changed literal native county identity/name")
            if template["count"]["status"] != "reported":
                continue
            if profile.get("positive_counts_only") and count(row[profile["count"]]) == 0:
                raise ValueError("A contradictory native zero requires review, not automatic promotion")
            if global_clock:
                prefix = profile["template_clock_prefix"]
                previous = template["source_clock"]["literal"]
                if not previous or not previous.startswith(prefix):
                    raise ValueError("Reviewed native statistical clock binding changed")
                previous = previous[len(prefix):].split(";", 1)[0]
                if datetime.fromisoformat(global_clock) < datetime.fromisoformat(previous):
                    raise ValueError("Native statistical edition regressed")
            if profile.get("edition_clock"):
                edition = str(row[profile["edition_clock"]])
                previous = (template["view"]["native_record"].get("query") or {}).get(
                    "last_report_timestamp")
                current_clock = datetime.strptime(edition, "%Y%m%d%H%M")
                if previous and current_clock < datetime.strptime(previous, "%Y%m%d%H%M"):
                    raise ValueError("Native statistical edition is older than the reviewed observation")
            value = count(row[profile["count"]])
            registered = count(row[profile["registered"]]) if profile.get("registered") else None
            clock = row[profile["clock"]] if profile.get("clock") else global_clock
            reported = count(row[profile["reported"]]) if profile.get("reported") else None
            total = count(row[profile["total"]]) if profile.get("total") else None
            query = {
                "query_id": profile["query_id"], "county_id": identity,
                "county_name": row[profile["name"]], "count": value,
                "registered": registered, "source_clock": clock,
                "reported_units": reported, "total_units": total,
                "selector": {profile["identity"]: row[profile["identity"]]},
            }
            if profile.get("edition_clock"):
                query["last_report_timestamp"] = str(row[profile["edition_clock"]])
                query["first_report_timestamp"] = str(row[profile["first_report"]])
            facts = {"query": query, "native_fields": row,
                     "private_original_pin": pin(body),
                     "whole_publisher_html_redistributed": False}
            updates.append(change(template, value, facts, registered=registered, clock=clock,
                reported=reported, total=total,
                rate_compatible=bool(registered and value <= registered
                                     and profile.get("analytical_rates_qualified", True))))
    return {"updates": updates, "complete_native_query": rows,
            "native_column_bindings": profile, "geographic_joins_changed": False,
            "native_measure_not_relabelled_as_ballots": True}


def pdf_measure(template):
    native = template["view"].get("native_record") or {}
    label = native.get("selected_native_parent_literal") or template["measure"]["literal"]
    return label if isinstance(label, str) and label in PDF_MEASURES else None


def clock_value(literal):
    literal = literal.strip()
    try:
        return datetime.fromisoformat(literal)
    except ValueError:
        pass
    matches = list(REPORT_CLOCK.finditer(literal))
    if len(matches) == 1:
        literal = matches[0].group(0)
    literal = re.sub(r"(20[0-9]{2})(?=[0-9]{1,2}:)", r"\1 ", literal)
    literal = " ".join(literal.replace(" - ", " ").split()).upper()
    for format_string in ("%m/%d/%Y %I:%M:%S%p", "%m/%d/%Y %I:%M:%S %p",
                          "%m/%d/%Y %I:%M%p", "%m/%d/%Y %I:%M %p",
                          "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S",
                          "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(literal, format_string)
        except ValueError:
            pass
    raise ValueError("Unreviewed native report-clock format")


def pdf_text_statistics(page, templates, pages, confidence=None, tokens=None):
    if len({(row["geography"]["state_code"], row["geography"]["name"])
            for row in templates}) != 1:
        raise ValueError("A shared PDF county parent cannot stand in for multiple counties")
    lines = [" ".join(line.split()) for line in page.splitlines() if line.strip()]
    text = "\n".join(lines)
    if (not ELECTION_DATE.search(text)
            or not re.search(r"\bGeneral(?:\s+State)?\s+Election\b", text, re.I)
            or re.search(r"\b(?:TEST RESULTS|PRIMARY ELECTION|RUNOFF ELECTION)\b", text, re.I)):
        raise ValueError("Native statistical PDF election scope changed or needs visual review")
    if PRIVATE_HEADERS.search(text):
        raise ValueError("Individual/contact PDF is excluded from numerical intake")
    if (re.search(r"\b(?:Election Day|Early Voting|Absentee|Mail)\s+Only\b", text, re.I)
            or "Summary for:" in text and not re.search(
                r"Summary for:\s*All Contests,\s*All Districts,\s*All Tabulators", text, re.I)):
        raise ValueError("Native statistical PDF ballot-method/geography scope changed")
    clocks = {match.group(0).strip() for match in REPORT_CLOCK.finditer(text)}
    dates = re.findall(r"\bDate:\s*(\d{1,2}/\d{1,2}/20\d{2})\b", text)
    times = re.findall(r"\bTime:\s*(\d{1,2}:\d{2}:\d{2}\s*[AP]M(?:\s+[ECMP][SD]T)?)\b", text)
    if dates or times:
        if len(set(dates)) != 1 or len(set(times)) != 1:
            raise ValueError("Ambiguous native report Date/Time fields")
        clocks.add(dates[0] + " " + times[0])
    decoded_clocks = {clock_value(item): item for item in sorted(clocks)}
    if len(decoded_clocks) > 1:
        raise ValueError("Ambiguous native first-page report clocks")
    clock = next(iter(decoded_clocks.values()), None)
    updates, queries = [], []
    for template in templates:
        if template["count"]["status"] != "reported":
            continue
        if template["election"]["year"] != 2026 or template["election"]["type"] != "general":
            raise ValueError("Reviewed native PDF election scope changed")
        label = pdf_measure(template)
        name = template["geography"]["name"]
        if (template["geography"]["level"] != "county" or not label
                or not re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.I)):
            raise ValueError("Native PDF county scope requires an explicit reviewed parent")
        matches = []
        label_pattern = r"\s*-\s*".join(
            r"\s+".join(map(re.escape, part.split())) for part in label.split("-"))
        for position, line in enumerate(lines):
            inline = re.fullmatch(
                r"Registered\s+Voters\s+(" + COUNT_LITERAL + r")\s*-\s*Total\s+Ballots\s+("
                + COUNT_LITERAL + r")\s*:?\s*([0-9]+\.[0-9]+)%\s*-\s*Blank\s+Ballots\s+("
                + COUNT_LITERAL + r")\s+([0-9]+)\s+of\s+([0-9]+)\s+Precincts\s+Reporting\s+"
                r"([0-9]+\.[0-9]+)%", line, re.I)
            if inline and label == "Total Ballots":
                registered, value = (int(inline.group(i).replace(",", "")) for i in (1, 2))
                if (not registered or int(inline.group(4).replace(",", "")) > value
                        or int(inline.group(5)) > int(inline.group(6))
                        or (Decimal(value) * 100 / registered).quantize(
                            Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(inline.group(3))):
                    raise ValueError("Native inline ballot/register/blank statistics disagree")
                matches.append((position + 1, inline.group(2), inline.span(2)))
                continue
            fraction = re.fullmatch(re.escape(label) + r":\s*(" + COUNT_LITERAL
                + r")\s+of\s+(" + COUNT_LITERAL + r")\s+\(([0-9]+\.[0-9]+)%\)",
                line, re.I)
            if fraction:
                numerator, denominator = (int(fraction.group(i).replace(",", "")) for i in (1, 2))
                if not denominator or (Decimal(numerator) * 100 / denominator).quantize(
                        Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(fraction.group(3)):
                    raise ValueError("Native PDF statistical fraction disagrees")
                matches.append((position + 1, fraction.group(1), fraction.span(1)))
                continue
            match = re.fullmatch(label_pattern + r"\s+(" + COUNT_LITERAL
                                 + r")((?:\s+" + COUNT_LITERAL + r")*)"
                                 + r"(?:\s+[0-9]+\.[0-9]+%)?", line, re.I)
            if match:
                header = lines[:position]
                if any(re.search(r"\b(?:Election\s*Day|Absentee|Early\s*Voting)\b.*\bTOTAL\b",
                                 item, re.I) for item in header):
                    raise ValueError("Native statistical total is not the first count column")
                single_total = ("total" in label.lower()
                    and re.fullmatch(label_pattern + r"\s+" + COUNT_LITERAL, line, re.I))
                if not single_total and not any(TOTAL_HEADER.fullmatch(item) for item in header):
                    raise ValueError("Native statistical total column is not explicitly identified")
                components = match.group(2).split()
                if components and sum(int(item.replace(",", "")) for item in components) != int(
                        match.group(1).replace(",", "")):
                    raise ValueError("Native statistical ballot components disagree with total")
                matches.append((position + 1, match.group(1), match.span(1)))
        if len(matches) != 1:
            raise ValueError("Native PDF statistic is absent or ambiguous; no candidate-vote substitution")
        previous_clock = template["source_clock"]["literal"]
        if previous_clock:
            if clock is None or clock_value(clock) < clock_value(previous_clock):
                raise ValueError("Native PDF clock is missing or older than the reviewed observation")
        value = int(matches[0][1].replace(",", ""))
        registered = None
        denominator = template.get("denominator")
        registration_line = None
        if denominator and denominator["qualified"]:
            literal = denominator["literal"]
            pattern = r"\s*-\s*".join(
                r"\s+".join(map(re.escape, part.split())) for part in literal.split("-"))
            registrations = [(position, match) for position, line in enumerate(lines)
                             for match in [re.fullmatch(pattern + r"\s+(" + COUNT_LITERAL + r")",
                                                       line, re.I)] if match]
            if len(registrations) != 1:
                raise ValueError("A qualified PDF fraction requires its literal native register")
            position, registration_match = registrations[0]
            registered = int(registration_match.group(1).replace(",", ""))
            if not registered or value > registered:
                raise ValueError("Native PDF count exceeds its qualified register")
            registration_line = lines[position]
            if tokens is not None:
                start, end = registration_match.span(1)
                selected = [item["confidence"] for item in tokens[position]
                            if item["start"] < end and item["end"] > start]
                if not selected or min(selected) < .98:
                    raise ValueError("Native PDF register OCR confidence requires review")
            elif confidence is not None and confidence[position] < .98:
                raise ValueError("Native PDF register OCR confidence requires review")
        numeric_confidence = confidence[matches[0][0] - 1] if confidence is not None else None
        if tokens is not None:
            start, end = matches[0][2]
            selected = [item["confidence"] for item in tokens[matches[0][0] - 1]
                        if item["start"] < end and item["end"] > start]
            if not selected:
                raise ValueError("Native PDF OCR count has no physical token binding")
            numeric_confidence = min(selected)
        if numeric_confidence is not None and numeric_confidence < .98:
            raise ValueError("Native PDF count OCR confidence requires review")
        query = {"native_measure_literal": label, "native_count_literal": matches[0][1],
                 "count": value, "county": name, "page": 1, "statistic_line": matches[0][0],
                 "pdf_pages": pages, "pdf_report_clock_literal": clock,
                 "native_statistical_line": lines[matches[0][0] - 1],
                 "election_date": "2026-11-03", "native_scope": "county_statistical_parent",
                 "registered_denominator_not_refreshed": registered is None}
        if registered is not None:
            query.update(registered=registered, native_registration_line=registration_line)
        zone = re.search(r"\b(?:[ECMP][SD]T|UTC|GMT)\b", clock or "")
        query["pdf_report_timezone_literal"] = zone.group(0) if zone else None
        if numeric_confidence is not None:
            query["ocr_selected_count_minimum_confidence"] = numeric_confidence
        queries.append(query)
        updates.append(change(template, value, query, registered=registered, clock=clock,
                              rate_compatible=registered is not None))
    return {"updates": updates, "complete_native_query": queries,
            "geographic_joins_changed": False, "analytical_rates_promoted": False,
            "pdf_report_clock_is_not_certification": True}


def pdf_parent_statistics(body, templates):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(body))
    if reader.is_encrypted or not reader.pages or len(reader.pages) > 6000:
        raise ValueError("Unqualified native statistical PDF")
    page = reader.pages[0].extract_text(extraction_mode="layout")
    if page.strip():
        return pdf_text_statistics(page, templates, len(reader.pages))
    from scripts.results_pdf_ocr import first_page_views

    views = first_page_views(body)
    results = [pdf_text_statistics(view["text"], templates, len(reader.pages),
                                   view["confidence"], view.get("tokens")) for view in views]
    vectors = [[(row["id"], row["value"], row["registered"],
                 clock_value(row["clock"]) if row["clock"] else None)
                for row in result["updates"]]
               for result in results]
    if len(results) != 2 or vectors[0] != vectors[1]:
        raise ValueError("Native PDF OCR count/clock disagreement requires review")
    result = results[0]
    result["ocr"] = {"passes": [view["receipt"] for view in views],
                     "same_engine_resolution_check_not_independent_validation": True}
    return result


def webforms_statistics(body, templates):
    text = body.decode("utf-8-sig")
    if not re.search(r">\s*GENERAL 2026\s*<", text) or not re.search(
            r">\s*November 3, 2026\s*<", text):
        raise ValueError("Native turnout HTML election scope changed")
    updated = re.search(r"Results last updated:</span><span>([^<]+)</span>", text)
    parent = re.search(
        r'header-ballot-number">(' + COUNT_LITERAL + r')</span><br /><span class="header-voter-text">'
        r'Eligible Voters</span><span class="header-voter-number">(' + COUNT_LITERAL + r')</span>', text)
    coverage = re.search(r'header-partial-number">(\d+)</span>.*?header-total-number">(\d+)</span>'
                         r'.*?header-totalprecincts-text">(\d+)</span>', text, re.S)
    if not updated or not parent or not coverage:
        raise ValueError("Native turnout HTML statistical header changed")
    clock = html.unescape(updated.group(1))
    current_clock = clock_value(clock)
    partial, reported, total = map(int, coverage.groups())
    if partial != 0 or reported != total:
        raise ValueError("Incomplete native turnout inventory requires review")
    sections = re.findall(r'<div class="col turnout-results-box-a">\s*<h1>(.*?)</h1>(.*?)(?='
                          r'<div class="col turnout-results-box-a">|</form>)', text, re.S)
    pattern = (r'<div class="(?:odd|even)">\s*<div class="county-precinct">(.*?)</div>\s*'
               r'<div class="county-cast">\s*<span>(' + COUNT_LITERAL + r')</span>\s*</div>\s*'
               r'<div class="county-counted">\s*<span>(' + COUNT_LITERAL + r')</span>')
    facts, identities = [], set()
    for label, block in sections:
        county = html.unescape(re.sub(r"<[^>]+>", "", label)).strip()
        identity = re.search(r'countyid="(\d+)"', block)
        rows = re.findall(pattern, block, re.S)
        declared_rows = len(re.findall(r'<div class="county-precinct">', block))
        if not identity or not rows or len(rows) != declared_rows:
            raise ValueError("Native turnout HTML has missing/unreadable statistical rows")
        children = []
        for unit, value, registered in rows:
            unit = html.unescape(re.sub(r"<[^>]+>", "", unit)).strip()
            key = identity.group(1), unit
            if not unit or key in identities:
                raise ValueError("Duplicate native county-scoped reporting unit")
            identities.add(key)
            children.append({"county_id": key[0], "county": county, "unit": unit,
                "geography_level": "reporting_unit", "count": int(value.replace(",", "")),
                "registered": int(registered.replace(",", "")), "source_clock": clock})
        facts.append({"county_id": identity.group(1), "county": county, "unit": "",
            "geography_level": "county", "count": sum(row["count"] for row in children),
            "registered": sum(row["registered"] for row in children), "source_clock": clock,
            "reported_units": len(children), "total_units": len(children)})
        facts.extend(children)
    if len(identities) != total:
        raise ValueError("Native turnout HTML reporting inventory changed")
    counties = [row for row in facts if row["geography_level"] == "county"]
    parent_count, parent_registered = (int(value.replace(",", "")) for value in parent.groups())
    if (sum(row["count"] for row in counties) != parent_count
            or sum(row["registered"] for row in counties) != parent_registered):
        raise ValueError("Native turnout HTML counties disagree with the separate state parent")
    expected = {}
    for template in templates:
        query = template["view"]["native_record"]["query"]
        if (template["geography"]["state_code"] != "NM" or template["election"]["year"] != 2026
                or template["election"]["type"] != "general" or query["query_id"] != "nm-all-turnout"):
            raise ValueError("Reviewed turnout HTML source/election scope changed")
        key = query["geography_level"], query["county_id"], query["unit"]
        expected.setdefault(key, []).append(template)
    observed = {(row["geography_level"], row["county_id"], row["unit"]): row for row in facts}
    if not expected or len(observed) != len(facts) or set(observed) != set(expected):
        raise ValueError("Reviewed turnout HTML native identities changed")
    updates = []
    for key, targets in expected.items():
        row = observed[key]
        for template in targets:
            old = template["view"]["native_record"]["query"]
            if row["county"] != old["county"] or row["unit"] != old["unit"]:
                raise ValueError("Literal native turnout HTML geography changed")
            if current_clock < clock_value(old["source_clock"]):
                raise ValueError("Native turnout HTML edition regressed")
            if template["count"]["status"] != "reported":
                continue
            query = {**row, "query_id": old["query_id"], "selector": old["selector"]}
            native = {"query": query, "private_original_pin": pin(body),
                      "whole_publisher_html_redistributed": False}
            updates.append(change(template, row["count"], native, registered=row["registered"],
                clock=clock, reported=row.get("reported_units"), total=row.get("total_units"),
                rate_compatible=bool(row["registered"] and row["count"] <= row["registered"])))
    facts.append({"geography_level": "state", "count": parent_count, "registered": parent_registered,
                  "source_clock": clock, "reported_units": reported, "total_units": total})
    return {"updates": updates, "complete_native_query": facts, "geographic_joins_changed": False,
            "native_measure_not_relabelled_as_ballots": True}


def source_plan(baseline):
    index = json.loads(baseline["index.json"])
    result = {}
    for state in sorted(index["states"]):
        templates = selected_records(baseline, state)
        sources = {}
        for template in templates:
            view = template.get("view") or {}
            url = view.get("source_url")
            if not isinstance(url, str):
                continue
            parsed = urlsplit(url)
            if (parsed.scheme != "https" or parsed.hostname in (
                    "raw.githubusercontent.com", "github.com", "www.themarginoferror.com",
                    "themarginoferror.com", "civicapi.org")
                    or parsed.hostname and parsed.hostname.endswith(".civicapi.org")
                    or NOT_RESULTS.search(parsed.path)):
                continue
            if (url == MN_URL or url.startswith(CT_ROOT)
                    or parsed.hostname == "er.ncsbe.gov"
                    or state == "AL" and parsed.path.lower().endswith(".zip")):
                continue
            profile = RECORD_PROFILES.get(url)
            native = view.get("native_record") or {}
            if profile and state == profile["state"] and (
                    (native.get("query") or {}).get("query_id") == profile["query_id"]
                    or url == IN_URL and "VotersVoting" in native):
                adapter = "reviewed_record_statistics"
            elif (url == NM_URL and state == "NM"
                  and (native.get("query") or {}).get("query_id") == "nm-all-turnout"):
                adapter = "reviewed_webforms_statistics"
            elif (template["geography"]["level"] == "county" and pdf_measure(template)
                  and (parsed.path.lower().endswith(".pdf") or "/DocumentCenter/View/" in parsed.path
                       or native.get("complete_native_pdf_pages") or native.get("pdf_metadata"))):
                adapter = "reviewed_pdf_county_parent"
            else:
                adapter = "unadapted_primary_product"
            key = state + "-registered-" + digest(url.encode())[:16]
            source = sources.setdefault(key, {"url": url, "adapter": adapter, "templates": []})
            if source["adapter"] != adapter:
                if source["adapter"] == "unadapted_primary_product":
                    source["adapter"] = adapter
                    source["templates"] = []
                else:
                    continue
            if adapter == "unadapted_primary_product" and source["templates"]:
                continue
            source["templates"].append(template)
        result[state] = sources
    return result


def collect_sources(collector, baseline):
    def collect_url(group):
        result = {}
        for identity, source in group:
            url, templates = source["url"], source["templates"]
            if source["adapter"] == "reviewed_record_statistics":
                def parse(body, templates=templates, profile=RECORD_PROFILES[url]):
                    return record_statistics(body, templates, profile)
            elif source["adapter"] == "reviewed_pdf_county_parent":
                def parse(body, templates=templates):
                    return pdf_parent_statistics(body, templates)
            elif source["adapter"] == "reviewed_webforms_statistics":
                def parse(body, templates=templates):
                    return webforms_statistics(body, templates)
            else:
                def parse(body, url=url):
                    return {"updates": [], "factual_product": factual_tables(body, url),
                            "numerical_data_qualified": False,
                            "semantic_review_required_before_projection": True}
            entry = collector.capture(identity, transport_url(url), parse)
            entry["adapter"] = source["adapter"]
            entry["reviewed_record_count"] = len(templates)
            result[identity] = entry
        return result
    groups = {}
    for sources in source_plan(baseline).values():
        for identity, source in sources.items():
            groups.setdefault(transport_url(source["url"]), []).append((identity, source))
    result = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for entries in pool.map(collect_url, groups.values()):
            result.update(entries)
    return result
