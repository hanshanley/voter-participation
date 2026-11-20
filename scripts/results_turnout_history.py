"""Read a public statewide general-election turnout series without guessing a missing year."""

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from email.utils import parsedate_to_datetime
from functools import partial
from html import unescape
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import unicodedata
from typing import Optional
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET

from scripts.participation_intake.contract import IntakeError, count, encoded, pin
from scripts import wyoming_participation_statistics as wy_profile
from scripts import colorado_voting_statistics, minnesota_precinct_history, nebraska_canvass, nebraska_county_reports


WA_FEED = "WA-general-election-turnout"
WA_URL = ("https://www.sos.wa.gov/elections/data-research/election-data-and-maps/"
          "reports-data-and-statistics/general-election-turnout")
WA_HEADER = ("Year", "Registered Voters", "Ballots Counted", "Turnout")
WA_FIRST = 1980
NC_HISTORY_FEED = "NC-general-election-turnout-history"
NC_HISTORY_URL = "https://www.ncsbe.gov/results-data/voter-turnout"
NC_HISTORY_HEADER = ("Election", "Eligible Voters", "Ballots Cast", "Turnout (%)")
WY_HISTORY_FEED = "WY-primary-general-turnout-profile"
WY_CANVASS_FEED = "WY-2026-precinct-ballot-canvass"
WY_CANVASS_URL = ("https://sos.wyo.gov/Elections/Docs/2026/Results/General/"
                  "2026_Wyoming_General_Election_Results.pdf")
VA_FEED = "VA-general-election-turnout"
VA_LOCALITY_DATE = "2022-11-08"
VA_LOCALITY_URL = ("https://results.elections.virginia.gov/vaelections/"
                   "2022%20November%20General/Site/Statistics/Turnout.html")
VA_LOCALITY_HEADER = ("Locality Name", "Early Voting", "Election Day", "By Mail**",
                     "Provisional", "Totals", "", "Curbside***")
VA_LOCALITY_ROSTER = "fdd899c080512865c463433dbba8b4de51a5e6344fd65337484267dabdc5f0bf"
VA_URL = "https://www.elections.virginia.gov/resultsreports/registrationturnout-statistics/"
VA_HEADER = ("Year", "Total Registered", "Percentage Change from Previous Year", "Total Voting",
             "Turnout (% Voting of Total Registered)", "Voting Absentee (Included in Total Voting)")
VA_TITLE = "November General Elections: 1976 \u2013 Present"
VA_CERTIFICATION = ("The Department of Elections only publishes turnout statistics for November Elections "
                    "and turnout figures are only published after the election is certified.")
VA_FIELDS = ("native_year", "registration_change_literal", "voting_absentee_literal")
TX_FEED = "TX-general-election-turnout"
TX_URL = "https://www.sos.state.tx.us/elections/historical/70-92.shtml"
TX_ARCHIVE_INPUT = "data/results-intake/tx-reviewed-turnout-history.json"
TX_ARCHIVE_PIN = {"bytes": 9746, "sha256": "94c22d392d24d2d9082b189a86a1f6b32ee2a847079aba6e65be99c3961959c5"}
TX_FIELDS = ("native_heading", "registered_literal", "voting_age_population",
             "published_registration_to_vap", "published_turnout_to_vap", "vap_rate_qualified")
TX_GENERAL = re.compile(
    r"(\d{4}) [-\u2013] (?:General|General Election,? November|November General|"
    r"(?:General, )?November \((?:Presidential|Gubernatorial)\))", re.I)
CURRENT_YEAR = 2026
KS_FEED = "KS-general-election-turnout-workbook"
KS_URL = "https://www.sos.ks.gov/elections/election-results.html"
KS_COUNTIES = {"bytes": 1737, "sha256": "a7dc594edcdb462f76861c8f1dfbc7f186b8929737c502771c7c3d264265b981"}
KS_HEADER = [["COUNTY", "ADVANCE BALLOTS", None, "TOTAL BALLOTS CAST", None, "REGISTERED"],
             [None, "RETURNED BY MAIL", None, None, None, "VOTERS"]]
NJ_FEED = "NJ-general-election-turnout-pdf"
NJ_URL = "https://www.nj.gov/state/elections/election-information-ballots-cast.shtml"
CA_URL = "https://www.sos.ca.gov/elections/statistics/voter-participation-stats-county"
CA_CURRENT_FEED = "CA-2026-general-election-turnout-pdf"
CA_CURRENT_ELECTION = "2026-11-03"
CA_CURRENT_CSV = "participation-ca-2026-county-turnout-report.csv"
CA_CURRENT_ROUTE = (r"https://(?:admin\.cdn\.sos\.ca\.gov/elections|elections\.cdn\.sos\.ca\.gov)"
                    r"/sov/2026-general/sov/03-voter-participation-stats-by-county\.pdf")
CA_REGISTRATION_NOTE = "15-day Report of Registration; excludes later registrations"
CA_SCAN_FILE = "results_ca_county_scan_transcriptions.json"
CA_SCAN_DATES = ("1990-11-06", "1992-11-03", "1994-11-08")
CA_ARCHIVES = {
    **dict.fromkeys(CA_SCAN_DATES[:2], "voter-participation-statistics.pdf"),
    "1994-11-08": "voter-participation-statistic.pdf",
    "1998-11-03": "v.pdf",
    "2000-11-07": "reg.pdf",
    "2002-11-05": "reg.pdf",
    "2004-11-02": "sov_pref_pg7_8_voter_participation_stats.pdf",
    "2006-11-07": "reg.pdf",
    "2008-11-04": "3_voter_part_stats_by_county.pdf",
    "2010-11-02": "03-voter-particpation-stats-by-county.pdf",
    "2012-11-06": "03-voter-participation-stats-by-county.pdf",
    "2014-11-04": "pdf/03-voter-particpiation-stats-by-county.pdf",
    **dict.fromkeys(("2016-11-08", "2018-11-06", "2020-11-03", "2022-11-08", "2024-11-05"),
                    "sov/03-voter-participation-stats-by-county.pdf"),
}
CA_COUNTIES = (
    "Alameda|Alpine|Amador|Butte|Calaveras|Colusa|Contra Costa|Del Norte|El Dorado|Fresno|Glenn|"
    "Humboldt|Imperial|Inyo|Kern|Kings|Lake|Lassen|Los Angeles|Madera|Marin|Mariposa|Mendocino|"
    "Merced|Modoc|Mono|Monterey|Napa|Nevada|Orange|Placer|Plumas|Riverside|Sacramento|San Benito|"
    "San Bernardino|San Diego|San Francisco|San Joaquin|San Luis Obispo|San Mateo|Santa Barbara|"
    "Santa Clara|Santa Cruz|Shasta|Sierra|Siskiyou|Solano|Sonoma|Stanislaus|Sutter|Tehama|Trinity|"
    "Tulare|Tuolumne|Ventura|Yolo|Yuba"
).split("|")
WV_ARCHIVE_URL = "https://sos.wv.gov/elections/election-data/historical-voter-turnout"
WV_ARCHIVES = {"2008-11-04": 655, "2010-11-02": 647, "2012-11-06": 649, "2014-11-04": 651, "2016-11-08": 653}
WV_COUNTIES = (
    "Barbour|Berkeley|Boone|Braxton|Brooke|Cabell|Calhoun|Clay|Doddridge|Fayette|Gilmer|Grant|"
    "Greenbrier|Hampshire|Hancock|Hardy|Harrison|Jackson|Jefferson|Kanawha|Lewis|Lincoln|Logan|"
    "Marion|Marshall|Mason|McDowell|Mercer|Mineral|Mingo|Monongalia|Monroe|Morgan|Nicholas|Ohio|"
    "Pendleton|Pleasants|Pocahontas|Preston|Putnam|Raleigh|Randolph|Ritchie|Roane|Summers|Taylor|"
    "Tucker|Tyler|Upshur|Wayne|Webster|Wetzel|Wirt|Wood|Wyoming"
).split("|")
WV_HISTORY_NOTE = "The source labels the count Ballots Cast (based on voter history)."
WY_ARCHIVE_BASE = "https://sos.wyo.gov/Elections/Docs/"
WY_ARCHIVES = {
    "2004-11-02": "04Results/04General/04_General_SW_Candidates.pdf",
    "2006-11-07": "06Results/06General/SW_TB_Summary.pdf",
    "2008-11-04": "08Results/General/SW-TotalBallotsCast.pdf",
    "2010-11-02": "Results/General/2010_Statewide_Total_Ballots_Cast_Summary.pdf",
    "2012-11-06": "Results/General/2012_Statewide_Total_Ballots_Cast_Summary.pdf",
    "2014-11-04": "Results/General/2014_Statewide_Total_Ballots_Cast_Summary.pdf",
    "2016-11-08": "Results/General/2016_General_Statewide_Total_Ballots_Cast_Summary.pdf",
    "2018-11-06": "Results/General/2018_Statewide_Total_Ballots_Cast_Summary.pdf",
    "2020-11-03": "Results/General/2020_General_Statewide_Total_Ballots_Cast_Summary.pdf",
    "2022-11-08": "Results/General/2022_General_Statewide_Total_Ballots_Cast_Summary.pdf",
    "2024-11-05": "Results/General/2024_General_Statewide_Total_Ballots_Cast_Summary.pdf",
}
WY_COUNTIES = (
    "Albany|Big Horn|Campbell|Carbon|Converse|Crook|Fremont|Goshen|Hot Springs|Johnson|"
    "Laramie|Lincoln|Natrona|Niobrara|Park|Platte|Sheridan|Sublette|Sweetwater|Teton|"
    "Uinta|Washakie|Weston"
).split("|")
COUNTY_ARCHIVES = {
    "VA-2022-general-election-locality-turnout": ("VA", VA_LOCALITY_DATE),
    **{f"MN-{election[:4]}-general-precinct-turnout-workbook": ("MN", election)
       for election in minnesota_precinct_history.EDITIONS},
    **{f"CO-{election[:4]}-general-voting-statistics": ("CO", election)
       for election in colorado_voting_statistics.EDITIONS},
    **{f"CA-{election[:4]}-general-election-turnout-pdf": ("CA", election) for election in CA_ARCHIVES},
    "KS-2022-general-election-turnout-workbook": ("KS", "2022-11-08"),
    "NJ-2020-general-election-turnout-pdf": ("NJ", "2020-11-03"),
    "NJ-2022-general-election-turnout-pdf": ("NJ", "2022-11-08"),
    "NJ-2023-general-election-turnout-pdf": ("NJ", "2023-11-07"),
    "NJ-2024-general-election-turnout-pdf": ("NJ", "2024-11-05"),
    "NJ-2025-general-election-turnout-pdf": ("NJ", "2025-11-04"),
    **{f"WV-{election[:4]}-general-election-turnout-pdf": ("WV", election) for election in WV_ARCHIVES},
    **{f"WY-{election[:4]}-general-election-ballots-pdf": ("WY", election) for election in WY_ARCHIVES},
    **{f"NE-{election[:4]}-general-election-canvass": ("NE", election)
       for election in nebraska_canvass.BOOKS},
}
COUNTY_ARCHIVE_CSV = "participation-state-county-turnout-archives.csv"
BUXTON_FEED = "ME-buxton-town-turnout"
BUXTON_URL = "https://www.buxton.me.us/news/11-3-2026-election-results"
BUXTON_TITLE = "Election Results for the Town of Buxton, Maine - November 3, 2026 State and Town Elections"
BUXTON_FIELDS = ("Registered Voters", "Absentee Ballots Cast", "Ballots Cast in Person",
                 "Total Ballots Cast", "Voter Turn Out Percent")
BATH_FEED = "ME-bath-municipal-turnout"
HOLLIS_FEED = "NH-hollis-municipal-turnout"
HOLLIS_INDEX = "https://www.hollisnh.gov/1447/Elections"
HOLLIS_REPORT = urljoin(HOLLIS_INDEX, "/DocumentCenter/View/6048/2026-General-Election-Results-PDF")


@dataclass(frozen=True)
class VotingWorksTown:
    feed: str
    town: str
    feature_key: str
    index: str
    link_label: str
    document_slug: Optional[str]
    election_id: str
    timestamped_slug: bool = False

    def permits_report(self, url):
        authority, candidate = urlsplit(self.index), urlsplit(url)
        path = r"/DocumentCenter/View/[1-9][0-9]*"
        if self.document_slug is None:
            if self.timestamped_slug or self.link_label != f"November 3, {CURRENT_YEAR} General Election":
                return False
        else:
            path += "/" + re.escape(self.document_slug)
            if self.timestamped_slug:
                path += r"__[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}"
        return (candidate.scheme == authority.scheme == "https"
                and candidate.netloc == authority.netloc and not candidate.query and not candidate.fragment
                and re.fullmatch(path, candidate.path) is not None)


VOTINGWORKS_TOWNS = {
    HOLLIS_FEED: VotingWorksTown(HOLLIS_FEED, "Hollis", "3337140", HOLLIS_INDEX,
                               "General Election (PDF)", "2026-General-Election-Results-PDF",
                               "a2c1dd6-9bf2c33"),
    "NH-bedford-municipal-turnout": VotingWorksTown(
        "NH-bedford-municipal-turnout", "Bedford", "3304500",
        "https://www.bedfordnh.gov/514/Election-Results", "Results",
        "official-full-election-tally-report", "663d329-455bc00", timestamped_slug=True),
    "NH-hanover-municipal-turnout": VotingWorksTown(
        "NH-hanover-municipal-turnout", "Hanover", "3333860",
        "https://hanovernh.org/359/Voting-Information", "November 3, 2026 General Election",
        None, "9b5c84a-d362699"),
}

BATH_INDEX = "https://www.cityofbathmaine.gov/Departments/City-Clerk/Elections/Past-Election-Results"
BATH_PDF = ("https://www.cityofbathmaine.gov/files/assets/bath/v/1/city-clerk/documents/"
            "election-night-results.pdf")
BATH_STATISTICS = re.compile(
    r"Total State Votes Cast: ([0-9]+) Total registered voters: ([0-9]+) % of Voter Turnout: ([0-9]+\.[0-9]%)")
