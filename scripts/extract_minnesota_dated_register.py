"""Freeze the complete factual Minnesota table; exclude app code and contacts."""

import argparse
import hashlib
import json
from pathlib import Path
import re


SOURCE_SHA = "632bd6192040f32929f6abb1b9d520a32ab8d1357ebb28ce40ecc654df156f38"


def extract(source, output):
    from lxml import etree, html

    body = source.read_bytes()
    if hashlib.sha256(body).hexdigest() != SOURCE_SHA or output.exists():
        raise ValueError("Changed original index or completed extraction")
    tables = re.findall(rb"<table\b.*?</table>", body, flags=re.DOTALL | re.IGNORECASE)
    if len(tables) != 1:
        raise ValueError("Changed complete native table inventory")
    table = tables[0]
    root = html.fromstring(table)
    caption = " ".join(root.xpath(".//caption")[0].text_content().split())
    rows = [[" ".join(cell.text_content().split()) for cell in row.xpath("./th|./td")]
            for row in root.xpath(".//tr")]
    scope = dict(
        source_url="https://www.sos.mn.gov/election-administration-campaigns/data-maps/voter-registration-counts/",
        native_caption=caption, native_snapshot_date="2026-11-02",
        registered_label="Registered Voters", preregistered_label="Pre-Registered Voters",
        preregistered_source_ages=[16, 17], source_activation_age=18,
        preregistered_excluded_from_model_denominator=True,
        native_time=None, native_timezone=None, active_inactive_status_qualified=False,
        independently_certified_legal_eligibility=False,
        older_May_June_workbook_dates_not_used_for_current_table=True,
        full_page_app_code_contacts_and_personal_records_excluded=True)
    if caption != "Voter Counts by County as of November 2, 2026":
        raise ValueError("Changed native table snapshot caption")
    output.mkdir()
    contents = {
        "native-table.html": table,
        "independent-table.json": (json.dumps(dict(caption=caption, rows=rows), indent=2) + "\n").encode(),
        "source-scope.json": (json.dumps(scope, indent=2) + "\n").encode(),
    }
    for name, value in contents.items():
        (output / name).write_bytes(value)
    receipt = dict(source_body_bytes=len(body), source_body_sha256=SOURCE_SHA,
        independent_reader="lxml/libxml2", lxml_version=etree.LXML_VERSION,
        full_native_table_extracted_byte_exact=True,
        outputs={name: dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
                 for name, value in contents.items()})
    (output / "extraction-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    extract(args.source, args.output)
