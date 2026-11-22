import pytest

from scripts import new_mexico_precinct_reference_audit as audit


@pytest.mark.parametrize(("county", "label", "code"), [
    ("Rio Arriba", "PREC 001", "1"),
    ("Colfax", "003", "3"),
    ("Hidalgo", "PRECINCT 7- LORDSBURG NORTH/WEST", "7"),
    ("Sandoval", "PCT 051A", "51A"),
])
def test_native_identifier_decoding(county, label, code):
    assert audit.label_code(county, label) == code


def test_does_not_infer_identifier_from_other_county_label():
    with pytest.raises(ValueError, match="Unrecognized turnout label"):
        audit.label_code("Sandoval", "PRECINCT 7 - OTHER")


def test_screen_retains_both_unmatched_sides_and_source_counts():
    ref = {("dona ana", "1"): ("35013000001", True),
           ("sandoval", "51"): ("35043000051", False),
           ("sandoval", "2"): ("35043000002", True)}
    rows = [{"county": county, "county_id": "01", "unit": unit, "source_reported_count": ballots,
             "source_eligible_voters": eligible, "rate_hold": hold}
            for county, unit, ballots, eligible, hold in (
                ("Doña Ana", "PCT 01", 11, 12, ""), ("Sandoval", "PCT 051", 0, -3, "held"),
                ("Hidalgo", "PCT 01", 13, 14, ""))]
    summary, screen = audit.screen_year(2022, ref, rows)
    assert (summary["matched_keys"], summary["matched_valid_polygons"],
            summary["matched_source_ballots"], summary["source_ballots"]) == (2, 1, 11, 24)
    assert [row["disposition"] for row in screen] == ["key_only", "key_only", "turnout_only", "reference_only"]
    assert screen[1]["eligible"] == -3 and screen[1]["rate_hold"] == "held"
    assert screen[2]["ballots"] == 13 and "ballots" not in screen[3]
    assert not any(row["election_day_geometry_verified"] for row in screen)
    with pytest.raises(ValueError, match="Ambiguous turnout key"):
        audit.screen_year(2022, ref, rows + [{**rows[0], "unit": "0001"}])


def test_reference_inventory_fails_closed(tmp_path):
    (tmp_path / "20240703.zip").write_bytes(b"not the original")
    with pytest.raises(ValueError, match="Changed reference original"):
        audit.reference_body("20240703", tmp_path)
    first = ["sandoval", "043", "000051", "35043000051", True]
    duplicate = ["sandoval", "043", "51", "3504351", False]
    with pytest.raises(ValueError, match="Conflicting GIS reference identifier"):
        audit.reference_index([first, duplicate], 2)


def test_symbolic_checkpoint_pointer_is_rejected_without_fetch():
    with pytest.raises(ValueError, match="commit-pinned"):
        audit.accepted_entries("https://raw.githubusercontent.com/hanshanley/voter-participation/results-data/latest.json")