OH_FEED = "OH-statewide-ballots-counted"
OH_BASE = "https://liveresults.ohiosos.gov/Api/v1/"
OH_BALLOTS = OH_BASE + "Contest/getBallotsCastByCounty"
OH_ELECTION = OH_BASE + "download?filename=VSSC1622XmlFileBlob"
OH_NS = {"n": "http://grouper.ieee.org/groups/1622/groups/2/V1/1622_2-election_results_reporting.xsd"}
OH_FIELDS = ("ballotCast", "registeredVoterTotal", "reportedPrecincts", "totalPrecincts",
             "outAbsentees", "outProvisionals")
OH_XML_FIELDS = ("VotersParticipated", "VotersRegistered", "SubUnitsReported", "TotalSubUnits")
OH_COUNTY_NAMES = {"bytes": 852, "sha256": "3d981909d6bb6f7addb671c20cf9e503e51f520909781c702ca1cc2b7c06d75c"}
MT_FEED = "MT-statewide-reported-turnout"
MT_URL = "https://electionresults.mt.gov/"
MT_TITLE = "General Election - November 3, 2026"
WV_FEED = "WV-statewide-preliminary-turnout-bulletin"
WV_URL = ("https://sos.wv.gov/article/"
          "wv-secretary-state-kris-warner-announces-canvassing-will-start-monday-november-9")
WV_TITLE = "WV Secretary of State Kris Warner announces canvassing will start on Monday, November 9"
ND_CANVASS_FEED = "ND-statewide-canvass-turnout-bulletin"
ND_CANVASS_URL = "https://www.sos.nd.gov/news/state-canvassing-board-certifies-2026-general-election-results"
ND_CANVASS_TITLE = "State Canvassing Board Certifies 2026 General Election Results"
GA_FEED = "GA-statewide-county-ballots-cast"
GA_URL = "https://results.sos.ga.gov/results/public/api/elections/Georgia/11032026GeneralAndSpecialElection/data"
GA_ELECTION = "01000000-70f4-ca87-08cb-08df23e5fea8"
GA_JURISDICTION = "09378a07-e6cf-4f66-be7c-ca4aa534f99a"
GA_COUNTIES = {"bytes": 8830, "sha256": "20c0309221a8d7a606eda3f5f90f7b074241c275be772e9bafde0bf024e1ec7f"}
NJ_COUNTIES = (
    "Atlantic", "Bergen", "Burlington", "Camden", "Cape May", "Cumberland", "Essex",
    "Gloucester", "Hudson", "Hunterdon", "Mercer", "Middlesex", "Monmouth", "Morris", "Ocean",
    "Passaic", "Salem", "Somerset", "Sussex", "Union", "Warren",
)
NJ_HEADER = [
    "Total Number of Registered Voters, Ballots Cast, Ballots Rejected, Percentage of Ballots Cast and the",
    "Total Number of Election Districts in New Jersey",
    "COUNTY Total Number of Total Number of Total Number of Percent of Ballots Number of",
    "Registered Voters Ballots Cast Ballots Rejected Cast Election Districts",
]


def archive_link(body, url, pattern, *, label=None):
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = set()
            self.active = None
            self.text = []

        def handle_starttag(self, tag, attrs):
            if tag == "a" and (href := dict(attrs).get("href")):
                target = urljoin(url, href)
                if url == nebraska_canvass.INDEX:
                    target = target.replace(" ", "%20")
                if label is None:
                    self.links.add(target)
                    return
                self.active = target
                self.text = []

        def handle_data(self, data):
            if self.active is not None and label is not None:
                self.text.append(data)

        def handle_endtag(self, tag):
            if tag != "a" or self.active is None:
                return
            if re.fullmatch(label, " ".join("".join(self.text).split()), re.I):
                self.links.add(self.active)
            self.active = None

    parser = Links()
    parser.feed(body.decode("utf-8-sig"))
    links = [link for link in parser.links if re.fullmatch(pattern, link)]
    if len(links) > 1:
        raise ValueError("Ambiguous general-election turnout archive report")
    return links[0] if links else None


def kansas_report_url(year):
    return (rf"https://(?:www\.)?sos\.ks\.gov/elections/{year % 100:02d}elec/"
            rf"{year}-General-Election-Turnout-Information\.xlsx")


def kansas_link(body, year):
    return archive_link(body, KS_URL, kansas_report_url(year))


def new_jersey_report_url(year):
    return (r"https://(?:www\.)?nj\.gov/state/elections/assets/pdf/election-results/"
            rf"{year}/{year}-official-general-voter-turnout\.pdf")


def kansas_workbook(body):
    from openpyxl import load_workbook

    with io.BytesIO(body) as stream:
        workbook = load_workbook(stream, read_only=True, data_only=True)
        try:
            if len(workbook.worksheets) != 1 or workbook.active.max_column != 6 or not 110 <= workbook.active.max_row <= 150:
                raise ValueError("Kansas turnout workbook dimensions changed")
            rows = [list(row) for row in workbook.active.values]
        finally:
            workbook.close()
    if rows[:2] != KS_HEADER:
        raise ValueError("Kansas turnout workbook column labels changed")
    nonblank = [row for row in rows[2:] if any(value is not None for value in row)]
    if len(nonblank) != 106 or any(row[2] is not None or row[4] is not None for row in nonblank):
        raise ValueError("Kansas turnout workbook row inventory changed")
    counties, total = nonblank[:-1], nonblank[-1]
    query = {"counties": [[row[0], row[1], row[3], row[5]] for row in counties],
             "total": [total[1], total[3], total[5]]}
    if total[0] not in (None, "TOTAL", "STATE TOTAL"):
        raise ValueError("Kansas turnout workbook statewide selector changed")
    kansas_controls(query, allow_county_conflicts=True)
    return query


def kansas_controls(query, *, allow_county_conflicts=False):
    counties, total = query["counties"], query["total"]
    if (len(counties) != 105 or any(len(row) != 4 or not isinstance(row[0], str) for row in counties)
            or pin(encoded(sorted(row[0] for row in counties))) != KS_COUNTIES
            or len(total) != 3):
        raise ValueError("Kansas turnout county identities changed")
    for mail, ballots, registered in [row[1:] for row in counties] + [total]:
        if (type(ballots) is not int or type(registered) is not int or min(ballots, registered) < 0
                or not (mail == "N/A" or type(mail) is int and 0 <= mail <= ballots)):
            raise ValueError("Invalid Kansas turnout workbook figures")
    if (sum(row[2] for row in counties) != total[1] or sum(row[3] for row in counties) != total[2]
            or not 0 < total[1] <= total[2]):
        raise ValueError("Kansas county and statewide totals disagree")
    conflicts = [name for name, _, ballots, registered in counties if ballots > registered]
    if conflicts and not allow_county_conflicts:
        raise ValueError("Kansas county ballot counts exceed reported registrations: " + ", ".join(conflicts))
    return total[1], total[2]


def collect_kansas(collector):
    def parse(index):
        url = kansas_link(index, CURRENT_YEAR)
        if url is None:
            if (collector.prior.get(KS_FEED, {}).get("data") or {}).get("report"):
                raise ValueError("Previously reported Kansas turnout workbook is no longer linked")
            return {"current_election_status": "workbook_not_linked", "participation_observation_qualified": False}
        body, _ = collector.acquire(url)
        if len(body) > 2_000_000:
            raise ValueError("Kansas turnout workbook exceeds reviewed size bound")
        query = kansas_workbook(body)
        kansas_controls(query)
        return {"report": {"url": url, **pin(body)}, "complete_native_query": query,
                "current_election_status": "row_published", "participation_observation_qualified": False}

    return collector.capture(KS_FEED, KS_URL, parse, equivalent=lambda old, new: old == new)


def new_jersey_controls(query, election_date):
    counties, total = query["counties"], query["total"]
    if (query["election_date"] != election_date
            or query["published_date"] < election_date
            or [row["county"] for row in counties] != list(NJ_COUNTIES)
            or total["county"] != "TOTAL"):
        raise ValueError("New Jersey turnout report election or county inventory changed")
    fields = ("registered", "ballots_cast", "ballots_rejected", "election_districts")
    for row in counties + [total]:
        registered, ballots, rejected, districts = (row[field] for field in fields)
        reported = row["printed_percent"]
        if (any(type(row[field]) is not int for field in fields)
                or not registered or not 0 <= ballots <= registered
                or rejected < 0 or districts <= 0
                or type(reported) is not int
                or reported != (Decimal(ballots) * 100 / registered).quantize(
                    Decimal(1), rounding=ROUND_HALF_UP)):
            raise ValueError("New Jersey turnout report has an invalid count or printed percentage")
    if any(total[field] != sum(row[field] for row in counties) for field in fields):
        raise ValueError("New Jersey turnout report county and statewide totals disagree")
    return total["ballots_cast"], total["registered"]


def new_jersey_report(body, election_date, *, allow_amended=False):
    from pypdf import PdfReader

    if len(body) > 2_000_000 or not body.startswith(b"%PDF-"):
        raise ValueError("New Jersey turnout report is not a bounded PDF")
    pdf = PdfReader(io.BytesIO(body))
    if pdf.is_encrypted or len(pdf.pages) != 1:
        raise ValueError("New Jersey turnout report page inventory changed")
    lines = [" ".join(line.split()) for line in
             pdf.pages[0].extract_text(extraction_mode="layout").splitlines() if line.strip()]
    amendment = None
    if allow_amended and lines and lines[0] == "-AMENDED-":
        footer = re.fullmatch(
            r"\*?(Based on additional information received by (.+?) County after the results were "
            r"certified on ([A-Z][a-z]+ \d{1,2}, \d{4})) (NJDOE-\d{1,2}/\d{1,2}/\d{4})",
            " ".join(lines[28:]),
        )
        if not footer or footer[2] not in NJ_COUNTIES:
            raise ValueError("Unrecognized amended New Jersey election turnout report")
        amendment = {"note": footer[1], "county": footer[2],
                     "original_certification_date": datetime.strptime(footer[3], "%B %d, %Y").date().isoformat()}
        lines = [*lines[1:28], footer[4]]
    headers = lines[:2] + lines[3:5]
    amended_headers = [NJ_HEADER[0] + " Total", NJ_HEADER[1].removeprefix("Total "), *NJ_HEADER[2:]]
    if len(lines) != 28 or not (headers == NJ_HEADER or amendment and headers == amended_headers):
        raise ValueError("New Jersey turnout report headings or row inventory changed")
    election = datetime.strptime(lines[2], "General Election %B %d, %Y").date().isoformat()
    published = datetime.strptime(lines[-1], "NJDOE-%m/%d/%Y").date().isoformat()
    rows = []
    number = r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)"
    for county, line in zip((*NJ_COUNTIES, "TOTAL"), lines[5:-1]):
        match = re.fullmatch(re.escape(county) + rf" ({number}) ({number}) ({number}) ([0-9]+)% ({number})",
                             line)
        if not match:
            raise ValueError("New Jersey official turnout row changed: " + county)
        values = [int(value.replace(",", "")) for value in match.groups()]
        rows.append(dict(zip(("county", "registered", "ballots_cast", "ballots_rejected",
                              "printed_percent", "election_districts"), (county, *values))))
    query = {"election_date": election, "published_date": published,
             "counties": rows[:-1], "total": rows[-1]}
    if amendment:
        if not election < amendment["original_certification_date"] < published:
            raise ValueError("Amended New Jersey report dates are inconsistent")
        query["amendment"] = amendment
    new_jersey_controls(query, election_date)
    return query


def collect_new_jersey(collector):
    def parse(index):
        url = archive_link(index, NJ_URL, new_jersey_report_url(CURRENT_YEAR))
        prior = collector.prior.get(NJ_FEED, {}).get("data") or {}
        if url is None:
            if prior.get("report"):
                raise ValueError("Previously reported New Jersey turnout PDF is no longer linked")
            return {"current_election_status": "report_not_linked", "participation_observation_qualified": False}
        body, _ = collector.acquire(url)
        query = new_jersey_report(body, "2026-11-03")
        return {"report": {"url": url, **pin(body)}, "complete_native_query": query,
                "date": query["published_date"], "current_election_status": "row_published",
                "participation_observation_qualified": False}

    return collector.capture(NJ_FEED, NJ_URL, parse, equivalent=lambda old, new: old == new)


def california_report_url(election):
    base = ("https://admin.cdn.sos.ca.gov/elections" if election[:4] == "2024"
            else "https://elections.cdn.sos.ca.gov")
    return f"{base}/sov/{election[:4]}-general/{CA_ARCHIVES[election]}"


def california_controls(query, election):
    rows = [*query["counties"], query["total"]]
    fields = ("election_districts", "eligible", "registered", "precinct_voters", "mail_voters", "ballots_cast")
    if (query["election_date"] != election or [row["county"] for row in rows] != [*CA_COUNTIES, "TOTAL"]
            or query["native_numerator"] != ("ballots_cast" if election[:4] == "2000" else "total_voters")):
        raise ValueError("California turnout report date, measure or county roster differs")
    for row in rows:
        if (any(type(row[field]) is not int or row[field] < 0 for field in fields)
                or not row["registered"] or not row["eligible"]
                or row["precinct_voters"] + row["mail_voters"] != row["ballots_cast"]):
            raise ValueError(f"Invalid California voter counts for {row['county']}")
        for field in ("registered", "eligible"):
            printed = row[f"printed_{field}_percent"]
            if not isinstance(printed, str) or not re.fullmatch(r"\d{1,3}\.\d{2}%", printed):
                raise ValueError("Invalid California printed turnout percentage")
    if any(rows[-1][field] != sum(row[field] for row in rows[:-1]) for field in fields):
        raise ValueError("California turnout report county and statewide totals disagree")


