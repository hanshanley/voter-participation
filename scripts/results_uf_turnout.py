"""Source-defined statewide turnout, separate from administrative/model frames."""

import copy
import csv
from datetime import datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import io
import json
import re
from urllib.parse import urljoin, urlsplit

from scripts.nationwide import STATES
from scripts.participation_intake.contract import encoded, pin


IDENTITY = "UF-national-turnout"
CONTRACT = "participation.uf_statewide_turnout.v1"
LANDING = "https://election.lab.ufl.edu/2026-general-election-turnout/"
CONFIG = {"contract": CONTRACT, "election_date": "2026-11-03", "landing_url": LANDING}
COUNTS = ("TOTAL_BALLOTS_COUNTED", "VAP", "INELIGIBLE_PRISON", "INELIGIBLE_PROBATION",
          "INELIGIBLE_PAROLE", "INELIGIBLE_FELONS_TOTAL", "ELIGIBLE_OVERSEAS", "VEP")
PERCENTAGES = ("NONCITIZEN_PCT", "VEP_TURNOUT_RATE", "VAP_TURNOUT_RATE")
FIELDS = {"STATE", "STATE_ABV", "SOURCE", "STATUS", *COUNTS, *PERCENTAGES}
NAMES = {**STATES, "US": "United States"}
LIMITATIONS = [
    "UF source-defined turnout, not independently verified administrative or certified counts.",
    "Blank STATUS means estimated even when SOURCE is an official link.",
    "Official/Final are UF assumptions, not independent certification evidence.",
    "VEP and VAP are estimated population frames, never registration stocks or local denominators.",
    "No county/precinct/group allocation, behavioral eligibility, or model refit.",
    "Source count-update time is not supplied; HTTP edition and retrieval are separate.",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def public_url(url):
    value = urlsplit(url)
    require(value.scheme == "https" and value.netloc == "election.lab.ufl.edu"
            and not value.query and not value.fragment, "Unexpected UF declaration origin")
    return value.path


class Links(HTMLParser):
    def __init__(self, body, base):
        super().__init__()
        self.urls, self.base = set(), base
        self.feed(body.decode("utf-8-sig"))

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.urls.add(urljoin(self.base, href))


def discover(body):
    versions = {}
    for url in Links(body, LANDING).urls:
        match = re.fullmatch(r"/dataset/2026-general-election-turnout-rates-v(\d+)-(\d+)/",
                             urlsplit(url).path)
        if match:
            public_url(url)
            version = tuple(map(int, match.groups()))
            require(version not in versions or versions[version] == url,
                    "Ambiguous UF dataset declaration")
            versions[version] = url
    require(bool(versions), "No advertised 2026 UF turnout dataset")
    version = max(versions)
    require(version >= (0, 3), "UF successor predates reviewed STATUS schema")
    return versions[version], ".".join(map(str, version))


def downloads(body, dataset, version):
    selected = {}
    for url in Links(body, dataset).urls:
        path = urlsplit(url).path
        match = re.fullmatch(
            r"/data-downloads/turnoutdata/Turnout_2026G_v(\d+\.\d+)(\.csv|_doc\.txt)", path)
        if match:
            public_url(url)
            require(match[1] == version, "UF dataset/file edition mismatch")
            key = "csv" if match[2] == ".csv" else "documentation"
            require(key not in selected or selected[key] == url, "Ambiguous UF file declaration")
            selected[key] = url
    require(set(selected) == {"csv", "documentation"}, "Incomplete advertised UF source package")
    return selected


def number(value, percentage=False):
    value = value.strip()
    if not value:
        return None
    if percentage:
        require(bool(re.fullmatch(r"\d+(?:\.\d+)?%", value)), "Invalid UF percentage")
        result = Decimal(value[:-1])
        require(0 <= result <= 100, "UF percentage outside 0-100")
        return float(result)
    require(bool(re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)", value)), "Invalid UF count")
    result = int(value.replace(",", ""))
    require(result <= 2**53 - 1, "Unsafe UF integer")
    return result


def parse(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    require(reader.fieldnames is not None and set(reader.fieldnames) == FIELDS
            and len(reader.fieldnames) == len(FIELDS), "Unreviewed UF turnout schema")
    rows, seen = [], set()
    for original in reader:
        require(set(original) == FIELDS and all(isinstance(value, str) for value in original.values()),
                "Malformed UF turnout row")
        code = original["STATE_ABV"]
        require(code in NAMES and code not in seen and original["STATE"].strip() == NAMES[code]
                and bool(original["SOURCE"].strip()), "UF jurisdiction/source identity differs")
        seen.add(code)
        values = {key: number(original[key], key in PERCENTAGES)
                  for key in (*COUNTS, *PERCENTAGES)}
        ballots = values["TOTAL_BALLOTS_COUNTED"]
        for basis in ("VEP", "VAP"):
            denominator, rate = values[basis], values[basis + "_TURNOUT_RATE"]
            require(rate is None or ballots is not None and denominator is not None
                    and denominator > 0
                    and abs(Decimal(ballots) * 100 / Decimal(denominator)
                            - Decimal(str(rate))) <= Decimal(".006"),
                    "UF rate differs from its own numerator/denominator")
        status = original["STATUS"].strip()
        classification = ("estimate" if status == "" else
                          "source_reported_not_independently_certified"
                          if status in ("Official", "Final") else "unrecognized_source_status")
        rows.append({
            "state_code": code, "state": original["STATE"], "year": 2026,
            "geographic_level": "national" if code == "US" else "state",
            "ballots": ballots, "vep": values["VEP"], "vap": values["VAP"],
            "vep_rate": values["VEP_TURNOUT_RATE"], "vap_rate": values["VAP_TURNOUT_RATE"],
            "source_status_literal": original["STATUS"], "ballots_status": classification,
            "source_update_label": None, "source_update_timezone": None,
            "independently_certified": False, "local_allocation_qualified": False,
            "native": dict(original), "numeric": values,
        })
    require(seen == set(NAMES), "UF inventory must include 50 states, DC and separate US")
    return sorted(rows, key=lambda row: row["state_code"])


def documentation(body, version):
    text = body.decode("utf-8-sig")
    require("DOCUMENTATION FOR 2026 GENERAL ELECTION TURNOUT RATES" in text.upper(),
            "Wrong UF election documentation")
    match = re.search(r"^Version:\s*(\d+\.\d+)\s*$", text, re.M)
    require(match is not None and match[1] == version, "UF documentation edition mismatch")
    require("Creative Commons 4.0 Attribution License" in text
            and 'If blank, STATUS indicates TOTAL_BALLOTS_COUNTED is estimated' in text,
            "UF license/status definition requires successor review")
    require(all(re.search(r"^" + field + r"\s*\n=+", text, re.M) for field in FIELDS),
            "UF documentation omits a source variable")
    date = re.search(r"^Date:\s*(.+)$", text, re.M)
    anomalies = []
    literal_date = date[1].strip() if date else None
    if literal_date:
        try:
            if datetime.strptime(literal_date, "%m/%d/%Y").date().isoformat() < "2026-11-03":
                anomalies.append("documentation_date_predates_election_not_a_count_clock")
        except ValueError:
            anomalies.append("documentation_date_format_unrecognized")
    if re.search(r"(?im)pre-election|forecast|v0\.2", text):
        anomalies.append("documentation_retains_forecast_or_prior_version_language")
    definition = re.search(r"TOTAL_BALLOTS_COUNTED\s*\n=+[ \t]*\r?\n(.*?)(?=\n[A-Z][A-Z_]*\s*\n=+|\Z)",
                           text, re.S)
    if definition is not None and len(definition[1].strip()) < 20:
        anomalies.append("total_ballots_definition_truncated")
    return {"version": version, "date_literal": literal_date,
            "anomalies": anomalies, "license": "CC-BY-4.0",
            "attribution": "Michael McDonald, University of Florida Election Lab"}


def edition_time(edition):
    literal = (edition or {}).get("http_last_modified")
    if literal is None:
        return None
    try:
        result = parsedate_to_datetime(literal)
        require(result.tzinfo is not None, "UF HTTP edition needs a timezone")
        return result
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Invalid UF HTTP edition") from error


def check_revision(prior, current):
    if prior is None:
        return
    before = tuple(map(int, prior["version"].split(".")))
    after = tuple(map(int, current["version"].split(".")))
    require(after >= before, "UF advertised edition regressed")
    require(current["contract"] == prior["contract"]
            and current["election_date"] == prior["election_date"], "UF source frame changed")
    if after > before:
        return
    require(current["declarations"] == prior["declarations"], "UF same-edition source route changed")
    old, new = edition_time(prior["csv_edition"]), edition_time(current["csv_edition"])
    require(old is None or new is None or new >= old, "UF HTTP source edition regressed")
    if current["sources"]["csv"] == prior["sources"]["csv"]:
        return
    require(old is not None and new is not None and new > old,
            "Changed same-version UF counts need an advancing HTTP source edition")


def collect(collector, config):
    require(config == CONFIG, "Unreviewed UF intake configuration")
    prior = collector.prior.get(IDENTITY, {}).get("data")

    def read(landing):
        dataset, version = discover(landing)
        dataset_body, _ = collector.acquire(dataset)
        declared = downloads(dataset_body, dataset, version)
        csv_body, _ = collector.acquire(declared["csv"])
        doc_body, _ = collector.acquire(declared["documentation"])
        result = {
            "contract": CONTRACT, "election_date": CONFIG["election_date"], "version": version,
            "declarations": {"landing": LANDING, "dataset": dataset, **declared},
            "sources": {name: {"url": url, **pin(body)} for name, url, body in (
                ("landing", LANDING, landing), ("dataset", dataset, dataset_body),
                ("csv", declared["csv"], csv_body), ("documentation", declared["documentation"], doc_body))},
            "csv_edition": collector.public_edition(declared["csv"]),
            "documentation": documentation(doc_body, version), "rows": parse(csv_body),
            "originals": {"csv": csv_body.decode("utf-8"),
                          "documentation": doc_body.decode("utf-8")},
            "limitations": LIMITATIONS,
        }
        check_revision(prior, result)
        return result

    return collector.capture(IDENTITY, LANDING, read)


def validate(entry):
    data = entry.get("data")
    require(data is not None and data.get("contract") == CONTRACT
            and data.get("election_date") == CONFIG["election_date"]
            and entry.get("status") in ("reported", "retained_after_failure"),
            "Unqualified UF participation entry")
    require(bool(re.fullmatch(r"\d+\.\d+", data["version"]))
            and tuple(map(int, data["version"].split("."))) >= (0, 3),
            "Unreviewed UF source version")
    declarations = data["declarations"]
    prefix = "https://election.lab.ufl.edu/"
    require(declarations == {
        "landing": LANDING,
        "dataset": prefix + "dataset/2026-general-election-turnout-rates-v"
                   + data["version"].replace(".", "-") + "/",
        "csv": prefix + "data-downloads/turnoutdata/Turnout_2026G_v" + data["version"] + ".csv",
        "documentation": prefix + "data-downloads/turnoutdata/Turnout_2026G_v"
                         + data["version"] + "_doc.txt",
    }, "UF source declaration/version changed")
    require(set(data["sources"]) == set(declarations)
            and all(data["sources"][name]["url"] == url for name, url in declarations.items()),
            "UF discovery source relation changed")
    edition_time(data["csv_edition"])
    require(data["rows"] == parse(data["originals"]["csv"].encode())
            and data["documentation"] == documentation(
                data["originals"]["documentation"].encode(), data["version"])
            and data["limitations"] == LIMITATIONS, "UF factual query changed")
    for key in ("csv", "documentation"):
        require(pin(data["originals"][key].encode()) == {
            name: data["sources"][key][name] for name in ("bytes", "sha256")},
            "UF original source pin changed")
        require(data["sources"][key]["url"] == data["declarations"][key],
                "UF original declaration changed")
        public_url(data["declarations"][key])
    require(entry["source"]["url"] == LANDING
            and entry["source"]["sha256"] == data["sources"]["landing"]["sha256"],
            "UF declaring source receipt changed")
    require(data["csv_edition"]["body_sha256"] == data["sources"]["csv"]["sha256"],
            "UF HTTP edition is not bound to the selected original")
    return data


def view(entry):
    data = validate(entry)
    return {
        "contract": CONTRACT, "election_date": CONFIG["election_date"], "version": data["version"],
        "status": entry["status"], "error": entry.get("error"),
        "first_observed_at": entry["first_observed_at"],
        "source": copy.deepcopy(data["sources"]["csv"]),
        "csv_edition": copy.deepcopy(data["csv_edition"]),
        "documentation": copy.deepcopy(data["documentation"]),
        "rows": copy.deepcopy(data["rows"]), "limitations": list(LIMITATIONS),
    }


def exports(entry):
    require(entry.get("data") is not None, "UF numerical exports require a last-good source")
    current = view(entry)
    stream = io.StringIO(newline="")
    columns = ("state_code", "state", "year", "geographic_level", "ballots", "vep", "vap",
               "vep_rate", "vap_rate", "source_status_literal", "ballots_status",
               "source_update_label", "source_update_timezone", "independently_certified",
               "local_allocation_qualified")
    writer = csv.DictWriter(stream, fieldnames=(*columns, "collection_status", "source_version",
                                              "source_url"), lineterminator="\n")
    writer.writeheader()
    for row in current["rows"]:
        writer.writerow({**{key: row[key] for key in columns}, "collection_status": entry["status"],
                         "source_version": current["version"], "source_url": current["source"]["url"]})
    return {"uf-turnout.csv": stream.getvalue().encode(), "uf-turnout.json": encoded(current),
            "uf-turnout-queries.json": encoded(entry)}
