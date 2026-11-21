import copy
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
import io
import json
import re

import pytest

from scripts import results_county_frame as frame
from scripts import results_intake
from scripts.participation_intake.contract import encoded, pin
from test_results_clarity_congress import capture, facts


def test_oktibbeha_keeps_last_good_and_accepts_reconciled_native_successors(tmp_path, monkeypatch):
    pypdf = pytest.importorskip("pypdf")
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    parser = frame.county_pdf
    report = parser.OKTIBBEHA_REVIEWED["url"]
    path = "/" + report.split("/", 3)[-1]
    index = f'<a href="{path}">{parser.OKTIBBEHA_LABEL}</a>'.encode()
    text = (
        "Summary Results\nOFFICIAL RESULTS\n2026 General Election\nNovember 3, 2026\n"
        "Oktibbeha County\n"
        "Statistics TOTAL Election Day In Person Absentee Mail in Absentee 5 Day Absentee Affidavit\n"
        "Election Day Precincts Reporting 20 of 20 20 0 0 0 20\n"
        "Registered Voters - Total 27,148\nBallots Cast - Total 15,771 13,319 1,768 161 10 513\n"
        "Voter Turnout - Total 58.09%\nElection Summary - 11/12/2026 12:07 PM 1 of 1"
    )

    def pdf(text):
        writer = pypdf.PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        name = NameObject
        font = DictionaryObject({name("/Type"): name("/Font"), name("/Subtype"): name("/Type1"),
                                 name("/BaseFont"): name("/Helvetica")})
        page[name("/Resources")] = DictionaryObject({name("/Font"): DictionaryObject({name("/F1"): font})})
        stream = DecodedStreamObject()
        stream.set_data(("BT /F1 8 Tf 10 TL 10 760 Td "
                         + " T* ".join(f"({line}) Tj" for line in text.splitlines()) + " ET").encode())
        page[name("/Contents")] = writer._add_object(stream)
        result = io.BytesIO()
        writer.write(result)
        return result.getvalue()

    def collect(text, prior=None, declaration=index):
        body = pdf(text)
        calls = []

        def acquire(self, url):
            calls.append(url)
            source = {parser.OKTIBBEHA_INDEX: declaration, report: body}[url]
            return source, {"origin": "fixture_transport", **pin(source)}

        monkeypatch.setattr(results_intake.Collector, "acquire", acquire)
        collector = results_intake.Collector(
            tmp_path, {parser.OKTIBBEHA_FEED: prior} if prior else {},
            {"urls": [], "prefixes": [], "hosts": []}, datetime(2026, 11, 19, tzinfo=timezone.utc))
        return parser.collect_oktibbeha(collector), calls

    first, _ = collect(text)
    assert first["status"] == "reported", first
    assert collect(text, first)[0] == first
    proposal = text.replace("15,771", "15,770").replace("513", "512")
    assert collect(proposal, first)[0]["status"] == "retained_after_failure"
    revised, _ = collect(proposal.replace("11/12/", "11/13/"), first)
    assert revised["status"] == "reported", revised
    assert parser.oktibbeha_controls(revised["data"])[1:3] == (15770, 27148)
    for rejected in (text, proposal.replace("15,770", "15,772"),
                     proposal.replace("OFFICIAL RESULTS", "UNOFFICIAL RESULTS"),
                     proposal.replace("Oktibbeha County", "Oktibbeha County Congressional District 1"),
                     proposal.replace("5 Day Absentee Affidavit", "Affidavit 5 Day Absentee"), ""):
        held, _ = collect(rejected, revised)
        assert held["status"] == "retained_after_failure" and held["data"] == revised["data"]
    held, calls = collect(text, revised, index + index)
    assert calls == [parser.OKTIBBEHA_INDEX] and held["data"] == revised["data"]


def test_oktibbeha_visual_transcription_is_bound_to_exact_original():
    parser = frame.county_pdf
    data = {"report": dict(parser.OKTIBBEHA_REVIEWED),
            "complete_native_query": copy.deepcopy(parser.OKTIBBEHA_REVIEWED_QUERY),
            "extraction": "visually_reviewed_exact_edition", "date": "2026-11-12T12:07:00"}
    row = frame.county_parent_observation(frame.OKTIBBEHA, data, {"review_id": "reference"}, "reported")
    assert (row["count"]["value"], row["denominator"]["value"]) == (15771, 27148)
    assert row["source_clock"]["literal"] is None and not row["view"]["maps_approved"]
    assert row["view"]["source_publication_label"] == "2026-11-12 12:07:00"
    data["report"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="reviewed edition differs"):
        parser.oktibbeha_controls(data)


def test_woodford_revisions_reconcile_and_preserve_count_only(tmp_path, monkeypatch):
    p = frame.county_pdf
    header = f"<b>{p.WOODFORD_INDEX_TITLE}</b><iframe src=\"results.html\"></iframe>"
    body = (
        f"{p.WOODFORD_HEADER}\nRUN DATE: 11/18/26 NOVEMBER 3, 2026\n"
        f"RUN TIME: 11:24 AM {p.WOODFORD_COUNTY}\nVOTES PERCENT\n"
        "PRECINCTS COUNTED (OF 37). 37 100.00\nREGISTERED VOTERS - TOTAL. 0\n"
        "BALLOTS CAST - TOTAL. 16,366\nBALLOTS CAST - BLANK. 2 .01\n"
        "BALLOTS CAST - STYLE 00001. 16,366\nBALLOTS CAST - STYLE 00002. 0\n"
        "A CONTEST\n(VOTE FOR) 1\nCANDIDATE. 16,365"
    )

    def collect(report, prior=None, declaration=header):
        hits = []

        def acquire(self, url):
            hits.append(url)
            if url == p.WOODFORD_REPORT and report is None:
                raise TimeoutError
            source = declaration if url == p.WOODFORD_INDEX else f"<html><pre>{report}</pre></html>"
            return source.encode(), {"origin": "fixture_transport"}

        monkeypatch.setattr(results_intake.Collector, "acquire", acquire)
        collector = results_intake.Collector(
            tmp_path, {p.WOODFORD_FEED: prior} if prior else {},
            {"urls": [], "prefixes": [], "hosts": []}, datetime(2026, 11, 19, tzinfo=timezone.utc))
        return p.collect_woodford(collector), hits

    first, _ = collect(body)
    assert first["status"] == "reported", first
    assert collect(body, first)[0] == first
    proposal = body.replace("16,366", "16,365")
    assert collect(proposal, first)[0]["status"] == "retained_after_failure"
    down, _ = collect(proposal.replace("11:24 AM", "11:25 AM"), first)
    up, _ = collect(body.replace("16,366", "16,368").replace("11:24 AM", "11:26 AM"), down)
    assert [p.woodford_controls(v["data"])[1] for v in (first, down, up)] == [16366, 16365, 16368]
    row = frame.county_parent_observation(frame.WOODFORD, up["data"], {"review_id": "reference"}, "reported")
    assert row["denominator"]["value"] is None and not row["denominator"]["qualified"]
    assert row["view"]["reported_pct"] is None and row["source_clock"]["literal"] is None
    for rejected in (None, body, body.replace("GENERAL ELECTION", "PRIMARY ELECTION"),
                     body.replace(p.WOODFORD_COUNTY, "OTHER COUNTY, IL"),
                     body.replace("37 100.00", "36 97.30"),
                     body.replace("STYLE 00002", "STYLE 00001"),
                     body.replace("TOTAL. 16,366", "TOTAL. 163,66"),
                     body.replace("TOTAL. 16,366", "TOTAL. 16,365"),
                     body.replace("BLANK. 2 .01", "BLANK. 2 9.99")):
        held, _ = collect(rejected.replace("11:24 AM", "11:27 AM") if rejected not in (None, body) else rejected, up)
        assert held["status"] == "retained_after_failure" and held["data"] == up["data"]
    held, hits = collect(body, up, header.replace("GENERAL", "PRIMARY"))
    assert hits == [p.WOODFORD_INDEX] and held["data"] == up["data"]


