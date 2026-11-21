from shapely.geometry import Polygon, box

from scripts.nc_precinct_reference import audit


def test_reference_does_not_draw_contained_supplement_or_parent():
    parent, split, neighboring = ("WAKE", "A"), ("WAKE", "A.1"), ("WAKE", "B")
    invalid = ("WAKE", "C")
    counts = {parent: 200, split: 25, neighboring: 230, invalid: 50}
    primary = {parent: box(0, 0, 10, 10), neighboring: box(10, 0, 20, 10),
               invalid: Polygon([(30, 0), (40, 10), (40, 0), (30, 10), (30, 0)])}
    decisions, accepted = audit(counts, primary, {split: box(1, 1, 5, 5)})
    assert set(accepted) == {neighboring}
    assert {row[1]: row[4] for row in decisions} == {
        "A": "overlapping_geometry", "A.1": "overlapping_geometry",
        "B": "reference_count_only", "C": "invalid_geometry",
    }
