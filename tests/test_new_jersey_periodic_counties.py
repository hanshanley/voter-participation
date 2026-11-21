import pytest

from scripts import new_jersey_periodic_counties as nj


def test_index_selects_latest_general_only():
    def link(day):
        return f'<a href="assets/pdf/periodic-report/2026/2026-{day}-essex-periodic-report.pdf">Report</a>'

    links = nj.links(("<h3>2026 General Election</h3>" + link("1118") + link("1117")
                      + "<h3>2026 Special Election</h3>" + link("1119")).encode())
    assert links["Essex"][0].isoformat() == "2026-11-18"


def test_components_preserve_disagreements_and_missing_cells():
    def row(name, ev, ed, mail, provisional):
        cells = [name, *[""] * 12]
        for i, x in zip(nj.COLUMNS, (ev, ed, mail, provisional), strict=True):
            cells[i] = x
        return cells

    headings = ["11/18/26 4:23 PM", *[""] * 12]
    for i, value in nj.GROUPS.items():
        headings[i] = value
    table = {"heading": headings, "columns": ["", *nj.LABELS], "status": "UNOFFICIAL", "rows": [
        row("Essex County", "", "", "", ""),
        row("Municipality TOTALS", "12", "23", "45", ""),
        row("Congressional TOTALS", "12", "23", "44", "9"),
    ]}
    feed = "NJ-2026-essex-periodic-components"
    report = {"url": nj.BASE + "2026-1118-essex-periodic-report.pdf", "bytes": 17, "sha256": "a" * 64}
    data = {"county": "Essex", "date": "2026-11-18T16:23:00", "posted_edition": "2026-11-18",
            "report": report, "complete_native_query": [table]}
    rows = list(nj.exports({feed: {"status": "retained_after_failure", "data": data}}))
    assert [r["reported_component"] for r in rows] == [12, 23, None, None]
    assert rows[2]["hold_reason"] == "printed_component_controls_disagree"
    assert rows[3]["hold_reason"] == "fewer_than_two_reported_component_controls"
    assert all(r["not_all_mode_ballots_or_turnout_rate"] for r in rows)
    table["columns"][3] = "Ballots Issued"
    with pytest.raises(ValueError, match="component order changed"):
        list(nj.exports({feed: {"status": "reported", "data": data}}))
