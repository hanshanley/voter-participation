"""Stage audited immutable viewer data and checksum-pinned website receipts."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.norc_house_model import encoded

TAG = "participation-house-comparability-20261112-01"
DOWNLOAD = "https://github.com/hanshanley/margin_of_error/releases/download/"+TAG+"/complete-analysis.zip"
DATA = "data/house-comparability/20261112-01"


def load(path):
    return json.loads(path.read_bytes())


def stage(results, research, website=None, source_commit=None, receipt_version="20261112-06"):
    destination = research/DATA
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("viewer-original.json", "viewer-attenuated.json", "viewer-full.json",
                 "complete-audit.json", "summary.json", "independent-verification.json",
                 "complete-profile-family-state-comparisons.csv"):
        target, body = destination/name, (results/name).read_bytes()
        if target.exists() and target.read_bytes() != body:
            raise ValueError("Do not overwrite a different immutable viewer dataset")
        target.write_bytes(body)
    if website is None:
        return
    if not source_commit or not re.fullmatch("[0-9a-f]{40}", source_commit):
        raise ValueError("Use an immutable published research source commit")

    def receipt(profile):
        body = (results/f"viewer-{profile}.json").read_bytes()
        return dict(url="https://raw.githubusercontent.com/hanshanley/voter-participation/"+
            source_commit+"/"+DATA+f"/viewer-{profile}.json", bytes=len(body),
            sha256=hashlib.sha256(body).hexdigest(), source_commit=source_commit,
            complete_download_url=DOWNLOAD, contest_comparability_required=True)

    original = load(results/"viewer-original.json")
    points = original["families"]["accepted_ridge_multinomial"]
    if not re.fullmatch(r"[0-9]{8}-[0-9]{2}", receipt_version):
        raise ValueError("Invalid immutable website receipt version")
    output = website/"data/participation-return-attribution"/receipt_version
    if output.exists():
        raise ValueError("Use a fresh website receipt version")
    output.mkdir(parents=True)
    (output/"norc-receipt.json").write_bytes(encoded(receipt("original")))
    (output/"family-summary.json").write_bytes(encoded({key: original[key] for key in
        ("summary", "source_validation", "family_labels", "comparison_policy")}))
    (output/"norc-point-summary.json").write_bytes(encoded(dict(
        validation=points["validation"], summary=points["summary"],
        preconditioning_margin_MAE_pp=points["preconditioning_margin_MAE_pp"],
        rows=[{key: row[key] for key in ("state_code", "point", "source_comparison_available",
                                       "reported_comparison", "contest_comparability")} for row in points["rows"]])))
    association = load(website/"data/participation-return-attribution/20261112-04/copula-receipt.json")
    association["historical_science_url"] = association["complete_science_url"]
    association["complete_science_url"] = DOWNLOAD
    association["profiles"] = {profile: receipt(profile) for profile in ("attenuated", "full")}
    maxima = {}
    for profile in ("original", "attenuated", "full"):
        viewer = load(results/f"viewer-{profile}.json")
        for model in viewer["families"].values():
            for row in model["rows"]:
                if not row["source_comparison_available"]:
                    continue
                groups = [("", row["point"])]
                groups += [(group["dimension"]+"|"+group["group"], group)
                           for group in row["groups"] if group["available"] and group["group"] != "unshown"]
                for key, value in groups:
                    maxima[key] = max(maxima.get(key, 0), abs(row["reported_comparison"]["reported_change_pp"]),
                                      abs(value["net_participation_pp"]),
                                      *(abs(number) for number in value["contributions_pp"].values()))
    reported_maximum = max(abs(row["reported_comparison"]["reported_change_pp"])
        for row in points["rows"] if row["source_comparison_available"])
    association["shared_max_abs_margin"] = {key: max(value, reported_maximum)
                                           for key, value in maxima.items()}
    association["comparison_policy"] = original["comparison_policy"]
    (output/"copula-receipt.json").write_bytes(encoded(association))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("results", "research"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--website", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--receipt-version", default="20261112-06")
    args = parser.parse_args()
    stage(args.results, args.research, args.website, args.source_commit, args.receipt_version)
