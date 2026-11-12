"""Complete public simulations from fitted synthetic inputs, never private cases."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("priors", "results", "accepted-science", "historical", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from scripts import norc_house_model as model
    from scripts import verify_norc_house_model as independent
    if args.output.exists():
        raise ValueError("Use a fresh scientific package")
    priors = json.loads(args.priors.read_bytes())
    result = json.loads((args.results / "complete-result.json").read_bytes())
    proof = independent.verify(result, priors)
    originals = args.accepted_science.read_bytes()
    if hashlib.sha256(originals).hexdigest() != "2377ea253d33b88af3146bad4e2a52c9936d97b178c00a4fa0e3be022aadeae1":
        raise ValueError("Changed complete return-input predecessor")
    members = {"inputs/fitted-synthetic-NORC-priors.json": args.priors.read_bytes(),
        "inputs/complete-return-source-science.zip": originals,
        "checks/independent-verification.json": model.encoded(proof),
        "checks/untouched-historical-transfer.json": args.historical.read_bytes()}
    for name in ("scripts/norc_house_model.py", "scripts/fit_norc_house_model.py",
            "scripts/validate_norc_historical_transfer.py", "scripts/verify_norc_house_model.py",
            "scripts/package_norc_house_model.py", "scripts/reproduce_norc_house_model.py",
            "tests/test_norc_house_model.py"):
        members["code/"+name] = (root / name).read_bytes()
    for name, body in model.result_files(result).items():
        if (args.results / name).read_bytes() != body:
            raise ValueError("Changed complete result or query bytes: "+name)
        members["results/"+name] = body
    members["README.txt"] = (
        "NORC-INFORMED DEMOGRAPHIC HOUSE TRANSITION MODEL\n\n"
        "NEW fitted priors learn demographic and prior-choice associations from\n"
        "113020 NORC CHEP2026 cases and136435 AP/NORC2024 positive-state-weight\n"
        "cases. Actual joint demographic records are used privately, not products\n"
        "of separate demographic marginals or the old synthetic state coupling.\n"
        "Ridge multinomial models have state effects and prior-choice/demographic\n"
        "interactions. Held-out tests compare demographic and prior/state-only\n"
        "models before any election-return calibration. All scores are included,\n"
        "including the bridge's slightly worse Brier score. An untouched AP2024\n"
        "source-response test of an AP2022 model gives only modest improvement.\n\n"
        "CHEP recalls2024 President, not House. The explicit AP2024 bridge learns\n"
        "House24 from President24, actual recalled House22, age, education, native\n"
        "race/ethnicity and income. Forced-choice QVOTE2022S is never consumed;\n"
        "AP recalled House22 party codes are the reverse of CHEP's codes. Current\n"
        "CHEP House-model responses also use source sex and county RUCC context.\n"
        "Current likelihood/model labels and respondent IDs are excluded as\n"
        "predictors. N/U remain separate; disclosure-removed values stay unknown.\n\n"
        "All50 source states are simulated.35 cases condition on both held native\n"
        "2024/2026 House endpoints;15 retain source scenarios with observed-return\n"
        "comparisons unavailable. No D.C. sample or borrowed state baseline.\n"
        "Source House22-to26 scenarios remain separately labeled robustness views.\n"
        "Endpoint calibration is not independent behavioral validation.\n\n"
        "For A=D-R and V=D+R, each flow/group contributes:\n"
        "C=50*(1/V0+1/V1)*deltaA -50*(A0+A1)/(V0*V1)*deltaV.\n"
        "This symmetric exact identity allocates denominator effects within each\n"
        "mechanism. Switching, exits, entry/return, Other and unresolved sum to\n"
        "the modeled margin change. Net participation=entry+exit contributions.\n"
        "Every separate age/race/education/sex/income/county-context partition sums\n"
        "to its state; overlapping dimensions are NOT additive causes. Source\n"
        "small/complementary holds are retained; opaque synthetic remainder rows\n"
        "keep accounting complete without exposing held native categories.\n\n"
        "Complete360 frame/latent-affinity cases,250 state seed cases and1500\n"
        "demographic-partition seed cases are included.15million partition-agent\n"
        "draws are alternate simulations, not15million distinct people. Monte\n"
        "Carlo noise is not source/design uncertainty. Frame scales0.8/1/1.2 and\n"
        "extra latent retention affinity0.5/1/2 are assumptions, not confidence\n"
        "intervals. Frame size is not measured eligible population. Native\n"
        "source clocks/coverage/competition and changed age/residence remain.\n\n"
        "Modeled nonparticipation is not administratively confirmed staying home;\n"
        "entry/return is not proven first-ever voting. Eligibility/death/migration\n"
        "remain unknown. No state estimates are allocated to counties/precincts.\n"
        "These are conditional model-based explanations, not identified causes.\n\n"
        "Complete permitted fitted/synthetic inputs, all result queries, every\n"
        "modeled flow, source/code/tests and the ENTIRE accepted predecessor are\n"
        "included. No raw cases or private fine source cells are redistributed.\n"
        "The private fitting code requires the user's exact original files and\n"
        "disclosure whitelist; public reproduction starts from the complete fitted\n"
        "synthetic inputs, NOT raw respondent-data reconstruction or old refits.\n"
        "Private fit toolchain: Python3.9/numpy2.0.2/scipy1.13.1/scikit-learn1.6.1.\n"
        "Public simulation reproduction uses only the Python standard library:\n"
        "Reference byte-identical public toolchain Python3.9; later versions can\n"
        "change floating-point summation/serialization. Return conditioning is\n"
        "not source training: the preconditioning margin errors are retained,\n"
        "not attributed to an extra behavioral mechanism or hidden as a residual.\n"
        "python3 -Werror code/scripts/reproduce_norc_house_model.py "
        "--package . --output /fresh/path\n"
    ).encode()
    manifest = dict(contract="participation.complete_norc_house_demographic_model.v1",
        source_commit=args.commit, complete_query_download=True,
        reference_python="3.9",
        raw_private_inputs_redistributed=False, public_simulation_reproduction_complete=True,
        private_training_reproduction_requires_originals=True,
        files={name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
            for name, body in sorted(members.items())})
    members["manifest.json"] = model.encoded(manifest)
    args.output.mkdir(parents=True)
    with zipfile.ZipFile(args.output / "complete-analysis.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 11, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, body)
    for name, body in members.items():
        if name.startswith(("results/", "checks/")) or name == "manifest.json":
            (args.output / Path(name).name).write_bytes(body)
    archive = (args.output / "complete-analysis.zip").read_bytes()
    receipt = dict(status="complete_NORC_demographic_House_model_package",
        source_commit=args.commit, archive_bytes=len(archive), archive_sha256=hashlib.sha256(archive).hexdigest(),
        members=len(members), summary=result["summary"], independent=proof,
        private_raw_respondents_exported=False)
    (args.output / "package-receipt.json").write_bytes(model.encoded(receipt))
    print(json.dumps(receipt))
