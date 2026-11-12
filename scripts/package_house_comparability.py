"""Package full sufficient inputs, every corrected query and offline reproduction code."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile


CODE = ("house_comparability", "reproduce_house_comparability", "package_house_comparability",
        "verify_house_comparability", "norc_house_model", "verify_norc_house_model",
        "house_clerk_endpoints", "compare_house_model_families", "stage_house_comparability")


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def build(source, packet, output, website=None):
    if output.exists():
        raise ValueError("Use a fresh scientific package")
    members = {"code/scripts/"+name+".py": (source/"scripts"/(name+".py")).read_bytes() for name in CODE}
    members["code/tests/test_house_comparability.py"] = (source/"tests/test_house_comparability.py").read_bytes()
    members["code/scripts/verify_house_comparability.mjs"] = (source/"scripts/verify_house_comparability.mjs").read_bytes()
    if website:
        for name in ("public/scripts/participation-norc-house.js", "public/scripts/participation-return-drivers.js",
                     "src/components/ParticipationReturnDrivers.astro", "scripts/participation-norc-house.test.mjs",
                     "scripts/check-participation-house-comparability-browser.py"):
            members["viewer-code/"+name] = (website/name).read_bytes()
    for directory in ("inputs", "results"):
        for path in sorted((packet/directory).rglob("*")):
            if path.is_file():
                members[path.relative_to(packet).as_posix()] = path.read_bytes()
    members["README.txt"] = (
        "All435district/50state House contest-comparability audit, not a new election return.\n"
        "A changed named-D/R slate can change pooled margins without a preference swing.\n"
        "Incompatible/missing/stage-unqualified comparisons do not condition modeled histories.\n"
        "Full inputs: pinned official2024Clerk PDF/native facts, all current435district\n"
        "candidate queries, frozen controls, all9public synthetic priors and predecessor\n"
        "complete results. Full outputs: all corrected states/groups/flows/assumptions/seeds\n"
        "for3families times3association profiles; no metadata-only query substitutes.\n"
        "Source fits and validated source-only association projections are reused, not refit.\n"
        "Unaffected numerical results and complete queries are preserved exactly.\n"
        "Source-only scenarios for held states remain explicitly UNCONDITIONED in downloads;\n"
        "they are not explanations of observed election results. No repaired native totals,\n"
        "measured staying home, first-ever voting, causal effects or population CIs claimed.\n"
        "Common-source-ID subsets are NOT statewide estimates or boundary-certified matches.\n"
        "Current counts are a frozen unofficial reporting snapshot, not certified final totals.\n"
        "MAEs use33comparisons, not the superseded48; this is NOT a source-fit improvement.\n"
        "No raw respondents, individual predictions, private fine cells or estimators exported.\n"
        "Offline Python3.9+ STANDARD LIBRARY replay, with network/external commands blocked:\n"
        "python3 -S code/scripts/reproduce_house_comparability.py --inputs inputs --packet /fresh/replay --expected results\n"
        "This rebuilds every published result and independently verifies native counts,\n"
        "candidate-coverage masks, rational accounting and complete demographic simulations.\n"
    ).encode()
    members["manifest.json"] = json.dumps({name: pin(body) for name, body in sorted(members.items())},
        indent=2, sort_keys=True).encode()+b"\n"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, body, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    output.mkdir(parents=True)
    body = stream.getvalue()
    (output/"complete-analysis.zip").write_bytes(body)
    for name in ("complete-audit.json", "summary.json", "independent-verification.json",
                 "viewer-original.json", "viewer-attenuated.json", "viewer-full.json",
                 "complete-profile-family-state-comparisons.csv"):
        (output/name).write_bytes((packet/"results"/name).read_bytes())
    receipt = dict(archive=pin(body), members=len(members),
        complete_sufficient_inputs_and_all_queries_included=True, source_only_holds_not_observed_effects=True,
        raw_respondents_and_private_fine_cells_exported=False)
    (output/"package-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True)+"\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "packet", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--website", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.packet, args.output, args.website), sort_keys=True))
