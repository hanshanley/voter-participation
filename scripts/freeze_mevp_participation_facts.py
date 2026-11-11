"""Verify new numeric selections from already-held text and independent PDF coordinates."""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


GROUPS = {"latino": "Latino", "aapi": "AAPI", "white": "White",
    "black": "Black", "native-american": "NativeAm"}
HISTORY = ("first_2026", "first_2024", "first_2022", "first_2020_or_earlier")
EXPERIENCE = ("language_information", "provisional_registration_list",
    "waiting_line", "equipment_delay", "harassment", "enforcement_seen",
    "travel_distance", "none_selected")


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def digest(body):
    return hashlib.sha256(body).hexdigest()


def question(text, name):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    start = next(index for index, line in enumerate(lines) if line.startswith(name + ":"))
    end = next(index for index in range(start + 1, len(lines))
        if lines[index].startswith("Q") and ":" in lines[index])
    return lines[start:end]


def numeric_rows(lines, width, count):
    values = [int(line) for line in lines if line.isdigit() and int(line) <= 100]
    if len(values) != width * count:
        raise ValueError("Incomplete new numerical table")
    return [values[index * width:(index + 1) * width] for index in range(count)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh output")
    import pdfplumber

    tables, checks = [], 0
    old = json.loads((args.originals / "selected-facts.json").read_bytes())
    old_tables = {row["group_id"]: row for row in old["tables"]}
    for group, label in GROUPS.items():
        original = (args.originals / (group + ".pdf")).read_bytes()
        receipt = json.loads((args.originals / (group + ".pdf.receipt.json")).read_bytes())
        if len(original) != receipt["bytes"] or digest(original) != receipt["sha256"]:
            raise ValueError("Changed already-held original")
        text = (args.originals / (group + ".txt")).read_text()
        prefix, rest = text.split("Respondent N=", 1)
        lines = [line.strip() for line in prefix.splitlines() if line.strip()]
        banners = lines[lines.index(label):]
        width = len(banners)
        n = [int(line.strip()) for line in rest.split("Q1:", 1)[0].splitlines() if line.strip()]
        if len(n) != width or len(set(banners)) != width:
            raise ValueError("Changed source banner/base inventory")
        q1 = numeric_rows(question(text, "Q1"), width, 4)
        q2 = numeric_rows(question(text, "Q2"), width, 8)
        with pdfplumber.open(args.originals / (group + ".pdf")) as document:
            words = document.pages[0].extract_words(x_tolerance=1, y_tolerance=2)
            base_y = next(word["top"] for word in words if word["text"] == "Respondent")
            bases = sorted([word for word in words if abs(word["top"] - base_y) < 1
                and word["text"].isdigit()], key=lambda word: word["x0"])
            if [int(word["text"]) for word in bases] != n:
                raise ValueError("Independent source bases differ")
            centers = [(word["x0"] + word["x1"]) / 2 for word in bases]
            tops = {code: next(word["top"] for word in words if word["text"] == code + ":")
                for code in ("Q1", "Q2", "Q3")}
            for name, end, expected in (("Q1", "Q2", q1), ("Q2", "Q3", q2)):
                rows = defaultdict(dict)
                for word in words:
                    if not (tops[name] + 20 < word["top"] < tops[end] and word["text"].isdigit()
                            and int(word["text"]) <= 100):
                        continue
                    center = (word["x0"] + word["x1"]) / 2
                    column = min(range(width), key=lambda index: abs(centers[index] - center))
                    if abs(centers[column] - center) > 3:
                        continue
                    key = round(word["top"])
                    if column in rows[key]:
                        raise ValueError("Duplicate independent numeric cell")
                    rows[key][column] = int(word["text"])
                independently_read = [[row[column] for column in range(width)]
                    for _, row in sorted(rows.items())]
                if independently_read != expected:
                    raise ValueError("Independent coordinate extraction differs")
                checks += sum(len(row) for row in expected)
        previous = old_tables[group]
        if n[0] != previous["raw_respondent_bases"][0] or [
                row[0] for row in q1] != list(previous["first_november_election_pct"].values()):
            raise ValueError("Previously accepted national source facts differ")
        tables.append(dict(group=group, native_group_label=label, source_url=receipt["declared_url"],
            source_sha256=receipt["sha256"], source_bytes=receipt["bytes"],
            original_retrieved_at=receipt["retrieved_utc"], source_page=1,
            field_start="2026-10-19", field_end="2026-11-02", columns=banners,
            raw_respondent_n=n, history_pct=dict(zip(HISTORY, q1)),
            experience_pct=dict(zip(EXPERIENCE, q2))))
    facts = dict(contract="participation.mevp_held_state_facts.v1", tables=tables,
        history_response_keys=list(HISTORY), experience_response_keys=list(EXPERIENCE),
        same_study_oversamples_not_independent_replications=True,
        original_documents_or_source_prose_redistributed=False)
    proof = dict(status="passed_new_held_source_participation_cells",
        independent_numeric_cells=checks + sum(len(table["columns"]) for table in tables),
        source_columns=sum(len(table["columns"]) for table in tables), source_documents=5,
        independent_engine="pdfplumber/pdfminer coordinate extraction",
        primary_uses_already_held_text=True, original_acquisitions_repeated=False,
        previous_joint_reductions_repeated=False, blocked_state_files_recovered=False,
        facts_sha256=digest(encoded(facts)))
    args.output.mkdir(parents=True)
    (args.output / "native-facts.json").write_bytes(encoded(facts))
    (args.output / "native-verification.json").write_bytes(encoded(proof))
    print(json.dumps(proof, sort_keys=True))


if __name__ == "__main__":
    main()
