"""Separate complete native district counts from unmatched county validation rows."""

from collections import Counter
import csv
from datetime import datetime
import gzip
import hashlib
import io
import re


def qualify_pa(native_csv, audit, control, expected_districts):
    pin = dict(bytes=len(native_csv), sha256=hashlib.sha256(native_csv).hexdigest())
    declared_pin = audit["files"]["district-candidate-totals.csv.gz"]
    if any(pin[key] != declared_pin[key] for key in pin):
        raise ValueError("The complete native candidate export differs from its accepted audit")
    if (audit["year"] != 2026 or audit["office"] != "U.S. House"
            or audit["declared_districts"] != 435 or audit["source_districts"] != 435
            or audit["withheld_states"] or audit["excluded_districts"]
            or audit["state_party_coverage"] != 50):
        raise ValueError("Only the complete accepted native district scope is qualified")
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(native_csv).decode("utf-8"))))
    if len(rows) != declared_pin["rows"]:
        raise ValueError("The complete native row inventory changed")
    expected = set(expected_districts)
    if len(expected) != 435 or {r["district"] for r in rows} != expected:
        raise ValueError("A missing native district cannot become a statewide endpoint")
    identities = set()
    urls, district_urls, clocks = {}, {}, {}
    for row in rows:
        if (row["year"] != "2026" or row["office"] != "U.S. House"
                or not row["district"].startswith(row["state_code"]+"-")
                or not row["name"] or not isinstance(row["votes"], str)
                or not re.fullmatch(r"[0-9]+", row["votes"])):
            raise ValueError("A native candidate count must be an explicit nonnegative integer")
        key = row["state_code"], row["district"], row["name"], row["party"]
        if key in identities:
            raise ValueError("A native candidate line cannot be counted twice")
        identities.add(key)
        if row["state_code"] != "PA":
            continue
        url = row["source_url"]
        if not re.fullmatch(r"https://civicapi\.org/api/v2/race/[0-9]+", url):
            raise ValueError("The reported candidate must retain its native source URL")
        if url in urls and urls[url] != row["district"]:
            raise ValueError("One native race cannot supply two districts")
        if row["district"] in district_urls and district_urls[row["district"]] != url:
            raise ValueError("A district cannot mix different native races")
        clock = datetime.fromisoformat(row["source_updated_at"].replace("Z", "+00:00"))
        if clock.tzinfo is None or clock.year != 2026:
            raise ValueError("Native district clocks must remain explicit")
        urls[url] = row["district"]
        district_urls[row["district"]] = url
        if row["district"] in clocks and clocks[row["district"]] != row["source_updated_at"]:
            raise ValueError("A district cannot mix source clocks")
        clocks[row["district"]] = row["source_updated_at"]
    selected = [r for r in rows if r["state_code"] == "PA"]
    if set(district_urls) != {d for d in expected if d.startswith("PA-")}:
        raise ValueError("Every Pennsylvania native district must remain present")
    if control["state_code"] != "PA" or control["office"] != "house":
        raise ValueError("This qualification is scoped to Pennsylvania House counts")
    reported, county_only = [], []
    for index, row in enumerate(control["full_candidate_control_rows"]):
        if row["reported_district_votes"] == "":
            if (row["status"] != "missing_reported_district_candidate"
                    or not re.fullmatch(r"[0-9]+", row["located_county_votes"])
                    or int(row["located_county_rows"]) <= 0):
                raise ValueError("An unexplained missing native count cannot be bypassed")
            county_only.append(dict(control_index=index, **row))
        else:
            reported.append(row)
    if [r["control_index"] for r in county_only] != control["missing_candidate_control_indices"]:
        raise ValueError("The held county-validation exceptions changed")
    def native_key(row):
        return row["district"], row["name"], row["party"], row["votes"]
    def control_key(row):
        return (row["district"], row["candidate"], row["literal_party"],
                row["reported_district_votes"])
    if Counter(map(native_key, selected)) != Counter(map(control_key, reported)):
        raise ValueError("Reported controls must equal every native candidate line without aliases")
    totals = dict(D=0, R=0, O=0)
    for row in selected:
        party = row["party"].strip().lower()
        group = "D" if party in ("democratic", "democrat", "dem") else (
            "R" if party in ("republican", "rep") else "O")
        totals[group] += int(row["votes"])
    if totals != control["current"]:
        raise ValueError("The accepted reported statewide counts must not change")
    return dict(status="qualified_complete_PA_native_reported_candidate_scope",
        source_snapshot=control["source_snapshot"], native_export_pin=pin,
        complete_native_districts=len(expected), native_candidate_rows=selected,
        current_reported_candidate_counts=totals, native_districts=sorted(district_urls),
        native_district_sources=[dict(district=d, url=district_urls[d], last_updated=clocks[d])
                                 for d in sorted(district_urls)],
        county_validation_only_exceptions=county_only,
        source_precedence=audit["source_precedence"], original_source_scope=audit["scope"],
        known_county_write_ins_not_added_to_provider_totals=True,
        candidate_aliases_joined=False, county_votes_summed_into_state=False,
        missing_counts_imputed=False, ballots_or_turnout_qualified=False,
        native_source_counts_changed=False)
