from datetime import datetime, timezone
import json

import pytest

from scripts import collect_census_county_reference as census, results_intake as intake


def test_batch_keeps_last_good_on_wrong_vintage_and_access_hold(tmp_path, monkeypatch):
    pytest.importorskip("shapely", minversion="2.1")
    root = census.ROOT + "tigerWMS_ACS2024/MapServer"
    edition = root + "?f=json"
    layer = root + "/82?f=json"
    geometry = {
        "type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {"GEOID": "45001", "STATE": "45", "BASENAME": "Abbeville"},
            "geometry": {"type": "Polygon", "coordinates": [[[-83, 34], [-82, 34], [-82, 35], [-83, 34]]]},
        }],
    }
    service = {"serviceDescription": "January 1, 2024 vintage", "layers": [{"name": "Counties", "id": 82}]}
    details = {
        "name": "Counties", "geometryType": "esriGeometryPolygon",
        "description": "Counties; January 1, 2024 vintage",
        "fields": [{"name": name} for name in ("GEOID", "STATE", "BASENAME")],
    }
    profiles = [{"state": "SC", "state_fips": "45", "counties": ["Abbeville"], "years": [2024]}]
    state = {"urls": [], "prefixes": [], "hosts": []}
    calls = []

    def acquire(_, spec, *, access_guard):
        url = spec["url"]
        access_guard(url)
        calls.append(url)
        if url == edition:
            data = service
        elif url == layer:
            data = details
        else:
            assert url.startswith(root + "/82/query?")
            data = geometry
        body = json.dumps(data).encode()
        return body, {"origin": "fixture", **intake.pin(body)}

    monkeypatch.setattr(intake.Store, "acquire", acquire)

    def capture(prior=None):
        collector = intake.Collector(tmp_path, prior or {}, state, datetime.now(timezone.utc))
        return census.capture_batch(collector, profiles)

    identity = "SC-2024-county-reference"
    before = capture()
    assert before[identity]["status"] == "reported"
    assert capture(before) == before
    data = before[identity]["data"]
    display = tmp_path / data["display"]["file"]
    assert intake.pin(display.read_bytes())["sha256"] == data["display"]["sha256"]
    details["description"] = "Counties; January 1, 2022 vintage"
    calls.clear()
    rejected = capture(before)[identity]
    assert calls == [edition, layer]
    assert rejected["status"] == "retained_after_failure"
    assert rejected["error"] == "county_layer_not_verified" and rejected["data"] == data
    state["urls"].append(edition)
    calls.clear()
    stopped = capture(before)[identity]
    assert not calls and stopped["error"] == "source_stopped" and stopped["data"] == data


def test_profile_rejects_duplicate_editions_before_collection():
    profile = {"state": "SC", "state_fips": "45", "counties": ["Abbeville"], "years": [2024]}
    with pytest.raises(ValueError, match="Duplicate requested"):
        census.requested([profile, profile])
    with pytest.raises(ValueError, match="Invalid reviewed"):
        census.requested([{**profile, "years": [2008]}])