def test_lawrence_binds_reviewed_scan_and_checks_native_text_successor():
    p = frame.county_pdf
    q = p.lawrence_text_query(
        "SUMMARY REPORT NOVEMBER 3, 2026 OFFICIAL RESULTS\n"
        "GENERAL ELECTION\nLAWRENCE COUNTY, ILLINOIS\n"
        "RUN DATE: 11/19/26 08:49 PM REPORT-EL45 PAGE 001\n"
        "VOTES PERCENT              VOTES PERCENT\n"
        "PRECINCTS COUNTED (OF 17). 17 100.00         STATE SENATOR\n"
        "REGISTERED VOTERS - TOTAL. 9,034             (VOTE FOR) 1\n"
        "BALLOTS CAST - TOTAL. 4,508                   Not a turnout value 22\n"
        "BALLOTS CAST - BLANK. 1 .02\n"
        "VOTER TURNOUT - TOTAL. 49.90\nVOTER TURNOUT - BLANK. .01"
    )
    reviewed = {"report": dict(p.LAWRENCE_REVIEWED), "complete_native_query": dict(p.LAWRENCE_QUERY),
                "date": "2026-11-03T20:49:00", "extraction": "visually_reviewed_exact_edition"}
    row = frame.county_parent_observation(frame.LAWRENCE, reviewed, {"review_id": "reference"}, "reported")
    assert (row["count"]["value"], row["denominator"]["value"]) == (4507, 9034)
    assert row["view"]["source_status_literal"] == "UNOFFICIAL RESULTS"
    updated = {**reviewed, "complete_native_query": q, "date": "2026-11-19T20:49:00",
               "extraction": "native_text"}
    assert p.lawrence_controls(updated)[1:3] == (4508, 9034)
    assert not p.county_summary_regressed(reviewed, updated)
    assert p.county_summary_regressed(updated, reviewed)
    for bad in ({"pct": "80.00"}, {"precincts": ["17", "16", "94.12"]}, {"ballots": "4,509"},
                {"county": "OTHER COUNTY, ILLINOIS"}):
        with pytest.raises(ValueError):
            p.lawrence_controls({**updated, "complete_native_query": {**q, **bad}})
    with pytest.raises(ValueError, match="exact edition"):
        p.lawrence_controls({**reviewed, "report": {**reviewed["report"], "sha256": "0" * 64}})
    link = f'<a href="{p.LAWRENCE_REVIEWED["url"]}">Unofficial Summary Election Results</a>'
    assert p.lawrence_discovery(link.encode()) == p.LAWRENCE_REVIEWED["url"]
    with pytest.raises(ValueError, match="ambiguous"):
        p.lawrence_discovery((link + link).encode())


def test_buxton_turnout_accepts_consistent_revisions_and_rejects_wrong_scope(tmp_path, monkeypatch):
    history = frame.history
    heading = f"<h2>{history.BUXTON_TITLE}</h2>"
    paragraphs = (
        "<p>6,386 Registered Voters</p><p>2,250 Absentee Ballots Cast</p>"
        "<p>2,307 Ballots Cast in Person</p><p>4,557 Total Ballots Cast</p>"
        "<p>71.36% Voter Turn Out Percent</p><p><strong>State of Maine General Election</strong></p>"
    )
    body = f"<article>{heading}{paragraphs}<p>5,000 Candidate Votes</p></article>".encode()
    now = datetime(2026, 11, 19, tzinfo=timezone.utc)

    def acquire(self, url):
        assert url == history.BUXTON_URL
        return body, {"origin": "fixture_transport", **pin(body)}

    monkeypatch.setattr(results_intake.Collector, "acquire", acquire)

    def collect(prior=None):
        collector = results_intake.Collector(tmp_path, {history.BUXTON_FEED: prior} if prior else {},
             {"urls": [], "prefixes": [], "hosts": []}, now)
        return history.collect_buxton(collector)

    entry = collect()
    assert history.buxton_controls(entry["data"]) == (4557, 6386, "71.36%")
    assert collect(entry) == entry
    original = body
    body = body.replace(b"2,250", b"2,249").replace(b"4,557", b"4,556").replace(b"71.36%", b"71.34%")
    revised = collect(entry)
    assert history.buxton_controls(revised["data"]) == (4556, 6386, "71.34%")
    body = original.replace(b"4,557", b"4,558")
    failed = collect(revised)
    assert failed["status"] == "retained_after_failure" and failed["data"] == revised["data"]
    body = original.replace(b"State and Town Elections", b"Town Elections")
    assert collect(revised)["status"] == "retained_after_failure"