def california_scan(report, election):
    source = json.loads(Path(__file__).with_name(CA_SCAN_FILE).read_bytes())
    if source.get("contract") != "participation.ca_county_scan_transcription.v1":
        raise ValueError("Unknown California scan transcription contract")
    scan = source["reports"][election]
    if scan["pdf"] != {key: report[key] for key in ("bytes", "sha256")}:
        raise IntakeError("unreviewed_report_revision", "Changed California scan needs a new checked transcription")
    fields = ("county", "election_districts", "eligible", "registered", "precinct_voters", "mail_voters",
              "ballots_cast", "printed_registered_percent", "printed_eligible_percent")
    if any(len(row) != len(fields) for row in scan["rows"]):
        raise ValueError("Malformed California scan transcription")
    rows = [dict(zip(fields, row)) for row in scan["rows"]]
    for row in rows:
        for field in fields[-2:]:
            row[field] += "%"
    query = {
        "election_date": election, "counties": rows[:-1], "total": rows[-1],
        "native_numerator": "total_voters", "registration_basis": "Report's registered voters",
        "secondary_denominator": "voting_age_population" if election == "1992-11-03" else "eligible_to_register",
        "extraction_method": "checked_transcription_of_pinned_pdf",
    }
    if election == "1994-11-08":
        query["report_note"] = ("County report's statewide Total Voters is 8,900,632. "
                                "The later statewide historical series reports 8,900,593; not substituted.")
    california_controls(query, election)
    return query


def california_report(body, election):
    from pypdf import PdfReader

    if not body.startswith(b"%PDF-") or len(body) > 2_000_000:
        raise ValueError("California turnout report is not a bounded PDF")
    pdf = PdfReader(io.BytesIO(body))
    if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 6:
        raise ValueError("California turnout report page inventory changed")
    year = int(election[:4])
    title = "VOTER PARTICIPATION STATISTICS BY COUNTY"
    extracted = []
    for page in pdf.pages:
        lines = [" ".join(line.split()) for line in page.extract_text(extraction_mode="layout").splitlines()
                 if line.strip()]
        if any(line.upper().startswith(title) for line in lines):
            extracted.extend(lines)
    if not extracted:
        raise ValueError("California turnout table heading not found")
    if year == 2004 or year >= 2020:
        day = int(election[-2:])
        if not any(re.fullmatch(rf"NOVEMBER {day}, {year},? GENERAL ELECTION", line.upper())
                   for line in extracted):
            raise ValueError("California turnout report election date differs")
    header = " ".join(line for line in extracted if re.match(
        r"^(?:County |Number of Eligible|Precincts |Precinct Absentee)", line))
    if ("Registered" not in header
            or ("Ballots Cast" if year == 2000 else "Voters") not in header):
        raise ValueError("California turnout table headers differ")
    if election == CA_CURRENT_ELECTION and not re.fullmatch(
            r"County Number of Eligible to Registered Precinct Vote-By-Mail Total Percent of Turnout Turnout "
            r"Precincts Register Voters1? Voters\*? Voters Voters Vote-By-Mail Registered Eligible",
            header):
        raise ValueError("California current turnout table columns differ from the reviewed layout")
    counties, total, total_index = [], None, None
    fields = ("election_districts", "eligible", "registered", "precinct_voters", "mail_voters", "ballots_cast")
    integer = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
    pct = r"[0-9]{1,3}\.[0-9]{2}%"
    names = "|".join(re.escape(name) for name in [*CA_COUNTIES, "STATEWIDE"]) + "|State Totals?"
    pattern = re.compile(rf"({names})(\*{{0,3}}) (.+)")
    for index, line in enumerate(extracted):
        if year == 2006 and index + 1 < len(extracted):
            for first, last in (("San", "Bernardino"), ("San Luis", "Obispo")):
                wrapped = re.fullmatch(rf"{last} ({integer})", extracted[index + 1])
                head = re.fullmatch(rf"{first} ({integer}) (.+)", line)
                if wrapped and head:
                    line = f"{first} {last} {head[1]} {wrapped[1]} {head[2]}"
        match = pattern.fullmatch(line)
        if not match:
            continue
        name, mark, values = match.groups()
        statewide = name.startswith("State Total") or name == "STATEWIDE"
        if not statewide and year == 2014:
            moved = (re.fullmatch(rf"(.+?%)({integer})( .+)?", values) if name != "Shasta"
                     else re.fullmatch(r"(.+ \d{1,3},\d{3})(\d{1,3})( .+)", values))
            if not moved:
                raise ValueError(f"Unrecognized 2014 California precinct field placement at {name}")
            values = f"{moved[2]} {moved[1]}{moved[3] or ''}"
        elif year == 2018 and name == "Sutter":
            moved = re.fullmatch(rf"({integer}) (.+%)({integer})", values)
            if moved:
                values = f"{moved[1]} {moved[3]} {moved[2]}"
        elif year >= 2024:
            values = re.sub(r"\* +\*", "**", values)
        tokens = values.split()
        numbers = tokens[:6]
        if (len(numbers) != 6 or any(not re.fullmatch(
            rf"{integer}(?:\*{{1,3}})?|-" if key == "precinct_voters" else integer, token)
                                    for key, token in zip(fields, numbers))
                or (numbers[3] == "-" and year != 2000)):
            raise ValueError(f"California turnout table includes malformed counts at {name}")
        row = dict(zip(fields, (int(x.replace(",", "").rstrip("*")) if x != "-" else 0 for x in numbers)))
        rates = tokens[6:]
        if statewide and not rates:
            if year < 2008:
                raise ValueError("Missing statewide rates")
            percent_lines = [l for l in extracted if l.startswith("Percent ")]
            if len(percent_lines) != 1:
                raise ValueError("Ambiguous California statewide rate line")
            rates = re.findall(pct, percent_lines[0])[-2:]
        allowed_rates = (2,) if statewide else (3,) if election == CA_CURRENT_ELECTION else (2, 3)
        if (len(rates) not in allowed_rates
                or not all(re.fullmatch(pct, token) for token in rates)):
            raise ValueError(f"California turnout table includes malformed rates at {name}")
        row.update(county="TOTAL" if statewide else name, county_mark=mark,
                   precinct_literal=numbers[3],
                   printed_mail_percent=rates[0] if len(rates) == 3 else None,
                   printed_registered_percent=rates[-2], printed_eligible_percent=rates[-1])
        if statewide:
            if total is not None:
                raise ValueError("California turnout report repeats its statewide row")
            total, total_index = row, index
        else:
            counties.append(row)
    if total is None:
        raise ValueError("California turnout report statewide row missing")
    notes = extracted[total_index + 1:]
    registration_basis = CA_REGISTRATION_NOTE if year in (2022, 2024) else "Report's registered voters"
    if election == CA_CURRENT_ELECTION:
        footnote = " ".join(notes)
        known_basis = ("based on the 15-day Report of Registration and do not include "
                       "voters registered after the 15-day close")
        registration_basis = (CA_REGISTRATION_NOTE if known_basis in footnote
                              else "Registration timing not independently qualified")
    query = {"election_date": election, "counties": counties, "total": total,
             "native_numerator": "ballots_cast" if year == 2000 else "total_voters",
             "registration_basis": registration_basis,
             "table_notes": notes}
    california_controls(query, election)
    return query


def west_virginia_archive_query(lines, election):
    year = int(election[:4])
    by_history = year in (2008, 2010)
    header = ["County Registered Voters Turnout Ballots Cast", "(based on voter history)"] if by_history else [
        "County Ballots Cast Registered Voters Turnout"]
    if election not in WV_ARCHIVES or lines[:1 + len(header)] != [f"{year} General", *header]:
        raise ValueError("West Virginia historical election or measure header differs")
    native = []
    for line in lines[1 + len(header):]:
        match = re.fullmatch(r"([A-Za-z ]+?) ([0-9,]+) ([0-9,]+) ([0-9]{1,3}\.[0-9]%)", line)
        if not match:
            raise ValueError("Unexpected West Virginia turnout table row")
        name, numerator, stock, rate = match.groups()
        votes, registered = integer(numerator), integer(stock)
        if not 0 <= votes <= registered or Decimal(rate[:-1]) > 100:
            raise ValueError("West Virginia turnout exceeds its same-report denominator")
        native.append({"county": name, "ballots_cast": votes, "registered": registered, "printed_percent": rate})
    if [row["county"] for row in native] != [*WV_COUNTIES, "West Virginia"]:
        raise ValueError("West Virginia county roster or state total differs")
    for key in ("ballots_cast", "registered"):
        if sum(row[key] for row in native[:-1]) != native[-1][key]:
            raise ValueError("West Virginia county rows do not reconcile to the state total")
    return {"election_date": election, "counties": native[:-1], "total": {**native[-1], "county": "TOTAL"},
            "native_numerator": "voter_history_credits" if by_history else "ballots_cast",
            "registration_basis": "Report's registered voters",
            "report_note": WV_HISTORY_NOTE if by_history else None,
            "extraction_method": "pdf_reviewed_county_table", "native_lines": lines}


def west_virginia_archive_report(body, election):
    from pypdf import PdfReader

    pdf = PdfReader(io.BytesIO(body), strict=True)
    if len(pdf.pages) != 1:
        raise ValueError("West Virginia historical turnout needs a single report page")
    lines = [" ".join(line.split()) for line in pdf.pages[0].extract_text(extraction_mode="layout").splitlines()]
    return west_virginia_archive_query([line for line in lines if line], election)


def wyoming_archive_query(lines, election):
    day = datetime.fromisoformat(election).day
    year = election[:4]
    date = f"November {day}, {year}"
    abstract = year == "2004"
    if abstract:
        title = f"Statewide Candidates' Abstract -- Official Wyoming General Election Results -- {date}"
        if (len(lines) != 31 or lines[0] != title or lines[1:3] != [
                "Total Presidential Presidential", "Ballots Cast Write-ins Over Votes"]):
            raise ValueError("Wyoming abstract no longer identifies its printed ballot-count column")
        rows = lines[5:29]
    else:
        title = {"2022": "Total Ballots Cast", "2024": "Statewide Total Ballots Cast"}.get(
            year, "Statewide Total Ballots Cast Official Summary")
        if lines[:2] != [title, f"Wyoming General Election - {date}"]:
            raise ValueError("Wyoming ballot summary identity differs")
        if year == "2006" and lines[2:3] == ["Total Ballots Cast"]:
            rows = lines[3:]
        elif year == "2008" and lines[2:3] == ["Page 1 of 1"] and lines[-2:] == ["Total", "Ballots Cast"]:
            rows = lines[3:-2]
        elif lines[2:5] == ["Page 1 of 1", "Total Ballots", "Cast"]:
            rows = lines[5:]
        elif year == "2016" and lines[-2:] == ["Total Ballots Cast", "Page 1 of 1"]:
            rows = lines[2:-2]
        elif year in ("2018", "2020") and lines[2:4] == ["Page 1 of 1", "Total Ballots Cast"]:
            rows = lines[4:]
        elif year in ("2022", "2024") and lines[2:3] == ["Total Ballots Cast"] and lines[-1:] == ["Page 1 of 1"]:
            rows = lines[3:-1]
        else:
            raise ValueError("Wyoming ballot summary header differs")
    names = [*WY_COUNTIES, "Official Totals" if abstract else "Total"]
    result = []
    for name, row in zip(names, rows, strict=True):
        found = re.fullmatch(re.escape(name) + r" ([0-9][0-9,]*)" + (r" .+" if abstract else ""), row)
        if not found:
            raise ValueError("Wyoming county ballot roster or column differs")
        result.append({"county": "TOTAL" if name == names[-1] else name,
                       "ballots_cast": integer(found[1]), "registered": None})
    if sum(row["ballots_cast"] for row in result[:-1]) != result[-1]["ballots_cast"]:
        raise ValueError("Wyoming county counts do not reconcile to printed statewide total")
    return {
        "extraction_method": "pdf_reviewed_county_table", "native_lines": lines,
        "election_date": election, "native_numerator": "ballots_cast", "registration_basis": None,
        "report_note": "Official ballot counts; the report supplies no registration denominator.",
        "counties": result[:-1], "total": result[-1],
    }


def wyoming_archive_report(body, election):
    from pypdf import PdfReader

    pdf = PdfReader(io.BytesIO(body), strict=True)
    year = election[:4]
    if len(pdf.pages) != {"2004": 8, "2024": 2}.get(year, 1):
        raise ValueError("Wyoming turnout report page inventory differs")
    page = pdf.pages[1 if year == "2024" else 0]
    text = page.extract_text(extraction_mode="layout") if year in ("2006", "2022", "2024") else page.extract_text()
    return wyoming_archive_query([" ".join(line.split()) for line in text.splitlines() if line.strip()],
                                 election)


def county_archive_routes(state, election):
    year = int(election[:4])
    if state == "MN":
        url = minnesota_precinct_history.route(election)
        return url, re.escape(url)
    if state == "VA" and election == VA_LOCALITY_DATE:
        return VA_LOCALITY_URL, re.escape(VA_LOCALITY_URL)
    if state == "CO":
        index, report = colorado_voting_statistics.routes(election)
        return index, re.escape(report)
    if state == "NE":
        return nebraska_canvass.routes(election)
    if state == "CA":
        if election == CA_CURRENT_ELECTION:
            return CA_URL, CA_CURRENT_ROUTE
        return CA_URL, re.escape(california_report_url(election))
    if state == "WV":
        return WV_ARCHIVE_URL, rf"https://sos\.wv\.gov/media/{WV_ARCHIVES[election]}/download\?inline=?"
    if state == "WY":
        base = f"{WY_ARCHIVE_BASE}{year}/"
        return f"{base}{year}GeneralResults.aspx", re.escape(base + WY_ARCHIVES[election])
    return (KS_URL, kansas_report_url(year)) if state == "KS" else (NJ_URL, new_jersey_report_url(year))


def wyoming_profile(body):
    from pypdf import PdfReader

    if not body.startswith(b"%PDF-") or len(body) > 2_000_000:
        raise ValueError("Wyoming turnout profile is not a bounded PDF")
    pdf = PdfReader(io.BytesIO(body), strict=True)
    if len(pdf.pages) != 1:
        raise ValueError("Wyoming turnout profile page inventory differs")
    return wy_profile.parse_profile(pdf.pages[0].extract_text())


