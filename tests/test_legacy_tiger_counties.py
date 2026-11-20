import io
import zipfile

import pytest

from scripts.legacy_tiger_counties import ARCHIVE, acquire_modules, boundary_area, build
from scripts.participation_intake.contract import IntakeError, pin


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


def test_acquisition_checks_exact_roster_resumes_and_preserves_stops(tmp_path):
    family = ARCHIVE + "CA/"
    name = "TGR06001.ZIP"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("TGR06001.MET", "Title: TIGER/Line Files, 2006 Second Edition, California, Alameda County")
        archive.writestr("TGR06001.RT1", b"\n".join(square()))
        archive.writestr("TGR06001.RT2", b"")
    original = output.getvalue()
    module = {"fips": "06001", "name": "Alameda", "census_title": "Alameda County"}
    roster = {"state": "CA", "state_name": "California", "state_fips": "06", "modules": [module]}

    class Collector:
        bodies = {}
        blocked = False
        requested = []
        index = f'<a href="{name}">County</a><a href>Missing link</a>'.encode()
        module = original

        def acquire(self, url):
            self.guard(url)
            self.requested.append(url)
            return (self.index if url == family else self.module), {}

        def guard(self, url):
            if self.blocked and url == family + name:
                raise IntakeError("source_stopped", "Stopped module")

    collector = Collector()
    collector.index += b'<a href="TGR06003.ZIP">Unexpected county</a>'
    with pytest.raises(ValueError, match="rosters differ"):
        acquire_modules(collector, roster, tmp_path)
    assert collector.requested == [family]
    collector.index = f'<a href="{name}">County</a>'.encode()
    (tmp_path / name).write_bytes(original)
    collector.requested.clear()
    manifest = acquire_modules(collector, roster, tmp_path)
    assert collector.requested == [family, family + name]
    assert len(build(manifest, tmp_path)["features"]) == 1
    collector.requested.clear()
    pinned = {**roster, "modules": [{**module, **pin(original)}]}
    assert acquire_modules(collector, pinned, tmp_path) == manifest
    assert collector.requested == [family]
    collector.blocked = True
    held = acquire_modules(collector, pinned, tmp_path)
    assert held["modules"] == [] and held["holds"][0]["status"] == "source_stopped"
    assert (tmp_path / name).read_bytes() == original
    with pytest.raises(ValueError, match="complete reviewed roster"):
        build(held, tmp_path)
