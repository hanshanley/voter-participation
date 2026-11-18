import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from scripts import congressional_geography as geography
from scripts import congressional_split_blocks as split
from scripts.participation_intake.contract import encoded


ROOT = Path(__file__).resolve().parents[1]


def test_real_source_proof_reproduces_without_changing_original_boundary_review():
    original_body = (ROOT / geography.REVIEW_PATH).read_bytes()
    before = geography.load_review(ROOT, include_split_geometry=False)
    extension = split.load_review(ROOT)
    assert split.compile_review(ROOT) == extension
    after = geography.load_review(ROOT)
    assert geography.validate_review(after) is after
    changed = {key for key in before["decisions"]
               if before["decisions"][key] != after["decisions"][key]}
    assert changed == {"CO-07", "CO-08"}
    for key in changed:
        row = after["decisions"][key]
        assert row["boundary_compatible"] and not row["holds"]
        assert not row["behavioral_model_qualified"]
        assert not row["historical_votes_allocated"] and not row["legal_boundary_certification"]
        assert row["previous_membership"] == row["current_membership"]
    assert (ROOT / geography.REVIEW_PATH).read_bytes() == original_body


@pytest.mark.parametrize("failure", ["split", "gap", "overlap", "unexpected", "inventory", "invalid"])
def test_exact_partition_refuses_changed_or_unsupported_geometry(failure):
    from shapely.geometry import Polygon, box
    block = box(0, 0, 2, 2)
    previous = {"AA-01": box(-1, -1, 1, 3), "AA-02": box(1, -1, 3, 3)}
    current = dict(previous)
    declared, inventory = set(previous), set(previous)
    assert split.prove_fragments(block, previous, current, declared, inventory)["proper_split"]
    if failure == "split":
        current = {"AA-01": box(-1, -1, 1.5, 3), "AA-02": box(1.5, -1, 3, 3)}
    elif failure == "gap":
        current["AA-02"] = box(1.5, -1, 3, 3)
    elif failure == "overlap":
        current["AA-02"] = box(0.5, -1, 3, 3)
    elif failure == "unexpected":
        previous["AA-03"] = current["AA-03"] = box(0.5, 0.5, 1.5, 1.5)
        inventory.add("AA-03")
    elif failure == "inventory":
        del current["AA-02"]
    else:
        block = Polygon([(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)])
    with pytest.raises(ValueError):
        split.prove_fragments(block, previous, current, declared, inventory)


@pytest.mark.parametrize("change", ["membership", "cycle", "extra_split", "proof", "promotion"])
def test_review_and_membership_mutations_fail_closed(change):
    original = geography.load_review(ROOT, include_split_geometry=False)
    extension = split.load_review(ROOT)
    if change == "membership":
        original["national_memberships"]["120"]["08"]["07"]["sha256"] = "0" * 64
    elif change == "cycle":
        original["decisions"]["CO-07"]["previous_year"] = 2022
    elif change == "extra_split":
        original["split_blocks"]["120"].append({
            "geoid": "080010096072001", "state_fips": "08",
            "districts": ["07", "08"], "tabulated_with": "07"})
    elif change == "proof":
        extension["geometry_checks"]["exact_fragment_equality"]["CO-07"] = False
    else:
        extension["districts"]["AL-01"] = copy.deepcopy(extension["districts"]["CO-07"])
    with pytest.raises(ValueError):
        split.apply_review(original, extension)


def test_changed_or_missing_originals_refuse_loading_and_metadata_alone_is_insufficient(tmp_path):
    for name in geography.DATA_PATHS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(ROOT / name)
    with pytest.raises(FileNotFoundError):
        geography.load_review(tmp_path)
    for name in split.DATA_PATHS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(ROOT / name)
    assert split.load_review(tmp_path) == split.load_review(ROOT)
    target = tmp_path / split.DIRECTORY / "block.json"
    target.unlink()
    with pytest.raises(FileNotFoundError):
        split.load_review(tmp_path)
    target.write_bytes(b"{}")
    with pytest.raises(ValueError, match="Changed original"):
        split.load_review(tmp_path)
    with pytest.raises(ValueError, match="Changed original"):
        geography.load_review(tmp_path)
    target.write_bytes((ROOT / split.DIRECTORY / "block.json").read_bytes())
    target = tmp_path / split.REVIEW_PATH
    target.unlink()
    review = split.load_review(ROOT)
    review["legal_boundary_certification"] = True
    target.write_bytes(encoded(review))
    with pytest.raises(ValueError, match="Changed reviewed"):
        split.load_review(tmp_path)


def test_export_inventory_includes_all_originals_only_for_extended_review():
    from scripts.congressional_analytical_bridge import data_paths, load_review
    review = load_review(ROOT)
    assert set(split.DATA_PATHS) <= set(data_paths(review))
    del review["house_boundaries"]["split_geometry_review"]
    assert not set(split.DATA_PATHS) & set(data_paths(review))
    assert json.loads((ROOT / split.REVIEW_PATH).read_bytes()) == split.compile_review(ROOT)


def test_actual_scientific_packet_recompiles_split_proof_from_included_originals(tmp_path):
    from scripts import automatic_runtime as runtime
    from scripts.congressional_analytical_bridge import load_review
    compiled = {"counts": {}, "native": {}, "model_files": {},
                "congressional_analytical_review": load_review(ROOT)}
    body = runtime.scientific_package({}, b"", {}, {}, {}, compiled)
    with zipfile.ZipFile(io.BytesIO(body)) as packet:
        for name in packet.namelist():
            if name.startswith(("code/", "inputs/reviewed-congressional-sources/")):
                target = tmp_path / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(packet.read(name))
        assert b"reproduced-split-review.json" in packet.read("REPRODUCE.txt")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.congressional_split_blocks",
         "--repository", str(tmp_path / "inputs/reviewed-congressional-sources"),
         "--output", str(tmp_path / "reproduced-split-review.json")],
        cwd=tmp_path / "code", capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "reproduced-split-review.json").read_bytes() == (
        ROOT / split.REVIEW_PATH).read_bytes()
