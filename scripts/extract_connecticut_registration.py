"""Freeze two independent text extractions of the pinned public registration PDF."""

import argparse
import hashlib
import json
from pathlib import Path


PDF_SHA = "2e4d8e75fac512763044e2229efbf10024a9d0ccff9f8ba1e6ccd820dd17746c"


def extract(pdf, output):
    import fitz
    import pypdf

    if hashlib.sha256(pdf.read_bytes()).hexdigest() != PDF_SHA or output.exists():
        raise ValueError("Changed original PDF or existing extraction")
    with fitz.open(pdf) as document:
        mupdf = [page.get_text(sort=True) for page in document]
    reader = pypdf.PdfReader(pdf)
    pure_python = [page.extract_text(extraction_mode="layout") for page in reader.pages]
    if len(mupdf) != 9 or len(pure_python) != 9:
        raise ValueError("Changed source page coverage")
    output.mkdir()
    for name, pages in (("pymupdf-pages.json", mupdf), ("pypdf-pages.json", pure_python)):
        (output / name).write_text(json.dumps(pages, indent=2) + "\n")
    receipt = dict(pdf_sha256=PDF_SHA, physical_pages=9, pymupdf_version=fitz.VersionBind,
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