def test_bath_turnout_refreshes_revisions_and_rejects_ambiguous_editions(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import pypdf

    history = frame.history
    declaration = f'<a href="{history.BATH_PDF}">2026 Preliminary Election Results<span>(PDF,&nbsp;101KB)</span></a>'.encode()
    body = declaration
    page_one = ("STATE GENERAL ELECTION TOTALS\nNovember 3, 2026\nCandidate 9999\n"
                "Total State Votes Cast: {count} Total registered voters: 5962 % of Voter Turnout: {pct}")
    next_page = "CITY OF BATH ELECTION TOTALS\nNovember 3, 2026\nCandidate 4444"
    pdf, counts, pct, day = b"%PDF-1 first", 4760, "79.8%", 4
    monkeypatch.setattr(pypdf, "PdfReader", lambda _: SimpleNamespace(pages=[
        SimpleNamespace(extract_text=lambda: page_one.format(count=counts, pct=pct)),
        SimpleNamespace(extract_text=lambda: next_page),
    ]))

    def acquire(self, url):
        assert url in {history.BATH_INDEX, history.BATH_PDF}
        content = body if url == history.BATH_INDEX else pdf
        if content is None:
            raise TimeoutError("unavailable")
        return content, {"origin": "fixture_transport", **pin(content)}

    def edition(self, url):
        assert url == history.BATH_PDF
        return {"body_sha256": pin(pdf)["sha256"], "http_last_modified": f"{day} Nov 2026 13:10:05 GMT"}

    monkeypatch.setattr(results_intake.Collector, "acquire", acquire)
    monkeypatch.setattr(results_intake.Collector, "public_edition", edition)

    def collect(prior=None):
        return history.collect_bath(results_intake.Collector(
            tmp_path, {history.BATH_FEED: prior} if prior else {},
            {"urls": [], "prefixes": [], "hosts": []}, datetime(2026, 11, 19, tzinfo=timezone.utc)))

    before = collect()
    assert history.bath_controls(before["data"]) == (4760, 5962, "79.8%")
    assert collect(before) == before
    pdf, day = b"%PDF-1 reformatted, same facts", 5
    refreshed = collect(before)
    assert history.bath_controls(refreshed["data"]) == history.bath_controls(before["data"])
    assert refreshed["data"]["report"]["sha256"] == pin(pdf)["sha256"]
    assert history.bath_precedes(before["data"], refreshed["data"])
    assert collect(refreshed) == refreshed
    pdf, day = b"%PDF-1 first", 4
    assert collect(refreshed)["data"] == refreshed["data"]
    for day, counts, pct in ((5, 4757, "79.8%"), (6, 4766, "79.9%")):
        pdf = f"%PDF-1 edition {day}".encode()
        after = collect(before)
        assert after["status"] == "reported"
        assert history.bath_controls(after["data"]) == (counts, 5962, pct)
        before = after

    counts, day, pct = 4760, 6, "79.8%"
    assert collect(before)["data"] == before["data"]
    for invalid in ("duplicate", "wrong_city", "rate", "outage"):
        counts, day, pct = 4760, 7, "79.8%"
        next_page = "CITY OF BATH ELECTION TOTALS\nNovember 3, 2026"
        body, pdf = declaration, b"%PDF-1 invalid"
        if invalid == "duplicate":
            body += declaration
        elif invalid == "wrong_city":
            next_page = next_page.replace("BATH", "OTHER")
        elif invalid == "rate":
            pct = "80.0%"
        else:
            pdf = None
        failed = collect(before)
        assert failed["status"] == "retained_after_failure"
        assert failed["data"] == before["data"]


def test_votingworks_scan_counts_require_two_confident_and_reconciled_queries():
    history = frame.history
    header = ["Official Tally Report VotingWorks", "GeneralElection,Nov3,2026,Hampton,NH",
              "ReportGenerated:Nov3,2026,11:25:36PM ElectionID:080271d-8a2e8f5"]
    evidence = [{"receipt": {"page": 1, "dpi": dpi}, "header": header,
                 "fields": [["9,012", True], ["8,903", True], ["109", True]],
                 "controls": [["8,903", "109", "9,012"]] * 2} for dpi in (180, 240)]
    query = history.votingworks_scan_query(evidence, "Hampton")
    assert query["statistics"] == ["Ballot Count 9,012", "Scanned 8,903", "Manually Entered 109"]
    for view in evidence:
        view["fields"][0][1] = False
    with pytest.raises(ValueError, match="lack a confident render"):
        history.votingworks_scan_query(evidence, "Hampton")
    evidence[0]["fields"][0][1] = True
    evidence[1]["controls"].pop()
    with pytest.raises(ValueError, match="repeated source controls"):
        history.votingworks_scan_query(evidence, "Hampton")


def test_votingworks_scanned_revision_reuses_rejection_and_preserves_last_good(tmp_path, monkeypatch):
    history = frame.history
    profile = history.VOTINGWORKS_TOWNS["NH-hampton-municipal-turnout"]
    from urllib.parse import urljoin

    url = urljoin(profile.index, f"/DocumentCenter/View/6048/{profile.document_slug}")
    assert profile.permits_report(url)
    index = f'<a href="{url}">{profile.link_label}</a>'.encode()
    calls = []

    def report(body, town, report_url, *, scanned):
        assert scanned
        calls.append(body)
        if body == b"bad revision":
            history.scan.fail("VotingWorks scan ballot columns do not reconcile")
        time = "11:25:36" if body == b"original" else "11:26:00"
        count = "9,012" if body == b"original" else "9,013"
        manually = "109" if body == b"original" else "110"
        return {"report": {"url": report_url, **pin(body)}, "complete_native_query": {
            "title": "Official Tally Report", "election": f"General Election, Nov 3, 2026, {town}, NH",
            "generated": f"Nov 3, 2026, {time} PM", "election_id": profile.election_id,
            "statistics": [f"Ballot Count {count}", "Scanned 8,903", f"Manually Entered {manually}"]}}

    monkeypatch.setattr(history, "votingworks_report", report)
    monkeypatch.setattr(history.scan, "scan_policy", lambda *args: "test-policy")
    prior = {}

    def refresh(body):
        collector = results_intake.Collector(tmp_path, prior, {"urls": [], "prefixes": [], "hosts": []},
                                             datetime(2026, 11, 21, tzinfo=timezone.utc))
        monkeypatch.setattr(collector, "acquire", lambda target: (
            index if target == profile.index else body, {"origin": "test"}))
        prior[profile.feed] = history.collect_votingworks_town(collector, profile)
        return prior[profile.feed]

    first = refresh(b"original")
    assert first["status"] == "reported" and refresh(b"original") == first
    held = refresh(b"bad revision")
    assert held["status"] == "retained_after_failure" and held["data"] == first["data"]
    assert held["error"] == "scan_reconciliation_failed" and refresh(b"bad revision") == held
    assert calls == [b"original", b"bad revision"]
    revised = refresh(b"corrected revision")
    assert revised["status"] == "reported" and "rejected_scan" not in revised
    assert history.votingworks_town_controls(revised["data"], profile)[0][0] == 9013


@pytest.mark.parametrize("locality", ["Hollis", "Fixture Town", "Bedford", "Hanover"])
def test_votingworks_town_report_retains_last_good_across_revisions(tmp_path, monkeypatch, locality):
    from dataclasses import replace
    from types import SimpleNamespace
    from urllib.parse import urljoin

    pypdf = pytest.importorskip("pypdf")
    history = frame.history
    if locality == "Fixture Town":
        profile = history.VOTINGWORKS_TOWNS[history.HOLLIS_FEED]
        profile = replace(profile, feed="NH-fixture-town-votingworks", town=locality, feature_key="3399999",
                          index="https://fixture-town.example/elections", election_id="1234567-abcdef0")
        monkeypatch.setitem(history.VOTINGWORKS_TOWNS, profile.feed, profile)
    else:
        profile, = (row for row in history.VOTINGWORKS_TOWNS.values() if row.town == locality)
    title = "Official Tally Report"
    town = locality
    path = "/DocumentCenter/View/6048"
    if profile.document_slug is not None:
        path += f"/{profile.document_slug}"
    if profile.timestamped_slug:
        path += "__2026-11-03_21-21-40"
    initial_url = urljoin(profile.index, path)
    report_url = initial_url
    extra_link = ""
    election_id = profile.election_id
    clock, total, scanned, manual = "9:21:41 PM", "5,005", "4,977", 28
    attempt = b"%PDF-1 original"
    text = ""
    monkeypatch.setattr(pypdf, "PdfReader", lambda _body, *, strict: SimpleNamespace(
        pages=[SimpleNamespace(extract_text=lambda: text)]))

    def acquire(self, url):
        self.guard(url)
        declaration = (f'<a href="{report_url}">{profile.link_label}</a>' + extra_link).encode()
        body = {profile.index: declaration, report_url: attempt}[url]
        if body is None:
            raise TimeoutError("offline")
        return body, {"origin": "fixture_transport", **pin(body)}

    monkeypatch.setattr(results_intake.Collector, "acquire", acquire)

    def collect(prior=None, *, stopped=()):
        nonlocal text
        text = (f"{title}\nGeneral Election, Nov 3, 2026, {town}, NH\n"
                f"Report Generated: Nov 3, 2026, {clock}Election ID: {election_id}\n"
                f"Certification Signatures: We, the undersigned\nBallot Count {total}\n"
                f"Scanned {scanned}\nManually Entered {manual}\nGovernor\nBallots Cast 12 3 15")
        collector = results_intake.Collector(
            tmp_path, {profile.feed: prior} if prior else {},
            {"urls": list(stopped), "prefixes": [], "hosts": []}, datetime(2026, 11, 19, tzinfo=timezone.utc))
        return history.collect_votingworks_town(collector, profile)

    first = collect()
    assert first["status"] == "reported"
    observation = frame.county_parent_observation(frame.votingworks_parent(profile), first["data"],
                                                  {"review_id": "test"}, "reported")
    assert observation["count"]["value"] == 5005
    assert observation["source_clock"]["literal"] is None
    assert observation["denominator"]["value"] is None
    assert observation["view"]["source_publication_label"] == "Nov 3, 2026, 9:21:41 PM"
    assert collect(first) == first
    total, manual = "5,004", 27
    assert collect(first)["status"] == "retained_after_failure"
    clock = "9:21:42 PM"
    decreased = collect(first)
    assert decreased["status"] == "reported"
    assert history.votingworks_town_controls(decreased["data"], profile)[0][0] == 5004
    total, manual, clock = "5,006", 29, "9:21:43 PM"
    increased = collect(decreased)
    assert increased["status"] == "reported" and collect(increased) == increased
    assert history.votingworks_town_controls(increased["data"], profile)[0][0] == 5006
    total, manual, clock = "5,002", 25, "9:21:44 PM"
    report_url = initial_url.replace("/6048", "/6050")
    if profile.timestamped_slug:
        report_url = report_url.replace("__2026-11-03_21-21-40", "__2026-11-04_21-21-40")
    successor = collect(increased)
    assert successor["status"] == "reported"
    assert successor["data"]["report"]["url"] == report_url
    next_observation = frame.county_parent_observation(frame.votingworks_parent(profile), successor["data"],
                                                       {"review_id": "test"}, "reported")
    assert next_observation["id"] == observation["id"]
    assert next_observation["count"]["value"] == 5002
    assert collect(successor) == successor
    stopped = collect(successor, stopped=[report_url])
    assert stopped["error"] == "source_stopped" and stopped["data"] == successor["data"]
    extra_link = f'<a href="{initial_url}">{profile.link_label}</a>'
    assert collect(successor)["status"] == "retained_after_failure"
    extra_link = ""
    for unapproved in ("https://example.org" + path, initial_url + "?bidId=", initial_url + "/extra"):
        report_url = unapproved
        assert collect()["data"] is None
    if profile.timestamped_slug:
        report_url = initial_url.replace("/official-", "/unofficial-")
        assert collect()["data"] is None
    report_url = initial_url
    clock = "9:21:43 PM"
    assert collect(successor)["data"] == successor["data"]
    clock = "9:21:45 PM"
    election_id = "0000000-0000000"
    assert collect(successor)["data"] == successor["data"]
    election_id = profile.election_id
    for bad_title, bad_town, bad_total in (
        ("Scanner Batch Report", locality, "5,002"), ("Official Tally Report", "Hampton", "5,002"),
        ("Official Tally Report", locality, "5,003"),
    ):
        title, town, total = bad_title, bad_town, bad_total
        rejected = collect(increased)
        assert rejected["status"] == "retained_after_failure"
        assert rejected["data"] == increased["data"]
    attempt = None
    assert collect(increased)["data"] == increased["data"]


def test_philadelphia_turnout_keeps_parent_residual_and_holds_testing_or_invalid_divisions(tmp_path, monkeypatch):
    parser = frame.county_pdf
    header = (
        '<div id="pnlTestBanner" style="display:none"></div>'
        '<a id="lnkElectionInfo" href="/"><h1><span>Unofficial</span> 2026 General Election Results</h1>'
        '<h2>November 3, 2026</h2></a>'
        '<span class="turnout-last-updated-time">11/18/2026 10:18:46 AM EST</span>'
        'Total Ballots Cast<span>134</span><br/>Registered Voters<span>264</span>'
        'Ballots Cast by Mail:<span>68</span><br/>Ballots Cast at Polling Place:<span>66</span>'
        '<br/>Ballots Cast by Provisional:<span>0</span>'
        'Divisions Reported<span>66</span><br/>Total Divisions<span>66</span>'
        '<canvas id="voter-turnout"></canvas><div class="dough-percent">'
        '<span class="int">50</span><span class="dec">.76%</span>'
    )
    rows = "".join(
        f'<div class="county-precinct odd">{ward:02}-01</div>'
        + "".join(f'<div class="county-cast odd">{count}</div>' for count in (4, 2, 1, 1, 0))
        for ward in range(1, 67)
    )
    body = (header + rows).encode()
    result = parser.philadelphia_report(body)
    assert parser.philadelphia_controls(result) == (
        134, 264, "50.76%", "Unofficial", "11/18/2026 10:18:46 AM EST", 2)
    assert result["complete_native_query"]["divisions"][0] == ["01-01", 4, 2, 1, 1, 0]
    with pytest.raises(ValueError, match="testing mode"):
        parser.philadelphia_report(body.replace(b"display:none", b"display:block"))
    with pytest.raises(ValueError, match="division inventory"):
        parser.philadelphia_report(body.replace(b"02-01</div>", b"01-01</div>"))
    with pytest.raises(ValueError, match="outside the unassigned mail residual"):
        parser.philadelphia_report(body.replace(b"Mail:<span>68", b"Mail:<span>67")
                                  .replace(b"Polling Place:<span>66", b"Polling Place:<span>67"))

    def acquire(self, url):
        assert url == parser.PHILADELPHIA_URL
        return body, {"origin": "fixture_transport", **pin(body)}

    monkeypatch.setattr(results_intake.Collector, "acquire", acquire)

    def collect(prior=None):
        collector = results_intake.Collector(
            tmp_path, {parser.PHILADELPHIA_FEED: prior} if prior else {},
            {"urls": [], "prefixes": [], "hosts": []}, datetime(2026, 11, 19, tzinfo=timezone.utc))
        return parser.collect_philadelphia(collector), collector.attempts[-1]

    first, _ = collect()
    body += b"<!-- different request-specific HTML -->"
    again, attempt = collect(first)
    assert again == first
    assert attempt["sha256"] == pin(body)["sha256"] != first["source"]["sha256"]
    assert attempt["accepted_equivalent_source"] == first["source"]
    body = body.replace(b"134</span>", b"133</span>").replace(b"Mail:<span>68", b"Mail:<span>67")
    body = body.replace(b".76%", b".38%").replace(b"10:18:46 AM EST", b"10:19:00 AM EST")
    revised, _ = collect(first)
    assert revised["status"] == "reported"
    assert parser.philadelphia_controls(revised["data"])[:3] == (133, 264, "50.38%")
    assert revised["source"]["sha256"] == pin(body)["sha256"]


def test_philadelphia_division_geometry_keeps_leading_zero_and_holds_changed_polygons(monkeypatch):
    from scripts import philadelphia_divisions as divisions

    polygon = {"type": "Polygon", "coordinates": [[[-75.2, 40], [-75.1, 40],
                                                   [-75.1, 40.1], [-75.2, 40]]]}
    monkeypatch.setattr(divisions, "KEYS", pin(encoded(["0101"])))
    monkeypatch.setattr(divisions, "POLYGONS", pin(encoded([["0101", polygon]])))
    shape = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"division_num": "0101", "short_div_num": "13"},
         "geometry": polygon},
    ]}
    data = divisions.parse_geometry(encoded(shape))
    assert data["features"] == [["0101", polygon]]
    assert data["short_field_conflicts"] == [["0101", "13"]]
    changed = copy.deepcopy(shape)
    changed["features"][0]["properties"]["division_num"] = "0102"
    with pytest.raises(ValueError, match="reviewed election inventory"):
        divisions.parse_geometry(encoded(changed))
    polygon["coordinates"][0][1][0] = -75.08
    with pytest.raises(ValueError, match="reviewed election inventory"):
        divisions.parse_geometry(encoded(shape))


