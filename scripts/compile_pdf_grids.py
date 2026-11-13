"""Compile pinned, reviewed rectangular PDF facts; never infer a population."""

import argparse
import gzip
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.native_pdf import project, read
from scripts.native_products import encoded, pin


def compile_grids(recipe, source_root):
    if recipe["contract"] != "participation.reviewed_pdf_grids.v1":
        raise ValueError("Unsupported reviewed PDF recipe")
    products = []
    for source in recipe["sources"]:
        name = Path(source["filename"])
        if name.name != str(name) or name.is_absolute():
            raise ValueError("A source must name one declared local file")
        body = (source_root / name).read_bytes()
        if pin(body) != source["pin"]:
            raise ValueError("Reviewed PDF source pin changed")
        facts = read(body)
        if len(facts["pages"]) != source["expected_pages"]:
            raise ValueError("Reviewed source page inventory changed")
        tables = [project(facts, spec) for spec in source["grids"]]
        if len({table["id"] for table in tables}) != len(tables):
            raise ValueError("Repeated declared PDF grid")
        products.append(dict(source={key: value for key, value in source.items()
            if key != "grids"}, tables=tables))
    if not products or len({product["source"]["id"] for product in products}) != len(products):
        raise ValueError("Empty or repeated source inventory")
    return dict(contract="participation.reviewed_pdf_factual_grids.v1",
        original_document_templates_redistributed=False,
        automatic_geographic_or_model_qualification=False, products=products)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compile_grids(json.loads(args.recipe.read_text()), args.source_root)
    body = encoded(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(body, mtime=0) if args.output.suffix == ".gz" else body)
    print(json.dumps(dict(output=str(args.output), **pin(args.output.read_bytes()))))


if __name__ == "__main__":
    main()
