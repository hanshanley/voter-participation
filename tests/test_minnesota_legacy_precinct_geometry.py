import pytest

from scripts.minnesota_legacy_precinct_geometry import identity_reason, overlaps


def test_legacy_precinct_geometry_requires_matching_count_identity_and_unique_polygon():
    date = "2010-11-02"
    row = {"VTDID": "271370005", "COUNTYCODE": "69", "COUNTYNAME": "Saint Louis",
           "PCTNAME": "Example W1 P2", "TOTVOTING": 120}
    record = {"NUMBER_": 271370005, "COUNTYCODE": 69, "COUNTY": "St. Louis",
              "PRECINCT": "EXAMPLE W-1 P-2", "TOTALVOTER": 120}
    match = (record, None)
    assert identity_reason(row, [match], date) is None
    assert identity_reason(row, [], date) == "missing_polygon"
    assert identity_reason(row, [match, match], date) == "duplicate_polygon_id"
    assert identity_reason(row, [({**record, "COUNTYCODE": 68}, None)], date) == "gis_identity_disagrees"
    assert identity_reason(row, [({**record, "PRECINCT": "Example W1 P3"}, None)], date) == "gis_name_disagrees"
    assert identity_reason(row, [({**record, "TOTALVOTER": 119}, None)], date) == "gis_voter_count_disagrees"


def test_legacy_precinct_geometry_ignores_shared_edges_but_holds_both_overlapping_shapes():
    box = pytest.importorskip("shapely.geometry").box
    assert overlaps({"a": box(0, 0, 1, 1), "b": box(1, 0, 2, 1), "c": box(1.5, 0, 3, 1)}) == {"b", "c"}