def collect_wyoming_history(collector):
    def parse(body):
        rows = wyoming_profile(body)
        month, year = rows[0]["source_revision"].split("/")
        edition = f"{year}-{month}"
        prior = (collector.prior.get(WY_HISTORY_FEED) or {}).get("data") or {}
        accepted = {(row["year"], row["election_type"]) for row in rows
                    if row["native_voter_turnout"] is not None}
        previously_reported = {(row["year"], row["election_type"])
                               for row in prior.get("complete_native_query", [])
                               if row["native_voter_turnout"] is not None}
        if not previously_reported <= accepted:
            raise ValueError("Wyoming turnout profile dropped a previously published election")
        return {"contract": "participation.wyoming_primary_general_turnout.v1",
                "date": edition, "complete_native_query": rows,
                "participation_observation_qualified": True, "certified_ballots_cast": False,
                "geographic_allocation": False, "registered_turnout_qualified": False}

    return collector.capture(WY_HISTORY_FEED, wy_profile.SOURCE_URL, parse)


def wyoming_history_exports(entry):
    facts = entry["data"]
    rows = facts["complete_native_query"]
    return ({**facts, "state_code": "WY", "status": entry["status"], "source": entry["source"],
             "first_observed_at": entry["first_observed_at"],
             "error_stage": entry.get("error_stage"), "error": entry.get("error")},
            wy_profile.csv_bytes(rows))


def wyoming_precinct_query(pages):
    election = "Wyoming General Election - November 3, 2026"
    if len(pages) != len(WY_COUNTIES) + 2:
        raise ValueError("Incomplete statewide and county precinct ballot tables")
    cover = pages[0].split()
    if cover != "SUMMARY Total Ballots Cast 2026 GENERAL ELECTION".split():
        raise ValueError("Wyoming canvass is not the ballot summary section")

    def lines(page):
        return [" ".join(line.split()) for line in page.splitlines() if line.strip()]

    amount = r"(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)"
    statewide = lines(pages[1])
    total = re.fullmatch(rf"({amount}) ?Total", statewide[-1]) if statewide else None
    expected_header = ["Page 1 of 1", "Statewide Total Ballots Cast", election, "Total Ballots Cast"]
    if statewide[:4] != expected_header or len(statewide) != len(WY_COUNTIES) + 5 or total is None:
        raise ValueError("Changed statewide ballot control table")
    state_ballots = count(total[1])
    rows, controls = [], []
    for county, county_line, page, text in zip(WY_COUNTIES, statewide[4:-1], range(3, 26), pages[2:]):
        control = re.fullmatch(rf"{re.escape(county)} ({amount})", county_line)
        if control is None:
            raise ValueError("Missing or out-of-order statewide county control: " + county)
        expected = rf"{re.escape(county)} County Official Precinct-by[- ]Precinct Total Ballots Summary"
        # Natrona's PDF text layer joins the header and election line.
        local = lines(text.replace("Summary" + election, "Summary\n" + election))
        if (len(local) < 8 or local[0] != "Page 1 of 1" or not re.fullmatch(expected, local[1])
                or local[2:5] != [election, "Total", "Precinct"] or local[-1] != "Total Ballots Cast"
                or not re.fullmatch(amount, local[-2])):
            raise ValueError("Changed precinct ballot table: " + county)
        seen, ballots = set(), 0
        for line in local[5:-2]:
            match = re.fullmatch(rf"([0-9]{{1,2}}-[0-9]{{1,2}}) ({amount})", line)
            if not match:
                raise ValueError("Malformed precinct ballot row: " + county)
            native, value = match[1], count(match[2])
            key = "-".join(str(int(part)) for part in native.split("-"))
            if key in seen:
                raise ValueError("Ambiguous precinct ID: " + county)
            seen.add(key)
            ballots += value
            rows.append({"state_code": "WY", "election_date": "2026-11-03", "county": county,
                         "native_precinct": native, "precinct_key": key, "ballots_cast": value,
                         "pdf_page": page, "registration": None, "turnout_rate": None,
                         "geometry_qualified": False})
        if ballots != count(control[1]) or ballots != count(local[-2]):
            raise ValueError("Precinct and statewide-county ballot controls differ: " + county)
        controls.append({"county": county, "ballots_cast": ballots, "precinct_rows": len(seen),
                         "pdf_page": page})
    if sum(row["ballots_cast"] for row in controls) != state_ballots:
        raise ValueError("County controls do not match the printed state total")
    return {"contract": "participation.wyoming_precinct_ballot_canvass.v1", "state_code": "WY",
            "election_date": "2026-11-03", "participation_observation_qualified": True,
            "source_stage": "official_general_canvass", "geographic_allocation": False,
            "state_ballots_cast": state_ballots, "county_controls": controls,
            "complete_native_query": rows}


def wyoming_precinct_canvass(body):
    from pypdf import PdfReader

    if not body.startswith(b"%PDF-") or len(body) > 10_000_000:
        raise ValueError("Wyoming precinct canvass is not a bounded PDF")
    pdf = PdfReader(io.BytesIO(body), strict=True)
    return wyoming_precinct_query([page.extract_text() for page in pdf.pages[:len(WY_COUNTIES) + 2]])


def collect_wyoming_precinct_canvass(collector):
    def parse(body):
        data = wyoming_precinct_canvass(body)
        prior = (collector.prior.get(WY_CANVASS_FEED) or {}).get("data") or {}
        keys = {(row["county"], row["precinct_key"]) for row in data["complete_native_query"]}
        if any((row["county"], row["precinct_key"]) not in keys for row in prior.get("complete_native_query", [])):
            raise ValueError("Wyoming precinct canvass dropped a previously published unit")
        return data

    return collector.capture(WY_CANVASS_FEED, WY_CANVASS_URL, parse)


def wyoming_precinct_exports(entry):
    data = entry["data"]
    rows = [{**row, "source_url": entry["source"]["url"], "source_sha256": entry["source"]["sha256"],
             "status": entry["status"], "first_observed_at": entry["first_observed_at"]}
            for row in data["complete_native_query"]]
    return ({**data, "status": entry["status"], "source": entry["source"],
             "first_observed_at": entry["first_observed_at"], "error": entry.get("error"),
             "error_stage": entry.get("error_stage")}, wy_profile.csv_bytes(rows))


def virginia_locality_query(rows, clock):
    if (len(rows) != 135 or any(len(row) != 8 for row in rows)
            or tuple(rows[0]) != VA_LOCALITY_HEADER or rows[-1][0] != "Total"):
        raise ValueError("Unexpected Virginia locality turnout table")
    if pin(encoded(sorted(row[0] for row in rows[1:-1])))["sha256"] != VA_LOCALITY_ROSTER:
        raise ValueError("Virginia locality roster differs")
    if not re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2} [AP]M", clock):
        raise ValueError("Missing Virginia turnout report clock")
    edition = datetime.strptime(clock, "%m/%d/%Y %I:%M %p").isoformat()
    if edition[:10] < VA_LOCALITY_DATE:
        raise ValueError("Virginia turnout report predates election")
    fields = ("early_voting", "election_day", "by_mail", "provisional", "ballots_cast", "curbside")
    facts = []
    for row in rows[1:]:
        if row[6] != "":
            raise ValueError("Unexpected Virginia turnout fields")
        values = [integer(row[i]) for i in (1, 2, 3, 4, 5, 7)]
        if sum(values[:4]) != values[4] or values[5] > values[4]:
            raise ValueError("Virginia locality turnout modes do not reconcile")
        facts.append({"county": "TOTAL" if row[0] == "Total" else row[0],
                      "registered": None, **dict(zip(fields, values, strict=True))})
    if any(sum(row[key] for row in facts[:-1]) != facts[-1][key] for key in fields):
        raise ValueError("Virginia localities do not reconcile to the printed state control")
    return {"native_rows": [list(row) for row in rows], "native_clock": clock, "edition": edition,
            "counties": facts[:-1], "total": facts[-1], "registration_basis": None,
            "report_note": "Official turnout by county and independent city. Curbside is already included. "
                           "A compatible registration denominator is not in this report.",
            "extraction_method": "statewide_locality_turnout_html"}


def virginia_locality_report(body, election):
    text = body.decode("utf-8-sig")
    clocks = re.findall(r'<p class="asOf">Page generated on ([^<]+)</p>', text)
    if (election != VA_LOCALITY_DATE or len(clocks) != 1
            or re.findall(r"<title>\s*([^<]+?)\s*</title>", text) != ["2022 November General"]
            or '<h2 class="entry-title">Official Results</h2>' not in text
            or "Curbside numbers are included in the Total." not in text):
        raise ValueError("Virginia official general-election turnout identity differs")
    tables = [rows for rows in html_tables(body) if rows and rows[0] == VA_LOCALITY_HEADER]
    if len(tables) != 1:
        raise ValueError("Missing or repeated Virginia turnout table")
    return virginia_locality_query(tables[0], clocks[0])


def collect_county_archive(collector, feed, *, reuse_checked_week=False):
    current = feed == CA_CURRENT_FEED
    state, election = ("CA", CA_CURRENT_ELECTION) if current else COUNTY_ARCHIVES[feed]
    index_url, report_pattern = county_archive_routes(state, election)
    old = collector.prior.get(feed) or {}
    checked_week = None
    if not collector.offline and int(election[:4]) < CURRENT_YEAR:
        day = collector.now.astimezone(timezone.utc).date()
        checked_week = (day - timedelta(days=day.weekday())).isoformat()
        if (reuse_checked_week and old.get("archive_check_week_utc") == checked_week
                and old.get("status") == "reported" and old.get("data") is not None):
            return old
    rejected_scan = old.get("rejected_scan")

    def parse(index):
        nonlocal rejected_scan
        if state == "MN":
            report = {"url": index_url, **pin(index)}
            previous = old.get("data")
            if previous and previous.get("report") == report:
                return previous
            query = minnesota_precinct_history.parse(index, election)
            return {"election_date": election, "report": report, "complete_native_query": query,
                    "participation_observation_qualified": False}
        if state == "VA":
            query = virginia_locality_report(index, election)
            return {"election_date": election, "date": query["edition"],
                    "report": {"url": index_url, **pin(index)},
                    "complete_native_query": query, "participation_observation_qualified": False}
        if state == "CO":
            url = colorado_voting_statistics.discover(index, election)
        elif current:
            url = archive_link(index, index_url, report_pattern,
                               label=r"November 3, 2026\s*[-–]\s*General Election \(PDF\)")
        elif state == "NE" and election == nebraska_canvass.CURRENT:
            url = archive_link(index, index_url, report_pattern, label="General Election Official Results")
        else:
            url = archive_link(index, index_url, report_pattern)
        if url is None:
            raise IntakeError("report_not_linked", f"No {feed} report linked in the official archive")
        body, _ = collector.acquire(url)
        if not 0 < len(body) <= county_archive_limit(state):
            raise ValueError("Historical county report exceeds reviewed size bound")
        report = {"url": url, **pin(body)}
        previous = old.get("data")
        supporting_report = None
        if state == "NE" and election == nebraska_canvass.PAIRED_ELECTION:
            supporting, _ = collector.acquire(nebraska_canvass.BLUE_BOOK)
            if not 0 < len(supporting) <= county_archive_limit(state):
                raise ValueError("Nebraska Blue Book exceeds reviewed size bound")
            supporting_report = {"url": nebraska_canvass.BLUE_BOOK, **pin(supporting)}
        if previous and previous.get("report") == report and previous.get("supporting_report") == supporting_report:
            rejected_scan = None
            return previous
        if state == "CO":
            query = colorado_voting_statistics.parse(body, election)
        elif state == "CA":
            query = (california_scan(report, election) if election in CA_SCAN_DATES
                     else california_report(body, election))
        elif state == "KS":
            query = kansas_workbook(body)
        elif state == "WV":
            query = west_virginia_archive_report(body, election)
        elif state == "WY":
            query = wyoming_archive_report(body, election)
        elif supporting_report:
            query = nebraska_canvass.parse_blue_book(supporting, body)
        elif state == "NE":
            scan_key = ({"report": report, "policy": nebraska_canvass.scan_policy(election)}
                        if election in nebraska_canvass.SCANS else None)
            if scan_key and rejected_scan and rejected_scan["key"] == scan_key:
                raise IntakeError("scan_reconciliation_failed", rejected_scan["detail"])
            try:
                query = nebraska_canvass.parse(body, election)
            except IntakeError as error:
                if scan_key and error.code == "scan_reconciliation_failed":
                    rejected_scan = {"key": scan_key, "detail": str(error)}
                raise
            rejected_scan = None
        else:
            query = new_jersey_report(body, election, allow_amended=True)
        data = {"election_date": election, "report": report, "complete_native_query": query,
                "participation_observation_qualified": False}
        if supporting_report:
            data["supporting_report"] = supporting_report
        if state == "NJ":
            data["date"] = query["published_date"]
        return data

    result = collector.capture(feed, index_url, parse, equivalent=lambda old, new: old == new,
                               shared_acquisition=True)
    if checked_week is not None:
        result["archive_check_week_utc"] = checked_week
    if rejected_scan is None:
        result.pop("rejected_scan", None)
    else:
        result["rejected_scan"] = rejected_scan
    return result


def county_archive_limit(state):
    if state == "MN":
        return minnesota_precinct_history.MAX_BYTES
    return nebraska_canvass.MAX_BYTES if state == "NE" else 2_000_000


