import json
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts import house_water_screen as screen


def test_one_land_witness_rejects_but_incomplete_water_cannot_pass():
    ids = [f"12001000100{i:04d}" for i in range(25)]

    def fetch(url):
        condition = parse_qs(urlsplit(url).query)["where"][0]
        selected = condition.split("'")[1::2]
        return json.dumps({"features": [{"attributes": {
            "GEOID": key, "AREALAND": 1 if key == ids[0] else 0,
            "AREAWATER": 10, "HU100": 0, "POP100": 0,
            "LWBLKTYP": "B" if key == ids[0] else "W", "VINTAGE": "70"
        }} for key in selected]}).encode()

    results, _ = screen.screen({
        "land": ids[:2], "water": ids[1:3], "not_exhaustive": ids[1:],
    }, fetch)
    assert [row["screen"] for row in results] == [
        "not_water_only", "all_changes_water", "incomplete_water_evidence"]
    assert results[0]["first_nonwater_witness"] == ids[0]
    assert not any(row["comparison_qualified_by_screen"] for row in results)


def test_census_response_must_match_requested_ids():
    with pytest.raises(ValueError, match="inventory differs"):
        screen.attributes(b'{"features":[]}', ["120010001000000"])
