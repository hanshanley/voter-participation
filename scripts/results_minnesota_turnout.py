"""Reconcile Minnesota's statewide reporting page to its complete statistical TXT."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import re

from scripts.participation_intake.contract import count


IDENTITY = "MN-statewide-reporting"
URL = "https://electionresults.sos.mn.gov/Results/CountyStatisticsStatewide/Index?ersElectionId=201"
TITLE = "Minnesota Statewide Reporting Statistics"
ELECTION = "Tuesday, November 3, 2026"
HEADER = ["County Name", "Number Precincts Reported", "Total Precincts in County",
          "Percent Precincts Reporting", "Date/Time First Precinct Reported",
          "Voters Registered at 7AM", "Estimated Voters"]
COUNTY_LINK = re.compile(r"/Results/CountyPrecinctStatisticsStatewide/Index\?ersElectionId=201&countyid=([0-9]+)")


def require(condition, detail):
    if not condition:
        raise ValueError(f"Minnesota statewide reporting: {detail}")


def integer(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+", value),
            "expected an explicit integer")
    return count(value.replace(",", ""))


def parse(body):
    from scripts.results_granular import FactualHTMLTables

    class Tables(FactualHTMLTables):
        def handle_starttag(self, tag, attributes):
            super().handle_starttag(tag, attributes)
            if tag == "a" and self.cell is not None:
                match = COUNTY_LINK.fullmatch(dict(attributes).get("href", ""))
                if match:
                    require("county_id" not in self.cell, "ambiguous county link")
                    self.cell["county_id"] = f"{int(match[1]):02d}"

    text = body.decode("utf-8-sig")
    statuses = re.findall(rf">\s*((?:Unofficial|Official) Results)\s+{ELECTION}\s*<", text)
    require(len(statuses) == 1, "election date or reporting status changed")
    parser = Tables()
    parser.feed(text)
    tables = [t["rows"] for t in parser.tables if t["rows"]]
    cells = lambda row: [" ".join(c["value"].split()) for c in row["cells"]]
    summary, = [table for table in tables if cells(table[0]) == [TITLE]]
    county_table, = [table for table in tables if cells(table[0]) == HEADER]
    labels = {}
    for row in summary[1:]:
        for cell in cells(row):
            name, sep, value = cell.partition(":")
            require(sep and name not in labels, "duplicate or missing summary label")
            labels[name] = value.strip()
    require(set(labels) == {"Eligible Population", "Estimated Voters", "Estimated Turnout",
                           "Counties Reporting", "Counties Complete", "Precincts Reporting in State",
                           "Last Updated", "Voters Registered at 7AM"}, "summary schema changed")
    counties = []
    for row in county_table[1:]:
        county, reported, total, pct, _, registered, voters = cells(row)
        county_id = row["cells"][0].get("county_id")
        require(county_id and county and pct == "100%" and integer(reported) == integer(total),
                "county inventory incomplete")
        counties.append({"county_id": county_id, "county": county, "precincts": integer(total),
                         "registered_7am": integer(registered), "total_number_voted": integer(voters)})
    data = {"status": statuses[0], "fields": labels, "counties": counties,
            "date": datetime.strptime(labels["Last Updated"], "%m/%d/%y %I:%M %p").isoformat()}
    return data


def reconcile(report, units):
    fields = report["fields"]
    require(report["status"] in {"Unofficial Results", "Official Results"}
            and report["date"] == datetime.strptime(fields["Last Updated"], "%m/%d/%y %I:%M %p").isoformat()
            and report["date"] >= "2026-11-03"
            and fields["Counties Reporting"] == "87 of 87" and fields["Counties Complete"] == "87",
            "election clock, status or county reporting is unqualified")
    counties = {}
    seen = set()
    for row in units:
        key = (row["county_id"], row["precinct_id"])
        require(key not in seen and row["state"] == "MN" and row["has_reported_statistics"] == "1"
                and all(type(row[k]) is int and count(row[k]) == row[k]
                        for k in ("registered_7am", "total_number_voted")),
                "missing or duplicate native precinct statistics")
        seen.add(key)
        summary = counties.setdefault(key[0], [0, 0, 0])
        summary[0] += 1
        summary[1] += row["registered_7am"]
        summary[2] += row["total_number_voted"]
    native = report["counties"]
    require(len(native) == len(counties) == 87
            and len({row["county"] for row in native}) == 87
            and {row["county_id"] for row in native} == set(counties)
            and all([row["precincts"], row["registered_7am"], row["total_number_voted"]]
                    == counties[row["county_id"]] for row in native),
            "statewide HTML and statistical TXT disagree by county")
    precincts = fields["Precincts Reporting in State"]
    inventories = re.fullmatch(r"100% ([0-9,]+) of ([0-9,]+)", precincts)
    total = sum(v[2] for v in counties.values())
    vep = integer(fields["Eligible Population"])
    require(inventories and integer(inventories[1]) == integer(inventories[2]) == len(seen)
            and integer(fields["Voters Registered at 7AM"]) == sum(v[1] for v in counties.values())
            and integer(fields["Estimated Voters"]) == total
            and 0 < total <= vep
            and fields["Estimated Turnout"] == f"{(Decimal(total) * 100 / vep).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)}%",
            "statewide display does not reconcile to the complete county frame")
    return {"total_number_voted": total, "precincts": len(seen), "counties": len(counties)}


def collect(collector, local):
    def parse_and_reconcile(body):
        report = parse(body)
        old = (collector.prior.get(IDENTITY) or {}).get("data") or {}
        require(old.get("status") != "Official Results" or report["status"] == "Official Results",
                "official status cannot regress")
        require(local.get("status") == "reported", "current statistical TXT is unavailable")
        result = reconcile(report, local["data"]["complete_native_query"])
        return {**report, "statistical_txt": local["source"], "reconciliation": result}

    return collector.capture(IDENTITY, URL, parse_and_reconcile)
