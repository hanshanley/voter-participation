"""Qualify House Clerk candidate endpoints without counting ballot accounting twice."""

import argparse
from collections import defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re


STATES = dict(zip(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split(),
    ("Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming").split("|")))
TARGETS = set("AK CT HI IL IN LA ME MS NJ OK PA RI SD VA VT".split())
PARTIES = {
    "Democrat", "Democratic", "Republican", "Libertarian", "Independent",
    "Independence", "Green", "Working Families", "Conservative", "Nonpartisan",
    "Unaffiliated", "Constitution", "Unenrolled Independent",
    "Green Mountain Peace and Justice", "American Solidarity", "Write-in",
    "Alliance", "America First", "American Constitution", "American Independent",
    "Approval Voting Party", "Aurora", "Better Party", "By Petition",
    "Cheaper Gas Groceries Party", "Common Sense", "Common Sense Independent",
    "Common Sense Suffolk", "Constitutional Conservative", "Disrupt the Corruption",
    "Epic", "Forward Party", "Green Independent", "Independence-Alliance",
    "Independent American", "Join The Revolution", "Justice", "Justice for All",
    "Kentucky Party", "LaRouche", "Labour", "Legal Marijuana NOW", "Miscellaneous",
    "Mountain", "Natural Law", "No Party", "No Party Affiliation",
    "No Party Preference", "No Political Party", "No Slogan",
    "Pacific Green", "Party for Socialism and Liberation", "Peace Freedom Liberty",
    "Peace and Freedom", "Petition", "Progressive", "Prohibition", "Social Activist",
    "Socialism and Liberation", "Socialist Equality", "Socialist Workers",
    "Truth", "Truth Freedom Prosperity", "U.S. Constitution", "U.S. Taxpayers",
    "Unenrolled", "United Citizens", "United Utah", "Unity Party", "Vote Better",
    "We The People", "We the People", "Workers", "Working Class",
}
NONCANDIDATE = re.compile(
    r"^(?:blanks?(?: votes)?|under ?votes|over ?votes|continuing ballots|"
    r"exhausted ballots|void|invalid|total(?: votes)?|none of (?:these|the) candidates)$", re.I)
NUMBER = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)\Z")
DEMOCRATIC = {"Democrat", "Democratic", "Democratic-Farmer-Labor",
              "Democratic-Nonpartisan League", "Working Families (Democratic Party Candidate)"}
REPUBLICAN = {"Republican", "Conservative (Republican Party Candidate)"}


def known_party(value):
    return value in PARTIES or bool(re.fullmatch(r"Write-in \([A-Za-z -]+\)", value))


def literal_minor_party(value):
    return (any(char.isalpha() for char in value)
            and all(char.isprintable() for char in value)
            and value.casefold().rstrip(".") not in ("jr", "sr", "ii", "iii", "iv"))


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def source_lines(pdf):
    import fitz

    result = []
    with fitz.open(pdf) as document:
        for page_number, page in enumerate(document, 1):
            bands = []
            for word in sorted(page.get_text("words"), key=lambda w: ((w[1]+w[3])/2, w[0])):
                if word[1] < 20 or word[3] > page.rect.height - 20:
                    continue
                center = (word[1]+word[3])/2
                if not bands or abs(bands[-1][0] - center) > 1.7:
                    bands.append([center, []])
                bands[-1][1].append(word)
            for _, words in bands:
                words.sort(key=lambda word: word[0])
                result.append(dict(page=page_number,
                    x=min(word[0] for word in words),
                    y=min(word[1] for word in words),
                    text=" ".join(word[4] for word in words),
                    words=[dict(x0=w[0], y0=w[1], x1=w[2], y1=w[3], text=w[4])
                           for w in words]))
    return result


def candidate_lines(lines, targets=TARGETS):
    names = {name.upper(): code for code, name in STATES.items()}
    state, district, mode, parent, page_number = None, None, None, None, None
    result, ignored = [], []
    for line in lines:
        if line["page"] != page_number:
            page_number, mode = line["page"], None
        text = line["text"].strip()
        heading = re.sub(r"[—-]Continued$", "", text).strip()
        if heading in names:
            code = names[heading]
            if code != state:
                district, parent = None, None
            state, mode = code, None
            continue
        if text.startswith("FOR UNITED STATES REPRESENTATIVE"):
            mode = "house"
            continue
        if text.startswith("FOR ") or "Recapitulation of Votes Cast" in text:
            mode = None
            continue
        if state not in targets or mode != "house":
            continue
        if text == "AT LARGE":
            district = "AL"
            parent = None
            continue
        match = re.match(r"^([0-9]{1,2})\.\s+(.*)", text)
        if match:
            district, text, parent = match[1].zfill(2), match[2], None
        if not district:
            raise ValueError("A native House district must precede every candidate: " + text)
        words = line["words"]
        last = words[-1]["text"]
        footnote = bool(re.fullmatch(r"\([0-9]+\)", last))
        if not NUMBER.fullmatch(last) and not footnote:
            if any(party in text for party in PARTIES):
                raise ValueError("Candidate count is absent or not an integer: " + text)
            continue
        label = text[:text.rfind(last)].rstrip(" .\u00a0")
        # A page footer is not a result; candidate counts occupy the right column.
        if not label or words[-1]["x0"] < 400:
            continue
        common = dict(state_code=state, district=state+"-"+district,
                      page=line["page"], native_label=label,
                      votes=None if footnote else int(last.replace(",", "")), native_count=last,
                      x=line["x"], y=line["y"])
        if NONCANDIDATE.fullmatch(label):
            ignored.append(dict(common, role="noncandidate_accounting"))
            parent = None
            continue
        if label.lower() in ("write-in", "write-in votes", "other write-ins",
                             "scattered", "scattering", "miscellaneous", "all others"):
            candidate, party = label, label
            parent = None
            role = ("source_unassigned_write_in" if "write-in" in label.lower()
                    else "source_unassigned_other_vote")
        elif label in PARTIES:
            if parent is None or parent["district"] != common["district"]:
                raise ValueError("An indented fusion line has no named nominee")
            if line["x"] <= parent["x"] + 5:
                raise ValueError("A fusion line must be natively indented under its nominee")
            candidate, party = parent["candidate"], label
            parent["affiliations"].append(party)
            role = "additional_party_line_for_same_named_nominee"
        elif "," in label:
            parts = [part.strip() for part in label.split(",")]
            first_party = next((i for i in range(1, len(parts))
                                if known_party(parts[i])), None)
            if first_party is None and literal_minor_party(parts[-1]):
                first_party = len(parts)-1
            if first_party is None:
                raise ValueError("Unqualified native party suffix: " + label)
            candidate = ", ".join(parts[:first_party])
            affiliations = parts[first_party:]
            if not all(known_party(party) or literal_minor_party(party) for party in affiliations):
                raise ValueError("Unknown mixed-party affiliation: " + label)
            party = ", ".join(affiliations)
            parent = dict(candidate=candidate, affiliations=affiliations,
                          district=common["district"], x=line["x"])
            role = "named_candidate"
        else:
            raise ValueError("Unclassified House row: " + label)
        result.append(dict(common, candidate=candidate, literal_party=party,
                           role=role, parent_affiliations=parent["affiliations"][:] if parent else [party]))
    return result, ignored


