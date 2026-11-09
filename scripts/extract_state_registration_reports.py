"""Freeze independent text extractions of the two pinned official PDFs."""

import argparse
import hashlib
import json
from pathlib import Path

from .state_registration_reports import REPORTS


def extract(state, pdf, output):
    import fitz
    import pypdf

    config = REPORTS[state]
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != config["pdf_sha256"] or output.exists():
        raise ValueError("Changed original PDF or existing extraction")
    with fitz.open(pdf) as document:
        first = [page.get_text(sort=True) for page in document]
    second = [page.extract_text(extraction_mode="layout") for page in pypdf.PdfReader(pdf).pages]
    if len(first) != config["pages"] or len(second) != config["pages"]:
        raise ValueError("Changed source page coverage")
    output.mkdir()
    for name, pages in (("pymupdf-pages.json", first), ("pypdf-pages.json", second)):
        (output / name).write_text(json.dumps(pages, indent=2) + "\n")
    receipt = dict(state_code=state, pdf_sha256=config["pdf_sha256"], physical_pages=len(first),
                   pymupdf_version=fitz.VersionBind, pypdf_version=pypdf.__version__,
                   extractions={name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                                for name in ("pymupdf-pages.json", "pypdf-pages.json")})
    (output / "extraction-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", choices=tuple(REPORTS), required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    extract(args.state, args.pdf, args.output)
