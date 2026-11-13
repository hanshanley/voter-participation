"""Package complete native grids, predecessor, numerical queries, and exact replay code."""

import argparse
import ast
from pathlib import Path
import shutil
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.native_products import encoded, pin

TESTS = ("test_native_tabular.py", "test_native_products.py", "test_native_reconciliation.py",
    "test_house_comparability.py", "test_house_official_sources.py",
    "test_official_house_successor.py", "test_norc_house_model.py", "test_house_model_families.py")
ENTRIES = ("native_tabular.py", "native_products.py", "native_reconciliation.py",
    "house_official_sources.py", "official_house_successor.py",
    "reproduce_official_house_update.py", "verify_official_house_update.py",
    "verify_native_products.py", "verify_native_pdf_controls.py", "package_official_house_update.py")


def code_closure(root):
    queue = [Path("scripts") / name for name in ENTRIES]
    queue.extend(Path("tests") / name for name in TESTS)
    selected = set()
    while queue:
        relative = queue.pop()
        if relative in selected:
            continue
        path = root / relative
        if not path.is_file():
            raise ValueError("Missing complete replay-code dependency: " + str(relative))
        selected.add(relative)
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                if node.module == "scripts":
                    queue.extend(Path("scripts") / (name.name + ".py") for name in node.names)
                elif node.module and node.module.startswith("scripts."):
                    queue.append(Path(*node.module.split(".")).with_suffix(".py"))
            elif isinstance(node, ast.Import):
                queue.extend(Path(*name.name.split(".")).with_suffix(".py")
                    for name in node.names if name.name.startswith("scripts."))
    return selected


def package(packet, destination, website):
    if destination.exists():
        raise ValueError("Use a fresh complete scientific package directory")
    root = Path(__file__).resolve().parents[1]
    destination.mkdir(parents=True)
    for name in ("inputs", "results", "recorded-counts"):
        shutil.copytree(packet / name, destination / name)
    shutil.copyfile(packet / "independent-verification.json", destination / "independent-verification.json")
    for relative in code_closure(root):
        target = destination / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    catalogs = destination / "code/data/official-native-products"
    catalogs.mkdir(parents=True)
    for path in sorted((root / "data/official-native-products").glob("20261113-hi-wy*.json")):
        shutil.copyfile(path, catalogs / path.name)
    for relative in (Path("scripts/export-house-recorded-counts.mjs"),
                     Path("scripts/participation-norc-house.test.mjs"),
                     Path("public/scripts/participation-norc-house.js"),
                     Path("data/participation-return-attribution/20261112-02/norc-test-oracle.json"),
                     Path("data/participation-return-attribution/20261112-02/norc-receipt.json"),
                     Path("data/participation-return-attribution/20261112-03/family-summary.json")):
        target = destination / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(website / relative, target)
    (destination / "code/package.json").write_bytes(encoded(dict(type="module", private=True)))
    readme = (
        "Official House source-count successor: complete public scientific packet\n\n"
        "All 50 states and 435 districts remain. Only HI/WY count endpoints and their\n"
        "conditional reconstructions change across all three profiles and families.\n"
        "Other 48 full state rows and complete assumption/seed queries are reused.\n"
        "The 33 conditional comparisons / 17 held states, learned priors, survey weights,\n"
        "source-validation scores and prior full scientific packet are preserved.\n\n"
        "Complete native inputs: every HI summary/precinct record and every declared\n"
        "WY cached/formula cell across all 52 worksheets. The factual grids preserve\n"
        "blank/zero/nonapplicability, source flags, original cell literals and formats.\n"
        "Original workbook templates remain local; they are not redistributed here.\n"
        "Offline replay starts from complete factual grids, not the original templates.\n"
        "All required reconciliations match. HI's seven-ballot accounting gap remains\n"
        "explicit. WY's unassigned write-ins, overvotes and undervotes remain distinct;\n"
        "the 1,031 unassigned write-ins now explicitly enter O, with blank party retained.\n"
        "Overvotes/undervotes never enter candidate counts; turnout is not inferred.\n"
        "No formulas are executed, native counts repaired, individual histories observed,\n"
        "source models refitted, new survey weights inferred or geographic joins approved.\n\n"
        "Python >=3.9 core replay (no networking, subprocesses or private survey inputs):\n"
        "  python code/scripts/reproduce_official_house_update.py --inputs inputs \\\n"
        "    --packet ../fresh-reproduction --expected results\n"
        "  python code/scripts/verify_official_house_update.py --inputs inputs \\\n"
        "    --results results --output ../fresh-independent-verification.json\n\n"
        "With Node >=22, reproduce both complete 50-state recorded-count JSON/CSV files:\n"
        "  node code/scripts/export-house-recorded-counts.mjs --source results/viewer-original.json \\\n"
        "    --source-sha256 <SHA256 of that file, as pinned in manifest.json> \\\n"
        "    --output ../fresh-recorded-counts\n\n"
        "From code/, node --test scripts/participation-norc-house.test.mjs runs the\n"
        "18 client contract/source-review tests with complete sufficient fixtures.\n\n"
        "Run each archived test_native_*, test_house_comparability, test_house_official_sources,\n"
        "test_official_house_successor, test_norc_house_model, and test_house_model_families\n"
        "with unittest discovery from code/. The 37 affected tests were run with no skips.\n"
        "Existing optional numpy/scikit-learn dependencies exercise the five fitting guards;\n"
        "no private fitting inputs or fits are required. openpyxl and pypdf are used only\n"
        "for optional independent checks against separately held original source files.\n\n"
        "results/ contains all nine full results, mechanism/group/flow CSV queries and\n"
        "full assumption, state-seed and demographic-seed arrays, plus all three viewer\n"
        "datasets, the full current candidate/control queries and the all-district audit.\n"
    )
    (destination / "README.txt").write_text(readme)
    manifest = {str(path.relative_to(destination)): pin(path.read_bytes())
        for path in sorted(destination.rglob("*")) if path.is_file()}
    (destination / "manifest.json").write_bytes(encoded(manifest))
    archive_path = destination.parent / (destination.name + ".zip")
    if archive_path.exists():
        raise ValueError("The complete immutable ZIP already exists")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                archive.write(path, str(path.relative_to(destination)))
    return dict(complete_files=len(manifest) + 1, complete_zip=pin(archive_path.read_bytes()),
        private_respondents_included=False, metadata_only=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--website", type=Path, required=True)
    args = parser.parse_args()
    print(encoded(package(args.packet, args.output, args.website)).decode(), end="")


if __name__ == "__main__":
    main()
