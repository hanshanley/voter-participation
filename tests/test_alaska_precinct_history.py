import csv
import io
from pathlib import Path

import pytest

from scripts import alaska_precinct_history as ak


def test_source_fields_agree_across_offices_and_are_not_summed_over_candidates():
    def body(second=5):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["Pct_Id", "Precinct_name", "Aggregation_ID", "Contest_title", "Contest_Id", *ak.FIELDS])
        first = ["01-600", "01-600 Ketchikan", "", ak.OFFICES[0], "1", 10, 5, 5, 0, 0, 0, 0]
        writer.writerows([first, first, ["01-600", "01-600 Ketchikan", "", ak.OFFICES[1], "2",
                                         10, second, second, 0, 0, 0, 0]])
        return stream.getvalue().encode()

    assert ak.parse_units(body()) == [["01-600 Ketchikan", "01-600", 10, 5, 5, 0, 0, 0, 0]]
    with pytest.raises(ValueError, match="between contests"):
        ak.parse_units(body(6))


def test_complete_mode_roster_and_control_include_unallocated_ballots():
    rows = [["01-600 Ketchikan", "01-600", 10, 5, 5, 0, 0, 0, 0],
            [ak.OVERSEAS, "99-999", 2, 1, 0, 1, 0, 0, 0]]
    for district in range(1, 41):
        for mode in ak.MODE_NAMES:
            rows.append([f"District {district} - {mode}", "", 0, 0, 0, 0, 0, 0, 0])
    control = ["2", "2", "6", "12", "50.00", "11/30/2024 4:00:37 PM"]
    ak.validate(rows, control)
    with pytest.raises(ValueError, match="complete official statewide"):
        ak.validate(rows[:-1], control)
    with pytest.raises(ValueError, match="complete official statewide"):
        ak.validate(rows, ["2", "2", "7", "12", "58.33", control[-1]])


@pytest.mark.parametrize("first,rate", [(52, "50.05%"), (50, "50.00%"), (48, "49.95%")])
def test_current_unit_revisions_require_literal_json_and_pdf_controls(first, rate):
    rows = [[f"01-{i:03d} Name {i}", f"01-{i:03d}", 10, 5, 5, 0, 0, 0, 0] for i in range(402)]
    rows[0][2:5] = [100, first, first]
    precincts = sorted([identity, label[len(identity) + 1:], ballots, registered]
                       for label, identity, registered, ballots, *_ in rows)
    rows += [[ak.OVERSEAS, "99-999", 2, 1, 0, 1, 0, 0, 0]]
    for district in range(1, 41):
        for mode in ak.MODE_NAMES:
            rows.append([f"District {district} - {mode}", "", 0, 0, 0, 0, 0, 0, 0])
    total, registered = sum(row[3] for row in rows), sum(row[2] for row in rows)
    pdf = {"page_clocks_and_ordinals": [["11/18/2026 5:25:35 PM", "1", "1"]],
           "statewide_header": ["401", "401", "100.00%", str(total), str(registered), rate, ak.current.STATUS[0]]}
    native = {"updated": "11/18/2026 5:56 PM", "certified": False,
              "federal_controls": [{"office": office, "b": total, "v": registered, "p": 403, "r": 401}
                                   for office in ak.current.OFFICES]}
    assert ak.current_reconcile(rows, pdf, native, precincts)["voters"] == total
    precincts[0][2] += 1
    with pytest.raises(ValueError, match="literal native roster"):
        ak.current_reconcile(rows, pdf, native, precincts)


def test_geometry_gate_reports_changed_and_unavailable_without_changing_counts():
    def fields(status, source):
        return ak.geometry_export({"display_geometry_check": {"status": status, "source": source}})

    receipt = {"url": ak.GEOMETRY_URL, **ak.GEOMETRY_PIN}
    assert fields("reported", receipt)["display_geometry_status"] == "verified_display_subset"
    assert fields("reported", {**receipt, "sha256": "a" * 64})["display_geometry_status"] == "geometry_changed"
    stopped = fields("source_stopped", None)
    assert stopped["display_geometry_status"] == "source_stopped" and stopped["display_geometry_sha256"] is None
    with pytest.raises(ValueError, match="Invalid Alaska geometry"):
        fields("reported", {**receipt, "url": ak.CURRENT_JSON})


