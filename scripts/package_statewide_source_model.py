"""Package complete public fitted inputs and deterministic all-state projections."""

import argparse
import csv
import gzip
import io
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

from scripts import statewide_source_model as source


def load_inputs(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_bytes())
    expected = {p + "/" + f for p in source.PROFILES for f in source.FAMILIES}
    if set(manifest.get("scenarios", {})) != expected:
        raise ValueError("Exactly nine declared public fitted priors are required")
    inputs, priors, declarations = {}, {}, {}
    for key in sorted(expected):
        declaration = manifest["scenarios"][key]["prior"]
        path = PurePosixPath(declaration["path"])
        if path.is_absolute() or ".." in path.parts or str(path) != declaration["path"]:
            raise ValueError("Unsafe fitted-input path")
        body = (root / str(path)).read_bytes()
        if source.pin(body) != {name: declaration[name] for name in ("bytes", "sha256")}:
            raise ValueError("Changed compressed fitted prior")
        if not 0 < declaration["decoded_bytes"] < 25_000_000:
            raise ValueError("Oversized public fitted prior")
        decoded = gzip.decompress(body) if declaration.get("compression") == "gzip" else body
        if source.pin(decoded) != {"bytes": declaration["decoded_bytes"], "sha256": declaration["decoded_sha256"]}:
            raise ValueError("Changed decoded fitted prior")
        priors[key] = json.loads(decoded)
        inputs[str(path)] = body
        declarations[key] = {"prior": declaration}
    inputs["manifest.json"] = source.encoded({"scenarios": declarations})
    return priors, inputs


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=sorted({key for row in rows for key in row}), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def outputs(product):
    result = source.files(product)
    states, groups, assumptions = [], [], []

    def row_values(row):
        point = row["point"]
        return {"state_code": row.get("state_code"), "available": row["available"],
                "total_D_share_change_pp": point["allocated_change_pp"] / 2 if point else None,
                "net_participation_D_share_pp": point["net_participation_pp"] / 2 if point else None,
                **{metric + "_D_share_pp": point["contributions_pp"][metric] / 2 if point else None
                   for metric in source.model.MECHANISMS},
                "return_conditioned": False, "population_calibrated": False,
                "interview_dates": None, "observed_individual_history": False}

    for profile in source.PROFILES:
        for family in source.FAMILIES:
            for row in product["profiles"][profile]["models"][family]["rows"]:
                values = {"profile": profile, "family": family, **row_values(row)}
                states.append({**values,
                    "previous_modeled_D_share_pct": 50 + row["point"]["previous_margin_pp"] / 2,
                    "current_modeled_D_share_pct": 50 + row["point"]["current_margin_pp"] / 2,
                    "total_sensitivity_minimum_pp": row["sensitivity"]["total_change"]["minimum"] / 2,
                    "total_sensitivity_maximum_pp": row["sensitivity"]["total_change"]["maximum"] / 2,
                    "sensitivity_is_confidence_interval": False})
                for group in row["groups"]:
                    groups.append({"profile": profile, "family": family, **row_values(group),
                                   "state_code": row["state_code"], "dimension": group["dimension"],
                                   "group": group["group"], "label": group["label"]})
    for case in product["queries"]["cases"].values():
        for row in case["rows"]:
            assumptions.append({"profile": case["profile"], "family": case["family"],
                                "affinity": case["affinity"], **row_values(row)})
    result.update({"complete-state-estimates.csv": csv_bytes(states),
                   "complete-demographic-contributions.csv": csv_bytes(groups),
                   "complete-assumption-estimates.csv": csv_bytes(assumptions),
                   "display-summary.json": source.encoded({"metadata": product["index"]["metadata"],
                       "rows": [{key: row[key] for key in ("state_code", "point", "sensitivity")}
                                for row in product["profiles"]["original"]["models"][source.FAMILIES[0]]["rows"]]})})
    return result


def archive_bytes(members):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            item = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            item.external_attr = 0o100644 << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, body, compresslevel=9)
    return target.getvalue()


def package(seed, code_root):
    priors, inputs = load_inputs(seed)
    product = source.build(priors)
    queries = outputs(product)
    members = {"inputs/" + name: body for name, body in inputs.items()}
    members.update({"results/" + name: body for name, body in queries.items()})
    for name in ("statewide_source_model.py", "norc_house_model.py", "package_statewide_source_model.py"):
        members["code/scripts/" + name] = (Path(code_root) / "scripts" / name).read_bytes()
    members["code/tests/test_statewide_source_model.py"] = (
        Path(code_root) / "tests/test_statewide_source_model.py").read_bytes()
    members["code/reproduce.py"] = (
        "import sys,unittest\nsys.dont_write_bytecode=True\nfrom pathlib import Path\n"
        "root=Path(__file__).resolve().parents[1]\nsys.path.insert(0,str(root/'code'))\n"
        "from scripts.package_statewide_source_model import reproduce\n"
        "suite=unittest.defaultTestLoader.discover(str(root/'code/tests'))\n"
        "assert unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()\n"
        "reproduce(root)\n").encode()
    members["REPRODUCE.txt"] = (
        "Use CPython 3.12, standard library only. From a fresh extraction:\n"
        "python3.12 code/reproduce.py\n\n"
        "This replays every public fitted-prior transformation, not respondent fitting.\n"
        "All 50 states use the same source-only method; no partisan returns constrain them.\n"
        "2024 House is bridged from AP2024 and CHEP recalled President in the CHEP2026\n"
        "source-weighted frame, not either year's observed statewide electorate.\n"
        "Model sensitivity is not a confidence interval or complete sampling/transport uncertainty.\n"
        "Native interview and fit dates are not supplied by these aggregate priors.\n"
        "No raw respondents, private fine cells, observed staying-home counts or new fits are included.\n"
    ).encode()
    members["checksums.json"] = source.encoded({name: source.pin(body) for name, body in sorted(members.items())})
    return product, queries, archive_bytes(members)


def reproduce(root):
    if sys.version_info[:2] != (3, 12):
        raise ValueError("The byte-exact numerical replay requires CPython 3.12")
    root = Path(root)
    manifest = json.loads((root / "checksums.json").read_bytes())
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual != set(manifest) | {"checksums.json"}:
        raise ValueError("Scientific archive member inventory differs")
    for name, expected in manifest.items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or str(path) != name:
            raise ValueError("Unsafe scientific member")
        if source.pin((root / name).read_bytes()) != expected:
            raise ValueError("Changed scientific member: " + name)
    _, queries, packet = package(root / "inputs", root / "code")
    for name, body in queries.items():
        if body != (root / "results" / name).read_bytes():
            raise ValueError("Projection differs: " + name)
    print(json.dumps({"status": "passed", "states": 50, "outputs": len(queries),
                      "complete_archive": source.pin(packet), "source_models_refitted": False}))
    return queries, packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Compile with CPython 3.12 to match the automatic publisher")
    if args.output.exists():
        raise ValueError("Use a fresh scientific output; immutable versions must not be overwritten")
    product, queries, packet = package(args.seed, Path(__file__).resolve().parents[1])
    args.output.mkdir(parents=True)
    for name, body in queries.items():
        target = args.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    (args.output / "complete-analysis.zip").write_bytes(packet)
    print(json.dumps({"status": "compiled", "version": product["index"]["metadata"]["version"],
                      "states": 50, "outputs": len(queries), "complete_archive": source.pin(packet)}))


if __name__ == "__main__":
    main()
