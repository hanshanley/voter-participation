import pytest

from scripts import alaska_age_history as ak


def report(year):
    template = ["100", "40", "50", "60", "20", "30"]
    groups = [[age, [[role, count, ""] for role, count in zip(ak.ROLES, template)]]
              for age in (*ak.AGES, "75+")]
    groups.append(["TOTALS", [[role, str(int(count) * len(groups)), ""]
                               for role, count in zip(ak.ROLES, template)]])
    return groups


def test_suppresses_known_conflicting_rates_without_dropping_counts():
    groups = report(2004)
    groups[-1][1][4][1] = "243"
    data = ak.facts(groups, 2004, None)
    feed = "AK-2004-general-age-voter-history"
    entry = {"source": {"url": ak.source(2004), "sha256": "a" * 64}, "status": "reported", "data": data}
    rows = list(ak.exports({feed: entry}))
    assert len(rows) == 39
    assert sum(row["history_per_registered"] is None for row in rows) == 13
    assert next(row for row in rows if row["age_group"] == "TOTALS"
                and row["reported_gender"] == "male")["voter_history_credits"] == 243
    with pytest.raises(ValueError, match="statewide controls"):
        ak.facts(groups, 2006, None)


def test_rejects_missing_age_and_mislabeled_registration():
    groups = report(2006)
    with pytest.raises(ValueError, match="Incomplete Alaska age history"):
        ak.facts(groups[1:], 2006, None)
    groups[0][1][0][0] = "VOTED"
    with pytest.raises(ValueError, match="reported-gender role"):
        ak.facts(groups, 2006, None)


def modern_report(year):
    rows = []
    labels = ("UNKNOWN DOB", *(age.replace("-", " THRU ") for age in ak.AGES), "ABOVE 75", "TOTALS")
    for label in labels:
        multiplier = len(labels) - 1 if label == "TOTALS" else 1
        for role, value, pct in zip((label, *ak.GENDERS, "VOTED", *ak.GENDERS),
                                    (100, 40, 50, 10, 50, 20, 25, 5),
                                    ("", "40.00", "50.00", "10.00",
                                     "45.00" if label == "TOTALS" else "50.00", "40.00", "50.00", "10.00")):
            count = str(value * multiplier)
            rows.append([role, count, pct, [count] + ["0"] * (len(ak.MODERN[year][2].split()) - 1)])
    return rows


def test_modern_age_exports_keep_explicit_unknowns_and_withhold_only_disputed_fraction():
    rows = modern_report(2022)
    data = ak.modern_facts(rows, 2022, "2022-11-30")
    feed = "AK-2022-general-age-voter-history"
    entry = {"source": {"url": ak.source(2022), "sha256": "a" * 64}, "status": "retained_after_failure", "data": data}
    exported = {(row["age_group"], row["reported_gender"]): row for row in ak.exports({feed: entry})}
    total = exported["TOTALS", "all"]
    assert total["history_per_registered"] is None
    assert total["source_reported_percent"] == "45.00"
    assert (total["registered_in_report"], total["voter_history_credits"]) == (1300, 650)
    unknown = exported["UNKNOWN DOB", "unknown"]
    assert unknown["history_per_registered"] == "0.50000000"
    assert unknown["source_status"] == "retained_after_failure"


def test_modern_age_rejects_corrupted_details_or_incomplete_roster():
    rows = modern_report(2018)
    with pytest.raises(ValueError, match="Incomplete Alaska age"):
        ak.modern_facts(rows[:-8], 2018, "2019-09-13")
    rows[0][3][0] = "99"
    with pytest.raises(ValueError, match="printed controls"):
        ak.modern_facts(rows, 2018, "2019-09-13")
