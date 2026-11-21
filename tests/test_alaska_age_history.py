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
