import copy
import gzip
import io
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from scripts import congressional_geography as geography


@pytest.fixture(scope="module")
def reviewed():
    root = Path(__file__).resolve().parents[1]
    return geography.load_review(root, include_split_geometry=False)


def test_unordered_blocks_preserve_leading_zeroes_and_unassigned_records():
    rows = (b"GEOID,CDFP\n090019900000001,ZZ\n010010201001001,03\n"
            b"010010201001000,03\n")
    ordered = b"GEOID,CDFP\n010010201001000,03\n010010201001001,03\n090019900000001,ZZ\n"
    actual = geography.membership(io.BytesIO(rows), 119)
    assert actual == geography.membership(io.BytesIO(ordered), 119)
    assert actual["01"]["03"]["blocks"] == 2 and actual["09"]["ZZ"]["blocks"] == 1
    with pytest.raises(ValueError, match="Duplicate Census block"):
        geography.membership(io.BytesIO(rows + b"010010201001000,03\n"), 119)


@pytest.mark.parametrize("record", [
    b"010010201001000,02,001,020100,1000,03",
    b"010010201001000,01,001,020100,1000,3",
    b"10010201001000,01,001,020100,1000,03",
    b"010010201001000,01,001,020100,1000,03,extra",
])
def test_current_components_widths_and_extra_fields_fail_closed(record):
    with pytest.raises(ValueError):
        geography.membership(io.BytesIO(
            b"GEOID,STATEFP,COUNTYFP,TRACTCE,BLOCKCE,CDFP\n" + record + b"\n"), 120)


def test_regional_copies_are_verified_not_added_or_assumed_consistent():
    def archive(regional):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as stream:
            stream.writestr("NationalCD119.txt", "GEOID,CDFP\n010010201001000,03\n")
            stream.writestr("01_AL_CD119.txt", regional)
        return output.getvalue()
    result, _ = geography.archive_membership(
        archive("GEOID,CDFP\n010010201001000,03\n"), 119)
    assert result["01"]["03"]["blocks"] == 1
    with pytest.raises(ValueError, match="Regional Census BEF"):
        geography.archive_membership(archive("GEOID,CDFP\n010010201001000,04\n"), 119)


def test_block_changes_preserve_transfers_unassigned_missing_and_equal_net_movement():
    past = b"GEOID,CDFP\n010010201001002,01\n010010201001000,01\n010010201001001,02\n"
    current = (b"GEOID,STATEFP,COUNTYFP,TRACTCE,BLOCKCE,CDFP\n"
               b"010010201001003,01,001,020100,1003,01\n"
               b"010010201001002,01,001,020100,1002,ZZ\n"
               b"010010201001001,01,001,020100,1001,01\n")
    districts = {f"AL-{code}": {"state_fips": "01", "district_code": code,
                                "previous_membership": {"blocks": before},
                                "current_membership": {"blocks": after},
                                "whole_block_membership_equal": False,
                                "affected_split_blocks": []}
                 for code, before, after in (("01", 2, 2), ("02", 1, 0))}
    with sqlite3.connect(":memory:") as database:
        rows = list(geography.block_changes(io.BytesIO(past), io.BytesIO(current), database))
    blocks, counties, summary = geography.CHANGE_FILES
    result = geography.change_tables({"decisions": districts}, rows)
    assert result[blocks][1] == [
        ("010010201001000", "01001", "01", None),
        ("010010201001001", "01001", "02", "01"),
        ("010010201001002", "01001", "01", "ZZ"),
        ("010010201001003", "01001", None, "01"),
    ]
    assert result[counties][1] == [("01001", "", "01", 1), ("01001", "01", "", 1),
                                  ("01001", "01", "ZZ", 1), ("01001", "02", "01", 1)]
    assert result[summary][1] == [("AL-01", 2, 2, 2, 2, 0, 0), ("AL-02", 1, 0, 0, 1, 0, 0)]
    with pytest.raises(ValueError, match="inventory does not reconcile"):
        geography.change_tables({"decisions": districts}, rows[:-1])


@pytest.mark.parametrize("congress", [119, 120])
def test_block_changes_reject_duplicate_blocks_in_either_edition(congress):
    past = b"GEOID,CDFP\n010010201001000,01\n"
    current = (b"GEOID,STATEFP,COUNTYFP,TRACTCE,BLOCKCE,CDFP\n"
               b"010010201001000,01,001,020100,1000,01\n")
    if congress == 119:
        past += b"010010201001000,01\n"
    else:
        current += b"010010201001000,01,001,020100,1000,01\n"
    with sqlite3.connect(":memory:") as database, pytest.raises(
            ValueError, match=f"Duplicate Census block identity in CD{congress}"):
        list(geography.block_changes(io.BytesIO(past), io.BytesIO(current), database))


