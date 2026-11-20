import pytest

from scripts.legacy_tiger_counties import boundary_area


def chain(tlid, start, end):
    a, b = start
    c, d = end
    return f"11006{tlid:10d}1{' ' * 174}{a:+010d}{b:+09d}{c:+010d}{d:+09d}".encode()


def square(first=1):
    nodes = [(0, 0), (1_000_000, 0), (1_000_000, 1_000_000), (0, 1_000_000), (0, 0)]
    return [chain(i, a, b) for i, (a, b) in enumerate(zip(nodes, nodes[1:]), first)]


def test_closed_chains_make_a_county_without_dropping_shape_points():
    intermediate = b"-000100000+00500000" + b"+000000000+00000000" * 9
    rt2 = b"21006         4  1" + intermediate
    result = boundary_area(b"\n".join(square()), rt2)
    assert result["type"] == "Polygon"
    assert [-0.1, 0.5] in result["coordinates"][0]


def test_open_and_duplicate_county_boundary_chains_are_rejected():
    rows = square()
    with pytest.raises(ValueError, match="closed county linework"):
        boundary_area(b"\n".join(rows[:-1]), b"")
    with pytest.raises(ValueError, match="Duplicate TIGER"):
        boundary_area(b"\n".join([*rows, rows[0]]), b"")