def baseline(value):
    profile = frame.IA
    bounds = {"sha256": profile["reference_sha256"], "boundary_year": 2026,
              "review_id": "test-existing-reference"}
    scopes, joins, records = {}, [], []
    for i, name in enumerate(value["status"]["P"]):
        key = f"19{2*i+1:03d}"
        county = name + " County"
        provider_id = f"provider:{key}"
        scopes[key] = {"state_code": "IA", "name": county, "boundary_year": 2026}
        joins.append({"county_id": provider_id, "feature_key": key})
        records.append({
            "id": provider_id, "source": {"id": "early"}, "denominator": None,
            "count": {"status": "reported", "value": 1},
            "view": {"county": county, "county_fips": key, "county_id": provider_id,
                     "reference_geometry": bounds},
        })
    early_ids = [row["id"] for row in records]
    for identity, name in zip(profile["old_selections"], ("Linn", "Marion")):
        records.append({
            "id": identity, "source": {"id": f"dated-{name}"}, "denominator": None,
            "count": {"status": "reported", "value": 2}, "view": {"county": name + " County"},
        })
    modes = {mode: {"qualified": True, "counties": list(profile["old_selections"]),
                    "nongeographic": [], "precincts": [], "holds": []} for mode in frame.MODES}
    modes["in_person_early"] = {"qualified": True, "counties": early_ids}
    modes["mail_returned"] = {"qualified": True, "counties": ["separate-mail-inventory"]}
    shard = {"contract": "participation.count_snapshot.v1", "state_code": "IA", "year": 2026,
             "records": records, "views": modes}
    path = "states/IA.json.gz"
    body = frame.compressed(shard)
    current = frame.compressed({"snapshot": {"reporting": []}})
    index = {"states": {"IA": {"file": path, **pin(body), "records": len(records),
             "views": {mode: {"counties": 2, "dispositions": {}} for mode in frame.MODES}}},
             "current_snapshot": {"file": "current.json.gz", **pin(current)},
             "coverage": {"IA": {"unrelated_field": "preserve"}}}
    native = {"county_bindings": {"IA": {"in_person_early": {
        "sha256": bounds["sha256"], "features": len(scopes), "feature_keys": list(scopes),
        "feature_scopes": scopes, "rows": joins}}}}
    return {path: body, "index.json": encoded(index),
            "current.json.gz": current}, {
                "index.json": encoded(native)}


