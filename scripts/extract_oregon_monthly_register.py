"""Freeze complete independent text views of the already-held Oregon originals."""

import argparse
import hashlib
import json
from pathlib import Path


SOURCES = {
    "2026-November-registration.pdf": "6ba27dc31ecb4b09d81ef9c9b3258dfa8fd44bdc8f2a1c34aa38d3dc5ab890b9",
    "2026-general-election-unofficial-ballot-returns.pdf": "0584cf65ac46bf34096e7c81544c54af97daf761aa050e75842812f36678f8d2",
}


def extract(originals, output):
    import fitz
    import pdfplumber

    if output.exists():
        raise ValueError("Do not overwrite a completed extraction")
    contents = {}
    for name, digest in SOURCES.items():
        pdf = originals / name
        if hashlib.sha256(pdf.read_bytes()).hexdigest() != digest:
            raise ValueError("Changed original PDF")
        with fitz.open(pdf) as native:
            first = [page.get_text(sort=True) for page in native]
        with pdfplumber.open(pdf) as native:
            second = [page.extract_text() for page in native.pages]
        expected = 7 if name.startswith("2026-November") else 5
        if len(first) != expected or len(second) != expected:
            raise ValueError("Changed native page coverage")
        target = "registration-source-views.json" if expected == 7 else "held-return-source-views.json"
        contents[target] = (json.dumps(dict(pymupdf=first, pdfplumber=second), indent=2) + "\n").encode()
    contents["extraction-receipt.json"] = (json.dumps(dict(
        pymupdf_version=fitz.VersionBind, pdfplumber_version=pdfplumber.__version__,
        successful_existing_originals_reused_not_reacquired=True,
        old_county_day_party_numeric_parser_not_rerun=True,
        complete_registration_pages_newly_frozen=7,
        sources=SOURCES,
        outputs={name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
                 for name, body in contents.items()}), indent=2) + "\n").encode()
    output.mkdir()
    for name, body in contents.items():
        (output / name).write_bytes(body)
    print(contents["extraction-receipt.json"].decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    extract(args.originals, args.output)
