"""Reduce held public CPS records to coarse response pairs, never respondent identifiers."""

import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
from collections import Counter

from .cps import LAYOUT, YEARS, demographics


def registration_class(interview, voted, registered):
    if interview == 2:
        if (voted, registered) != (-1, -1):
            raise ValueError("Noninterview routing conflict")
        return "registration_unknown", "supplement_noninterview"
    if interview != 1:
        raise ValueError("Unexpected supplement interview code")
    if voted == 1:
        if registered != -1:
            raise ValueError("Reported voter has unexpected registration answer")
        return "registration_supported", "reported_voter_registration_question_routed_out"
    if voted not in (2, -2, -3, -9) or registered not in (1, 2, -2, -3, -9):
        raise ValueError("Unexpected native registration/voting routing")
    if registered == 1:
        return "registration_supported", "explicit_registration_yes"
    if registered == 2:
        return "reported_not_registered", "explicit_registration_no"
    return "registration_unknown", {-2: "registration_dont_know", -3: "registration_refused",
                                     -9: "registration_no_response"}[registered]


def reduce_originals(root):
    manifest = json.loads((root / "data/cps-sources.json").read_bytes())
    counts, weights, audits = Counter(), Counter(), []
    layout = dict(LAYOUT, registered=(1005, 1006))
    for year in YEARS:
        metadata = next(row for row in manifest["sources"]
                        if row["year"] == year and row["kind"] == "cps_public_use_survey")
        body = (root / metadata["path"]).read_bytes()
        if len(body) != metadata["bytes"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
            raise ValueError("Changed original held CPS survey")
        audit = Counter()
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            if archive.namelist() != [f"nov{year % 100}pub.dat"]:
                raise ValueError("Changed public CPS record inventory")
            for line in archive.open(archive.namelist()[0]):
                audit["source_records"] += 1
                line = line.rstrip(b"\r\n")
                if len(line) != 1020:
                    raise ValueError("Changed documented source record width")
                row = {field: int(line[a - 1:b]) for field, (a, b) in layout.items()}
                if row["year"] != year or row["month"] != 11:
                    raise ValueError("Wrong source election year/month")
                if row["age"] < 18 or row["person_type"] != 2 or row["citizenship"] not in (1, 2, 3, 4):
                    audit["outside_adult_citizen_universe"] += 1
                    continue
                if row["weight"] < 0:
                    raise ValueError("Negative final CPS weight")
                if not row["weight"]:
                    audit["zero_weight_records"] += 1
                    continue
                registration_class(row["interview"], row["voted"], row["registered"])
                state, age, sex, education, race = demographics(row)
                for dimension, group in (("overall", "All"), ("age_group", age), ("sex", sex),
                                         ("education", education), ("race_ethnicity", race)):
                    key = year, state, dimension, group, row["interview"], row["voted"], row["registered"]
                    counts[key] += 1
                    weights[key] += row["weight"]
                audit["included_records"] += 1
                audit["included_weight_units"] += row["weight"]
        audits.append(dict(year=year, **audit))
    fields = ("year", "state_fips", "dimension", "group", "interview", "voted", "registered")
    result = [dict(zip(fields, key), sample_n=counts[key], weight_units=weights[key]) for key in sorted(counts)]
    return result, audits


def csv_bytes(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()
