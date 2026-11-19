import copy
from datetime import datetime, timezone
import gzip
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import pytest

from scripts import protected_official_house as protected
from scripts import protected_official_wyoming as official
from scripts import results_intake, results_official_congress
from scripts.participation_intake.contract import encoded, pin
from test_protected_official_house import original, seed, snapshot


ROOT = Path(__file__).resolve().parents[1]


def facts():
    paths = (ROOT / official.FACTS_PATH,
             ROOT.parent / "inputs/reviewed-protected-house-sources" / official.FACTS_PATH)
    path = next((path for path in paths if path.is_file()), None)
    assert path is not None, "Complete selected native Wyoming facts must be packaged"
    return json.loads(gzip.decompress(path.read_bytes()))


def changed(delta=0):
    value = facts()
    for table, addresses in ((value["tables"][0], {"B5", "B28"}),
                             (value["tables"][1], {"H5", "H28"})):
        for row in table["rows"]:
            for cell in row["cells"]:
                if cell["address"] in addresses:
                    cell["value"] += delta
                    cell["cached_literal"] = str(cell["value"])
    return value


def native(value=None):
    value = value or facts()
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relationship = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    workbook = ET.Element("workbook", {"xmlns": namespace, "xmlns:r": relationship})
    sheets = ET.SubElement(workbook, "sheets")
    relations = ET.Element(
        "Relationships", {"xmlns": "http://schemas.openxmlformats.org/package/2006/relationships"})
    contents = {}
    for index, name in enumerate(official.SHEETS, 1):
        ET.SubElement(sheets, "sheet", {"name": name, "sheetId": str(index), "r:id": f"rId{index}"})
        ET.SubElement(relations, "Relationship", {
            "Id": f"rId{index}", "Target": f"worksheets/sheet{index}.xml",
            "Type": relationship + "/worksheet"})
        sheet = ET.Element("worksheet", {"xmlns": namespace})
        data = ET.SubElement(sheet, "sheetData")
        for row in value["tables"][index - 1]["rows"] if index <= 2 else []:
            element = ET.SubElement(data, "row", {"r": str(row["row"])})
            selected = copy.deepcopy(row["cells"])
            if index == 2 and row["row"] == 3:
                selected.append({"address": "N3", "value": "Governor", "formula": None})
            for cell in selected:
                attributes = {"r": cell["address"]}
                decoded = cell["value"]
                if isinstance(decoded, str):
                    attributes["t"] = "inlineStr"
                item = ET.SubElement(element, "c", attributes)
                if isinstance(decoded, str):
                    ET.SubElement(ET.SubElement(item, "is"), "t").text = decoded
                elif decoded is not None:
                    ET.SubElement(item, "v").text = str(decoded)
        contents[f"xl/worksheets/sheet{index}.xml"] = ET.tostring(sheet)
    contents["xl/workbook.xml"] = ET.tostring(workbook)
    contents["xl/_rels/workbook.xml.rels"] = ET.tostring(relations)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, body in contents.items():
            archive.writestr(zipfile.ZipInfo(name), body)
    bulk = io.BytesIO()
    with zipfile.ZipFile(bulk, "w") as archive:
        for name in official.MEMBERS:
            archive.writestr(zipfile.ZipInfo(name), output.getvalue())
    return bulk.getvalue()


def entry(value=None):
    data = official.from_facts(value or facts())
    return {"status": "reported", "data": data,
            "source": {"url": official.URL, **data["native_facts"]["original"]},
            "first_observed_at": "2026-11-18T00:00:00Z"}


def reviewed_seed():
    value = seed()
    value["protected_official_house_review"] = protected.prepare_review(value, original(), facts())
    return value


