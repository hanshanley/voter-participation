from pathlib import Path

import pytest

from scripts import idaho_turnout_history as idaho, retained_bulk_turnout


def test_selects_general_history_and_checks_each_denominator_separately():
    header = "<tr>" + "".join(f"<th>{cell}</th>" for cell in idaho.HISTORY_HEADER) + "</tr>"
    rows = "".join(f"<tr><td>{year}</td><td>200</td><td>100</td><td>50</td>"
                   "<td>50.00%</td><td>26.00%</td></tr>" for year in range(2024, 1979, -2))
    body = (f'<h4>General Election - November 5, 2024</h4>'
            f'<a href="{idaho.BOOK}">Data for turnout</a><h4>May Primary</h4>'
            f'<h3>General Elections (1980-2024)</h3><table>{header}{rows}</table>'
            f'<h3>Primary Elections (1980-2024)</h3><table>{header}</table>').encode()
    result = list(idaho.statewide_rows(idaho.index(body)))
    assert len(result) == 23 and result[0]["election_date"] == "2024-11-05"
    assert result[0]["registered_reconciled_pct"] == 50
    assert result[0]["vap_reconciled_pct"] is None
    with pytest.raises(ValueError, match="Incomplete Idaho"):
        idaho.index(body.replace(b"<td>2004</td>", b"<td>2006</td>"))


def test_pool_retains_counts_but_withholds_local_rates_and_checks_both_rollups(monkeypatch):
    monkeypatch.setattr(idaho, "COUNTIES", {"Boise", "Ada"})
    native = [["Boise County", "1", 10, 0, 10, 3, 0.3],
              ["Boise County", "#90 Absentee", 0, 0, 0, 6, None],
              ["Boise County", "Total", 10, 0, 10, 9, 0.9],
              ["Ada County", 1, 10, 0, 10, 3, 0.3],
              ["Ada County", "Total", 10, 0, 10, 3, 0.3]]
    state = {"registered_voters": 20, "ballots_cast": 12}
    rows = list(idaho.local_rows(native, state))
    assert [row["reconciled_pct"] for row in rows] == [None, None, 90, 30, 30]
    assert rows[0]["rate_hold"] == "county_has_separately_reported_absentee_ballots"
    assert rows[1]["ballots_cast"] == 6 and rows[1]["source_printed_fraction"] is None
    with pytest.raises(ValueError, match="roll-up differs"):
        list(idaho.local_rows(native, {**state, "ballots_cast": 11}))
    with pytest.raises(ValueError, match="county control"):
        list(idaho.local_rows(native[:1] + native[2:], state))
    with pytest.raises(ValueError, match="duplicate"):
        list(idaho.local_rows(native + native[:1], state))


def test_pinned_idaho_fallback_preserves_native_rows_and_yields_to_an_accepted_source():
    body = (Path(__file__).resolve().parents[1] / retained_bulk_turnout.INPUT).read_bytes()
    stopped = {idaho.FEED: {"status": "source_stopped"}}
    entries = retained_bulk_turnout.historical_entries(stopped, body)
    state, local = idaho.exports(entries)
    assert len(state) == 23 and {row["source_status"] for row in state + local} == {"retained_after_failure"}
    assert (state[0]["registered_voters"], state[0]["ballots_cast"]) == (1_178_750, 917_469)
    assert len(local) == 1030
    pool = [row for row in local if row["rate_hold"] == "pooled_absentee_reporting_unit"]
    assert all(row["reconciled_pct"] is None for row in pool) and sum(row["ballots_cast"] for row in pool) == 41_062
    accepted = {**entries[idaho.FEED], "status": "reported"}
    assert retained_bulk_turnout.historical_entries({idaho.FEED: accepted}, body)[idaho.FEED] is accepted
