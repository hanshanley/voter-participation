import copy
from types import SimpleNamespace

import pytest

from scripts import congressional_baselines as baselines
from scripts import results_congress as congress
from test_results_congress import collect, race, review


def reference(state="AL", seat="2", cycle=2020, stage="general", kind="regular"):
    return {
        "state_code": state, "seat": seat, "cycle_year": cycle,
        "year": cycle + (stage == "general_runoff"), "stage": stage,
        "election_kind": kind, "ranked_choice": False,
        "counts": {"D": 100, "R": 110, "O": 0}, "candidate_facts": [],
        "major_party_nominees": {"D": 1, "R": 1},
        "source_urls": ["https://official.test/bulk"],
    }


def test_latest_reference_is_same_seat_including_special_and_decisive_runoff():
    initial = reference()
    special = reference(cycle=2022, kind="special")
    other_seat = reference(seat="3", cycle=2024)
    history = {"contract": baselines.CONTRACT, "references": [initial, special, other_seat]}
    assert baselines.select_reference(history, "AL", "2") == special
    runoff = reference(cycle=2022, stage="general_runoff", kind="special")
    history["references"].append(runoff)
    assert baselines.select_reference(history, "AL", "2") == runoff
    history["references"].append(copy.deepcopy(runoff))
    with pytest.raises(ValueError, match="Ambiguous"):
        baselines.select_reference(history, "AL", "2")


@pytest.mark.parametrize("independent_hold", ["absent_party", "multiple_nominees", "rcv", "outage"])
def test_new_reference_does_not_remove_an_independent_comparison_hold(tmp_path, independent_hold):
    bodies = {"house": [race()], "senate": [race("senate", seat="2")]}
    result = collect(tmp_path, bodies)
    baseline = reference()
    if independent_hold == "absent_party":
        baseline["counts"]["D"] = 0
        baseline["major_party_nominees"]["D"] = 0
    elif independent_hold == "multiple_nominees":
        baseline["major_party_nominees"]["R"] = 2
    elif independent_hold == "rcv":
        baseline["ranked_choice"] = True
    else:
        for entry in result["races"].values():
            if entry["data"]["chamber"] == "senate":
                entry["status"] = "retained_after_failure"
    rows = congress.comparisons(result, review(), {
        "contract": baselines.CONTRACT, "references": [baseline]})
    senate = next(row for row in rows if row["chamber"] == "senate")
    assert not senate["qualified_comparison"]
    assert senate["raw_recorded_margin_change_pp"] is not None


def test_final_to_final_is_explicit_and_districts_remain_boundary_held(tmp_path):
    result = collect(tmp_path, {"house": [race()], "senate": [race("senate", seat="2")]})
    scientific = review()
    scientific["previous_district_queries"][0]["geographic_boundary_stability_independently_qualified"] = False
    rows = congress.comparisons(result, scientific, {
        "contract": baselines.CONTRACT,
        "references": [reference(stage="general_runoff")]})
    senate = next(row for row in rows if row["chamber"] == "senate")
    assert senate["qualified_comparison"]
    assert senate["baseline"]["previous_stage_differs"]
    assert senate["baseline"]["comparison_policy"].endswith("final_election_to_final_election")
    assert not next(row for row in rows if row["chamber"] == "house")["qualified_comparison"]


def test_complete_queries_keep_reviewed_special_seat_despite_legacy_display_limit(tmp_path):
    result = collect(tmp_path, {"house": [race()],
                                "senate": [race("senate", seat="3", special=True)]})
    policy = {
        "version": "test-reviewed-successor", "candidate_crosswalk": [],
        "legacy_candidates_preserved": [], "states": {}, "Senate_models": {"decision": "held"},
        "historical_senate": {"contract": baselines.CONTRACT, "datasets": [],
                              "references": [reference(seat="3", cycle=2022)]},
    }
    files, descriptor = congress.runtime(result, review(), policy)
    data = congress.decode(files["congressional/results.json.gz"])
    senate = next(row for row in data["races"] if row["chamber"] == "senate")
    assert not senate["qualified_comparison"] and senate["legacy_reader_display_limit"]
    query = congress.decode(files["congressional/queries.json.gz"])
    reviewed = next(row for row in query["reviewed_race_comparisons"] if row["chamber"] == "senate")
    assert reviewed["qualified_comparison"]
    assert reviewed["baseline"]["seat"] == "3" and reviewed["election_kind"] == "special"
    assert senate["raw_recorded_margin_change_pp"] == reviewed["qualified_margin_change_pp"]
    assert "reviewed_analytical_policy" in query
    assert "congressional/congress-candidate-crosswalk.csv" in descriptor["downloads"]


def test_complete_fec_native_sheet_fusion_special_and_zero(tmp_path):
    import openpyxl

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "12. US Senate Results by State"
    header = [None] * 24
    for column, value in ((1, "STATE ABBREVIATION"), (10, "PARTY"),
                          (15, "GENERAL VOTES"), (17, "GENERAL RUNOFF VOTES")):
        header[column] = value
    sheet.append(header)
    for state, office, party, votes in (
            ("OR", "S", "DEM/IP/WF", 125), ("OR", "S", "R", 100),
            ("GA", "S-UNEXPIRED TERM", "D", 0)):
        row = [None] * 24
        row[1], row[3], row[4], row[8], row[10], row[15] = (
            state, office, "native-id-" + state + party, "Native Candidate", party, votes)
        sheet.append(row)
    path = tmp_path / "fec.xlsx"
    book.save(path)
    result = baselines.fec_records(path, 2020)
    assert len(result["native_rows"]) == 4
    assert result["candidate_stage_records"][0]["party_group"] == "D"
    assert result["candidate_stage_records"][0]["literal_party"] == "DEM/IP/WF"
    assert result["candidate_stage_records"][-1]["seat"] == "3"
    assert result["candidate_stage_records"][-1]["votes"] == 0


def test_nebraska_ignores_contents_but_requires_both_complete_tables(tmp_path, monkeypatch):
    import pypdf

    def page(text):
        return SimpleNamespace(extract_text=lambda: text)

    def table(term, header, width):
        return (
            "General Election - November 5, 2024\n"
            "Member of the United States Senate - " + term + " Year Term\n\nCounty\n"
            + header + "\nTotal " + " ".join(["93"] * width) + "\n"
            + "\n".join("County " + chr(65 + i // 26) + chr(65 + i % 26)
                        + " " + " ".join(["1"] * width) for i in range(93))
        )
    texts = [
        page("Table of Contents\nMember of the United States Senate - Six Year Term .... 16"),
        page(table("Six", "Deb Fischer (Republican)\nDan Osborn (By Petition)", 3)),
        page(table("Two", "Pete Ricketts (Republican)\nPreston Love Jr. (Democratic)", 2)),
    ]
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: SimpleNamespace(pages=texts))
    path = tmp_path / "native.pdf"
    path.write_bytes(b"synthetic native reader input")
    result = baselines.nebraska_records(path)
    assert len(result["senate_tables"]) == 2
    assert {row["seat"] for row in result["candidate_stage_records"]} == {"1", "2"}
    texts.pop()
    with pytest.raises(ValueError, match="Both Nebraska"):
        baselines.nebraska_records(path)
