from copy import deepcopy

import pytest

from scripts import maryland_current_cards as md


def report():
    names = [name if name in {"Baltimore City", "Baltimore County"} else name + " County"
             for name in md.COUNTIES]
    return {"rows": [
        {"native_county_label": name, "native_cards_cast": "50", "native_eligible_voters": "100",
         "native_percentage": "50.00%", "reported_source_units": 2, "expected_source_units": 2}
        for name in names
    ] + [{"native_county_label": "Total", "native_cards_cast": "1,200", "native_eligible_voters": "2,400",
          "native_percentage": "50.00%", "reported_source_units": None, "expected_source_units": None}]}


def test_current_card_report_needs_complete_geographies_and_same_report_arithmetic():
    baseline = report()
    assert md.query(baseline)[-1]["reported_cards_cast"] == 1200
    for key, candidate, error in (
        ("reported_source_units", 1, "coverage"),
        ("native_percentage", "50.01%", "fraction"),
        ("native_county_label", "Baltimore", "roster"),
        ("native_eligible_voters", "80", "fraction"),
    ):
        changed = deepcopy(baseline)
        changed["rows"][0][key] = candidate
        with pytest.raises(ValueError, match=error):
            md.query(changed)
    baseline["rows"][-1].update(native_cards_cast="1,201", native_percentage="50.04%")
    with pytest.raises(ValueError, match="statewide"):
        md.query(baseline)
