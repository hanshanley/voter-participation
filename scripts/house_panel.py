"""Join exact source House counts without allocating geography or inferring turnout."""

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal, localcontext
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile


HISTORICAL = "data/historical-house-counties/20261105-medsl-04"
CURRENT = "data/county-results/20261107T125502Z"
PARTIES = {
    "democratic": "D", "democrat": "D", "dem": "D", "democratic-npl": "D",
    "republican": "R", "rep": "R",
}
AT_LARGE = {"AK", "DE", "ND", "SD", "VT", "WY"}


def party(label):
    return PARTIES.get(label.strip().casefold(), "O")


def integer(value):
    if not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError(f"Not a nonnegative literal integer: {value!r}")
    return int(value)


def district(state, label):
    label = label.strip()
    if label.startswith(state + "-"):
        label = label[len(state) + 1:]
    if label in ("00", "0", "AL") and state in AT_LARGE:
        return "AL"
    if label.isdigit() and int(label) > 0:
        return str(int(label)).zfill(2)
    return ""


def csv_bytes(rows, fields=None):
    if fields is None:
        fields = list(rows[0]) if rows else []
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def build(historical, current, reviews, no_ballot, controls, state_codes):
    reviews = [r for r in reviews if r["year"] == "2024" and r["office"] == "house"]
    review_index = {(r["state_code"], r["county_fips"]): r for r in reviews}
    accepted = {key for key, row in review_index.items()
                if row["accepted_for_scoped_export"] == "True"}
    historical = [r for r in historical if r["year"] == "2024" and r["office"] == "house"]
    current = [r for r in current if r["year"] == "2026" and r["office"] == "U.S. House"]
    no_ballot = [r for r in no_ballot if r["year"] == "2024" and r["office"] == "house"]
    controls = [r for r in controls if r["year"] == "2026" and r["office"] == "U.S. House"]
    county, fragments = defaultdict(dict), defaultdict(dict)
    flags = defaultdict(set)
    choices = defaultdict(set)
    dispositions = []
    selected_count = 0
    for row in historical:
        key = row["state_po"], row["county_fips"]
        approved = key in accepted
        reason = review_index.get(key, {}).get("withheld_reasons", "no_county_review")
        dispositions.append(dict(row, selected_for_counts=approved,
                                 selection_reason="reviewed_source_scope" if approved else reason))
        if not approved:
            flags[key].add("historical_county_withheld:" + reason)
    for year, rows in (("2024", historical), ("2026", current)):
        for row in rows:
            state = row["state_po"] if year == "2024" else row["state_code"]
            key = state, row["county_fips"]
            if year == "2024" and key not in accepted:
                continue
            if not re.fullmatch(r"[0-9]{5}", key[1]):
                raise ValueError(f"Unqualified county FIPS: {key}")
            if key[1][:2] != state_codes[state]:
                raise ValueError(f"County FIPS belongs to a different state: {key}")
            if year == "2024" and row["stage"] != "general":
                raise ValueError("Non-general historical row")
            value = integer(row["votes"])
            selected_count += year == "2024"
            d = district(state, row["district"])
            group = party(row["party"])
            choices[year, state, d].add(group)
            for index, target in ((county, key), (fragments, (*key, d))):
                counts = index[target].setdefault(year, Counter())
                counts[group] += value
                counts["total"] += value
                counts["rows"] += 1
            if not d:
                flags[key].add("unresolved_district_label")
            if "/" in row["party"] or row["party"].strip().casefold() in {
                "conservative", "working families",
            }:
                flags[key].add("fusion_or_composite_ballot_label")
            if year == "2024" and row["party_group"] != {
                "D": "DEM", "R": "REP", "O": "OTHER",
            }[group]:
                flags[key].add("historical_party_group_differs_from_literal_label")
    # Current district controls include choices with no located county votes.
    for row in controls:
        choices["2026", row["state_code"], district(row["state_code"], row["district"])].add(
            party(row["party"]))
    for row in no_ballot:
        flags[row["state_po"], row["county_fips"]].add("historical_unopposed_not_on_ballot")
    located = Counter()
    located_rows = Counter()
    for row in current:
        key = row["state_code"], row["district"], row["name"], row["party"]
        located[key] += integer(row["votes"])
        located_rows[key] += 1
    control_index = {}
    for row in controls:
        key = row["state_code"], row["district"], row["name"], row["party"]
        if key in control_index:
            raise ValueError(f"Duplicate district candidate control: {key}")
        control_index[key] = integer(row["votes"])
    control_rows = []
    unresolved_control_districts = set()
    for key in sorted(set(control_index) | set(located)):
        total, count = control_index.get(key), located.get(key)
        status = ("missing_reported_district_candidate" if total is None else
                  "no_located_county_rows" if count is None else
                  "arithmetic_match_same_source" if count == total else
                  "unlocated_or_different_source_scope")
        if status != "arithmetic_match_same_source":
            unresolved_control_districts.add((key[0], district(key[0], key[1])))
        control_rows.append(dict(
            state_code=key[0], district=key[1], candidate=key[2], literal_party=key[3],
            reported_district_votes=total, located_county_votes=count,
            located_county_rows=located_rows[key],
            located_minus_reported=count - total if count is not None and total is not None else None,
            status=status, independent_validation=False))
    for (state, fips, d), years in fragments.items():
        if "2026" in years and (state, d) in unresolved_control_districts:
            flags[state, fips].add("current_district_control_has_unlocated_or_different_scope")
    all_counties = set(county) | set(review_index) | set(flags)
    panel = []
    with localcontext() as context:
        context.prec = 60
        for key in sorted(all_counties):
            years = county.get(key, {})
            reasons = set(flags[key])
            if key[0] in {"AK", "CT"}:
                reasons.add("geography_or_round_requires_separate_qualification")
            for year in ("2024", "2026"):
                if year not in years:
                    reasons.add("missing_" + year + "_reviewed_counts")
                elif not years[year]["total"]:
                    reasons.add("zero_" + year + "_source_contest_votes")
                for state, fips, d in fragments:
                    if (state, fips) == key and year in fragments[state, fips, d]:
                        if not {"D", "R"} <= choices[year, state, d]:
                            reasons.add(year + "_one_major_party_in_source_district_scope")
            row = dict(state_code=key[0], county_fips=key[1])
            for year in ("2024", "2026"):
                counts = years.get(year)
                for group, field in (("D", "d_literal_votes"), ("R", "r_literal_votes"),
                                     ("O", "other_literal_votes"), ("total", "contest_votes")):
                    row[year + "_" + field] = counts[group] if counts is not None else None
                districts = sorted(d for state, fips, d in fragments
                                   if (state, fips) == key and year in fragments[state, fips, d])
                row[year + "_district_labels"] = ";".join(districts)
                row[year + "_d_minus_r_margin_pct"] = (
                    str(Decimal(100) * (counts["D"] - counts["R"]) / counts["total"])
                    if counts and counts["total"] else None)
            paired = all(year in years and years[year]["total"] > 0 for year in ("2024", "2026"))
            row["contest_vote_count_change"] = (
                years["2026"]["total"] - years["2024"]["total"] if paired else None)
            row["contest_vote_count_change_pct"] = (
                str(Decimal(100) * row["contest_vote_count_change"] / years["2024"]["total"])
                if paired else None)
            row["unadjusted_literal_d_minus_r_margin_change_pp"] = (
                str(Decimal(row["2026_d_minus_r_margin_pct"]) -
                    Decimal(row["2024_d_minus_r_margin_pct"])) if paired else None)
            row["positive_count_pair"] = paired
            row["passes_known_descriptive_screens"] = paired and not reasons
            row["screen_reasons"] = ";".join(sorted(reasons))
            row["district_boundaries_matched"] = None
            row["complete_source_coverage_certified"] = False
            row["measured_turnout_change"] = None
            row["individual_switching_estimate"] = None
            panel.append(row)
    fragment_rows = []
    for (state, fips, d), years in sorted(fragments.items()):
        row = dict(state_code=state, county_fips=fips, district_label=d,
                   same_label_is_not_matched_boundaries=True)
        for year in ("2024", "2026"):
            for group in ("D", "R", "O", "total"):
                row[year + "_" + group] = years[year][group] if year in years else None
        fragment_rows.append(row)
    summary = dict(
        historical_source_candidate_rows=len(historical),
        historical_selected_candidate_rows=selected_count,
        historical_withheld_candidate_rows=len(historical) - selected_count,
        current_county_district_candidate_rows=len(current), county_query_rows=len(panel),
        positive_count_pairs=sum(r["positive_count_pair"] for r in panel),
        known_screen_passes=sum(r["passes_known_descriptive_screens"] for r in panel),
        known_screen_states=len({r["state_code"] for r in panel if r["passes_known_descriptive_screens"]}),
        county_district_query_rows=len(fragment_rows), no_ballot_source_rows=len(no_ballot),
        current_candidate_control_rows=len(control_rows),
        current_candidate_control_statuses=dict(Counter(r["status"] for r in control_rows)),
        screen_reason_counts=dict(Counter(reason for r in panel
            for reason in r["screen_reasons"].split(";") if reason)),
        notes=[
            "Exact candidate contest counts, not ballots, turnout or individual transitions.",
            "All pairs are descriptive source comparisons, not complete-source or geography certification.",
            "County-district labels do not establish matched district boundaries or fixed electorates.",
            "Literal D/R aliases only; native historical party_group is retained, never silently substituted.",
            "O includes all non-D/R literal labels, including blank/unresolved party labels.",
            "Missing years and controls are null; present source rows with zero votes remain zero.",
            "Historical no-ballot, withheld counties, fusion and party-group ambiguities remain visible.",
            "Current county and provider district controls can have different scopes, including PA write-ins.",
            "Unadjusted numeric margin changes remain in the full query even where comparisons are screened out.",
        ])
    return {
        "county-panel.csv": csv_bytes(panel),
        "county-district-panel.csv": csv_bytes(fragment_rows),
        "historical-source-dispositions.csv": csv_bytes(dispositions),
        "current-county-district-candidates.csv": csv_bytes(current),
        "historical-no-ballot.csv": csv_bytes(no_ballot),
        "current-candidate-controls.csv": csv_bytes(control_rows),
        "summary.json": (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode(),
    }, summary


def export(website_root, output, inputs=None):
    if output.exists():
        raise ValueError("Refusing to overwrite an existing analysis")
    paths = {
        "historical": HISTORICAL + "/source-candidate-party-lines.csv.gz",
        "reviews": HISTORICAL + "/county-review.csv.gz",
        "no_ballot": HISTORICAL + "/source-no-ballot.csv.gz",
        "current": CURRENT + "/party-votes/county-district-candidate-totals.csv.gz",
        "controls": CURRENT + "/party-votes/district-candidate-totals.csv.gz",
        "state_codes": CURRENT + "/state-codes.json",
    }
    if website_root:
        website_root = website_root.resolve()
        commit = subprocess.check_output(
            ["git", "-C", str(website_root), "rev-parse", "HEAD"], text=True).strip()
    else:
        manifest = json.loads((inputs / "source-manifest.json").read_bytes())
        commit = manifest["source_commit"]
        if (manifest["website_repository"] != "hanshanley/margin_of_error"
                or not re.fullmatch(r"[a-f0-9]{40}", commit)):
            raise ValueError("Unqualified aggregate input manifest")
    native, rows, receipts = {}, {}, {}
    for name, relative in paths.items():
        member = "inputs/" + name + (".json" if name == "state_codes" else ".csv.gz")
        content = (website_root / relative if website_root else inputs / member).read_bytes()
        if website_root:
            pinned = subprocess.check_output(
                ["git", "-C", str(website_root), "show", commit + ":" + relative])
            if pinned != content:
                raise ValueError("Input differs from its declared Git snapshot: " + relative)
        else:
            receipt = manifest["inputs"][name]
            if (receipt["path"] != relative or receipt["bytes"] != len(content)
                    or receipt["sha256"] != hashlib.sha256(content).hexdigest()):
                raise ValueError("Changed complete-package aggregate input: " + name)
        native[member] = content
        if name == "state_codes":
            rows[name] = json.loads(content)
        else:
            with gzip.open(io.BytesIO(content), "rt", encoding="utf-8", newline="") as stream:
                rows[name] = list(csv.DictReader(stream))
        receipts[name] = dict(path=relative, bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
    files, summary = build(**rows)
    files["source-manifest.json"] = (json.dumps(dict(
        website_repository="hanshanley/margin_of_error", source_commit=commit,
        inputs=receipts, redistribution_scope="Previously published aggregate candidate election counts",
    ), indent=2, sort_keys=True) + "\n").encode()
    files["scripts/house_panel.py"] = Path(__file__).read_bytes()
    files["tests/test_house_panel.py"] = Path(__file__).parents[1].joinpath(
        "tests/test_house_panel.py").read_bytes()
    files["README.txt"] = (
        "Exact 2024/2026 House source-count comparison, not turnout or individual switching.\n"
        "Unpack this entire archive into a new directory. No packages or network access required.\n"
        "From that directory:\n"
        "  python3 -m unittest discover -s tests -p test_house_panel.py\n"
        "  python3 -m scripts.house_panel --inputs . --output reproduced\n"
        "All six pinned aggregate inputs, complete queries, exclusions, code and tests are included.\n"
        "Missing observations remain null; screened-out numerical comparisons are still in the query.\n"
        "Read summary.json and source-manifest.json for the source-frame and geography limitations.\n"
    ).encode()
    files.update(native)
    checksums = {name: dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
                 for name, data in sorted(files.items())}
    files["checksums.json"] = (json.dumps(checksums, indent=2, sort_keys=True) + "\n").encode()
    output.mkdir(parents=True)
    for name, data in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--website-root", type=Path)
    source.add_argument("--inputs", type=Path, help="Unpacked complete analysis directory; offline reproduction")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.website_root, args.output, args.inputs)
