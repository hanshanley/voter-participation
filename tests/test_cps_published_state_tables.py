import io
from pathlib import Path
import zipfile

import pytest

from scripts import cps_published_state_tables as cps


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / cps.INPUT_PATH
if not BUNDLE.exists():
    BUNDLE = ROOT.parent / "inputs" / cps.INPUT


def test_published_cells_preserve_native_denominators_and_suppression():
    rows = cps.build(BUNDLE.read_bytes())
    assert len(rows) == 10300
    keyed = {(r["year"], r["source_table"], r["state_code"], r["group"]): r for r in rows}
    assert len(keyed) == len(rows)
    usa = keyed[2020, "4c", "US", "18 to 24"]
    assert (usa["vap_voted_pct"], usa["cvap_voted_pct"], usa["cvap_voted_moe_pp"]) == (48, 51.4, 1.2)
    assert usa["cvap_registered_pct"] == 59.8
    suppressed = keyed[2016, "4b", "WY", "Black alone"]
    assert suppressed["cvap_voted_pct"] is None
    assert suppressed["source_markers"]["cvap_voted_pct"] == "B"
    mature = keyed[2024, "4c", "WY", "65+"]
    assert (mature["native_group"], mature["cvap_voted_pct"], mature["cvap_voted_moe_pp"]) == (
        "65 years and over", 76.1, 3.9)
    assert cps.summary(rows)["states_and_dc"] == 51
    age_2010 = keyed[2010, "4c", "US", "25 to 44"]
    assert (age_2010["cvap_voted_pct"], age_2010["cvap_voted_moe_pp"]) == (37.1, 0.5)
    assert (2010, "4c", "US", "25 to 34") not in keyed
    assert keyed[2012, "4c", "US", "25 to 34"]["cvap_voted_pct"] == 53.5
    assert keyed[2014, "4b", "US", "Total"]["cvap_voted_pct"] == 41.9
    assert cps.summary(rows)["held_2008_age_frames"] == ["FL", "GA", "HI"]
    assert keyed[2008, "4b", "FL", "Total"]["cvap_voted_pct"] == 63.8
    assert not any((2008, "4c", "FL", group) in keyed for group in ("Total", "18 to 24"))
    assert (2008, "4c", "AK", "18 to 44") in keyed
    assert (2008, "4c", "AK", "18 to 24") not in keyed
    sd = keyed[2008, "4b", "SD", "White alone or in combination"]
    assert sd["cvap_registered_pct"] is sd["cvap_registered_moe_pp"] is None
    assert sd["source_markers"]["cvap_registered_pct"] == "invalid_published_rate"
    assert sd["reported_registered_thousands"] == 423


def test_2006_midterm_has_published_group_rates_but_no_state_age_table():
    rows = [r for r in cps.build(BUNDLE.read_bytes()) if r["year"] == 2006]
    assert len(rows) == 572
    assert {r["source_table"] for r in rows} == {"4b"}
    assert {r["election_type"] for r in rows} == {"midterm"}
    assert {r["dimension"] for r in rows} == {"overall", "sex", "race_or_hispanic_origin"}
    assert sum(r["cvap_voted_pct"] is not None for r in rows) == 443
    benchmark = next(r for r in rows if r["state_code"] == "US" and r["group"] == "Total")
    assert (benchmark["vap_voted_pct"], benchmark["cvap_voted_pct"],
            benchmark["cvap_voted_moe_pp"]) == (43.6, 47.8, 0.3)


def test_legacy_vap_groups_do_not_receive_reconstructed_citizen_rates():
    rows = cps.build(BUNDLE.read_bytes())
    keyed = {(r["year"], r["source_table"], r["state_code"], r["group"]): r for r in rows}
    overall_vap = keyed[2004, "4a", "US", "Total"]
    overall_cvap = keyed[2004, "4c", "US", "Total"]
    assert (overall_vap["vap_voted_pct"], overall_vap["cvap_voted_pct"]) == (58.3, None)
    assert (overall_cvap["vap_voted_pct"], overall_cvap["cvap_voted_pct"]) == (None, 63.8)
    age = keyed[2002, "4b", "US", "18 to 24"]
    assert age["vap_voted_pct"] == 17.2
    assert age["cvap_voted_pct"] is None and age["source_markers"]["cvap_voted_pct"] == "not_in_table"
    assert cps.summary(rows)["held_vap_age_frames"] == {"2002": ["DC", "PA"], "2004": []}
    assert (2002, "4b", "PA", "65 to 74") not in keyed
    assert (2004, "4a", "AZ", "Non-Hispanic White") not in keyed
    assert keyed[2004, "4a", "AZ", "White alone"]["vap_voted_pct"] == 55.9
    national = keyed[2002, "4a", "US", "Non-Hispanic White"]
    assert national["vap_voted_pct"] is None and national["source_markers"]["vap_voted_pct"] == "invalid_published_rate"
    wisconsin = keyed[2002, "4a", "WI", "Non-Hispanic White"]
    assert (wisconsin["vap_registered_pct"], wisconsin["vap_voted_pct"]) == (None, 52.1)


def test_changed_workbook_and_incomplete_bundle_are_rejected():
    with zipfile.ZipFile(BUNDLE) as source:
        members = {n: source.read(n) for n in source.namelist()}
    name = "2016-table4b.xlsx"
    for changed, reason in (({**members, name: members[name] + b"changed"}, "checksum differs"),
                            ({k: b for k, b in members.items() if k != name}, "Incomplete"),
                            ({k: b for k, b in members.items() if k != "2006-table4a.xls"}, "Incomplete")):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            for label, body in changed.items():
                archive.writestr(label, body)
        with pytest.raises(ValueError, match=reason):
            cps.build(out.getvalue())


def test_statewide_history_preserves_partial_early_coverage_and_source_definition():
    rows = cps.build_overall(BUNDLE.read_bytes())
    keyed = {(r["state_code"], r["year"], r["denominator_basis"]): r for r in rows}
    assert len(keyed) == len(rows) == 2754
    assert cps.overall_summary(rows)["reported_voting_rates"] == 2503
    assert keyed["AK", 1972, "vap"]["voted_source_marker"] == "N"
    assert keyed["CA", 1972, "cvap"]["voted_source_marker"] == "not_in_table"
    assert keyed["CA", 1994, "cvap"]["citizenship_measurement_caution"]
    assert keyed["CA", 1994, "cvap"]["reported_voted_pct"] == 57.5
    assert keyed["CA", 2024, "cvap"]["reported_voted_pct"] == 64.7
    assert not keyed["CA", 2024, "cvap"]["citizenship_measurement_caution"]
    assert "US" not in {row["state_code"] for row in rows}