def snapshot(entry):
    return {"congress": {"official_candidate_evidence": {frame.clarity.IDENTITY: entry}}}


def test_cuyahoga_complete_scope_revision_and_failure(tmp_path, monkeypatch):
    parser = frame.county_pdf
    _, native = baseline(facts())
    counts_root = results_intake.ROOT / "data/results-intake/baseline/counts"
    counts = {name: (counts_root / name).read_bytes() for name in ("index.json", "states/OH.json.gz")}
    shard = frame.decode(counts["states/OH.json.gz"])
    early = next(row["view"] for row in shard["records"]
                 if row["view"].get("county_fips") == frame.CUYAHOGA_FIPS
                 and row["id"] in shard["views"]["in_person_early"]["counties"])
    code = "OH"
    bounds = {"feature_keys": [frame.CUYAHOGA_FIPS], "features": 1,
              "feature_scopes": {frame.CUYAHOGA_FIPS: dict(state_code=code, name=parser.COUNTY, boundary_year=2026)},
              "sha256": early["reference_geometry"]["sha256"],
              "rows": [dict(feature_key=frame.CUYAHOGA_FIPS, county_id=early["county_id"])]}
    native["index.json"] = encoded({"county_bindings": {code: {"in_person_early": bounds}}})
    route = parser.REPORT + "20096519-6ca4-4375-b2f3-d07c61762bfb/"
    report = b"fixture PDF body"
    label = parser.STATUSES[0]
    pages = [dict(title=label, election=parser.TITLE, scope=parser.SCOPE,
                  statistics="Total Ballots Cast: 482011, Registered Voters: 878381, Overall Turnout: 54.87%",
                  clock="2026-11-04 05:29:45", page=f"Page: {number} of 2") for number in (1, 2)]
    monkeypatch.setattr(parser, "parse_report", lambda body: copy.deepcopy(pages))
    def collect(previous=None, body=report):
        collector = results_intake.Collector(tmp_path, {parser.IDENTITY: previous},
            {"urls": [], "hosts": [], "prefixes": []}, datetime(2026, 11, 19, tzinfo=timezone.utc))
        index_body = f'<a href="{route}"> {label} </a>'.encode()
        def acquire(url):
            if url == parser.INDEX_URL:
                return index_body, {"origin": "test"}
            assert url.endswith(route)
            if body is None:
                raise ValueError("Incomplete report transport")
            return body, {"origin": "test"}
        collector.acquire = acquire
        return parser.collect(collector)

    def project(previous_counts, previous_native, entry):
        return frame.project_cuyahoga(previous_counts, previous_native, {"granular_sources": {parser.IDENTITY: entry}})

    initial = collect()
    assert initial["status"] == "reported"
    result, mapped, changes = project(counts, native, initial)
    assert changes[0]["current"] == 482011
    after = frame.decode(result["states/OH.json.gz"])
    assert after["records"][:-1] == shard["records"]
    row = after["records"][-1]
    assert row["denominator"]["value"] == 878381 and row["denominator"]["qualified"]
    assert row["view"]["native_printed_pct"] == "54.87%" and row["source_clock"]["literal"] is None
    for mode in ("available", "in_person_early", "mail_returned"):
        assert after["views"][mode] == shard["views"][mode]
    for mode in ("official", "uf_vap", "uf_vep"):
        assert row["id"] in after["views"][mode]["counties"]
        binding = json.loads(mapped["index.json"])["county_bindings"][code][mode]
        assert binding["rows"][-1]["feature_key"] == frame.CUYAHOGA_FIPS
    assert project(result, mapped, collect(initial)) == (result, mapped, [])
    for outage in ({}, {"status": "source_stopped", "data": None}):
        held, same_map, updates = project(result, mapped, outage)
        assert updates[0]["current"] == 482011 and updates[0]["source_status"] == "retained_after_failure"
        assert same_map == mapped and project(held, same_map, outage) == (held, same_map, [])
        assert project(held, same_map, initial)[:2] == (result, mapped)
    with pytest.raises(ValueError, match="reported source is missing"):
        project(result, mapped, {"status": "reported"})
    for value, fraction, clock in [(482111, "54.89", "2026-11-05 05:29:45"),
                                  (481911, "54.86", "2026-11-06 05:29:45")]:
        for page in pages:
            page.update(clock=clock, statistics=f"Total Ballots Cast: {value}, Registered Voters: 878381, Overall Turnout: {fraction}%")
        initial = collect(initial, body=str(value).encode())
        assert initial["status"] == "reported"
        result, mapped, changes = project(result, mapped, initial)
        assert changes[0]["current"] == value
    pages.pop()
    rejected = collect(initial)
    assert rejected["status"] == "retained_after_failure"
    assert "page sequence" in rejected["error_detail"]
    result, mapped, changes = project(result, mapped, rejected)
    assert changes[0]["current"] == 481911 and changes[0]["source_status"] == "retained_after_failure"
    assert project(result, mapped, collect(initial, body=None)) == (result, mapped, [])


