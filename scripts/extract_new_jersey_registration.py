"""Freeze two independent extractions of the pinned public county summary."""

import argparse
import hashlib
import json
from pathlib import Path


PDF_SHA = "a14234d4c27984fa01e9547f1a3a796c14fbb7397c5fc891cc607d7f6f9ef1db"


def extract(pdf, output):
    import fitz
    import pypdf

    if hashlib.sha256(pdf.read_bytes()).hexdigest() != PDF_SHA or output.exists():
        raise ValueError("Changed original PDF or existing extraction")
    with fitz.open(pdf) as document:
        first = [page.get_text(sort=True) for page in document]
    second = [page.extract_text(extraction_mode="layout") for page in pypdf.PdfReader(pdf).pages]
    if len(first) != 1 or len(second) != 1:
        raise ValueError("Changed native page coverage")
    output.mkdir()
    for name, pages in (("pymupdf-pages.json", first), ("pypdf-pages.json", second)):
        (output / name).write_text(json.dumps(pages, indent=2) + "\n")
    receipt = dict(pdf_sha256=PDF_SHA, physical_pages=1, pymupdf_version=fitz.VersionBind,
                   pypdf_version=pypdf.__version__,
                   extractions={name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                                for name in ("pymupdf-pages.json", "pypdf-pages.json")})
    (output / "extraction-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    extract(args.pdf, args.output)
