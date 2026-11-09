"""Freeze two independent coordinate views and a third native text view."""

import argparse
import hashlib
import json
from pathlib import Path

from .nebraska_registry_count import PDF_SHA


def extract(pdf,output):
    import fitz
    import pdfplumber
    import pypdf

    if hashlib.sha256(pdf.read_bytes()).hexdigest()!=PDF_SHA or output.exists():raise ValueError("Changed original or existing extraction")
    views={"pymupdf":[],"pdfplumber":[]}
    with fitz.open(pdf) as native:
        for page in native:
            views["pymupdf"].append(dict(width=page.rect.width,height=page.rect.height,
                text=page.get_text(sort=True),words=[list(word[:5]) for word in page.get_text("words")]))
    with pdfplumber.open(pdf) as native:
        for page in native.pages:
            views["pdfplumber"].append(dict(width=page.width,height=page.height,text=page.extract_text(),
                words=[[word["x0"],word["top"],word["x1"],word["bottom"],word["text"]] for word in page.extract_words()]))
    third=[page.extract_text(extraction_mode="layout") for page in pypdf.PdfReader(pdf).pages]
    if len(third)!=7 or any(len(pages)!=7 for pages in views.values()):raise ValueError("Changed source page coverage")
    output.mkdir()
    for name,value in (("coordinate-views.json",views),("pypdf-pages.json",third)):
        (output/name).write_text(json.dumps(value,indent=2)+"\n")
    receipt=dict(source_pdf_sha256=PDF_SHA,pymupdf_version=fitz.VersionBind,pdfplumber_version=pdfplumber.__version__,
        pypdf_version=pypdf.__version__,physical_pages=7,
        extractions={name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in ("coordinate-views.json","pypdf-pages.json")})
    (output/"extraction-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n");print(json.dumps(receipt,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--pdf",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();extract(args.pdf,args.output)