def test_complete_review_reconciles_real_split_tables_and_corrected_missouri(reviewed):
    assert reviewed is not None
    root = Path(__file__).resolve().parents[1] / geography.DIRECTORY
    for congress in (119, 120):
        assert geography.split_blocks((root / f"CD{congress}_BlockSplits.pdf").read_bytes(),
                                      congress) == reviewed["split_blocks"][str(congress)]
    decisions = reviewed["decisions"]
    assert len(decisions) == 435 and not any(key.startswith(("DC-", "PR-")) for key in decisions)
    assert all(decisions[f"MO-0{seat}"]["boundary_compatible"] for seat in range(1, 9))
    for seat in ("07", "08"):
        row = decisions["CO-" + seat]
        assert row["whole_block_membership_equal"] and not row["boundary_compatible"]
        assert row["holds"] == ["split_block_geometry_unresolved"]
    assert decisions["CO-06"]["boundary_compatible"]
    assert decisions["AL-03"]["boundary_compatible"]
    assert decisions["AL-01"]["holds"] == ["changed_2020_block_membership"]


def test_florida_water_proof_preserves_donor_and_all_other_decisions(reviewed):
    root = Path(__file__).resolve().parents[1]
    verified = geography.water_evidence(root, reviewed)
    candidate = geography.apply_water_evidence(reviewed, verified)
    assert geography.validate_review(candidate) is candidate
    changed = {district for district, decision in candidate["decisions"].items()
               if reviewed["decisions"][district] != decision}
    assert changed == {"FL-03", "FL-06"}
    assert all(candidate["decisions"][district]["boundary_compatible"] for district in changed)
    assert all(not candidate["decisions"][district]["boundary_compatible"]
               for district in ("FL-11", "FL-12"))
    altered = copy.deepcopy(candidate)
    altered["decisions"]["FL-03"]["affected_split_blocks"] = ["120830010031087"]
    with pytest.raises(ValueError, match="Water-only review differs"):
        geography.validate_review(altered)
    altered = copy.deepcopy(verified)
    altered["districts"]["FL-03"]["block"] = "120830010031088"
    with pytest.raises(ValueError, match="Unresolved land"):
        geography.apply_water_evidence(reviewed, altered)


@pytest.mark.parametrize("change", ["promotion", "fingerprint", "split", "inventory", "version", "source"])
def test_review_changes_cannot_silently_grant_comparison_eligibility(reviewed, change):
    value = copy.deepcopy(reviewed)
    if change == "promotion":
        value["decisions"]["CO-07"].update(boundary_compatible=True, holds=[])
    elif change == "fingerprint":
        value["national_memberships"]["120"]["01"]["03"]["sha256"] = "f" * 64
    elif change == "split":
        value["split_blocks"]["120"][0]["geoid"] = "0800100960720010"
    elif change == "inventory":
        del value["national_memberships"]["120"]["01"]["03"]
    elif change == "version":
        value["version"] = "unreviewed"
    else:
        value["evidence"]["cd120.zip"]["url"] = "https://example.test/plan.zip"
    with pytest.raises(ValueError):
        geography.validate_review(value)
    assert geography.validate_review(reviewed) is reviewed


def test_changed_review_body_and_changed_originals_refuse_loading(tmp_path, reviewed, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    path = tmp_path / geography.REVIEW_PATH
    path.parent.mkdir(parents=True)
    original = (root / geography.REVIEW_PATH).read_bytes()
    value = copy.deepcopy(reviewed)
    value["split_blocks"]["119"] = []
    path.write_bytes(gzip.compress(json.dumps(value).encode()))
    with pytest.raises(ValueError, match="Changed reviewed House boundary policy"):
        geography.load_review(tmp_path, include_split_geometry=False)
    path.write_bytes(original)
    for name in geography.NAMES:
        (path.parent / name).symlink_to(root / geography.DIRECTORY / name)
    assert geography.load_review(tmp_path, include_split_geometry=False) == reviewed
    (path.parent / "cd120.zip").unlink()
    (path.parent / "cd120.zip").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Changed original Census evidence"):
        geography.load_review(tmp_path, include_split_geometry=False)