@pytest.mark.parametrize("delta", [0, -205, 200])
def test_wilson_uses_positioned_countywide_cells_not_candidate_totals(delta):
    parser = frame.county_pdf
    ballots, registered = 57_775 + delta, 115_323
    rate = (100 * Decimal(ballots) / registered).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    values = ("UNOFFICIAL RESULTS", str(registered), str(ballots), str(1_158 + delta),
              "35,619", "20,998", "0", f"{rate}%")
    cells = {**parser.WILSON_CELLS, **dict(zip(parser.WILSON_VALUES, values))}
    page = "".join(f'<div style="position:absolute;left:{x}px;top:{y}px;">{value}</div>'
                   for (x, y), value in reversed(list(cells.items())))
    html = ('<html><body><a name="JR_PAGE_ANCHOR_0_1"></a>' + page
            + '<a name="JR_PAGE_ANCHOR_0_2"></a>Candidate total is 99999</body></html>').encode()
    data = parser.wilson_summary(html)
    assert parser.wilson_controls(data) == (ballots, registered, f"{rate}%", "UNOFFICIAL RESULTS")
    with pytest.raises(ValueError, match="do not reconcile"):
        parser.wilson_summary(html.replace(b">20,998<", b">20,997<"))
    with pytest.raises(ValueError, match="Incomplete Wilson"):
        parser.wilson_summary(html[:-7])


def test_sumner_rejects_disagreement_and_incomplete_reporting():
    parser = frame.county_pdf
    header = ("11/9/2026-10:43:27AM\nElection Date:11/3/2026\nElection Summary Report\n"
              "Sumner County, Tennessee\n2026 General Election\nTNSUMG26\n")
    values = (28277, 1598, 36168, 66043, 145728, "45.32%", 33, 33, 0, 0, 182, 182)
    text = header + "\n".join(f"{key} {value}" for key, value in zip(parser.SUMNER_ROLES, values))

    def view(body, dpi):
        return parser.sumner_view({"text": body, "receipt": {
            "dpi": dpi, "page": 1, "rotation_degrees": 0, "text_angle_classifier_enabled": False}})

    data = {"date": "2026-11-09T10:43:27",
            "report": {"url": "https://www.votesumnertn.org/uploads/files/" + "a" * 40 + ".pdf",
                       **pin(b"report")},
            "complete_native_query": [view(text, dpi) for dpi in (180, 240)]}
    assert parser.sumner_controls(data) == ("2026-11-09T10:43:27", 66043, 145728, "45.32%")
    data["complete_native_query"][1] = view(text.replace("66043", "66042"), 240)
    with pytest.raises(ValueError, match="passes disagree"):
        parser.sumner_controls(data)
    partial = text.replace("#OFPRECINCTSREPORTED: 33", "#OFPRECINCTSREPORTED: 32")
    data["complete_native_query"] = [view(partial, dpi) for dpi in (180, 240)]
    with pytest.raises(ValueError, match="completeness"):
        parser.sumner_controls(data)


