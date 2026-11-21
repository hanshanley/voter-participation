import pytest

from scripts import results_connecticut_congress as ct


def fixture():
    ids = {str(i): f"Town {i}" for i in range(1, 170)}
    parties = {code: {"CD": code, "NM": code} for code in ("D", "R", "WF", "WI")}
    contest_keys = ["10" + str(i) for i in range(1, 6)]
    candidates = {"d": ("Dem", "D"), "d2": ("Dem", "WF"), "r": ("Rep", "R"), "w": ("Named", "WI")}
    lookup = {
        "election": {"ID": "108", "DT": "11/03/2026", "ET": "G", "EC": "SE"},
        "townIds": ids, "partyIds": parties,
        "candidateIds": {key: {"NM": name, "P": party, "AD": "not part of the aggregate query"}
                         for key, (name, party) in candidates.items()},
        "officeList": [{key: {"ID": key, "OT": "C", "D": str(i),
                             "DT": f"Connecticut 0{i}", "NM": f"Representative in Congress {i}"}}
                       for i, key in enumerate(contest_keys, 1)],
    }

    def rows(counts):
        return [{key: {"V": str(value)}} for key, value in counts.items()]

    totals = {"d": 12, "d2": 1, "r": 7, "w": 1}
    parent = {"ID": "108", "PR": "169 of 169 (100%)", "T": "169 of 169", "PT": "0 of 169"}
    return dict(zip(ct.FILES, (
        lookup, {key: rows(totals) for key in contest_keys},
        {key: rows({"d": 13}) for key in contest_keys}, parent,
        {town: {key: rows(totals) for key in contest_keys} if town == "1" else {} for town in ids},
        {town: {"TS": "( *Unofficial Results )"} for town in ids},
    )))


def test_sources_reconcile_fusion_lines_and_named_write_ins_without_certifying():
    data = ct.normalize(55785, fixture())
    assert len(data["races"]) == 5
    r = data["races"][0]
    assert r["complete_reporting"] and r["native_status_literal"] == "Unofficial Results"
    assert r["contest_total"] == 21
    assert [(row["votes"], row["ballot_line_ids"], row["write_in"]) for row in r["candidates"]] == [
        (13, ["d", "d2"], False), (7, ["r"], False), (1, ["w"], True)]
    assert len(r["native_ballot_lines"]) == 4 and "AD" not in repr(r["native_ballot_lines"])


@pytest.mark.parametrize("changed,detail", [
    ("townVotes_Electiondata", "town roll-up"),
    ("candidateGrouping_Electiondata", "fusion total"),
])
def test_reject_conflicts_in_separate_controls(changed, detail):
    source = fixture()
    if changed == "townVotes_Electiondata":
        source[changed]["1"]["101"][0]["d"]["V"] = "14"
    else:
        source[changed]["101"][0]["d"]["V"] = "14"
    with pytest.raises(ValueError, match=detail):
        ct.normalize(55785, source)
