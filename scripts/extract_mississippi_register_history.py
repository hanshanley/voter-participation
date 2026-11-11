"""Extract newly selected historical active-registration tables, not voter histories."""

import hashlib
import io
import re

from pypdf import PdfReader


SHA = {2022: "ecb1ad8faa5662db61caec6df843a9d3213fe404dd9d7062ee90c23a0f00b627",
       2024: "57d64fbf0df237cce7ce0370434dac20a0f325aca544861d4442e81fe813efb1"}


def read_pdf(body, year):
    if year not in SHA or hashlib.sha256(body).hexdigest() != SHA[year]:
        raise ValueError("Changed original historical active-registration report")
    reader = PdfReader(io.BytesIO(body))
    if len(reader.pages) != 3:
        raise ValueError("Changed complete historical page inventory")
    text = [page.extract_text(extraction_mode="layout") for page in reader.pages]
    if "County 2020 CVAP Estimate Number of Active Voters Percentage" not in re.sub(r"\s+", " ", text[0]):
        raise ValueError("Changed native historical column meanings")
    pattern = re.compile(r"(?m)^\s*(\d{2} - [^\n]*?)\s+(\d+)\s+(\d+)\s+(\d+\.\d{3}%)\s*$")
    rows = [dict(page=page, native_county_label=label, native_cvap_estimate=cvap,
                 native_active_voters=active, native_percentage=percentage)
            for page, value in enumerate(text, 1)
            for label, cvap, active, percentage in pattern.findall(value)]
    if [row["native_county_label"][:2] for row in rows] != [f"{i:02}" for i in range(1, 83)]:
        raise ValueError("Incomplete or duplicated native historical county coverage")
    return rows
