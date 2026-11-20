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
    assert len(rows) == 7072
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


def test_changed_workbook_and_incomplete_bundle_are_rejected():
    with zipfile.ZipFile(BUNDLE) as source:
        members = {n: source.read(n) for n in source.namelist()}
    name = "2016-table4b.xlsx"
    for changed, reason in (({**members, name: members[name] + b"changed"}, "checksum differs"),
                            ({k: b for k, b in members.items() if k != name}, "Incomplete")):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            for label, body in changed.items():
                archive.writestr(label, body)
        with pytest.raises(ValueError, match=reason):
            cps.build(out.getvalue())