def test_complete_minor_write_in_and_ballot_roles_reproduce():
    parsed = official.parse(native())
    assert protected.from_facts(parsed["native_facts"]) == parsed
    race = parsed["races"][0]
    assert {party: sum(row["votes"] for row in race["candidates"] if row["party_group"] == party)
            for party in "DRO"} == {"D": 61689, "R": 99906, "O": 22659}
    write_in = next(row for row in race["candidates"] if row["role"] == "generic_write_in")
    assert write_in["votes"] == 1031 and write_in["literal_party"] == ""
    assert race["contest_total"] == 184254
    assert race["native_contest_controls"]["overvotes"] == 1231
    assert race["native_contest_controls"]["undervotes"] == 6228
    assert race["native_contest_controls"]["ballots"] == 191713
    assert len(race["native_contest_controls"]["counties"]) == 23
    assert race["reported_units"] is race["total_units"] is race["complete_reporting"] is None
    assert race["source_update_label"] is parsed["source_updated_at"] is None
    assert parsed["participation_observation_qualified"] is False


@pytest.mark.parametrize("table,address,value", [
    (0, "B1", "Primary Election - 2026"), (1, "G3", "Governor"),
    (1, "K4", "Other"), (1, "L4", "Write-Ins"), (1, "H4", "Unknown (X)"),
    (1, "H5", None), (1, "H5", True), (1, "H5", -1),
    (1, "H5", 2**53), (1, "H28", 61690), (0, "B28", 191714),
    (1, "A5", "Different county"),
])
def test_wrong_election_roles_missing_unsafe_and_conflicting_counts_hold(table, address, value):
    selected = facts()
    cell = next(cell for row in selected["tables"][table]["rows"]
                for cell in row["cells"] if cell["address"] == address)
    cell["value"] = value
    cell["cached_literal"] = str(value) if type(value) is int else None
    with pytest.raises(ValueError):
        official.from_facts(selected)


@pytest.mark.parametrize("delta", [7, -13])
def test_actual_workbook_corrections_and_outage_keep_last_good(tmp_path, delta):
    first_body = native()
    collector = results_intake.Collector(
        tmp_path, {}, {"urls": [], "hosts": [], "prefixes": []},
        datetime(2026, 11, 18, tzinfo=timezone.utc))
    collector.acquire = lambda url: (
        first_body, {"url": url, "origin": "new_source_response", **pin(first_body)})
    first = official.collect(collector)
    assert first["status"] == "reported"
    collector.prior = {official.IDENTITY: first}
    revised_body = native(changed(delta))
    collector.acquire = lambda url: (
        revised_body, {"url": url, "origin": "new_source_response", **pin(revised_body)})
    revised = official.collect(collector)
    assert revised["status"] == "reported"
    assert revised["data"]["races"][0]["candidates"][1]["votes"] == 61689 + delta
    collector.prior = {official.IDENTITY: revised}

    def failed(url):
        raise OSError("Official workbook unavailable")

    collector.acquire = failed
    retained = official.collect(collector)
    assert retained["status"] == "retained_after_failure"
    assert retained["source"] == revised["source"] and retained["data"] == revised["data"]
    assert retained["first_observed_at"] == revised["first_observed_at"]