def test_summit_binds_complete_counted_modes_to_county_summary():
    parser = frame.county_pdf
    labels = zip(parser.SUMMIT_MODES, ("18,367", "302", "1,160", "0", "194", "200", "0"))
    cover = "11/17/2026 Summit County General Election 11/3/26 Final Ballot Summary Number of Ballots Counted: 20,223"
    form = (
        "68.8% Voter turnout\n29,388 Active voters (use only the number given to counties)\n"
        "20,223 Total ballots counted\n" + "\n".join(f"{value} {label}" for label, value in labels)
        + "\n20,223 Vote histories given\nYes Does total ballots counted match the number of voters given vote history in VISTA?"
        + "\n200 Provisional ballots counted\nStandardized Canvass Statistics Report\nCounty Name - November 3, 2026"
    )
    summary = (
        "Summit County General Election November 3, 2026 OFFICIAL RESULTS General 2026 County Summary Results "
        "STATISTICS TOTAL Registered Voters - Total 29,388 20,223Ballots Cast - Total Voter Turnout - Total 68.81% "
        "General 2026 County Summary Results - 11/17/2026 05:50PM"
    )
    path = "/DocumentCenter/View/27896/2026-General-Canvass-Packet-executed-revised"
    index = f'<p><strong>Official results for the 2026 General Election:</strong></p><ul><li><a href="{path}">Canvass Packet</a></li></ul>'
    assert parser.summit_discovery(index.encode()).endswith(path)
    with pytest.raises(ValueError, match="destination"):
        parser.summit_discovery(index.replace(path, "https://example.test" + path).encode())
    assert parser.summit_pages([cover, form, summary])[:4] == ("2026-11-17T17:50:00", 20223, 29388, "68.81%")
    for changed in (form.replace("18,367", "18,366"), form.replace("29,388", "29,387")):
        with pytest.raises(ValueError, match="do not reconcile"):
            parser.summit_pages([cover, changed, summary])
    with pytest.raises(ValueError, match="scope changed"):
        parser.summit_pages([cover, form, summary.replace("Summit County", "Other County")])


def test_sussex_selects_certified_county_summary_and_validates_ballot_modes():
    parser = frame.county_pdf
    path = "/DocumentCenter/View/4874/2026-NOV-3-GE---OFFICIAL-results---countywide-SUPP"
    index = (f'<h2><strong>2026 November 3 General Election</strong></h2><p><a href="{path}">'
             "<strong>OFFICIAL Results</strong> - Countywide Summary</a> (certified 11/18/2026)</p>")
    url, date = parser.sussex_discovery(index.encode())
    assert url.endswith(path) and date == "11/18/2026"
    for changed in (index.replace("Countywide Summary", "District Report"),
                    index.replace(path, "//example.com" + path)):
        with pytest.raises(ValueError):
            parser.sussex_discovery(changed.encode())
    stats = (
        "Countywide OFFICIAL RESULTSSussex County, New Jersey General Election Summary Results ReportNovember 3, 2026 "
        "Statistics TOTAL Election Day Early Voting Mail-InProvisional Emergenc y Overseas "
        "Election Day Precincts Reporting 119 of 119 119 0 0 0 0 0 Precincts Complete 119 of 119 119 0 0 0 0 0 "
        "Registered Voters - Total 112,512 57,818Ballots Cast - Total 38,037 11,227 8,145 294 1 114 "
        "Voter Turnout - Total 51.39% Election Summary - 11/18/2026 01:44PM 14Page 1 of"
    )
    assert parser.sussex_statistics(stats, date) == (
        "2026-11-18T13:44:00", 57818, 112512, "51.39%",
        dict(zip(parser.SUSSEX_MODES, (38037, 11227, 8145, 294, 1, 114))), 119)
    for old, new in (("119 of 119", "118 of 119"), ("38,037", "38,036"),
                     ("51.39%", "51.38%"), ("11/18/2026", "11/17/2026")):
        with pytest.raises(ValueError):
            parser.sussex_statistics(stats.replace(old, new), date)


def test_douglas_discovery_and_certified_county_scope():
    parser = frame.county_pdf
    path = "/Archive.aspx?ADID=3836"
    index = (f'<h1>November 3, 2026 Election Results</h1><ul><li><a href="{path}">'
             "Results County-wide</a> - COMPLETE</li></ul>")
    url = parser.douglas_discovery(index.encode())
    assert url.endswith(path)
    with pytest.raises(ValueError, match="summary link"):
        parser.douglas_discovery(index.replace(path, "//example.test" + path).encode())
    header = ("Summary Results Report General Election November 3, 2026 CERTIFIED RESULTS "
              "26 of 26 Reporting COMPLETE Douglas County, Wisconsin")
    stats = ("Statistics TOTAL Registered Voters - Total 26,599 Ballots Cast - Total 19,423 "
             "Voter Turnout - Total 73.02%")
    footer = "Election Summary - 11/10/2026 10:37 AM {} of 2 Report generated with Electionware Copyright © 2007-2019"
    pages = [f"{header} {stats} {footer.format(1)}", f"{header} {footer.format(2)}"]
    data = {"date": "2026-11-10T10:37:00", "report": {"url": url, **pin(b"fixture")},
            "complete_native_query": pages}
    assert parser.douglas_controls(data) == ("2026-11-10T10:37:00", 19423, 26599, "73.02%", 26)
    for edit in (lambda text: text.replace("CERTIFIED RESULTS", "UNOFFICIAL RESULTS"),
                 lambda text: text.replace("73.02%", "73.01%"),
                 lambda text: text.replace("1 of 2", "2 of 2")):
        with pytest.raises(ValueError):
            parser.douglas_controls({**data, "complete_native_query": [edit(pages[0]), pages[1]]})


def revised_ballots(value, delta):
    value = copy.deepcopy(value)
    value["version"] = str(int(value["version"]) + 1)
    county = "Linn"
    index = value["status"]["P"].index(county)
    value["status"]["B"][index] += delta
    for table in (value["sum"]["Contests"], value["summary"]):
        next(row for row in table if row["K"] == "1000")["BC"] += delta
    lines = value["text_report"].splitlines()
    for i, line in enumerate(lines):
        cells = re.split(r"\s{2,}", line.strip())
        if len(cells) == 4 and cells[0] in (county, "Total:") and cells[-1].endswith("%"):
            cells[2] = str(int(cells[2]) + delta)
            rate = (Decimal(cells[2]) * 100 / Decimal(cells[1])).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP)
            cells[3] = f"{rate}%"
            lines[i] = "  ".join(cells)
    value["text_report"] = "\n".join(lines)
    return value