def candidate_totals(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["district"], row["candidate"]].append(row)
    result = []
    for (district, candidate), lines in sorted(grouped.items()):
        if sum(line["role"] == "named_candidate" for line in lines) > 1:
            raise ValueError("Repeated named nominee needs election-scope qualification")
        affiliations = set()
        for line in lines:
            affiliations.update(line["parent_affiliations"])
        d = bool(affiliations.intersection(DEMOCRATIC))
        r = bool(affiliations.intersection(REPUBLICAN))
        if d and r:
            raise ValueError("A nominee explicitly on both major-party lines needs separate qualification")
        result.append(dict(state_code=lines[0]["state_code"], district=district,
                           candidate=candidate, literal_affiliations=sorted(affiliations),
                           counted_as="D" if d else "R" if r else "O",
                           votes=(sum(line["votes"] for line in lines)
                                  if all(line["votes"] is not None for line in lines) else None),
                           source_lines=lines))
    return result


def national_house_recap(text):
    columns = ("Republican", "Democratic", "Independent", "Libertarian", "Green",
               "Constitution", "Other Parties", "Write-in", "Total")
    names = {name: code for code, name in STATES.items()}
    pattern = r"^(" + "|".join(re.escape(n) for n in [*names, "Total"]) + r")\s*\.{2,}\s*"
    text = text.split("1See each State")[0]
    matches = list(re.finditer(pattern, text, flags=re.MULTILINE))
    if len(matches) != 51:
        raise ValueError("The complete 50-state/one-parent House recap is required")
    result = {}
    for index, match in enumerate(matches):
        body = text[match.end():matches[index+1].start() if index+1 < len(matches) else len(text)]
        tokens = re.findall(r"[0-9][0-9,]*|\.{2,}", body)
        if len(tokens) != len(columns):
            raise ValueError("Native recap columns shifted for " + match[1])
        code = names.get(match[1], "US50")
        result[code] = {column: dict(literal=token,
            value=None if token.startswith(".") else int(token.replace(",", "")))
            for column, token in zip(columns, tokens)}
    if set(result) != set(STATES) | {"US50"}:
        raise ValueError("Missing or repeated native recap state")
    for column in columns:
        if sum(result[code][column]["value"] or 0 for code in STATES) != result["US50"][column]["value"]:
            raise ValueError("Reported numeric recap cells differ from the printed parent")
    return result


def extract_from_lines(lines, targets=TARGETS):
    rows, ignored = candidate_lines(lines, targets)
    candidates = candidate_totals(rows)
    totals = {}
    for state in sorted(targets):
        selected = [row for row in candidates if row["state_code"] == state]
        if not selected:
            raise ValueError("Target state has no extracted House candidates: " + state)
        totals[state] = dict(D=sum(r["votes"] for r in selected if r["counted_as"] == "D" and r["votes"] is not None),
                            R=sum(r["votes"] for r in selected if r["counted_as"] == "R" and r["votes"] is not None),
                            O=sum(r["votes"] for r in selected if r["counted_as"] == "O" and r["votes"] is not None),
                            missing_numeric_candidate_counts=sum(r["votes"] is None for r in selected),
                            districts=sorted({r["district"] for r in selected}),
                            candidate_rows=len(selected))
    return dict(status="native_candidate_extraction_not_endpoint_approval",
                candidate_party_lines=rows, candidates=candidates,
                excluded_noncandidate_accounting=ignored, target_state_totals=totals,
                full_native_line_facts=lines, observed_participation=False)


def extract(pdf, targets=TARGETS):
    return dict(extract_from_lines(source_lines(pdf), targets),
                source_pdf_sha256=hashlib.sha256(Path(pdf).read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all-states", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh extraction path")
    result = extract(args.pdf, set(STATES) if args.all_states else TARGETS)
    args.output.write_bytes(encoded(result))
    print(json.dumps(result["target_state_totals"], sort_keys=True))
