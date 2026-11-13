"""Project only the explicitly reviewed, pinned complete official House queries."""

import copy
import json
from pathlib import Path
import re

from scripts.native_products import integer, pin

CATALOG = Path(__file__).resolve().parents[1] / "data/official-native-products/20261113-hi-wy-house.json"
FIELDS = ("year", "state_code", "district", "office", "name", "party", "votes",
          "source_url", "source_updated_at")


def qualified(queries_body):
    catalog = json.loads(CATALOG.read_bytes())
    if pin(queries_body) != catalog["query_pin"]:
        raise ValueError("Only the reviewed complete native query version is allowed")
    queries = json.loads(queries_body)["queries"]
    candidates, policies, selectors = [], [], {}
    for spec in catalog["sources"]:
        local = []
        rows = queries[spec["query"]]["rows"]
        common = dict(year=spec["year"], state_code=spec["state_code"], office=spec["office"],
            source_url=spec["url"], source_updated_at="")
        if spec["kind"] == "candidate_records":
            for contest, binding in spec["districts"].items():
                selected = [row for row in rows if row["contest"] == contest]
                if (sorted(row["candidate_id"] for row in selected) != binding["candidate_ids"]
                        or any(row["title"] != binding["title"] for row in selected)):
                    raise ValueError("Reviewed native contest inventory changed")
                selectors[(spec["url"], binding["district"])] = "#Contest ID=" + contest
                for row in selected:
                    party = re.match(spec["party_pattern"], row["candidate"])
                    if party is None or party.group(1) not in spec["party_labels"]:
                        raise ValueError("Party affiliation must follow an explicit native marker")
                    local.append(dict(common, district=binding["district"], name=row["candidate"],
                        party=spec["party_labels"][party.group(1)], votes=str(integer(row["total"]))))
        elif spec["kind"] == "wide_candidate_control":
            selected = [row for row in rows if row[spec["control_key"]] == spec["control_value"]]
            if len(selected) != 1:
                raise ValueError("Reviewed native statewide control is ambiguous")
            selectors[(spec["url"], spec["district"])] = spec["selector"]
            for binding in spec["candidates"]:
                local.append(dict(common, district=spec["district"], name=binding["name"],
                    party=binding["party"], votes=str(integer(selected[0][binding["count_field"]]))))
        else:
            raise ValueError("Unreviewed official projection")
        candidates.extend(local)
        policies.append(dict(state_code=spec["state_code"], year=int(spec["year"]),
            office="house", stage=spec["stage"], source_url=spec["url"],
            source_pin=spec["source_pin"], native_updated_at=spec["native_updated_at"],
            retrieved_at_utc=spec["retrieved_at_utc"], query=spec["query"],
            query_pin=catalog["query_pin"], districts=sorted({row["district"] for row in local}),
            count_scope=spec["count_scope"], independent_behavioral_validation=False,
            counting_complete_independently_qualified=False))
    return dict(candidates=candidates, policies=policies, selectors=selectors)


def validate_current(current, queries_body):
    review = qualified(queries_body)
    urls = {row["source_url"] for row in review["candidates"]}
    actual = [row for row in current if row["source_url"] in urls]
    key = lambda row: tuple(row.get(field) for field in FIELDS)
    if sorted(key(row) for row in actual) != sorted(key(row) for row in review["candidates"]):
        raise ValueError("Official candidates/counts/clocks differ from the complete reviewed native queries")
    return review


def replace_current(previous, queries_body):
    review = qualified(queries_body)
    states = {row["state_code"] for row in review["candidates"]}
    result = copy.deepcopy([row for row in previous if row["state_code"] not in states])
    result.extend(review["candidates"])
    return sorted(result, key=lambda row: (row["state_code"], row["district"], row["name"], row["party"]))
