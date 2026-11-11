"""Freeze new aggregate facts with an independent pypdf coordinate-reader check."""

import argparse
import hashlib
import json
from pathlib import Path
import re


FIELDS = ("VOTES", "WHITE", "BLACK", "OTHER", "MALE", "FEMALE", "DEM", "REP",
    "NO PARTY", "OTH", "UOCAVA IN", "UOCAVA OUT", "INPER", "ABS", "ASST D", "ASST I")
PDF_SHA = "03662b5a09ee09ca57b6806e7ba97e52561317f540dbc6ddafeb56d33f164390"


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def freeze(pdf, cached_text):
    import pypdf

    if hashlib.sha256(pdf.read_bytes()).hexdigest() != PDF_SHA:
        raise ValueError("Changed original")
    text = cached_text.read_text()
    if (text.count("Statewide Early Voting Statistical Report") != 2
            or text.count("Begin Date 1/1/1900 AND End Date 11/9/2026") != 2
            or text.count("Print Date: 11/10/2026 3:10:06 AM") != 2):
        raise ValueError("Changed source frame or printed clock")
    rows = []
    for page, page_text in enumerate(text.split("\n\f\n"), 1):
        for line in page_text.splitlines():
            parts = line.rsplit(None, 16)
            if len(parts) != 17 or not all(re.fullmatch(r"\d[\d,]*", word) for word in parts[1:]):
                continue
            label = parts[0]
            if label != "STATE TOTAL" and not re.fullmatch(r"[A-Z. ]+-\d{2}", label):
                raise ValueError("Unexpected native geography")
            rows.append(dict(source_key=f"native.pdf:page{page}:{label}", page=page,
                native_label=label, native_code=None if label == "STATE TOTAL" else label[-2:],
                scope_kind="state_parent" if label == "STATE TOTAL" else "parish",
                counts=dict(zip(FIELDS, [int(word.replace(",", "")) for word in parts[1:]]))))
    independent = []
    doc = pypdf.PdfReader(pdf)
    for page_number, page in enumerate(doc.pages, 1):
        lines = {}

        def fragment(value, cm, tm, font, size):
            value = value.strip()
            if value:
                x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                lines.setdefault(round(y, 2), []).append((x, value))

        page.extract_text(visitor_text=fragment)
        for _, words in sorted(lines.items(), reverse=True):
            values = sorted([word for word in words if re.fullmatch(r"\d[\d,]*", word[1])])
            if len(values) != 16:
                continue
            label = " ".join(word[1] for word in sorted(words) if word[0] < values[0][0])
            independent.append(dict(page=page_number, native_label=label,
                counts=dict(zip(FIELDS, [int(word[1].replace(",", "")) for word in values]))))
    expected = {(row["page"], row["native_label"]): row["counts"] for row in rows}
    actual = {(row["page"], row["native_label"]): row["counts"] for row in independent}
    if expected != actual or len(rows) != 65 or len(independent) != 65 or len(expected) != 65:
        raise ValueError("Independent original coordinate fields differ")
    if {row["native_code"] for row in rows if row["scope_kind"] == "parish"} != {f"{i:02}" for i in range(1, 65)}:
        raise ValueError("Incomplete source parish roster")
    facts = dict(contract="participation.louisiana_early_native_facts.v1", pdf_sha256=PDF_SHA,
        fields=list(FIELDS), rows=rows, source_title="Statewide Early Voting Statistical Report",
        election_date="2026-11-03", filter_begin_date="1900-01-01", filter_end_date="2026-11-09",
        print_clock_literal="11/10/2026 3:10:06 AM", print_timezone=None,
        pdf_creation_metadata=doc.metadata.get("/CreationDate"),
        pdf_metadata_timezone_not_assigned_to_print_clock=True)
    proof = dict(status="passed_independent_original_louisiana_early_cells",
        primary_engine="held pdfplumber/pdfminer text, native full-row parsing",
        independent_engine="pypdf text-visitor coordinates, numeric-column order",
        independent_engine_version=pypdf.__version__,
        numeric_cells=1040, rows=65, pages=2, facts_sha256=hashlib.sha256(encoded(facts)).hexdigest(),
        complete_independent_rows=independent, original_or_count_corrections=False)
    return facts, proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pdf", "cached-text", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh output")
    facts, proof = freeze(args.pdf, args.cached_text)
    args.output.mkdir(parents=True)
    (args.output / "native-facts.json").write_bytes(encoded(facts))
    (args.output / "independent-native.json").write_bytes(encoded(proof))
    print(json.dumps({key: value for key, value in proof.items() if key != "complete_independent_rows"}, sort_keys=True))
