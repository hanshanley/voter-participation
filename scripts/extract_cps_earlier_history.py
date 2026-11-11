"""Coarse public-use CPS aggregates using the documented 2018/2020 layout."""

from collections import Counter
import csv
import hashlib
import io
import zipfile

from .cps import LAYOUT, demographics


YEARS = (2018, 2020)
SHA = {2018: "5cb90c130a8a98ed4fe1ddf2205685420e09a4630e52462c832c8d5ef03cd8ad",
       2020: "72297163d4c7e34ce6f97bdbc929eafe56231f9c76b93bb5b554b52fd631932f"}
EARLY_LAYOUT = {field: value for field, value in LAYOUT.items() if field not in ("interview", "voted")}
EARLY_LAYOUT.update(voted=(1001, 1002), registered=(1003, 1004))


def registry(voted, registered):
    if voted == 1:
        if registered != -1:
            raise ValueError("Unexpected registration answer for routed voter")
        return "registration_supported"
    if voted not in (2, -1, -2, -3, -9):
        raise ValueError("Unknown native older voting code")
    if voted == -1:
        if registered != -1:
            raise ValueError("Unexpected out-of-universe registration response")
        return "registration_unknown"
    if registered not in (1, 2, -2, -3, -9):
        raise ValueError("Unexpected native older registration response")
    return "registration_supported" if registered == 1 else "reported_not_registered" if registered == 2 else "registration_unknown"


def reduce_originals(folder):
    counts, weights, audits = Counter(), Counter(), []
    for year in YEARS:
        body = (folder / f"nov{year % 100}pub.zip").read_bytes()
        if hashlib.sha256(body).hexdigest() != SHA[year]:
            raise ValueError("Changed original historical CPS archive")
        audit = Counter()
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            if archive.namelist() != [f"nov{year % 100}pub.dat"]:
                raise ValueError("Changed original historical record inventory")
            for line in archive.open(archive.namelist()[0]):
                audit["source_records"] += 1
                line = line.rstrip(b"\r\n")
                if len(line) != 1018:
                    raise ValueError("Use the native 1018-character older layout, not the 1020-character newer layout")
                row = {field: int(line[a - 1:b]) for field, (a, b) in EARLY_LAYOUT.items()}
                if row["year"] != year or row["month"] != 11:
                    raise ValueError("Wrong native survey year/month")
                if row["age"] < 18 or row["person_type"] != 2 or row["citizenship"] not in (1, 2, 3, 4):
                    audit["outside_civilian_adult_citizen_universe"] += 1
                    continue
                if row["weight"] < 0:
                    raise ValueError("Negative native final weight")
                if not row["weight"]:
                    audit["zero_weight_records"] += 1
                    continue
                registry(row["voted"], row["registered"])
                state, age, sex, education, race = demographics(row)
                for dimension, group in (("overall", "All"), ("age_group", age), ("sex", sex),
                                         ("education", education), ("race_ethnicity", race)):
                    key = year, state, dimension, group, row["voted"], row["registered"]
                    counts[key] += 1
                    weights[key] += row["weight"]
                audit["included_records"] += 1
                audit["included_weight_units"] += row["weight"]
        audits.append(dict(year=year, **audit))
    fields = ("year", "state_fips", "dimension", "group", "voted", "registered")
    return [dict(zip(fields, key), sample_n=counts[key], weight_units=weights[key]) for key in sorted(counts)], audits


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()