def county_archive_originals(entries):
    originals = {}
    for feed, (state, election) in sorted(COUNTY_ARCHIVES.items()):
        data = (entries.get(feed) or {}).get("data")
        if state not in ("CO", "MN", "NE", "VA", "WV", "WY") or data is None:
            continue
        report = data["report"]
        _, pattern = county_archive_routes(state, election)
        if (data["election_date"] != election or not re.fullmatch(pattern, report["url"])
                or type(report["bytes"]) is not int or not 0 < report["bytes"] <= county_archive_limit(state)
                or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])):
            raise ValueError(f"Invalid original county report pin: {feed}")
        originals[feed] = {"filename": feed + {"CO": ".csv", "MN": ".xlsx", "VA": ".html"}.get(state, ".pdf"),
                           **{key: report[key] for key in ("url", "bytes", "sha256")}}
        if state == "NE" and election == nebraska_canvass.PAIRED_ELECTION:
            supporting = data["supporting_report"]
            if (supporting["url"] != nebraska_canvass.BLUE_BOOK
                    or type(supporting["bytes"]) is not int or not 0 < supporting["bytes"] <= county_archive_limit(state)
                    or not re.fullmatch(r"[a-f0-9]{64}", supporting["sha256"])):
                raise ValueError(f"Invalid supporting county report pin: {feed}")
            extra = feed + "-blue-book"
            originals[extra] = {"filename": extra + ".pdf", **supporting}
    for row in nebraska_county_reports.rows(entries):
        if "source_url" in row:
            identity = nebraska_county_reports.FEED + "-" + row["county"].replace(" ", "-")
            originals[identity] = {"filename": identity + ".pdf", "url": row["source_url"],
                                   "bytes": row["source_bytes"], "sha256": row["source_sha256"]}
    return originals


def nebraska_canvass_original_matches(extracted, retained, election):
    if election not in nebraska_canvass.SCANS:
        return extracted == retained
    if any(nebraska_canvass.replay_query(facts, election) != facts for facts in (extracted, retained)):
        return False

    def literal_facts(facts):
        evidence = facts["scan_evidence"]
        # Confidence flags and OCR line ordinals can vary after an independently valid extraction.
        tables = {
            table: [[{**view, "rows": [
                {key: value for key, value in row.items() if key not in ("high_confidence", "row")}
                for row in view["rows"]]} for view in pair] for pair in panels]
            for table, panels in evidence["tables"].items()
        }
        return {**facts, "scan_evidence": {**evidence, "tables": tables}}

    return literal_facts(extracted) == literal_facts(retained)


def nebraska_county_original_matches(extracted, retained, county, status):
    if "scan_evidence" not in extracted or "scan_evidence" not in retained:
        return extracted == retained

    def literal_facts(facts):
        evidence = facts["scan_evidence"]
        counts = {key: value for key, value in facts.items() if key != "scan_evidence"}
        if nebraska_county_reports.scan_query(evidence, county, status) != counts:
            raise ValueError("County scan evidence differs from its stored facts")
        # Compare independently admitted scans, preserving cell boundaries and all non-space characters.
        views = [{**{key: value for key, value in view.items() if key != "high_confidence"}, "cells": [
            [re.sub(r"\s+", "", cell) for cell in row] for row in view["cells"]]} for view in evidence]
        return counts, views

    return literal_facts(extracted) == literal_facts(retained)


def verify_county_archive_originals(entries, directory):
    originals = county_archive_originals(entries)
    if not originals:
        raise ValueError("This checkpoint contains no supported county report originals to verify")
    def checked_original(feed):
        report = originals[feed]
        path = directory / report["filename"]
        with path.open("rb") as source:
            body = source.read(report["bytes"] + 1)
        if pin(body) != {key: report[key] for key in ("bytes", "sha256")}:
            raise ValueError(f"Changed original county report: {feed}")
        return body

    for feed in originals.keys() & COUNTY_ARCHIVES.keys():
        body = checked_original(feed)
        state, election = COUNTY_ARCHIVES[feed]
        parse = {"VA": virginia_locality_report, "WV": west_virginia_archive_report, "WY": wyoming_archive_report,
                 "NE": nebraska_canvass.parse, "CO": colorado_voting_statistics.parse,
                 "MN": minnesota_precinct_history.parse}[state]
        query = (nebraska_canvass.parse_blue_book(checked_original(feed + "-blue-book"), body)
                 if state == "NE" and election == nebraska_canvass.PAIRED_ELECTION else parse(body, election))
        retained = entries[feed]["data"]["complete_native_query"]
        if not (nebraska_canvass_original_matches(query, retained, election) if state == "NE"
                else query == retained):
            raise ValueError(f"County report extraction differs from the accepted query: {feed}")
    for county, item in (entries.get(nebraska_county_reports.FEED, {}).get("data") or {}).get("counties", {}).items():
        if accepted := item["accepted"]:
            identity = nebraska_county_reports.FEED + "-" + county.replace(" ", "-")
            status = accepted["report"]["status"]
            query = nebraska_county_reports.extract(checked_original(identity), county, status)
            if not nebraska_county_original_matches(query, accepted["facts"], county, status):
                raise ValueError(f"County report extraction differs from the accepted query: {identity}")
    return len(originals)


def county_archive_rows(entries, *, current_california=False, current_nebraska=False,
                        colorado_precincts=False, minnesota_precincts=False):
    rows = []
    if current_california:
        declarations = {CA_CURRENT_FEED: ("CA", CA_CURRENT_ELECTION)}
    elif current_nebraska:
        declarations = {nebraska_canvass.CURRENT_FEED: ("NE", nebraska_canvass.CURRENT)}
    elif colorado_precincts:
        declarations = {key: value for key, value in COUNTY_ARCHIVES.items() if value[0] == "CO"}
    elif minnesota_precincts:
        declarations = {key: value for key, value in COUNTY_ARCHIVES.items() if value[0] == "MN"}
    else:
        declarations = {key: value for key, value in COUNTY_ARCHIVES.items() if key != nebraska_canvass.CURRENT_FEED}
    for feed, (state, election) in sorted(declarations.items()):
        entry = entries.get(feed, {})
        data = entry.get("data")
        if data is None:
            continue
        year = int(election[:4])
        index, pattern = county_archive_routes(state, election)
        report, query = data["report"], data["complete_native_query"]
        source = entry.get("source") or {}
        if (data["election_date"] != election or entry["status"] not in ("reported", "retained_after_failure")
                or data["participation_observation_qualified"] is not False
                or source.get("url") != index or not re.fullmatch(pattern, report["url"])
                or type(report["bytes"]) is not int or not 0 < report["bytes"] <= county_archive_limit(state)
                or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])):
            raise ValueError("Invalid historical county report binding")
        if state == "CO":
            if query != colorado_voting_statistics.query(query["native_rows"], election):
                raise ValueError("Colorado turnout differs from its retained source rows")
            count_only = query["registration_basis"] is None
            registration_hold = query.get("registration_hold", colorado_voting_statistics.REGISTRATION_HOLD)
            if colorado_precincts:
                for county, units in query["precincts"].items():
                    shortfall = query.get("county_ballot_shortfalls", {}).get(county)
                    for unit in units:
                        n, d = unit["ballots_cast"], unit.get("registered")
                        hold = (registration_hold if count_only else
                                "county_ballot_control_disagrees" if shortfall else
                                "ballots_exceed_registered" if n > d else
                                "no_positive_registration_denominator" if not d else None)
                        if count_only:
                            unit = {**unit, **dict.fromkeys(("registered", "active", "inactive"))}
                        rows.append({"state_code": "CO", "election_date": election, "county": county, **unit,
                                     "registration_basis": query["registration_basis"],
                                     "qualified_same_report_registration_fraction_pct": None if hold else 100 * n / d,
                                     "rate_hold_reason": hold, "source_status": entry["status"],
                                     **({"county_ballot_shortfall": shortfall} if shortfall else {}),
                                     "source_url": report["url"], "source_sha256": report["sha256"],
                                     "source_bytes": report["bytes"]})
                continue
            counties = [*query["counties"], query["total"]]
            if query.get("state_ballot_shortfall"):
                counties[-1] = {**counties[-1], "state_ballot_shortfall": query["state_ballot_shortfall"],
                                "rate_hold_reason": "state_ballot_control_disagrees"}
            counties = [{**row, "county_ballot_shortfall": query["county_ballot_shortfalls"][row["county"]]}
                        if row["county"] in query.get("county_ballot_shortfalls", {}) else row for row in counties]
            if count_only:
                counties = [{**row, "registered": None, "rate_hold_reason": registration_hold}
                            for row in counties]
            county_conflict = not count_only and any(row["ballots_cast"] > row["registered"] for row in counties[:-1])
        elif state == "MN":
            if (query != minnesota_precinct_history.query(
                    query["fields"], query["precincts"], query["county_roster"], query["printed_total"], election)
                    or any(source.get(field) != report[field] for field in ("bytes", "sha256"))):
                raise ValueError("Minnesota turnout differs from its retained source rows")
            if minnesota_precincts:
                for unit in query["precincts"]:
                    rows.append({
                        "state_code": state, "election_date": election, "county": unit["COUNTYNAME"],
                        "county_geoid": unit["VTDID"][:5], "precinct_id": unit["VTDID"],
                        "precinct_name": unit["PCTNAME"], "municipality": unit["MCDNAME"],
                        "reported_total_voters": unit["TOTVOTING"], "registered_at_7am": unit["REG7AM"],
                        "same_day_registrations": unit["EDR"],
                        "reported_roster_signatures": unit["SIGNATURES"],
                        "reported_accepted_absentee_mail": unit["AB_MB"],
                        "reported_federal_only_absentee": unit["FEDONLYAB"],
                        "reported_presidential_only_absentee": unit.get("PRESONLYAB"),
                        "registration_basis": query["registration_basis"],
                        "rate_hold_reason": minnesota_precinct_history.RATE_HOLD,
                        "source_id": feed, "source_status": entry["status"], "source_url": report["url"],
                        "source_sha256": report["sha256"], "source_bytes": report["bytes"],
                    })
                continue
            counties = [*query["counties"], query["total"]]
            county_conflict = False
        elif state == "KS":
            kansas_controls(query, allow_county_conflicts=True)
            counties = [{"county": name, "advance_ballots_returned_by_mail": mail,
                         "ballots_cast": ballots, "registered": registered}
                        for name, mail, ballots, registered in [*query["counties"], ["TOTAL", *query["total"]]]]
            county_conflict = any(row["ballots_cast"] > row["registered"] for row in counties[:-1])
        elif state == "CA":
            california_controls(query, election)
            if election in CA_SCAN_DATES and query != california_scan(report, election):
                raise ValueError("California scan query differs from its reviewed transcription")
            counties = [*query["counties"], query["total"]]
            county_conflict = False
        elif state == "VA":
            if (query != virginia_locality_query(query["native_rows"], query["native_clock"])
                    or query["edition"] != data.get("date")
                    or any(source.get(field) != report[field] for field in ("bytes", "sha256"))):
                raise ValueError("Virginia locality turnout differs from its retained source rows")
            counties = [*query["counties"], query["total"]]
            county_conflict = False
        elif state == "WV":
            if query != west_virginia_archive_query(query["native_lines"], election):
                raise ValueError("West Virginia turnout differs from its retained source rows")
            counties = [*query["counties"], query["total"]]
            county_conflict = False
        elif state == "WY":
            if query != wyoming_archive_query(query["native_lines"], election):
                raise ValueError("Wyoming turnout differs from its retained source rows")
            counties = [*query["counties"], query["total"]]
            county_conflict = False
        elif state == "NE":
            if query != nebraska_canvass.replay_query(query, election):
                raise ValueError("Nebraska turnout differs from its retained source rows")
            counties = [*query["counties"], query["total"]]
            county_conflict = any(row["ballots_cast"] > row["registered"] for row in counties[:-1])
        else:
            new_jersey_controls(query, election)
            if data.get("date") != query["published_date"]:
                raise ValueError("New Jersey historical report edition differs")
            counties = [*query["counties"], query["total"]]
            county_conflict = False
        for native in counties:
            county, registered, ballots = native["county"], native["registered"], native["ballots_cast"]
            statewide = county == "TOTAL"
            hold = ("county_conflict_included_in_statewide_total" if statewide and county_conflict
                    else (native.get("rate_hold_reason") or "registration_not_in_report") if registered is None
                    else "ballots_exceed_registered" if ballots > registered
                    else "no_positive_registration_denominator" if not registered else native.get("rate_hold_reason"))
            if state == "CA" and not hold and (
                    (Decimal(ballots) * 100 / registered).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
                    != Decimal(native["printed_registered_percent"][:-1])):
                hold = "printed_registration_fraction_disagrees"
            if state == "WV" and not hold and (
                    (Decimal(ballots) * 100 / registered).quantize(Decimal(".1"), rounding=ROUND_HALF_UP)
                    != Decimal(native["printed_percent"][:-1])):
                hold = "printed_registration_fraction_disagrees"
            if current_california and not hold and query["registration_basis"] != CA_REGISTRATION_NOTE:
                hold = "registration_timing_unqualified"
            measure = query.get("native_numerator", "ballots_cast")
            vap_basis = query.get("secondary_denominator") == "voting_age_population"
            rows.append({
                "state_code": state, "year": year, "election_date": election,
                "election_type": "off_year_general" if year % 2 else "presidential" if year % 4 == 0 else "midterm",
                "geography_level": ("state" if statewide else "county_equivalent"
                                    if state == "VA" and county.endswith(" CITY") else "county"),
                "geography": {"CO": "Colorado", "KS": "Kansas", "MN": "Minnesota", "NE": "Nebraska", "NJ": "New Jersey", "CA": "California", "WV": "West Virginia",
                              "VA": "Virginia", "WY": "Wyoming"}[state]
                if statewide else county,
                "reported_ballots_cast": ballots if measure == "ballots_cast" else None,
                "reported_total_voters": ballots if measure == "total_voters" else None,
                **({"reported_voter_history_credits": ballots} if measure == "voter_history_credits" else {}),
                "participation_measure": measure,
                "reported_registered_voters": registered,
                "registration_basis": query.get("registration_basis", "Report's registered voters"),
                "reported_eligible_to_register": None if vap_basis else native.get("eligible"),
                "reported_turnout_eligible_pct": None if vap_basis else native.get("printed_eligible_percent"),
                "reported_voting_age_population": native.get("eligible") if vap_basis else None,
                "reported_turnout_vap_pct": native.get("printed_eligible_percent") if vap_basis else None,
                "reported_precinct_voters": native.get("precinct_voters"),
                "reported_mail_voters": native.get("mail_voters"),
                "qualified_same_report_registration_fraction_pct": None if hold else 100 * ballots / registered,
                "rate_hold_reason": hold,
                **{field: native[field] for field in ("state_ballot_shortfall", "county_ballot_shortfall")
                   if field in native},
                **{"reported_" + field: native[field] for field in
                   ("early_voting", "election_day", "by_mail", "provisional", "curbside") if state == "VA"},
                **{field: native[field] for field in ("registered_at_7am", "same_day_registrations")
                   if field in native},
                "advance_ballots_returned_by_mail": native.get("advance_ballots_returned_by_mail"),
                "reported_ballots_rejected": native.get("ballots_rejected"),
                "reported_turnout_pct": native.get("printed_registered_percent", native.get("printed_percent")),
                "reported_election_districts": native.get("election_districts"),
                "source_id": feed, "source_status": entry["status"], "report_edition": data.get("date"),
                "report_note": query.get("report_note"), "extraction_method": query.get("extraction_method"),
                "amended_county": query.get("amendment", {}).get("county"),
                "original_certification_date": query.get("amendment", {}).get("original_certification_date"),
                "source_url": report["url"], "source_sha256": report["sha256"], "source_bytes": report["bytes"],
            })
    return rows


