from copy import deepcopy

import pytest

from scripts.nm_precinct_reference import bind, draw


def fixture():
    common = {"county": "San Juan", "county_id": "45", "source_clock": "11/20/2026 4:02 PM MT"}
    rows = [{"geography_level": "county", **common, "count": 90, "registered": 180}]
    features = []
    for precinct, (code, offset) in enumerate(zip(("35045002", "35045001", " "), (0, 0.02, 0.04)), 1):
        x, y = -108.2 + offset, 36.7
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [
                [[x, y], [x + 0.01, y], [x + 0.01, y + 0.01], [x, y + 0.01], [x, y]]]},
            "properties": {"OBJECTID": precinct, "State": "35", "County": "45", "PctTxt": str(precinct),
                           "Pct2026": precinct, "PctCode": code, "Split_fr1": 0, "Split_fr2": 0},
        })
        rows.append({"geography_level": "reporting_unit", **common, "unit": f"PRECINCT {precinct:03d}",
                     "count": 30, "registered": 60})
    return features, rows


def test_reference_does_not_color_conflicting_ids_or_invent_legacy_codes():
    features, rows = fixture()
    decisions, shapes = bind(features, rows, expected=3)
    assert [r["decision"] for r in decisions] == [
        "conflicting_compound_code", "conflicting_compound_code", "reference_count_only",
    ]
    assert [r["gis_compound_code"] for r in decisions] == ["35045002", "35045001", " "]
    svg = draw(decisions, shapes)
    assert svg.count('fill="#eceeef"') == 2
    assert "Precinct 003: 30 reported participants" in svg


def test_held_roster_and_count_differences_do_not_leak_into_the_map():
    features, rows = fixture()
    broken = deepcopy(rows)
    broken[1]["count"] += 1
    with pytest.raises(ValueError, match="reconcile"):
        bind(features, broken, expected=3)
    broken = deepcopy(features)
    broken[2]["properties"]["PctTxt"] = "04"
    broken[2]["properties"]["Pct2026"] = 4
    with pytest.raises(ValueError, match="rosters differ"):
        bind(broken, rows, expected=3)
    features[0]["geometry"] = features[2]["geometry"]
    decisions, _ = bind(features, rows, expected=3)
    assert decisions[2]["decision"] == "overlapping_geometry"
