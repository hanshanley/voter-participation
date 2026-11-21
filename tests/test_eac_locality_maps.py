from shapely.geometry import box

from scripts.eac_locality_maps import bind, draw


def test_reference_requires_name_and_code_and_keeps_zero_shaded():
    rows = [
        {"native_fips": "2300327855", "native_name": "GLENWOOD PLT",
         "reported_counted_ballot_participants": "0", "same_report_registration_fraction_pct": "0.0"},
        {"native_fips": "2301955225", "native_name": "OLD ORCHARD BEACH",
         "reported_counted_ballot_participants": "90", "same_report_registration_fraction_pct": "60.0"},
    ]
    geometry = {
        "2300327855": ("Glenwood", "Glenwood plantation", box(0, 0, 100, 100)),
        "2301955225": ("Old Town", "Old Town city", box(100, 0, 200, 100)),
    }
    decisions, matched, shapes = bind("ME", rows, geometry)
    assert [r["reference_map_decision"] for r in decisions] == [
        "matched_reference", "name_disagrees_with_subdivision_code",
    ]
    svg = draw("ME", matched, shapes, rate=True)
    assert "GLENWOOD PLT: 0.00%" in svg
    assert "OLD ORCHARD BEACH: 60.00%" not in svg
