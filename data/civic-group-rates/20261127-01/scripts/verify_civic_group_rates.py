"""Independent native-column check of the percentage-only broad-group export."""

import argparse
from collections import defaultdict
import csv
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
import json
from pathlib import Path
import re
import zipfile


MAPS = {
    "AGE6": {1: "18_29", 2: "18_29", 3: "30_49", 4: "30_49", 5: "50_64", 6: "65_plus"},
    "EDUC": {1: "high_school_or_less", 2: "some_college", 3: "college_postgraduate", 4: "college_postgraduate"},
    "SEX": {1: "male", 2: "female"},
    "RACETH5": {1: "white", 2: "black", 3: "hispanic", 4: "asian_pacific", 5: "other_unknown"},
    "INCOME": {1: "under_25000", 2: "25000_49999", 3: "50000_74999", 4: "75000_99999", 5: "100000_plus"},
    "RUCC": {1: "urban_county", 2: "suburban_county", 3: "rural_county"},
}


def verify(source, product):
    data = json.loads((product / "viewer-data.json").read_bytes())
    before_bytes = (product / "inputs/previous-public-query.json").read_bytes()
    before = json.loads(before_bytes)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == data["source_csv_sha256"]
    totals = defaultdict(lambda: [0, 0, Decimal(0), Decimal(0)])
    with source.open(encoding="utf-8-sig", newline="") as stream:
        for record in csv.DictReader(stream):
            state = record["P_STATE"]
            outcome = int(re.match(r"\(?([0-9]+)", record["LIKELYVOTER"])[1])
            weight = Decimal(record["CHEP_WEIGHT"])
            assert outcome in (1, 2) and weight > 0
            groups = [("overall", "all")]
            for dimension, mapping in MAPS.items():
                match = re.match(r"\(?([0-9]+)", record[dimension])
                value = int(match[1]) if match else 99
                groups.append((dimension, mapping.get(value, "other_unknown" if dimension == "RACETH5" else "unknown")))
            for dimension, group in groups:
                item = totals[state, dimension, group]
                item[0] += 1
                item[1] += outcome == 1
                item[2] += weight
                item[3] += weight if outcome == 1 else 0
    rows = data["groups"]
    assert len(rows) == len(before["groups"]) == 1530
    keys = lambda row: (row["state_code"], row["dimension"], row["group"])
    assert list(map(keys, rows)) == list(map(keys, before["groups"]))
    public = new = 0
    with localcontext() as context:
        context.prec = 80
        for row, previous in zip(rows, before["groups"]):
            n, voters, weight, voter_weight = totals.get(keys(row), [0, 0, Decimal(0), Decimal(0)])
            expected = (row["state_code"] != "DC" and row["dimension"] != "GENDER3" and row["group"] != "unknown"
                        and n >= 100 and voters >= 30 and n - voters >= 30)
            assert (row["modeled_voter_pct"] is not None) == expected
            assert row["n"] is None and row["source_weight_concentration_effective_n"] is None
            assert not any(key in row for key in ("weight", "weight_squared", "modeled_voter_weight",
                                                   "native_model_voter_cases", "native_model_nonvoter_cases"))
            assert row["measured_staying_home"] is None and row["administratively_observed_turnout"] is False
            if expected:
                value = (100 * voter_weight / weight).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                assert Decimal(row["modeled_voter_pct"]) == value
                assert Decimal(row["modeled_nonvoter_pct"]) + value == 100
                if previous["modeled_voter_pct"] is not None:
                    assert Decimal(previous["modeled_voter_pct"]).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) == value
                public += 1
                new += previous["modeled_voter_pct"] is None
            else:
                assert row["modeled_nonvoter_pct"] is None
    with zipfile.ZipFile(product / "complete-analysis.zip") as archive:
        pins = json.loads(archive.read("checksums.json"))
        assert set(archive.namelist()) == set(pins) | {"checksums.json"}
        for name, pin in pins.items():
            body = archive.read(name)
            assert body == (product / name).read_bytes()
            assert len(body) == pin["bytes"] and hashlib.sha256(body).hexdigest() == pin["sha256"]
        assert archive.read("inputs/previous-public-query.json") == before_bytes
    return dict(status="passed", independently_checked_queries=len(rows), supported_rates=public,
                additional_broad_group_rates=new, previous_public_rates_preserved_at_display_precision=True,
                no_new_subgroup_counts_or_weight_primitives=True, actual_turnout_not_claimed=True,
                complete_archive_members_verified=len(pins) + 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--product", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.source, args.product)))
