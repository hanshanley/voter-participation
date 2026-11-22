"""Separate 2014-to-2026 recorded comparisons; never replace the 2020 baseline."""

from collections import Counter

from scripts.participation_intake.contract import pin

PATH = "data/results-intake/senate-long-baseline/fec-2014-results.xls"
URL = "https://www.fec.gov/documents/1705/results14.xls"
SHA = "62fa46fc365cc54c3290deda16b0ee2c3e97158adcca020781b3a42396435158"
FRAMES = {"AR": (15, "general", "2014-11-04"), "LA": (17, "general_runoff", "2014-12-06")}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_review(root):
    import xlrd

    body = (root / PATH).read_bytes()
    receipt = pin(body)
    require(receipt["sha256"] == SHA, "Changed 2014 Senate workbook")
    book = xlrd.open_workbook(file_contents=body, on_demand=True)
    try:
        sheet = book.sheet_by_name("2014 US Senate Results by State")
        header = sheet.row_values(0)
        require(header[1:5] == ["STATE ABBREVIATION", "STATE", "D", "FEC ID#"]
                and header[10] == "PARTY" and header[15].strip() == "GENERAL VOTES"
                and header[17] == "GE RUNOFF ELECTION VOTES (LA)", "Changed 2014 Senate table")
        frames = {}
        for state, (column, stage, date) in FRAMES.items():
            candidates, controls = [], []
            for index in range(1, sheet.nrows):
                row = sheet.row_values(index)
                if row[1] != state or row[column] == "":
                    continue
                votes = row[column]
                require(row[3] == "S" and type(votes) is float and votes.is_integer() and votes >= 0,
                        "Unexpected historical Senate office or count")
                if row[9] == "Total State Votes:":
                    controls.append(int(votes))
                    continue
                require(row[8].strip() and row[10] and row[4].strip(), "Missing historical candidate identity")
                candidates.append({"name": row[8].strip(), "party": row[10], "votes": int(votes),
                                   "fec_candidate_id": row[4].strip(), "workbook_row": index + 1})
            require(len(controls) == 1 and sum(row["votes"] for row in candidates) == controls[0]
                    and Counter(row["party"] for row in candidates if row["party"] in "DR") == {"D": 1, "R": 1},
                    "2014 Senate frame does not reconcile")
            frames[state] = {"date": date, "seat": "2", "stage": stage, "candidates": candidates,
                             "candidate_votes": controls[0]}
        return {"source": {"url": URL, **receipt}, "historical_frames": frames}
    finally:
        book.release_resources()


def comparisons(races, candidates, review):
    nominees = Counter((c["id"], c["party_group"]) for c in candidates
                       if c["role"] == "named_candidate")
    result = []
    for row in races:
        state = row["state_code"]
        if (state not in FRAMES or row["id"] != f"npr:senate:{state}:2:regular:general:not_ranked"
                or not row["advertised"] or row["qualified_comparison"]):
            continue
        previous = review["historical_frames"][state]
        counts = {party: sum(c["votes"] for c in previous["candidates"] if c["party"] == party)
                  for party in "DR"}
        counts["O"] = previous["candidate_votes"] - counts["D"] - counts["R"]
        current = {party: row[party] for party in "DROU"}
        holds = []
        if row["status"] != "reported":
            holds.append("Current returns were not refreshed")
        if (row["ranked_choice"] or row["native_runoff"]
                or not row["count_coverage_complete"] or current["U"] != 0
                or any(type(current[p]) is not int or current[p] <= 0
                       or nominees[row["id"], p] != 1 for p in "DR")):
            holds.append("Current regular general-election count frame differs")
        change = (100 * (current["D"] - current["R"]) / (current["D"] + current["R"])
                  - 100 * (counts["D"] - counts["R"]) / (counts["D"] + counts["R"])) if not holds else None
        result.append({"race_id": row["id"], "state_code": state, "seat": "2",
                       "scope": "older_same_seat_recorded_margin_not_last_cycle",
                       "previous_election_date": previous["date"], "current_election_date": row["election_date"],
                       "previous_stage": previous["stage"], "current_stage": row["stage"],
                       "stage_changed": previous["stage"] != row["stage"], "previous_counts": counts,
                       "current_counts": current, "historical_candidates": previous["candidates"],
                       "historical_source": review["source"], "comparison_holds": holds,
                       "margin_change_pp": change, "D_two_party_share_change_pp": None if change is None else change / 2,
                       "replaces_last_cycle": False, "behavioral_estimate_updated": False})
    return result
