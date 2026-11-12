"""Package every permitted input, model-family query and public replay implementation."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile


CODE = ("scripts/fit_house_model_families.py", "scripts/compare_house_model_families.py",
        "scripts/verify_house_model_families.py", "scripts/reproduce_house_model_families.py",
        "scripts/package_house_model_families.py", "scripts/norc_house_model.py",
        "scripts/verify_norc_house_model.py", "scripts/fit_norc_house_model.py",
        "scripts/validate_norc_historical_transfer.py",
        "tests/test_house_model_comparison.py", "tests/test_house_model_families.py")


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def build(source, experiment, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed package")
    members = {"code/" + name: (source / name).read_bytes() for name in CODE}
    for directory in ("inputs", "results"):
        for path in (experiment / directory).rglob("*"):
            if path.is_file():
                members[path.relative_to(experiment).as_posix()] = path.read_bytes()
    members["README.txt"] = (
        "Three fixed NORC-informed House model families; 50 states, 48 return comparisons each.\n"
        "Ridge remains preferred under the preregistered source-only rule. Boosting's lower\n"
        "current-return error does not override its worse historical transfer. Historical\n"
        "transfer is selection validation, NOT an independent post-selection test.\n"
        "Full inputs include the ENTIRE accepted 48-state scientific predecessor and coarse\n"
        "synthetic priors for all three families. All state/group/assumption/seed queries,\n"
        "negative source scores, errors and disclosure holds remain in results/.\n"
        "No raw respondents, individual predictions, fine cells or trained estimators included.\n"
        "Exact endpoint reconstruction does not identify individual switching/staying home.\n"
        "Change in Democratic two-party share = half D-R margin change; retained percentages\n"
        "are not halved. Family/assumption spreads are not confidence intervals. No precinct\n"
        "allocation, first-ever entry, eligibility/death/migration identification is claimed.\n"
        "Public replay needs Python 3.9+ STANDARD LIBRARY ONLY, no network or private fitting:\n"
        "python3 -S code/scripts/reproduce_house_model_families.py --root . --output /fresh/path\n"
        "This reuses baseline bytes and recalculates only the two new public simulations.\n"
        "Private fitting implementation is provided for authorized local originals only;\n"
        "it requires numpy/scikit-learn/threadpoolctl. Optional private-stack tests skip\n"
        "without those packages; public selection/accounting/units tests must still pass.\n"
        "Source originals: CHEP2026 and AP VoteCast2024/2022; source hashes/cases and fixed\n"
        "settings/holdout policy are retained in the priors and preregistered-policy.json.\n"
    ).encode()
    manifest = {name: pin(body) for name, body in sorted(members.items())}
    members["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, body, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    output.mkdir(parents=True)
    body = buffer.getvalue()
    (output / "complete-analysis.zip").write_bytes(body)
    for name in ("summary.json", "viewer-data.json", "complete-source-validation.csv",
                 "complete-state-family-comparisons.csv", "complete-family-dispersion.csv",
                 "selection-before-return-evaluation.json", "preregistered-policy.json"):
        (output / name).write_bytes((experiment / "results" / name).read_bytes())
    receipt = dict(archive=pin(body), members=len(members), all_complete_queries_included=True,
                   entire_accepted_predecessor_included=True, private_records_exported=False)
    (output / "package-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.experiment, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
