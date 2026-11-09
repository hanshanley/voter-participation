"""Read the complete native county table without inferring an election-time stock."""

import hashlib
import io
import re

from pypdf import PdfReader


PDF_SHA = "f13ab6a61cd3e633374091e6618ab257c57089438be337568fc65587eba69f0b"
HEADERS = ["County", "CVAP Estimate", "Number of Active Voters", "Percentage"]


def read_pdf(body):
    if hashlib.sha256(body).hexdigest() != PDF_SHA:
        raise ValueError("Changed original active-voter report")
    reader = PdfReader(io.BytesIO(body))
    if len(reader.pages) != 3:
        raise ValueError("Changed complete native page inventory")
    text = [page.extract_text() for page in reader.pages]
    if ("County CVAP Estimate Number of Active Voters Percentage" not in text[0]
            or "2023 American Community Survey 5-year estimates" not in text[0]
            or "2020 Census" not in text[0]):
        raise ValueError("Changed native columns or mixed CVAP source note")
    pattern = re.compile(r"(?m)^(\d{2} - [^\n]*?)\s+(\d+)\s+(\d+)\s+(\d+\.\d{3}%)\s*$")
    rows = []
    for page, value in enumerate(text, 1):
        for label, cvap, active, percentage in pattern.findall(value):
            rows.append(dict(page=page, native_county_label=label,
                native_cvap_estimate=cvap, native_active_voters=active,
                native_percentage=percentage))
    if [row["native_county_label"][:2] for row in rows] != [f"{i:02}" for i in range(1, 83)]:
        raise ValueError("Incomplete, duplicated or unordered native 82-county coverage")
    return dict(pages=3, headers=HEADERS, rows=rows)