def buxton_controls(data):
    source, query = data["report"], data["complete_native_query"]
    if (source["url"] != BUXTON_URL or type(source["bytes"]) is not int or source["bytes"] <= 0
            or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            or query["heading"] != BUXTON_TITLE or len(query["statistics"]) != len(BUXTON_FIELDS)):
        raise ValueError("Buxton town election identity or source receipt changed")
    values = []
    for label, line in zip(BUXTON_FIELDS, query["statistics"]):
        number = r"[0-9]+\.[0-9]{2}%" if label == BUXTON_FIELDS[-1] else r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)"
        match = re.fullmatch(f"({number}) {label}", line)
        if not match:
            raise ValueError("Buxton town statistic missing or changed: " + label)
        values.append(match[1])
    registered, absentee, in_person, ballots = (int(value.replace(",", "")) for value in values[:-1])
    pct = values[-1]
    if (not registered or ballots > registered or absentee + in_person != ballots
            or (Decimal(ballots) * 100 / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(pct[:-1])):
        raise ValueError("Buxton town ballot components, register or printed rate disagree")
    return ballots, registered, pct


def buxton_report(body):
    class Blocks(HTMLParser):
        inside = False
        text = None
        tag = None

        def __init__(self):
            super().__init__()
            self.blocks = []

        def handle_starttag(self, tag, attrs):
            if tag == "article":
                self.inside = True
            if self.inside and tag in {"h2", "p"}:
                self.tag, self.text = tag, []

        def handle_data(self, text):
            if self.text is not None:
                self.text.append(text)

        def handle_endtag(self, tag):
            if tag == self.tag:
                self.blocks.append((tag, " ".join("".join(self.text).split())))
                self.tag = self.text = None
            if tag == "article":
                self.inside = False

    parser = Blocks()
    parser.feed(body.decode("utf-8-sig"))
    headings = [i for i, block in enumerate(parser.blocks) if block == ("h2", BUXTON_TITLE)]
    if len(headings) != 1:
        raise ValueError("Missing or repeated Buxton state-and-town election heading")
    start = headings[0] + 1
    fields = parser.blocks[start:start + 6]
    if not fields or fields[-1] != ("p", "State of Maine General Election") or any(
            tag != "p" for tag, _ in fields):
        raise ValueError("Buxton turnout is not in the reviewed pre-contest section")
    data = {"report": {"url": BUXTON_URL, **pin(body)}, "complete_native_query": {
        "heading": BUXTON_TITLE, "statistics": [text for _, text in fields[:-1]]}}
    buxton_controls(data)
    return data


def collect_buxton(collector):
    return collector.capture(BUXTON_FEED, BUXTON_URL, buxton_report)


def bath_declared_report(body):
    class Links(HTMLParser):
        href = None

        def __init__(self):
            super().__init__()
            self.matches = []
            self.parts = []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.href = dict(attrs).get("href")
                self.parts = []

        def handle_data(self, text):
            if self.href:
                self.parts.append(text)

        def handle_endtag(self, tag):
            if tag == "a" and self.href:
                label = " ".join("".join(self.parts).split())
                if re.fullmatch(r"2026 Preliminary Election Results(?:\s*\(PDF, [0-9,]+\s*KB\))?", label):
                    self.matches.append(urljoin(BATH_INDEX, self.href))
                self.href = None

    parser = Links()
    parser.feed(body.decode("utf-8-sig"))
    if parser.matches != [BATH_PDF]:
        raise ValueError("Bath preliminary general-election report declaration missing or changed")
    return parser.matches[0]


def bath_controls(data):
    source, query = data["report"], data["complete_native_query"]
    if (source["url"] != BATH_PDF or type(source["bytes"]) is not int or source["bytes"] <= 0
            or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            or query["state_heading"] != ["STATE GENERAL ELECTION TOTALS", "November 3, 2026"]
            or query["municipal_heading"] != ["CITY OF BATH ELECTION TOTALS", "November 3, 2026"]):
        raise ValueError("Bath municipal general-election identity or receipt changed")
    match = BATH_STATISTICS.fullmatch(query["statistics"])
    if not match:
        raise ValueError("Bath report does not supply a separate municipal turnout total")
    ballots, registered = map(integer, match.groups()[:2])
    pct = match[3]
    if (not registered or ballots > registered or
            (Decimal(ballots) * 100 / registered).quantize(
                Decimal(".1"), rounding=ROUND_HALF_UP) != Decimal(pct[:-1])):
        raise ValueError("Bath municipal register or printed rate disagrees")
    return ballots, registered, pct


def bath_report(body):
    from pypdf import PdfReader

    if not body.startswith(b"%PDF-") or len(body) > 2_000_000:
        raise ValueError("Unexpected Bath turnout PDF")
    pdf = PdfReader(io.BytesIO(body))
    if len(pdf.pages) != 2:
        raise ValueError("Bath report page inventory changed")
    first, second = ([" ".join(line.split()) for line in page.extract_text().splitlines() if line.strip()]
                     for page in pdf.pages)
    if not first or sum(bool(BATH_STATISTICS.fullmatch(line)) for line in first + second) != 1:
        raise ValueError("Missing or repeated Bath municipal turnout totals")
    data = {"report": {"url": BATH_PDF, **pin(body)}, "complete_native_query": {
        "state_heading": first[:2], "municipal_heading": second[:2], "statistics": first[-1]}}
    bath_controls(data)
    return data


def bath_edition(value):
    if not isinstance(value, str):
        return None
    try:
        date = parsedate_to_datetime(value)
    except ValueError:
        return None
    return date if date.tzinfo is not None else None


def bath_precedes(old, new):
    old_edition, new_edition = (bath_edition(item.get("report_http_last_modified")) for item in (old, new))
    return old_edition is not None and new_edition is not None and new_edition > old_edition


def collect_bath(collector):
    def parse(body):
        url = bath_declared_report(body)
        report, _ = collector.acquire(url)
        data = bath_report(report)
        edition = collector.public_edition(url)
        if edition["body_sha256"] != data["report"]["sha256"]:
            raise ValueError("Bath PDF and HTTP edition receipt disagree")
        data["report_http_last_modified"] = edition["http_last_modified"]
        previous = (collector.prior.get(BATH_FEED) or {}).get("data")
        if previous and bath_controls(previous) != bath_controls(data) and not bath_precedes(previous, data):
            raise ValueError("Changed Bath counts lack a newer ordered HTTP edition of the same official report")
        return data

    return collector.capture(BATH_FEED, BATH_INDEX, parse, equivalent=lambda old, new:
                             bath_controls(old) == bath_controls(new) and not bath_precedes(old, new))


def votingworks_controls(data, town, report_url):
    source = data["report"]
    query = data["complete_native_query"]
    if (source["url"] != report_url or type(source["bytes"]) is not int or source["bytes"] <= 0
            or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            or query["title"] != "Official Tally Report"
            or query["election"] != f"General Election, Nov 3, 2026, {town}, NH"):
        raise ValueError("VotingWorks report authority or election differs")
    generated = datetime.strptime(query["generated"], "%b %d, %Y, %I:%M:%S %p")
    if (generated.date() < datetime(2026, 11, 3).date()
            or not re.fullmatch(r"[0-9a-f]{7}-[0-9a-f]{7}", query["election_id"])):
        raise ValueError("VotingWorks report generation or election ID differs")
    values = []
    for label, line in zip(("Ballot Count", "Scanned", "Manually Entered"), query["statistics"]):
        match = re.fullmatch(rf"{label} (0|[1-9]\d{{0,2}}(?:,\d{{3}})*|[1-9]\d{{3,}})", line, re.ASCII)
        if not match:
            raise ValueError("VotingWorks report-level ballot table differs")
        values.append(int(match[1].replace(",", "")))
    if len(query["statistics"]) != 3 or len(values) != 3 or values[0] != sum(values[1:]):
        raise ValueError("VotingWorks report-level ballot components do not reconcile")
    return tuple(values), generated


def votingworks_report(body, town, report_url):
    from pypdf import PdfReader

    pdf = PdfReader(io.BytesIO(body), strict=True)
    if not pdf.pages:
        raise ValueError("Missing VotingWorks title page")
    lines = [" ".join(line.split()) for line in
             unicodedata.normalize("NFKC", pdf.pages[0].extract_text()).splitlines() if line.strip()]
    if (len(lines) < 8 or not lines[3].startswith("Certification Signatures:")
            or any(re.search(r"\b(?:scanner|batch)\s+(?:id|number|report|tally)\b", line, re.I)
                   for line in lines[:7])
            or sum(line.startswith("Ballot Count ") for line in lines) != 1):
        raise ValueError("Missing VotingWorks whole-town report header or ballot table")
    meta = re.fullmatch(r"Report Generated: (.+?)\s*Election ID: ([0-9a-f-]+)", lines[2])
    if not meta:
        raise ValueError("Missing VotingWorks report metadata")
    data = {"report": {"url": report_url, **pin(body)}, "complete_native_query": {
        "title": lines[0], "election": lines[1], "generated": meta[1], "election_id": meta[2],
        "statistics": lines[4:7]}}
    votingworks_controls(data, town, report_url)
    return data


def votingworks_successor(old, new, town, report_url):
    previous, previous_edition = votingworks_controls(old, town, old["report"]["url"])
    current, current_edition = votingworks_controls(new, town, report_url)
    if (old["complete_native_query"]["election_id"] != new["complete_native_query"]["election_id"]
            or current_edition < previous_edition
            or (current != previous and current_edition == previous_edition)):
        raise ValueError("VotingWorks election identity or report edition regressed or conflicts")
    return (previous == current and previous_edition == current_edition
            and old["report"]["url"] == report_url)


def votingworks_town_controls(data, profile):
    url = data["report"]["url"]
    if not profile.permits_report(url) or data["complete_native_query"]["election_id"] != profile.election_id:
        raise ValueError("VotingWorks town report route or reviewed election ID differs")
    return votingworks_controls(data, profile.town, url)


def votingworks_declared_report(body, profile):
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.matches = []
            self.href = None
            self.parts = []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.href = dict(attrs).get("href")
                self.parts = []

        def handle_data(self, text):
            if self.href:
                self.parts.append(text)

        def handle_endtag(self, tag):
            if tag == "a" and self.href:
                url = urljoin(profile.index, self.href)
                if profile.permits_report(url) and " ".join("".join(self.parts).split()) == profile.link_label:
                    self.matches.append(url)
                self.href = None

    parser = Links()
    parser.feed(body.decode("utf-8-sig"))
    if len(parser.matches) != 1:
        raise ValueError(f"{profile.town} general-election report declaration missing or ambiguous")
    return parser.matches[0]


def collect_votingworks_town(collector, profile):
    def parse(body):
        report_url = votingworks_declared_report(body, profile)
        report, _ = collector.acquire(report_url)
        data = votingworks_report(report, profile.town, report_url)
        votingworks_town_controls(data, profile)
        return data

    def equivalent(old, new):
        votingworks_town_controls(old, profile)
        return votingworks_successor(old, new, profile.town, new["report"]["url"])

    return collector.capture(profile.feed, profile.index, parse, equivalent=equivalent)


def municipal_feeds():
    return {
        BUXTON_FEED: ("ME", collect_buxton),
        BATH_FEED: ("ME", collect_bath),
        **{town.feed: ("NH", partial(collect_votingworks_town, profile=town))
           for town in VOTINGWORKS_TOWNS.values()},
    }


def ohio_election(body):
    if len(body) > 15_000_000 or re.search(r"<!DOCTYPE|<!ENTITY", body.decode("utf-8-sig"), re.I):
        raise ValueError("Ohio election XML exceeds reviewed document bounds")
    root = ET.fromstring(body)
    elections = root.findall("n:Election", OH_NS)
    if len(elections) != 1 or elections[0].attrib != {"Date": "2026-11-03", "Type": "General"}:
        raise ValueError("Ohio election XML does not declare the November 2026 general election")
    title = elections[0].findtext("n:Name/n:LanguageString", namespaces=OH_NS)
    clock = root.get("GeneratedDate")
    status = root.get("Status")
    if (root.tag != f"{{{OH_NS['n']}}}ElectionReport"
            or root.get("IssuerAbbreviation") != "OH"
            or status not in {"UnofficialComplete", "UnofficialPartial"}
            or title != "November 3, 2026 General Unofficial Canvass"
            or not re.fullmatch(r"202[67]-\d\d-\d\dT\d\d:\d\d:\d\dZ", clock or "")
            or datetime.strptime(clock, "%Y-%m-%dT%H:%M:%SZ").date().isoformat() < "2026-11-03"):
        raise ValueError("Ohio election XML issuer, status or report clock changed")
    rows = [[unit.get("ObjectId"), unit.get("Name"),
             *[integer(unit.get(field, "")) for field in OH_XML_FIELDS]]
            for unit in root.findall("n:GpUnitCollection/n:GpUnit", OH_NS)
            if unit.get("Type") == "County" and unit.get("IsElectoralDistrict") == "false"]
    return {"source": {"url": OH_ELECTION, **pin(body)}, "date": "2026-11-03",
            "title": title, "status": status, "generated_at": clock, "counties": rows}


def ohio_controls(query):
    rows, total, control = query["counties"], query["total"], query["election"]
    derived = query.get("basis") == "dated_xml_county_sum"
    if (len(rows) != 88 or len({row[0] for row in rows}) != 88
            or any(not isinstance(row[1], str) for row in rows)
            or pin(encoded(sorted(row[1] for row in rows))) != OH_COUNTY_NAMES
            or total[:2] != [None, "County sum" if derived else "Totals"] or len(total) != 9
            or len(control["counties"]) != 88
            or control["source"]["url"] != OH_ELECTION or control["source"]["bytes"] <= 0
            or not re.fullmatch(r"[a-f0-9]{64}", control["source"]["sha256"])
            or control["date"] != "2026-11-03"
            or control["title"] != "November 3, 2026 General Unofficial Canvass"
            or control["status"] not in {"UnofficialComplete", "UnofficialPartial"}
            or sorted(row[:6] for row in rows) != sorted(control["counties"])):
        raise ValueError("Ohio ballot county frame is not reconciled to its dated XML")
    for row in rows + [total]:
        ballots, registered, reported, units, absentee, provisional = row[2:8]
        if (len(row) != 9 or any(type(n) is not int or n < 0 for n in row[2:6])
                or not registered or ballots > registered or not 0 <= reported <= units
                or (derived and (absentee, provisional, row[8]) != (None, None, None))
                or (not derived and (any(type(n) is not int or n < 0 for n in (absentee, provisional))
                    or not re.fullmatch(r"[0-9]+\.[0-9]{2}", row[8])
                    or (Decimal(ballots) * 100 / registered).quantize(
                        Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(row[8])))):
            raise ValueError("Ohio turnout count, denominator or reported fraction changed")
    stop = 6 if derived else 8
    if [sum(row[n] for row in rows) for n in range(2, stop)] != total[2:stop]:
        raise ValueError("Ohio county totals do not reconcile to the printed statewide rows")
    return total[2], total[3]


def ohio_ballots(body, control):
    entries = json.loads(body)
    if len(entries) != 90:
        raise ValueError("Ohio ballot table inventory changed")
    rows = [[entry["objectId"], entry["name"],
             *[integer(entry[field]) for field in OH_FIELDS], entry["ballotCastPercent"]]
            for entry in entries]
    if rows[0] != rows[-1]:
        raise ValueError("Ohio's two printed statewide totals disagree")
    query = {"counties": rows[1:-1], "total": rows[0], "election": control}
    ohio_controls(query)
    return query


def collect_ohio(collector):
    def parse_xml(body):
        control = ohio_election(body)
        rows = [row + [None, None, None] for row in control["counties"]]
        total = [None, "County sum", *[sum(row[i] for row in rows) for i in range(2, 6)],
                 None, None, None]
        query = {"basis": "dated_xml_county_sum", "counties": rows, "total": total, "election": control}
        ohio_controls(query)
        return {"report": control["source"], "complete_native_query": query,
                "date": control["generated_at"], "participation_observation_qualified": False}

    def stopped():
        try:
            collector.guard(OH_BALLOTS)
        except IntakeError as error:
            if error.code == "source_stopped":
                return True
            raise
        return False

    def parse(body):
        control, _ = collector.acquire(OH_ELECTION)
        query = ohio_ballots(body, ohio_election(control))
        return {"report": {"url": OH_BALLOTS, **pin(body)}, "complete_native_query": query,
                "date": query["election"]["generated_at"], "participation_observation_qualified": False}

    previous = collector.prior.get(OH_FEED) or {}
    keep_direct = (previous.get("source") or {}).get("url") == OH_BALLOTS
    if stopped() and not keep_direct:
        return collector.capture(OH_FEED, OH_ELECTION, parse_xml)
    result = collector.capture(OH_FEED, OH_BALLOTS, parse)
    if not keep_direct and result["status"] != "reported" and stopped():
        return collector.capture(OH_FEED, OH_ELECTION, parse_xml)
    return result


def montana_controls(query):
    turnout, registered = query["total_turnout"], query["registered_voters"]
    fully, partial, missing = query["precincts"]
    printed = query["printed_rate"]
    clock = datetime.strptime(query["clock"], "%m/%d/%Y %I:%M:%S %p MT")
    if (query["election"] != MT_TITLE or clock.date().isoformat() < "2026-11-03"
            or any(type(n) is not int or n < 0 for n in (turnout, registered, fully, partial, missing))
            or not 0 <= turnout <= registered or not registered or not fully + partial + missing
            or turnout != query["chart_turnout"] or registered - turnout != query["chart_remainder"]
            or not re.fullmatch(r"[0-9]+\.[0-9]{2}%", printed)
            or (Decimal(turnout) * 100 / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(printed[:-1])
            or (Decimal(fully) * 100 / (fully + partial + missing)).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(query["precinct_rate"][:-1])):
        raise ValueError("Montana statewide election, turnout or reporting fields do not reconcile")
    return turnout, registered, clock


def montana_report(body):
    html = body.decode("utf-8-sig")

    def fields(pattern):
        hits = re.findall(pattern, html)
        if len(hits) != 1:
            raise ValueError("Missing or repeated Montana statewide report field")
        return hits[0]

    election = fields(r"<h2>(General Election - [^<]+)</h2>")
    turnout, registered = fields(
        r"<h2>Total Turnout <span>([\d,]+)</span><br\s*/>\s*Registered Voters <span[^>]*>([\d,]+)</span></h2>")
    chart = r"<canvas id=\"{}\" {}></canvas><div class=\"dough-percent\">"
    rate = r'<span class="int">(\d+)</span><span class="dec">(\.\d{{2}}%)</span>'
    desktop, remainder, pct, decimal = fields((chart + rate).format(
        "voter-turnout", r"voterturnout='(\d+)' votertotal='(\d+)'"))
    fully, partial, missing, ppct, pdecimal = fields((chart + rate).format(
        "precinct-reported", r"precinctsreported='(\d+)' precinctspartial='(\d+)' precinctsnotreported='(\d+)'"))
    printed_partial, printed_fully = fields(
        r"Partially <span[^>]*>([\d,]+)</span><br/>\s*<div[^>]*></div>Fully <span>([\d,]+)</span>")
    if (integer(printed_partial), integer(printed_fully)) != (int(partial), int(fully)):
        raise ValueError("Montana printed precinct counts differ from the chart")
    query = {"election": election, "total_turnout": integer(turnout), "registered_voters": integer(registered),
             "chart_turnout": int(desktop), "chart_remainder": int(remainder), "printed_rate": pct + decimal,
             "clock": fields(r"Results last updated:\s*([0-9/]+ [0-9:]+ [AP]M MT)"),
             "precincts": [int(fully), int(partial), int(missing)], "precinct_rate": ppct + pdecimal}
    _, _, clock = montana_controls(query)
    return {"report": {"url": MT_URL, **pin(body)}, "complete_native_query": query,
            "date": clock.isoformat(), "participation_observation_qualified": False}


def collect_montana(collector):
    return collector.capture(MT_FEED, MT_URL, montana_report,
                             equivalent=lambda old, new: old["complete_native_query"] == new["complete_native_query"])


def west_virginia_controls(query):
    if (set(query) != {"title", "publication_date", "turnout_passage"}
            or query["title"] != WV_TITLE or query["publication_date"] != "2026-11-06"):
        raise ValueError("West Virginia preliminary bulletin identity changed")
    match = re.fullmatch(
        r"Preliminary turnout totals for West Virginia's November 3 General Election show that "
        r"([\d,]+) ballots were cast statewide, representing (\d{1,3}\.\d{2}%) of "
        r"West Virgin(?:i)?a's ([\d,]+) registered voters\.", query["turnout_passage"])
    if match is None:
        raise ValueError("Missing or incompatible West Virginia statewide turnout passage")
    ballot_literal, printed, registration_literal = match.groups()
    ballots, registered = integer(ballot_literal), integer(registration_literal)
    if not 0 < ballots <= registered or (Decimal(ballots) * 100 / registered).quantize(
            Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(printed[:-1]):
        raise ValueError("West Virginia ballot counts and registration fraction do not reconcile")
    return ballots, registered, printed


def west_virginia_report(body):
    text = body.decode("utf-8-sig")
    titles = re.findall(r"<h1\b[^>]*><span>([^<>]+)</span></h1>", text)
    dates = re.findall(r'<time\s+datetime="(\d{4}-\d\d-\d\d)T[^"]+">November 6, 2026</time>', text)
    passages = re.findall(r"<p>(Preliminary turnout totals for West Virginia's November 3 General Election "
                          r"show that .*? registered voters\.)", text, re.S)
    if len(titles) != 1 or len(dates) != 1 or len(passages) != 1:
        raise ValueError("Missing or repeated West Virginia ballot bulletin fields")
    passage = " ".join(unescape(re.sub(r"</?a\b[^>]*>", "", passages[0])).split())
    query = {"title": titles[0], "publication_date": dates[0], "turnout_passage": passage}
    west_virginia_controls(query)
    return {"report": {"url": WV_URL, **pin(body)}, "complete_native_query": query,
            "date": dates[0], "participation_observation_qualified": False}


def collect_west_virginia(collector):
    return collector.capture(WV_FEED, WV_URL, west_virginia_report,
                             equivalent=lambda old, new: old["complete_native_query"] == new["complete_native_query"])


def north_dakota_canvass_controls(query):
    if (set(query) != {"title", "publication_date", "voters_cast_ballots", "printed_pct"}
            or query["title"] != ND_CANVASS_TITLE or query["publication_date"] != "2026-11-18"
            or not re.fullmatch(r"\d{1,3}\.\d%", query["printed_pct"])):
        raise ValueError("North Dakota canvass bulletin scope changed")
    voters = integer(query["voters_cast_ballots"])
    if not voters or not 0 < Decimal(query["printed_pct"][:-1]) <= 100:
        raise ValueError("Invalid North Dakota canvass turnout")
    return voters, query["printed_pct"]


def north_dakota_canvass_report(body):
    text = body.decode("utf-8-sig")
    titles = re.findall(r"<h1\b[^>]*>([^<>]+)</h1>", text)
    dates = re.findall(r'<time class="news-date" datetime="(\d{4}-\d\d-\d\d)T[^"]+">', text)
    totals = re.findall(
        r"<p>In the 2026 General Election,\s*([\d,]+) eligible voters cast ballots "
        r"for a statewide voter turnout of (\d{1,3}\.\d%)\.</p>", text)
    if len(titles) != 1 or len(dates) != 1 or len(totals) != 1:
        raise ValueError("Missing or repeated North Dakota canvass turnout fields")
    voters, printed = totals[0]
    query = {"title": titles[0], "publication_date": dates[0],
             "voters_cast_ballots": voters, "printed_pct": printed}
    north_dakota_canvass_controls(query)
    return {"report": {"url": ND_CANVASS_URL, **pin(body)}, "complete_native_query": query,
            "date": dates[0], "participation_observation_qualified": False}


def collect_north_dakota_canvass(collector):
    return collector.capture(
        ND_CANVASS_FEED, ND_CANVASS_URL, north_dakota_canvass_report,
        equivalent=lambda old, new: old["complete_native_query"] == new["complete_native_query"])


def georgia_edition(value):
    if not isinstance(value, str) or not re.fullmatch(r"202[67]-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,7})?Z", value):
        raise ValueError("Invalid Georgia publication or county timestamp")
    whole, _, fraction = value[:-1].partition(".")
    parsed = datetime.fromisoformat(whole)
    if not datetime(2026, 11, 3) <= parsed < datetime(2027, 2, 1):
        raise ValueError("Georgia timestamp outside the 2026 general-election window")
    return whole + "." + fraction.ljust(7, "0") + "Z"


def georgia_controls(query):
    rows = query["counties"]
    georgia_edition(query["published"])
    if (query["election_id"] != GA_ELECTION or query["jurisdiction_id"] != GA_JURISDICTION
            or query["election_date"] != "2026-11-03" or type(query["official"]) is not bool
            or len(rows) != 159 or pin(encoded({row["id"]: row["name"] for row in rows})) != GA_COUNTIES):
        raise ValueError("Georgia election scope or county inventory changed")
    for row in rows:
        ballots, registered = row["ballots"], row["registered"]
        if (type(ballots) is not int or type(registered) is not int or not 0 < ballots <= registered
                or type(row["official"]) is not bool
                or not re.fullmatch(r"[a-f0-9-]{36}", row["election_id"])
                or type(row["precincts_reporting"]) not in (int, float)
                or not 0 <= row["precincts_reporting"] <= 1):
            raise ValueError("Missing or invalid Georgia county turnout fields")
        if georgia_edition(row["updated"]) > georgia_edition(query["published"]):
            raise ValueError("Georgia county count postdates its statewide publication")
    ballots = sum(row["ballots"] for row in rows)
    registered = sum(row["registered"] for row in rows)
    if (len({row["election_id"] for row in rows}) != 159 or query["state_registered"] != registered
            or query["state_ballots"] not in (0, ballots)):
        raise ValueError("Georgia statewide and county reporting frames disagree")
    return ballots, registered


def georgia_report(body):
    if len(body) > 10_000_000:
        raise ValueError("Georgia bulk results exceed reviewed document bounds")
    document = json.loads(body)
    election, jurisdiction = document["election"], document["jurisdiction"]

    def name(row, field):
        text, = (label["text"] for label in row[field] if label["languageId"] == "en")
        return text

    def indexed(rows, field):
        result = {row[field].lower(): row for row in rows}
        if len(result) != len(rows):
            raise ValueError("Duplicate Georgia county identity")
        return result

    def total(value):
        if type(value) not in (int, float) or not 0 <= value <= 20_000_000 or int(value) != value:
            raise ValueError("Georgia counts must be nonnegative whole numbers")
        return int(value)

    if (name(jurisdiction, "name") != "Georgia" or jurisdiction["id"] != GA_JURISDICTION
            or name(election, "name") != "November 3, 2026 - General & Special Elections"
            or election["isPrimary"] is not False or election["isProduction"] is not True):
        raise ValueError("Georgia feed does not declare reviewed production general election")
    localities = indexed(jurisdiction["childLocalities"], "id")
    results = indexed(document["localityElections"], "jurisdictionId")
    registrations = indexed(document["voterRegistration"], "id")
    if set(localities) != set(results) or set(localities) != set(registrations):
        raise ValueError("Georgia county results, registrations and localities differ")
    rows = []
    for key in sorted(localities):
        local, result, registration = localities[key], results[key], registrations[key]
        county = name(local, "name")
        registered = total(result["totalVoters"])
        if (name(registration, "localityName") != county or total(registration["total"]) != registered
                or result["electionDate"] != election["electionDate"]
                or name(result, "name") != name(election, "name")
                or result["isPrimary"] is not False or result["isProduction"] is not True):
            raise ValueError("Georgia county count and registration evidence disagree")
        rows.append({"id": key, "name": county, "election_id": result["id"],
                     "ballots": total(result["ballotsCast"]), "registered": registered,
                     "updated": result["lastUpdated"], "official": result["isOfficialResults"],
                     "precincts_reporting": result["precinctsReporting"]})
    query = {"election_id": election["id"], "election_date": election["electionDate"],
             "jurisdiction_id": election["jurisdictionId"], "published": election["publishDate"],
             "official": election["isOfficialResults"], "state_ballots": total(election["ballotsCast"]),
             "state_registered": total(election["totalVoters"]), "counties": rows}
    georgia_controls(query)
    return {"report": {"url": GA_URL, **pin(body)}, "complete_native_query": query,
            "date": georgia_edition(query["published"]),
            "participation_observation_qualified": False}


def collect_georgia(collector):
    return collector.capture(GA_FEED, GA_URL, georgia_report,
                             equivalent=lambda old, new: old["complete_native_query"] == new["complete_native_query"])


def integer(value):
    if not re.fullmatch(r"[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+", value):
        raise ValueError("Turnout table needs literal integer counts")
    return count(value.replace(",", ""))


def table_rows(rows, first, last):
    result = []
    for cells in rows:
        if len(cells) != 4 or not re.fullmatch(r"[0-9]{4}", cells[0]) or not re.fullmatch(
                r"[0-9]{1,3}(?:\.[0-9]{1,2})?%", cells[3]):
            raise ValueError("Turnout table row schema changed")
        year, registered, ballots, printed = int(cells[0]), integer(cells[1]), integer(cells[2]), cells[3]
        if registered is None or ballots is None or not 0 <= ballots <= registered or not registered:
            raise ValueError("Turnout table count is missing or outside its register")
        digits = len(printed.partition(".")[2].removesuffix("%"))
        period = Decimal(1).scaleb(-digits)
        rounded = (Decimal(ballots) * 100 / registered).quantize(period, rounding=ROUND_HALF_UP)
        result.append({"year": year, "registered_voters": registered, "ballots_counted": ballots,
                       "published_turnout": printed, "rate_qualified": rounded == Decimal(printed[:-1])})
    years = [r["year"] for r in result]
    if years not in (list(range(last, first - 1, -1)), list(range(last - 1, first - 1, -1))):
        raise ValueError("Unexpected election-year inventory; missing years are never zero")
    return result


def html_tables(body, *, with_captions=False):
    from scripts.results_granular import FactualHTMLTables

    class CaptionedTables(FactualHTMLTables):
        in_caption = False

        def handle_starttag(self, tag, attributes):
            super().handle_starttag(tag, attributes)
            if self.depth == 1 and tag == "caption":
                self.table["caption"] = ""
                self.in_caption = True

        def handle_endtag(self, tag):
            if tag in ("caption", "table"):
                self.in_caption = False
            super().handle_endtag(tag)

        def handle_data(self, text):
            super().handle_data(text)
            if self.in_caption and self.depth == 1 and not self.hidden:
                self.table["caption"] += text

    parser = CaptionedTables() if with_captions else FactualHTMLTables()
    parser.feed(body.decode("utf-8-sig"))
    result = []
    for table in parser.tables:
        rows = [tuple(" ".join(cell["value"].split()) for cell in row["cells"]) for row in table["rows"]]
        result.append((" ".join(table.get("caption", "").split()), rows) if with_captions else rows)
    return result


def north_carolina_tables(tables):
    facts, native = [], []
    for number, label, first, last in ((1, "Presidential", 1972, 2024),
                                       (2, "Non-Presidential", 1974, CURRENT_YEAR)):
        caption = f"Table {number}: North Carolina {label} General Election Voter Turnout ({first}\u2013Present)"
        matches = [rows for title, rows in tables if title == caption]
        if len(matches) != 1 or not matches[0] or tuple(matches[0][0]) != NC_HISTORY_HEADER:
            raise ValueError("Missing or ambiguous North Carolina general-election turnout table")
        native.append([caption, [list(row) for row in matches[0]]])
        rows = matches[0][1:]
        years = [r[0] for r in rows if r]
        inventories = [list(range(last, first - 1, -4))]
        if last == CURRENT_YEAR:
            inventories.append(inventories[0][1:])
        if not any(years == [f"{year} General" for year in inventory] for inventory in inventories):
            raise ValueError("Unexpected North Carolina general-election year inventory")
        # Reuse the count/percentage guard without renaming the official denominator.
        for row in rows:
            year = int(row[0][:4])
            (fact,) = table_rows([(str(year), *row[1:])], year, year)
            facts.append({"year": year, "eligible_voters": fact["registered_voters"],
                          "ballots_cast": fact["ballots_counted"], "published_turnout": fact["published_turnout"],
                          "rate_qualified": fact["rate_qualified"]})
    facts.sort(key=lambda row: -row["year"])
    current = facts[0]["year"] == CURRENT_YEAR
    if current and facts[0]["ballots_cast"] <= 0:
        raise ValueError("Current North Carolina statewide historical count must be positive")
    return {"complete_native_query": facts, "current_election_status": "row_published" if current else "not_yet_published",
            "native_denominator": "Eligible Voters", "native_measure": "Ballots Cast",
            "participation_observation_qualified": False, "native_tables": native}


def parse_north_carolina_history(body):
    return north_carolina_tables(html_tables(body, with_captions=True))


def parse_washington(body):
    candidates = [rows[1:] for rows in html_tables(body) if rows and rows[0] == WA_HEADER]
    if len(candidates) != 1:
        raise ValueError("Missing or ambiguous Washington general-election turnout table")
    facts = table_rows(candidates[0], WA_FIRST, CURRENT_YEAR)
    return history_query(facts)


def parse_virginia(body):
    tables = [rows[2:] for rows in html_tables(body) if rows[:2] == [(VA_TITLE,), VA_HEADER]]
    notes = [" ".join(unescape(text).split()) for text in re.findall(
        r"<p>(\*[^<]+|The Department of Elections only publishes turnout statistics[^<]+)</p>",
        body.decode("utf-8-sig"))]
    if len(tables) != 1 or len(notes) != 4 or notes[0] != VA_CERTIFICATION:
        raise ValueError("Virginia November election table, certification policy or footnotes changed")
    native = tables[0]
    for row in native:
        if (len(row) != 6 or not re.fullmatch(r"[0-9]{4}\*?", row[0])
                or "*" in row[0] and row[0] != "1996*"):
            raise ValueError("Virginia November election row schema changed")
    facts = table_rows([(year.rstrip("*"), register, voting, rate)
                        for year, register, _, voting, rate, _ in native], 1976, CURRENT_YEAR)
    for row, (year, _, change, _, _, absentee) in zip(facts, native):
        if absentee != "***" and not 0 <= integer(absentee) <= row["ballots_counted"]:
            raise ValueError("Virginia absentee count is incompatible with Total Voting")
        row.update(zip(VA_FIELDS, (year, change, absentee)))
    query = history_query(facts)
    for row in facts:
        row["total_voting"] = row.pop("ballots_counted")
    return {**query, "native_measure": "Total Voting", "published_after_certification": True,
            "registered_includes": ["active", "inactive", "overseas"],
            "historical_qualifications": ["Virginia implemented NVRA in March 1996.",
                "** marks earlier roll purges; *** marks no separately reported absentee total."]}


def parse_texas(body):
    def printed(literal, numerator, denominator):
        if not re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,2})?%?", literal):
            raise ValueError("Invalid Texas printed turnout fraction")
        number = Decimal(literal.rstrip("%"))
        period = Decimal(1).scaleb(number.as_tuple().exponent)
        return (Decimal(numerator) * 100 / denominator).quantize(
            period, rounding=ROUND_HALF_UP) == number

    tables = [table for table in html_tables(body) if any(len(row) == 1 and TX_GENERAL.fullmatch(row[0])
                                                          for row in table)]
    if len(tables) != 1:
        raise ValueError("Missing or ambiguous Texas election turnout table")
    table, = tables
    labels = ("Registered Voters", "Voting Age Population (VAP)", "Percentage of VAP Registered",
              "Turnout", "Percent of Turnout to Registered", "Percent of Turnout to VAP")
    facts = []
    for offset, heading in enumerate(table):
        match = TX_GENERAL.fullmatch(heading[0]) if len(heading) == 1 else None
        if not match:
            continue
        fields = table[offset + 1:offset + 7]
        if (len(fields) != 6 or any(len(row) != 2 for row in fields)
                or tuple(key.removesuffix(" Voters") if key.startswith("Percent of Turnout to Registered")
                         else key for key, _ in fields) != labels):
            raise ValueError("Texas election turnout field labels changed")
        register, vap, reg_pct, turnout, turnout_pct, vap_pct = (value for _, value in fields)
        year = int(match[1])
        registered, population, reported = integer(register.rstrip("*")), integer(vap), integer(turnout)
        if (not registered or not population or not reported
                or not reported <= min(registered, population)
                or year == CURRENT_YEAR and register.endswith("*")):
            raise ValueError("Texas election turnout counts do not fit their denominators")
        rate = printed(turnout_pct, reported, registered) and not register.endswith("*")
        vap_rate = printed(vap_pct, reported, population)
        facts.append({"year": year, "registered_voters": registered, "total_voting": reported,
                      "published_turnout": turnout_pct, "rate_qualified": rate,
                      **dict(zip(TX_FIELDS, (heading[0], register, population, reg_pct, vap_pct, vap_rate)))})
    expected = list(range(2024, 1969, -2))
    if [row["year"] for row in facts] not in (expected, [CURRENT_YEAR, *expected]):
        raise ValueError("Texas November general-election inventory changed")
    return {"complete_native_query": facts, "native_measure": "Turnout",
            "current_election_status": "row_published" if facts[0]["year"] == CURRENT_YEAR else "not_yet_published",
            "participation_observation_qualified": False}


def history_query(facts):
    if facts[0]["year"] == CURRENT_YEAR and not facts[0]["ballots_counted"]:
        raise ValueError("Current statewide count must be positive")
    return {"complete_native_query": facts,
            "current_election_status": "row_published" if facts[0]["year"] == CURRENT_YEAR else "not_yet_published",
            "participation_observation_qualified": False}


def collect_history(collector, feed, url, parser):
    def parse(body):
        data = parser(body)
        previous = (collector.prior.get(feed) or {}).get("data") or {}
        if (previous.get("current_election_status") == "row_published"
                and data["current_election_status"] != "row_published"):
            raise ValueError("Previously published general-election row is missing")
        return data

    return collector.capture(feed, url, parse, equivalent=lambda old, new: old == new)


def collect_washington(collector):
    return collect_history(collector, WA_FEED, WA_URL, parse_washington)


def collect_north_carolina_history(collector):
    def parse(body):
        data = parse_north_carolina_history(body)
        prior = (collector.prior.get(NC_HISTORY_FEED) or {}).get("data") or {}
        if prior.get("current_election_status") == "row_published" and data["current_election_status"] != "row_published":
            raise ValueError("Previously published North Carolina general-election row is missing")
        return data

    return collector.capture(NC_HISTORY_FEED, NC_HISTORY_URL, parse,
                             equivalent=lambda old, new: old == new)


def north_carolina_history_facts(entry):
    data = entry["data"]
    if entry["source"]["url"] != NC_HISTORY_URL or data != north_carolina_tables(data["native_tables"]):
        raise ValueError("North Carolina statewide history differs from its retained source rows")
    return {key: value for key, value in data.items() if key != "native_tables"}


def collect_virginia(collector):
    return collect_history(collector, VA_FEED, VA_URL, parse_virginia)


def collect_texas(collector):
    return collect_history(collector, TX_FEED, TX_URL, parse_texas)


def texas_history_entry(entry, retained_archive):
    if entry.get("data") or retained_archive is None:
        return entry
    if pin(retained_archive) != TX_ARCHIVE_PIN:
        raise ValueError("Texas retained turnout archive checksum differs")
    data = json.loads(retained_archive)
    source = data.pop("source")
    if (source["url"] != TX_URL or data["current_election_status"] != "not_yet_published"
            or data["native_measure"] != "Turnout"
            or [row["year"] for row in data["complete_native_query"]] != list(range(2024, 1969, -2))):
        raise ValueError("Texas retained turnout archive scope differs")
    data["latest_attempt_status"] = entry.get("status", "not_reported")
    return {"status": "retained_after_failure", "source": source, "data": data}


def history_csv(entry, *, virginia=False, texas=False, north_carolina=False):
    out = io.StringIO(newline="")
    count_field = "total_voting" if virginia or texas else "ballots_counted"
    columns = ("year", "registered_voters", count_field, "published_turnout", "rate_qualified")
    if north_carolina:
        columns = ("year", "eligible_voters", "ballots_cast", "published_turnout", "rate_qualified")
    columns += (VA_FIELDS if virginia else TX_FIELDS if texas else ()) + ("publication_status", "source_url", "source_sha256")
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in entry["data"]["complete_native_query"]:
        writer.writerow({**row, "publication_status": entry["status"],
                         "source_url": entry["source"]["url"], "source_sha256": entry["source"]["sha256"]})
    return out.getvalue().encode()


def washington_csv(entry):
    return history_csv(entry)