def test_both_protected_frames_and_original_science_are_bound():
    value = reviewed_seed()
    assert set(value["protected_official_house_review"]["states"]) == {"HI", "WY"}
    observed = snapshot(value)
    observed["congress"]["official_candidate_evidence"][official.IDENTITY] = entry(changed(7))
    before = copy.deepcopy(observed)
    projected = protected.project_snapshot(observed, value)
    assert observed == before and projected["congress"] == observed["congress"]
    assert [row for row in projected["house_candidates"] if row["state_code"] not in ("HI", "WY")] == [
        row for row in observed["house_candidates"] if row["state_code"] not in ("HI", "WY")]
    assert next(row for row in projected["house_candidates"]
                if row["state_code"] == "WY" and row["party"] == "Democratic")["votes"] == "61696"
    broken = copy.deepcopy(value)
    broken["protected_official_house_review"]["states"]["WY"]["accepted_guard"]["guard_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        protected.project_snapshot(observed, broken)


@pytest.mark.parametrize("delta", [7, -13])
def test_all_nine_models_recondition_without_refitting_or_provider_substitution(delta):
    from scripts.automatic_estimates import build
    value = reviewed_seed()
    observed = snapshot(value)
    observed["congress"]["official_candidate_evidence"][official.IDENTITY] = entry(changed(delta))
    result = build(observed, value)
    decision = next(row for row in result["decisions"]["states"] if row["state_code"] == "WY")
    assert decision["decision"] == "changed_recompute_behavioral"
    assert decision["provider_bridge"] is False and decision["accepted_official_scope_preserved"]
    paths = [path for path in result["artifacts"] if path.startswith("house/")
             and path.endswith("/complete-result.json.gz")]
    assert len(paths) == 9
    for path in paths:
        row = next(row for row in result["artifacts"][path]["content"]["rows"]
                   if row["state_code"] == "WY")
        assert row["reported_comparison"]["current"] == {
            "D": 61689 + delta, "R": 99906, "O": 22659}
        assert row["reported_comparison"]["current_native_clock"] is None
        assert "unassigned write-ins" in row["reported_comparison"]["current_source_scope"]
        assert "source-unassigned write-ins retained" in row["reported_comparison"][
            "current_native_control_scope_qualification"]
    advanced = result["artifacts"]["rolling/next-seed.json.gz"]["content"]
    repeat = build(snapshot_with_wyoming(advanced, entry(changed(delta))), advanced)
    assert next(row for row in repeat["decisions"]["states"] if row["state_code"] == "WY")[
        "decision"] == "retained_fresh_unchanged"
    failed = entry(changed(delta))
    failed["status"] = "retained_after_failure"
    retained = build(snapshot_with_wyoming(advanced, failed), advanced)
    for path in paths:
        a = next(row for row in retained["artifacts"][path]["content"]["rows"]
                 if row["state_code"] == "WY")
        b = next(row for row in repeat["artifacts"][path]["content"]["rows"]
                 if row["state_code"] == "WY")
        assert a["point"] == b["point"]
        for key in ("current", "previous", "current_native_clock"):
            assert a["reported_comparison"][key] == b["reported_comparison"][key]


def snapshot_with_wyoming(value, supplied):
    observed = snapshot(value)
    observed["congress"]["official_candidate_evidence"][official.IDENTITY] = supplied
    return observed


def test_registered_dispatch_source_export_and_zero_participation_leakage(tmp_path):
    assert official.IDENTITY in results_official_congress.source_ids(results_official_congress.WY_CONFIG)
    collector = results_intake.Collector(
        tmp_path, {}, {"urls": [], "hosts": [], "prefixes": []},
        datetime(2026, 11, 18, tzinfo=timezone.utc))
    body, calls = native(), []

    def acquire(url):
        calls.append(url)
        return body, {"url": url, "origin": "new_source_response", **pin(body)}

    collector.acquire = acquire
    collected = results_official_congress.collect_sources(
        collector, results_official_congress.WY_CONFIG, selected=[official.IDENTITY])
    assert calls == [official.URL] and collected[official.IDENTITY]["status"] == "reported"
    assert results_intake.numeric_observations(
        {"index.json": encoded({"states": {}})}, collected) == []


def test_original_source_pins_cannot_be_substituted():
    value = reviewed_seed()
    policy = value["protected_official_house_review"]["states"]["WY"]
    supplied = entry()
    supplied["source"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="original"):
        protected.current(supplied, policy)
    broken = copy.deepcopy(value)
    broken["protected_official_house_review"]["states"]["WY"]["original"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="original"):
        protected.validate_review(broken["protected_official_house_review"], broken)


def test_explicit_native_zero_is_preserved_and_duplicate_identity_is_rejected():
    selected = facts()
    adjustments = {0: {"B5": -55, "B28": -55}, 1: {"K5": -55, "K28": -55}}
    for table, addresses in adjustments.items():
        for row in selected["tables"][table]["rows"]:
            for cell in row["cells"]:
                if cell["address"] in addresses:
                    cell["value"] += addresses[cell["address"]]
                    cell["cached_literal"] = str(cell["value"])
    data = official.from_facts(selected)
    assert data["races"][0]["native_contest_controls"]["counties"][0]["house_columns"]["K"] == 0
    duplicate = facts()
    cells = duplicate["tables"][1]["rows"][4]["cells"]
    cells.append(copy.deepcopy(cells[0]))
    with pytest.raises(ValueError, match="ambiguous"):
        official.from_facts(duplicate)