def test_midterm_continuation_checks_edition_and_excludes_candidate_tables(monkeypatch):
    class Page(str):
        def extract_text(self):
            return self

    edition = "11/30/2022 2:11:57 PM"
    first = (
        f"{ak.MIDTERM_TABLE}State State of Alaska 36-001 Goldstream No. 1 10 5 5 50.00% "
        f"{ak.MIDTERM_IDENTITY} Statement of Votes Cast November 8 , 2022 OFFICIAL RESULTS {edition} Page: 1 of 3"
    )
    second = (
        f"{ak.MIDTERM_TABLE}District 36 - Absentee 0 1 1 N/A District 36 - Early Voting 0 1 1 N/A "
        f"District 36 - Question 0 0 0 N/A State of Alaska - Total 10 7 7 70.00% "
        f"State - Total 10 7 7 70.00% {edition} Page: 2 of 3"
    )
    pages = [Page(first), Page(second), None]
    monkeypatch.setattr(ak, "midterm_document", lambda _: pages)
    report = ak.midterm_district(b"", 36)
    assert report["rows"][0] == ["36-001 Goldstream No. 1", 10, 5, 5, "50.00%"]
    assert report["total"] == [10, 7, 7, "70.00%"]
    pages[1] = Page(second.replace("Page: 2 of 3", "Page: 3 of 3"))
    with pytest.raises(ValueError, match="continuation"):
        ak.midterm_district(b"", 36)
    pages[1] = Page(second.replace("State - Total 10 7 7 70.00%", "State - Total 10 8 8 80.00%"))
    with pytest.raises(ValueError, match="totals disagree"):
        ak.midterm_district(b"", 36)


def test_midterm_districts_reconcile_separate_registrations_and_central_modes():
    ctl = {"precincts_reported": 41, "registered": 405, "ballots": 281}
    districts = {str(n): {"rows": [[f"{n:02d}-001 Precinct", 10, 5, 5, "50.00%"],
                                 *([f"District {n} - {mode}", 0, count, count, "N/A"]
                                   for mode, count in zip(ak.MODE_NAMES, (1, 1, 0), strict=True))],
                          "total": [10, 7, 7, "70.00%"]} for n in range(1, 41)}
    districts["99"] = {"rows": [[ak.OVERSEAS, 5, 1, 1, "20.00%"]], "total": [5, 1, 1, "20.00%"]}
    ak.reconcile_midterm(districts, ctl)
    with pytest.raises(ValueError, match="statewide control"):
        ak.reconcile_midterm(districts, {**ctl, "ballots": ctl["ballots"] - 1})
    districts["1"]["rows"][-1][0] = "District 1 - Remote"
    with pytest.raises(ValueError, match="geography or mode"):
        ak.reconcile_midterm(districts, ctl)


def test_reviewed_midterm_archive_provides_complete_count_only_fallback():
    from scripts import retained_bulk_turnout as retained

    original = (Path(ak.__file__).resolve().parents[1] / retained.INPUT).read_bytes()
    stopped = {ak.MIDTERM_FEED: {"status": "source_unavailable", "data": None}}
    entries = retained.historical_entries(stopped, original)
    rows = list(ak.midterm_exports(entries))
    assert len(rows) == 522 and sum(row["reported_ballots"] for row in rows) == 267_047
    assert sum(row["reported_ballots"] for row in rows
               if row["unit_scope"] == "precinct_election_day_only") == 167_836
    assert all(not row["all_mode_precinct_rate_qualified"] and not row["precinct_geometry_verified"] for row in rows)
    assert {row["latest_acquisition_status"] for row in rows} == {"source_unavailable"}
    accepted = {**entries[ak.MIDTERM_FEED], "status": "reported"}
    assert retained.historical_entries({ak.MIDTERM_FEED: accepted}, original)[ak.MIDTERM_FEED] is accepted
