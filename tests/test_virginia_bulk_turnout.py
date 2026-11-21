import csv
import io
import json

import pytest

from scripts import virginia_bulk_turnout as va
from scripts.results_native_virginia import DOCUMENT_FIELDS


LOCALITY = "YORK COUNTY"
DATE = "11/05/2024 00:00:00"
ROWS = [
    ["2024 November General", DATE, LOCALITY, "101 - YORK", 3, 5, 1, 0, "", 9, 12, 1, 13],
    ["2024 November General", DATE, LOCALITY, "YORK COUNTY PROVISIONALS", "", "", "", "", "", "", "", "", ""],
]


def report(rows):
    buffer = io.StringIO()
    csv.writer(buffer).writerows([va.HEADER, *rows])
    return buffer.getvalue().encode()


def test_catalog_requires_the_advertised_statewide_blob(monkeypatch):
    monkeypatch.setattr(va, "virginia_native_locality_report",
                        lambda _: {"edition": "edition", "native_rows": [[LOCALITY]]})
    item = {"reportName": "Election Turnout", "county": None,
            "blobName": "Election Turnout_0869920c-fc10-402c-9c5c-f335d00f3d1f.csv"}
    data = {**dict.fromkeys(DOCUMENT_FIELDS), "jurisdiction": {"id": "test-authority"},
            "election": {"publicReportCategories": [{"reports": [item]}]}}
    assert va.catalog(json.dumps(data).encode())["url"].endswith("/test-authority/Election%20Turnout_" +
                                                                "0869920c-fc10-402c-9c5c-f335d00f3d1f.csv")
    item["blobName"] = "https://outside.invalid/report.csv"
    with pytest.raises(ValueError, match="filename"):
        va.catalog(json.dumps(data).encode())
    data["election"]["publicReportCategories"][0]["reports"].append(item)
    with pytest.raises(ValueError, match="repeated"):
        va.catalog(json.dumps(data).encode())


def test_audit_preserves_blank_measures_and_emits_signed_discrepancies():
    rows = va.extract(report(ROWS), locality_names={LOCALITY})
    assert rows[0]["provisional"] == 0 and rows[0]["post_election"] is None
    assert rows[1]["printed_turnout"] is None and rows[1]["precinct_code"] is None
    pin = dict(url="https://official.test/example.csv", sha256="a" * 64)
    entries = {va.FEED: {"status": "reported", "source": pin, "first_observed_at": "2026-11-21",
                         "data": {"rows": rows, "report": pin, "history": pin,
                                  "certified_state": {"total_voting": 8, "registered_voters": 13},
                                  "catalog": {"edition": "edition", "localities": [
                                      [LOCALITY, None, None, False, True, 10.0, 13.0],
                                  ]}}}}
    native, controls = va.exports(entries)
    assert all(not row["precinct_ballots_qualified"] and not row["rate_qualified"] for row in native)
    assert controls[0]["difference_from_locality_api"] == -1
    assert controls[0]["difference_from_certified_state"] is None
    assert controls[1]["difference_from_certified_state"] == 1
    assert controls[1]["csv_printed_registration"] == controls[1]["certified_state_registration"]


@pytest.mark.parametrize("rows", [
    [ROWS[0]],
    [*ROWS, ROWS[0]],
    [[*ROWS[0][:9], 10, *ROWS[0][10:]], ROWS[1]],
    [[*ROWS[0][:12], 14], ROWS[1]],
    [ROWS[0], [*ROWS[1][:3], "YORK COUNTY UNKNOWN", *ROWS[1][4:]]],
])
def test_missing_duplicate_and_inconsistent_rows_do_not_compile(rows):
    with pytest.raises(ValueError):
        va.extract(report(rows), locality_names={LOCALITY})