def test_county_frame_replaces_selections_not_observations_and_has_no_rate(tmp_path):
    value = facts()
    original, maps = baseline(value)
    entry, _ = capture(tmp_path, value)
    assert entry["status"] == "reported"
    counts, native, changes = frame.project(original, maps, snapshot(entry))
    before = frame.decode(original["states/IA.json.gz"])
    after = frame.decode(counts["states/IA.json.gz"])
    assert len(changes) == 100
    assert after["records"][:len(before["records"])] == before["records"]
    new = {row["id"]: row for row in after["records"][len(before["records"]):]}
    selected = after["views"]["official"]["counties"]
    assert len(selected) == 99 and sum(new[key]["count"]["value"] for key in selected) == 1382511
    assert all(new[key]["denominator"] is None and new[key]["view"]["reported_pct"] is None
               for key in selected)
    assert {new[key]["view"]["county"]: new[key]["count"]["value"] for key in selected
            if new[key]["view"]["county"] in ("Linn County", "Marion County")} == {
                "Linn County": 107512, "Marion County": 16379}
    bindings = json.loads(native["index.json"])["county_bindings"]["IA"]
    for mode in frame.MODES:
        assert after["views"][mode]["counties"] == selected
        assert {item["feature_key"] for item in bindings[mode]["rows"]} == set(bindings[mode]["feature_keys"])
    for mode in ("in_person_early", "mail_returned"):
        assert after["views"][mode] == before["views"][mode]
    state, = frame.decode(counts["current.json.gz"])["snapshot"]["reporting"]
    assert json.loads(counts["index.json"])["current_snapshot"] == {
        "file": "current.json.gz", **pin(counts["current.json.gz"])}
    assert state["ballots"] == 1382511 and state["registered"] == 2178374
    assert state["source_update_label"] is None and state["source_publication_label"]
    assert frame.project(counts, native, snapshot(entry)) == (counts, native, [])


def test_revised_ballots_flow_through_shared_collector_and_outage_keeps_last_good(tmp_path):
    value = facts()
    counts, native = baseline(value)
    entry, _ = capture(tmp_path / "first", value)
    counts, native, _ = frame.project(counts, native, snapshot(entry))
    for delta in (7, -13):
        value = revised_ballots(value, delta)
        entry, _ = capture(tmp_path / value["version"], value, entry)
        assert entry["status"] == "reported", entry.get("error")
        counts, next_native, changes = frame.project(counts, native, snapshot(entry))
        assert next_native == native
        assert sorted(row["current"] - row["previous"] for row in changes
                      if row["current"] != row["previous"]) == [delta, delta]
    failure, _ = capture(tmp_path / "outage", None, entry)
    assert failure["status"] == "retained_after_failure"
    retained, retained_native, changes = frame.project(counts, native, snapshot(failure))
    assert retained_native == native and len(changes) == 100
    assert all(row["current"] == row["previous"] and row["source_status"] == "retained_after_failure"
               for row in changes)
    assert frame.project(retained, native, snapshot(failure)) == (retained, native, [])
    assert frame.project(retained, native, snapshot(entry))[:2] == (counts, native)


def test_binding_does_not_accept_unreviewed_county_selection(tmp_path):
    value = facts()
    counts, native = baseline(value)
    index = json.loads(native["index.json"])
    index["county_bindings"]["IA"]["in_person_early"]["rows"][0]["feature_key"] = "19003"
    entry, _ = capture(tmp_path, value)
    with pytest.raises(ValueError, match="County reference"):
        frame.project(counts, {"index.json": encoded(index)}, snapshot(entry))


@pytest.mark.parametrize("missing", [{}, {"status": "source_stopped"}])
def test_missing_source_data_marks_only_existing_iowa_frame_retained(tmp_path, missing):
    value = facts()
    initial, initial_native = baseline(value)
    unavailable = snapshot(missing) if missing else {}
    assert frame.project(initial, initial_native, unavailable) == (initial, initial_native, [])
    entry, _ = capture(tmp_path, value)
    counts, native, _ = frame.project(initial, initial_native, snapshot(entry))

    kept, kept_native, changes = frame.project(counts, native, unavailable)
    assert kept_native == native and len(changes) == 100
    before = frame.decode(counts["states/IA.json.gz"])
    after = frame.decode(kept["states/IA.json.gz"])
    for row in before["records"]:
        if row["source"]["id"] == frame.clarity.IDENTITY:
            row["source"]["fields"]["status"] = row["view"]["status"] = "retained_after_failure"
    assert after == before
    state, = frame.decode(kept["current.json.gz"])["snapshot"]["reporting"]
    assert state["status"] == "retained_after_failure"
    assert state["source_version"] == entry["data"]["source_version"]
    assert frame.project(kept, kept_native, unavailable) == (kept, kept_native, [])
    assert frame.project(kept, kept_native, snapshot(entry))[:2] == (counts, native)


def test_reported_source_without_facts_is_an_integrity_failure():
    with pytest.raises(ValueError, match="missing its facts"):
        frame.project({}, {}, snapshot({"status": "reported"}))


def test_reviewed_retained_capture_bootstraps_only_a_dated_count_frame(tmp_path, monkeypatch):
    from scripts import results_intake
    from scripts.participation_intake.contract import IntakeError

    source = frame.clarity
    path = results_intake.ROOT / source.RETAINED_CAPTURE
    if not path.is_file():
        pytest.skip("Retained collector bootstrap input is not part of this runtime-only archive")
    saved = source.document(path.read_bytes())
    counts, native = baseline(saved["data"]["native_facts"])
    collector = results_intake.Collector(
        tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
        source.datetime.fromisoformat(saved["first_observed_at"]))

    def incomplete(url):
        collector.guard(url)
        assert url == source.URL
        raise IntakeError("source_access", "Source did not return a complete successful original")

    monkeypatch.setattr(collector, "acquire", incomplete)
    held = source.collect(collector)
    assert held["reviewed_retained_capture"] is True
    assert held["first_observed_at"] == saved["first_observed_at"]
    assert held["status"] == "retained_after_failure"
    projected, mapping, changes = frame.project(counts, native, snapshot(held))
    state, = frame.decode(projected["current.json.gz"])["snapshot"]["reporting"]
    assert len(changes) == 100
    assert len(json.loads(mapping["index.json"])["county_bindings"]["IA"]["official"]["rows"]) == 99
    assert state["ballots"] == 1382511 and state["validated_pct"] is None
    assert state["status"] == "retained_after_failure"
    assert frame.project(projected, mapping, snapshot(held)) == (projected, mapping, [])
    held["first_observed_at"] = "2026-11-19T00:00:00+00:00"
    with pytest.raises(ValueError, match="retained capture pin"):
        frame.project(counts, native, snapshot(held))
    collector.stopped["urls"].append(source.report_url(saved["data"]["source_version"]))
    assert source.collect(collector)["data"] is None
    collector.stopped["urls"].append(source.URL)
    stopped = source.collect(collector)
    assert stopped["status"] == "source_stopped" and stopped["data"] is None
